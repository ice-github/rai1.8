#!/usr/bin/env python3
"""Fetch the fixed official SD3.5 T5-XXL checkpoint for CPU prompt encoding."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


REPOSITORY = "stabilityai/stable-diffusion-3.5-medium"
REVISION = "b940f670f0eda2d07fbb75229e779da1ad11eb80"
TARGET_DIRECTORY = "text_encoder_3"
FILES = {
    "config.json": "9035948b0904c536918a88b5d984a52cfca26a5c57efa9e90149790cf38c151e",
    "model.safetensors.index.json": "3bacec0f0cf392399d4a385908f67dd73df99c9e9cfee669f148858ba9fbdb0a",
    "model-00001-of-00002.safetensors": "4f2751ceeb2a96edd693e539dc5d6bba0b8d3814f49a9b3798403a0cec4b2e3d",
    "model-00002-of-00002.safetensors": "f63154532130422309532ff56f11945fbea8266c958e3133e8e5aef85c6293c7",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_token() -> str | bool:
    token = os.environ.get("HF_TOKEN")
    if token:
        return token
    if os.environ.get("HF_HOME"):
        return True
    try:
        result = subprocess.run(
            ["fish", "-lc", 'printf "%s" "$HF_TOKEN"'],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    return result.stdout.strip() or True


def verify(target: Path) -> dict:
    missing = [name for name in FILES if not (target / name).is_file()]
    if missing:
        raise SystemExit("missing CPU T5 files: " + ", ".join(missing))
    actual_hashes = {name: sha256(target / name) for name in FILES}
    for name, expected in FILES.items():
        if actual_hashes[name] != expected:
            raise SystemExit(f"SHA-256 mismatch for {name}: {actual_hashes[name]}")

    config = json.loads((target / "config.json").read_text(encoding="utf-8"))
    if config.get("architectures") != ["T5EncoderModel"] or config.get("d_model") != 4096:
        raise SystemExit("checkpoint config is not the expected T5-XXL encoder")
    index = json.loads((target / "model.safetensors.index.json").read_text(encoding="utf-8"))
    weight_files = set(index.get("weight_map", {}).values())
    if weight_files != {"model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors"}:
        raise SystemExit("unexpected T5 weight index")
    manifest = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "revision": REVISION,
        "architecture": "T5EncoderModel",
        "dtype": "bfloat16-at-load-time",
        "files": actual_hashes,
    }
    manifest_path = target.parent / ".cpu-t5-manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    print(json.dumps({"target": str(target), "manifest": str(manifest_path), "files": actual_hashes}, indent=2))
    return manifest


def main() -> int:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(
            f"Usage: {sys.argv[0]} CPU_T5_ROOT [--verify-only]\n"
            "HF access to stabilityai/stable-diffusion-3.5-medium is required."
        )
    root = Path(sys.argv[1]).resolve()
    verify_only = len(sys.argv) == 3 and sys.argv[2] == "--verify-only"
    if len(sys.argv) == 3 and not verify_only:
        raise SystemExit("the only supported option is --verify-only")
    target = root / TARGET_DIRECTORY
    if not verify_only:
        root.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=REPOSITORY,
            revision=REVISION,
            local_dir=str(root),
            allow_patterns=[f"{TARGET_DIRECTORY}/{name}" for name in FILES],
            token=resolve_token(),
            max_workers=2,
        )
    verify(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
