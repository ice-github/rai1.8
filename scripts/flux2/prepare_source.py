#!/usr/bin/env python3
"""Create the Linux-compatible copy of the pinned sd-sandbox source.

The upstream source targets Windows in a few places. This script copies the
pristine checkout to a separate tree and applies the minimum Linux changes,
recording provenance (original and patched SHA256 per file) so the exact
differences can be audited later.

Usage:
    prepare_source.py [--source DIR] [--dest DIR] [--provenance FILE]

Idempotent: already-applied patches are detected and skipped. Unknown or
partially matched files cause a non-zero exit instead of a silent guess.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

PATCHES = [
    {
        "id": "flux2-text-encoder-cpu",
        "file": "src/trigger/StableDiffusionFlux2KleinONNXPipelineTrigger.py",
        "reason": (
            "The Qwen3 text encoder is pinned to CPU on Linux. DML does not "
            "exist there, and this makes the CPU choice explicit instead of "
            "relying on the provider fallback loop."
        ),
        "old": '            execution_providers=["DmlExecutionProvider", "CPUExecutionProvider"],\n',
        "new": '            execution_providers=["CPUExecutionProvider"],\n',
    },
    {
        "id": "physical-memory-psutil",
        "file": "src/utils/common.py",
        "reason": (
            "get_total_physical_memory_gb() called ctypes.windll, which does "
            "not exist on Linux. Use psutil off Windows."
        ),
        "old": (
            'def get_total_physical_memory_gb() -> float:\n'
            '    """Get the total physical memory of the system (GiB) using the Windows GlobalMemoryStatusEx API."""\n'
            '    kernel32 = ctypes.windll.kernel32\n'
        ),
        "new": (
            'def get_total_physical_memory_gb() -> float:\n'
            '    """Get the total physical memory of the system (GiB).\n'
            '\n'
            '    Linux port: psutil is used off Windows. The original Windows\n'
            '    GlobalMemoryStatusEx path is kept for Windows.\n'
            '    """\n'
            '    if sys.platform != "win32":\n'
            '        return psutil.virtual_memory().total / (1024 ** 3)\n'
            '    kernel32 = ctypes.windll.kernel32\n'
        ),
    },
    {
        "id": "ort-log-severity-default",
        "file": "src/utils/common.py",
        "reason": (
            "Upstream silences ORT completely (severity 4). Errors and "
            "provider failures must be visible in the verification logs."
        ),
        "old": "onnxruntime.set_default_logger_severity(4)",
        "new": "onnxruntime.set_default_logger_severity(2)",
        "replace_all": True,
    },
    {
        "id": "ort-log-severity-session",
        "file": "src/utils/common.py",
        "reason": "Same as ort-log-severity-default, for the per-session option.",
        "old": "session_options.log_severity_level = 4",
        "new": "session_options.log_severity_level = 2",
    },
    {
        "id": "ort-profiling-env",
        "file": "src/utils/common.py",
        "reason": (
            "Profiling is opt-in via FLUX2_ORT_PROFILE=1 so the run wrapper can "
            "collect per-provider execution events without enabling the "
            "pipeline's multi-round profiling mode."
        ),
        "old": (
            'def ort_profiling_enabled() -> bool:\n'
            '    return _ORT_ENABLE_PROFILING\n'
        ),
        "new": (
            'def ort_profiling_enabled() -> bool:\n'
            '    # Linux port: ORT profiling is requested per process so the run\n'
            '    # wrapper can collect dispatch events without the pipeline\'s\n'
            '    # multi-round profiling mode.\n'
            '    return os.environ.get("FLUX2_ORT_PROFILE", "0") == "1"\n'
        ),
    },
    {
        "id": "ort-profiling-prefix-dir",
        "file": "src/utils/common.py",
        "reason": "Allow profile files to be written directly into the result directory.",
        "old": (
            'def ort_profile_file_prefix(model_name: str) -> str:\n'
            '    model_id = _sanitize_profile_prefix_component(_ORT_MODEL_ID)\n'
            '    component = _sanitize_profile_prefix_component(model_name)\n'
            '    return f"{model_id}_{component}_"\n'
        ),
        "new": (
            'def ort_profile_file_prefix(model_name: str) -> str:\n'
            '    model_id = _sanitize_profile_prefix_component(_ORT_MODEL_ID)\n'
            '    component = _sanitize_profile_prefix_component(model_name)\n'
            '    prefix = f"{model_id}_{component}_"\n'
            '    profile_dir = os.environ.get("FLUX2_PROFILE_DIR")\n'
            '    if profile_dir:\n'
            '        return os.path.join(profile_dir, prefix)\n'
            '    return prefix\n'
        ),
    },
    {
        "id": "ort-profiling-enable",
        "file": "src/utils/common.py",
        "reason": (
            "The upstream implementation had profiling commented out, so no "
            "dispatch evidence could be produced."
        ),
        "old": (
            '    if not _ORT_ENABLE_PROFILING:\n'
            '        return\n'
            '    # session_options.enable_profiling = True\n'
            '    # if model_name:\n'
            '    #     session_options.profile_file_prefix = ort_profile_file_prefix(model_name)\n'
        ),
        "new": (
            '    if not ort_profiling_enabled():\n'
            '        return\n'
            '    session_options.enable_profiling = True\n'
            '    if model_name:\n'
            '        session_options.profile_file_prefix = ort_profile_file_prefix(model_name)\n'
        ),
    },
    {
        "id": "session-provider-log",
        "file": "src/utils/model_loader.py",
        "reason": (
            "Record each ONNX session's actual provider list so the run wrapper "
            "can prove Transformer/VAE used RyzenAILightExecutionProvider."
        ),
        "old": (
            '        for provider in session.get_providers():\n'
            '            logger.debug("  - provider: %s", provider)\n'
        ),
        "new": (
            '        for provider in session.get_providers():\n'
            '            logger.debug("  - provider: %s", provider)\n'
            '        # Linux port: record the session providers for the evidence file.\n'
            '        session_log = os.environ.get("FLUX2_SESSION_LOG")\n'
            '        if session_log:\n'
            '            with open(session_log, "a", encoding="utf-8") as fh:\n'
            '                fh.write(json.dumps({\n'
            '                    "component": model_name,\n'
            '                    "model_file": str(model_file_path),\n'
            '                    "providers": list(session.get_providers()),\n'
            '                }) + "\\n")\n'
        ),
    },
    {
        "id": "profile-flush-at-exit",
        "file": "src/utils/model_loader.py",
        "reason": "Flush each ORT profile before process exit so dispatch events are persisted.",
        "old": "import ctypes\nimport numpy as np\n",
        "new": "import atexit\nimport ctypes\nimport numpy as np\n",
    },
    {
        "id": "profile-register-end",
        "file": "src/utils/model_loader.py",
        "reason": "Persist ORT profiling traces and their paths for dispatch evidence.",
        "old": (
            '        session = onnxruntime.InferenceSession(\n'
            '            model_file_path, sess_options=session_options, providers=execution_providers\n'
            '        )\n'
        ),
        "new": (
            '        session = onnxruntime.InferenceSession(\n'
            '            model_file_path, sess_options=session_options, providers=execution_providers\n'
            '        )\n'
            '        profile_log = os.environ.get("FLUX2_PROFILE_LOG")\n'
            '        if profile_log and session_options is not None and session_options.enable_profiling:\n'
            '            def _end_profile(_session=session, _name=model_name):\n'
            '                try:\n'
            '                    profile_path = _session.end_profiling()\n'
            '                    with open(profile_log, "a", encoding="utf-8") as fh:\n'
            '                        fh.write(json.dumps({"component": _name, "profile": profile_path}) + "\\n")\n'
            '                except Exception as exc:\n'
            '                    with open(profile_log, "a", encoding="utf-8") as fh:\n'
            '                        fh.write(json.dumps({"component": _name, "profile_error": str(exc)}) + "\\n")\n'
            '            atexit.register(_end_profile)\n'
        ),
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        return
    print(f"copying {src} -> {dest}")
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        symlinks=True,
    )


