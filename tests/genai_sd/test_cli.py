from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "scripts/genai_sd"
sys.path.insert(0, str(ROOT.parent))

from genai_sd.cli import PROTOCOL_VERSION, _load_request, validate_matrix


def test_protocol_version_is_available_without_frontend_imports():
    result = subprocess.run(
        [sys.executable, "-m", "genai_sd.cli", "--protocol-version"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {"protocol_version": PROTOCOL_VERSION}
    assert "app" not in result.stdout
    assert "config" not in result.stdout


def test_request_preserves_empty_negative_prompt(tmp_path):
    path = tmp_path / "request.json"
    request = {
        "protocol_version": PROTOCOL_VERSION,
        "model_id": "test/model",
        "model_revision": "a" * 40,
        "model_path": str(tmp_path / "model"),
        "flux_root": str(tmp_path / "flux"),
        "python": sys.executable,
        "prompt": "test",
        "negative_prompt": "",
        "width": 1024,
        "height": 1024,
        "steps": 8,
        "seed": 42,
        "guidance_scale": 4.5,
        "npu_component": "transformer",
        "supports_negative_prompt": True,
        "work_dir": str(tmp_path / "work"),
    }
    path.write_text(json.dumps(request))
    assert _load_request(path)["negative_prompt"] == ""


def test_validation_matrix_rejects_unexpected_scenario_set(tmp_path):
    with pytest.raises(ValueError, match="validation_scenarios"):
        validate_matrix({"validation_scenarios": []}, tmp_path / "suite.json")


@pytest.mark.parametrize("bad_width", [True, 0, -1, "1024"])
def test_request_rejects_invalid_dimensions(tmp_path, bad_width):
    path = tmp_path / "request.json"
    request = {
        "protocol_version": PROTOCOL_VERSION,
        "model_id": "test/model",
        "model_revision": "a" * 40,
        "model_path": str(tmp_path / "model"),
        "flux_root": str(tmp_path / "flux"),
        "python": sys.executable,
        "prompt": "test",
        "negative_prompt": "",
        "width": bad_width,
        "height": 1024,
        "steps": 8,
        "seed": 42,
        "guidance_scale": 4.5,
        "npu_component": "transformer",
        "supports_negative_prompt": True,
        "work_dir": str(tmp_path / "work"),
    }
    path.write_text(json.dumps(request))
    with pytest.raises(ValueError, match="width"):
        _load_request(path)
