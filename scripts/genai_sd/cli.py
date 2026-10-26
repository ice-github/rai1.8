#!/usr/bin/env python3
"""Stable JSON CLI for one-image Ryzen AI GenAI-SD execution.

This tool intentionally has no dependency on the frontend repository. The
frontend supplies a request document and receives a result document; model
preparation and evidence validation live with the runtime tooling.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from . import PROTOCOL_VERSION
from .models import fetch_model, prepare_model

TIMEOUT_SECONDS = 1800
VALIDATION_SCENARIOS = (
    {"steps": 8, "negative_prompt": "text, watermark"},
    {"steps": 8, "negative_prompt": ""},
    {"steps": 30, "negative_prompt": "text, watermark"},
    {"steps": 30, "negative_prompt": ""},
)


def _load_request(path: Path) -> dict:
    request = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(request, dict) or request.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("request protocol_version is unsupported")
    required = (
        "model_id", "model_revision", "model_path", "flux_root", "python",
        "prompt", "negative_prompt", "width", "height", "steps", "seed",
        "guidance_scale", "npu_component", "work_dir",
    )
    missing = [key for key in required if key not in request]
    if missing:
        raise ValueError("missing request fields: " + ", ".join(missing))
    if not isinstance(request["negative_prompt"], str):
        raise ValueError("negative_prompt must be a string; use an empty string for none")
    for name in ("width", "height", "steps"):
        if isinstance(request[name], bool) or not isinstance(request[name], int) or request[name] <= 0:
            raise ValueError(f"{name} must be a positive integer")
    return request


def _run(command: list[str], *, env: dict, cwd: Path, log: Path, timeout: int) -> None:
    shell = 'source "$1/env.sh"; shift; exec "$@"'
    with log.open("wb") as output:
        result = subprocess.run(
            ["bash", "-c", shell, "genai-sd", str(cwd), *command],
            cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
            timeout=timeout + 60, check=False,
        )
    if result.returncode:
        tail = log.read_text(errors="replace")[-3000:]
        raise RuntimeError(f"command exited {result.returncode}: {tail}")


def run_one(request: dict) -> dict:
    flux_root = Path(request["flux_root"]).resolve()
    model_root = Path(request["model_path"]).resolve()
    # Keep the virtualenv launcher path itself. resolve() follows the venv
    # symlink to the base interpreter and silently drops the venv site-packages.
    python = Path(os.path.abspath(request["python"]))
    work = Path(request["work_dir"]).resolve()
    if not (flux_root / "env.sh").is_file() or not python.is_file():
        raise ValueError("configured GenAI-SD runtime is incomplete")
    runner = flux_root / "source-linux/test/run.py"
    if not runner.is_file():
        raise ValueError(f"GenAI-SD runner is missing: {runner}")
    work.mkdir(parents=True, exist_ok=False)
    image_dir = work / "images"
    profile_dir = work / "profiles"
    image_dir.mkdir()
    profile_dir.mkdir()
    env = os.environ.copy()
    env.update({
        "FLUX2_ORT_PROFILE": "1",
        "FLUX2_PROFILE_DIR": str(profile_dir),
        "FLUX2_SESSION_LOG": str(work / "sessions.jsonl"),
        "FLUX2_PROFILE_LOG": str(work / "profile-files.jsonl"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "LC_ALL": "C",
        "LANGUAGE": "C",
        "GENAI_SD_ROOT": str(flux_root / "source-linux"),
    })

    t5_evidence = None
    t5_path = request.get("t5_model_path")
    if t5_path:
        embedding_path = work / "t5-embeddings.safetensors"
        metrics_path = work / "t5-cpu-metrics.json"
        precompute = Path(__file__).with_name("precompute_sd3_t5.py")
        measure = Path(__file__).with_name("measure_memory.py")
        t5_command = [
            str(python), str(precompute), "--model-path", str(t5_path),
            "--tokenizer-path", str(model_root / "common/tokenizer_3"),
            "--model-revision", request["t5_model_revision"],
            "--sequence-length", str(request["t5_sequence_len"]),
            "--prompt", request["prompt"], "--negative-prompt", request["negative_prompt"],
            "--output", str(embedding_path), "--metrics", str(metrics_path),
        ]
        measured = [
            str(python), str(measure), "--csv", str(work / "t5-memory.csv"),
            "--summary", str(work / "t5-memory-summary.json"), "--interval", "0.2",
            "--min-available-gib", "2", "--timeout", str(TIMEOUT_SECONDS), "--", *t5_command,
        ]
        _run(measured, env=env, cwd=flux_root, log=work / "t5-precompute.log", timeout=TIMEOUT_SECONDS)
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        memory = json.loads((work / "t5-memory-summary.json").read_text(encoding="utf-8"))
        if (metrics.get("model_revision") != request["t5_model_revision"]
                or metrics.get("sequence_length") != request["t5_sequence_len"]
                or not all(metrics.get("components", {}).get(k, {}).get("finite") is True
                           for k in ("positive", "negative"))
                or memory.get("stop_reason") != "completed"
                or memory.get("minimum_system_mem_available_gib", 0) < 2):
            raise RuntimeError("CPU T5 embedding or memory verification failed")
        env["SD3_T5_EMBEDDINGS_PATH"] = str(embedding_path)
        env["SD3_T5_CPU_REVISION"] = request["t5_model_revision"]
        t5_evidence = {
            "device": "CPU", "model_revision": request["t5_model_revision"],
            "metrics": metrics, "memory": memory,
        }

    command = [
        str(python), str(runner), "--model_id", request["model_id"],
        "--revision", request["model_revision"], "--model_path", str(model_root),
        "--width", str(request["width"]), "--height", str(request["height"]),
        "--num_inference_steps", str(request["steps"]),
        "--guidance_scale", str(request["guidance_scale"]), "--seed", str(request["seed"]),
        "--num_images_per_prompt", "1", "--prompt", request["prompt"],
        "--output_path", str(image_dir),
    ]
    if request.get("supports_negative_prompt", False):
        command.extend(["--n_prompt", request["negative_prompt"]])
    if request.get("input_image_path"):
        command.extend(["--control_image_path", request["input_image_path"],
                        "--strength", str(request["strength"])])
    if request.get("t5_sequence_len"):
        command.extend(["--t5_sequence_len", str(request["t5_sequence_len"])])
    if request.get("dynamic_shape"):
        command.append("--dynamic_shape")
    measure = Path(__file__).with_name("measure_memory.py")
    measured = [
        str(python), str(measure), "--csv", str(work / "memory.csv"),
        "--summary", str(work / "memory-summary.json"), "--interval", "0.2",
        "--min-available-gib", "2", "--timeout", str(TIMEOUT_SECONDS), "--", *command,
    ]
    _run(measured, env=env, cwd=flux_root, log=work / "run.log", timeout=TIMEOUT_SECONDS)
    verifier = Path(__file__).with_name("evidence.py")
    verification = subprocess.run(
        [str(python), str(verifier), str(work), "--npu-component", request["npu_component"],
         "--width", str(request["width"]), "--height", str(request["height"])],
        cwd=flux_root, env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    if verification.returncode:
        raise RuntimeError("NPU evidence verification failed: " + verification.stdout[-3000:])

    evidence_path = work / "dispatch-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["request"] = {
        key: request[key] for key in (
            "model_id", "model_revision", "steps", "negative_prompt", "width", "height",
        )
    }
    evidence["request"].update({
        "model_path": str(model_root), "t5_sequence_len": request.get("t5_sequence_len"),
    })
    for key in ("input_image_path", "strength"):
        if key in request:
            evidence["request"][key] = request[key]
    if t5_evidence:
        evidence["text_encoder_3"] = t5_evidence
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    image_path = next(image_dir.glob("*.png"), None)
    if image_path is None:
        raise RuntimeError("verified run produced no PNG")
    return {"image_path": str(image_path), "evidence_path": str(evidence_path),
            "dispatch": evidence["dispatch"]}


def validate_matrix(base_request: dict, suite_path: Path) -> dict:
    """Run the canonical SD3 four-case matrix and write a standalone suite."""
    scenarios = base_request.get("validation_scenarios")
    if scenarios != list(VALIDATION_SCENARIOS):
        raise ValueError("validation_scenarios do not match protocol v1 requirements")
    model_root = Path(base_request["model_path"]).resolve()
    manifest_path = Path(base_request["model_manifest_path"]).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if (manifest_hash != base_request["model_manifest_sha256"]
            or manifest.get("model_id") != base_request["model_id"]
            or manifest.get("source_revision") != base_request["model_revision"]
            or manifest.get("prepared_path") != str(model_root)):
        raise ValueError("prepared model manifest does not match validation request")

    records = []
    validation_root = Path(base_request["validation_work_root"]).resolve()
    for index, scenario in enumerate(VALIDATION_SCENARIOS):
        request = dict(base_request)
        request.pop("validation_scenarios", None)
        request.pop("model_manifest_path", None)
        request.pop("model_manifest_sha256", None)
        request.pop("validation_work_root", None)
        request["steps"] = scenario["steps"]
        request["negative_prompt"] = scenario["negative_prompt"]
        request["work_dir"] = str(validation_root / f"case-{index}-{scenario['steps']}")
        result = run_one(request)
        records.append({
            **scenario,
            "image_path": result["image_path"],
            "evidence_path": result["evidence_path"],
            "npu_event_count": result["dispatch"]["npu_event_count"],
            "vae_event_count": result["dispatch"]["vae_event_count"],
        })
        print(json.dumps({"event": "validated", **scenario}), flush=True)

    suite = {
        "schema_version": 1,
        "status": "verified",
        "model_id": base_request["model_id"],
        "revision": base_request["model_revision"],
        "model_path": str(model_root),
        "model_manifest_path": str(manifest_path),
        "model_manifest_sha256": manifest_hash,
        "scenarios": records,
    }
    suite_path.parent.mkdir(parents=True, exist_ok=True)
    suite_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    return suite


def runtime_lock(flux_root: str):
    """Serialize independent frontend/validation invocations on one NPU."""
    from contextlib import contextmanager

    @contextmanager
    def locked():
        lock_path = Path(flux_root) / ".genai_sd.lock"
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return locked()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-version", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--request", required=True, type=Path)
    run_parser.add_argument("--result", required=True, type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--request", required=True, type=Path)
    validate_parser.add_argument("--suite", required=True, type=Path)
    fetch_parser = subparsers.add_parser("fetch-model")
    fetch_parser.add_argument("--model-id", required=True)
    fetch_parser.add_argument("--revision", required=True)
    fetch_parser.add_argument("--target", required=True, type=Path)
    prepare_parser = subparsers.add_parser("prepare-model")
    prepare_parser.add_argument("--model-id", required=True)
    prepare_parser.add_argument("--revision", required=True)
    prepare_parser.add_argument("--source", required=True, type=Path)
    prepare_parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.protocol_version:
        print(json.dumps({"protocol_version": PROTOCOL_VERSION}))
        return 0
    if args.command != "run":
        if args.command not in ("validate", "fetch-model", "prepare-model"):
            parser.error("choose --protocol-version, run, validate, fetch-model, or prepare-model")
    try:
        if args.command in ("fetch-model", "prepare-model"):
            if args.command == "fetch-model":
                fetch_model(args.model_id, args.revision, args.target)
                print(json.dumps({"protocol_version": PROTOCOL_VERSION, "status": "fetched"}))
            else:
                manifest = prepare_model(args.model_id, args.revision, args.source, args.target)
                print(json.dumps({"protocol_version": PROTOCOL_VERSION, "status": "prepared",
                                  "manifest": str(args.target / ".linux-shape-manifest.json"),
                                  "bundle_count": len(manifest["bundles"])}))
            return 0
        request = _load_request(args.request)
        with runtime_lock(request["flux_root"]):
            if args.command == "run":
                result = run_one(request)
                args.result.parent.mkdir(parents=True, exist_ok=True)
                args.result.write_text(json.dumps({
                    "protocol_version": PROTOCOL_VERSION, "status": "verified", **result,
                }, indent=2) + "\n", encoding="utf-8")
                print(json.dumps({"protocol_version": PROTOCOL_VERSION, "status": "verified"}))
            else:
                suite = validate_matrix(request, args.suite)
                print(json.dumps({"protocol_version": PROTOCOL_VERSION, "status": "verified",
                                  "suite": str(args.suite), "scenario_count": len(suite["scenarios"])}))
        return 0
    except Exception as exc:
        print(json.dumps({"protocol_version": PROTOCOL_VERSION, "status": "failed",
                          "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
