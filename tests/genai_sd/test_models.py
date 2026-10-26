from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "scripts/genai_sd"
sys.path.insert(0, str(ROOT.parent))

from genai_sd.bundle_aliases import inspect
from genai_sd.models import REQUIRED_FILES, prepare_model


def write_bundle(path: Path) -> bytes:
    key = b"height_64_width_64_"
    record = len(key).to_bytes(4, "little") + key + bytes(range(48))
    index = (1).to_bytes(4, "little") + record
    payload = b"compiled-payload"
    bundle = payload + index + len(index).to_bytes(4, "little") + b"\0" * 4 + b"BXI0"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bundle)
    return bundle


def test_prepare_model_normalizes_only_isolated_copy(tmp_path):
    source = tmp_path / "source"
    for relative in REQUIRED_FILES:
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    bundle_path = source / "common/vae_decoder/dynamic/dd/test.ddbundle"
    original_bundle = write_bundle(bundle_path)
    target = tmp_path / "prepared"

    manifest = prepare_model(
        "stabilityai/stable-diffusion-3-medium-amdnpu",
        "a" * 40,
        source,
        target,
    )

    assert bundle_path.read_bytes() == original_bundle
    prepared_bundle = target / bundle_path.relative_to(source)
    assert not inspect(prepared_bundle)["aliases"]
    assert (prepared_bundle.with_name(prepared_bundle.name + ".linux-shape.bak")).read_bytes() == original_bundle
    saved = json.loads((target / ".linux-shape-manifest.json").read_text())
    assert saved["prepared_path"] == str(target.resolve())
    assert saved["source_revision"] == "a" * 40
    assert saved == manifest
