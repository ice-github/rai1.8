"""Provision and prepare revision-pinned AMD Stable Diffusion 3 bundles."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .bundle_aliases import apply, ensure_no_symlink_components, inspect

SUPPORTED_MODELS = {
    "stabilityai/stable-diffusion-3-medium-amdnpu",
    "stabilityai/stable-diffusion-3.5-medium-amdnpu",
}
REQUIRED_FILES = (
    "common/tokenizer/tokenizer_config.json",
    "common/tokenizer_2/tokenizer_config.json",
    "common/tokenizer_3/tokenizer.json",
    "common/text_encoder/model.onnx",
    "common/text_encoder_2/model.onnx",
    "common/text_encoder_3_gptq_v2/serialized_quantized_t5-v1_1-xxl_w4_g128_gptq.safetensors",
    "common/text_encoder_3_gptq_v2/serialized_quantized_t5-v1_1-xxl_w4_g128_gptq.bin",
    "common/scheduler/scheduler_config.json",
    "common/vae_decoder/dynamic/dd/replaced.onnx",
    "normal/transformer/dynamic/dd/replaced.onnx",
    "normal/transformer/dynamic/dd/replaced.onnx.data",
)


def validate_identity(model_id: str, revision: str) -> None:
    if model_id not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported SD3 model: {model_id}")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a 40-character lowercase commit hash")


def fetch_model(model_id: str, revision: str, target: Path) -> None:
    """Download the pinned upstream snapshot without modifying app state."""
    validate_identity(model_id, revision)
    from huggingface_hub import snapshot_download

    target = target.absolute()
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=model_id, revision=revision, local_dir=str(target),
        allow_patterns=["LICENSE", "README.md", "common/**", "normal/**"],
        max_workers=8,
    )
    missing = [relative for relative in REQUIRED_FILES if not (target / relative).is_file()]
    if missing:
        raise RuntimeError("download is missing required files: " + ", ".join(missing))


def _atomic_json(path: Path, value: object) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare_model(model_id: str, revision: str, source: Path, target: Path) -> dict:
    """Make an isolated copy and normalize only validated bundle index keys."""
    validate_identity(model_id, revision)
    source, target = source.absolute(), target.absolute()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("source and prepared model paths must be separate, non-nested trees")
    ensure_no_symlink_components(source)
    ensure_no_symlink_components(target)
    if not source.is_dir():
        raise ValueError(f"source model is missing: {source}")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("source contains symlinks; refusing a copy that could escape its tree")
    if target.exists():
        raise ValueError(f"prepared target already exists; refusing to overwrite: {target}")
    missing = [relative for relative in REQUIRED_FILES if not (source / relative).is_file()]
    if missing:
        raise ValueError("source model is incomplete: " + ", ".join(missing))

    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-a", "--reflink=auto", str(source), str(target)], check=True)
    if any(path.is_symlink() for path in target.rglob("*")):
        raise RuntimeError("prepared copy unexpectedly contains symlinks")

    bundles = []
    for bundle in sorted(target.rglob("*.ddbundle")):
        result = apply(bundle, check_only=False)
        parsed = inspect(bundle)
        if parsed["aliases"]:
            raise RuntimeError(f"normalization incomplete for {bundle}")
        bundles.append({
            "path": str(bundle.relative_to(target)),
            "status": result["status"],
            "keys_rewritten": result["keys_rewritten"],
            "key_rewrites": result.get("key_rewrites", []),
            "payload_sha256": result["payload_sha256"],
        })
    if not bundles:
        raise RuntimeError("source model has no DDBUNDLE files")
    manifest = {
        "schema_version": 1,
        "model_id": model_id,
        "source_revision": revision,
        "source_path": str(source.resolve()),
        "prepared_path": str(target.resolve()),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "bundles": bundles,
    }
    _atomic_json(target / ".linux-shape-manifest.json", manifest)
    return manifest