def apply_patch(dest: Path, patch: dict) -> str:
    path = dest / patch["file"]
    text = path.read_text(encoding="utf-8")
    old = patch["old"]
    new = patch["new"]

    if new in text and old not in text:
        return "already-applied"
    if old not in text:
        raise SystemExit(
            f"ERROR: {patch['id']}: anchor not found in {patch['file']}. "
            "The pinned commit may not match this source tree."
        )
    count = text.count(old)
    if count > 1 and not patch.get("replace_all"):
        raise SystemExit(
            f"ERROR: {patch['id']}: anchor occurs {count} times in "
            f"{patch['file']} but replace_all is not set."
        )
    path.write_text(text.replace(old, new), encoding="utf-8")
    return "applied"


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(here / "source"))
    ap.add_argument("--dest", default=str(here / "source-linux"))
    ap.add_argument("--provenance", default=str(here / "source-provenance.json"))
    args = ap.parse_args(argv[1:])

    src = Path(args.source).resolve()
    dest = Path(args.dest).resolve()
    if not (src / "src" / "utils" / "common.py").exists():
        print(f"ERROR: {src} does not look like the sd-sandbox tree", file=sys.stderr)
        return 2

    copy_tree(src, dest)

    records = []
    for patch in PATCHES:
        path = dest / patch["file"]
        before = sha256(path)
        result = apply_patch(dest, patch)
        after = sha256(path)
        records.append(
            {
                "id": patch["id"],
                "file": patch["file"],
                "result": result,
                "reason": patch["reason"],
                "sha256_before": before,
                "sha256_after": after,
            }
        )
        print(f"{result:16s} {patch['id']:32s} {patch['file']}")

    provenance = {
        "source": str(src),
        "dest": str(dest),
        "upstream_commit": "e13ca6d7ac14fc415f8aa58acc027f427197e300",
        "patches": records,
    }
    prov_path = Path(args.provenance)
    prov_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"provenance: {prov_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
