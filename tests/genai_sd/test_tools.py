from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "scripts/genai_sd"
sys.path.insert(0, str(ROOT.parent))

from genai_sd import bundle_aliases
from genai_sd.patches.cpu_t5_cache import patch as patch_cpu_t5
from genai_sd.patches.empty_negative_prompt import patch_runner


def write_bundle(path: Path, keys: list[str], payload: bytes = b"compiled-payload") -> None:
    records = [len(keys).to_bytes(4, "little")]
    for index, key in enumerate(keys):
        encoded = key.encode("ascii")
        records.extend((
            len(encoded).to_bytes(4, "little"), encoded,
            b"".join((index * 100 + part).to_bytes(8, "little") for part in range(6)),
        ))
    index = b"".join(records)
    path.write_bytes(payload + index + len(index).to_bytes(4, "little") + b"\0" * 4 + b"BXI0")


@pytest.mark.parametrize(("source", "expected"), [
    (b"height_64_width_48_", b"width_48_height_64_"),
    (b"batch_2_2_w_64_h_48_state_dim1_768_max_length_160_",
     b"h_48_w_64_batch_2_2_state_dim1_768_max_length_160_"),
    (b"latent_h_128_latent_w_96_", b"latent_w_96_latent_h_128_"),
])
def test_shape_key_aliases(source, expected):
    assert bundle_aliases.preferred_key(source) == expected


def test_bundle_patch_preserves_payload_values_and_original(tmp_path):
    bundle = tmp_path / "vae.ddbundle"
    write_bundle(bundle, ["height_64_width_48_", "height_48_width_64_"])
    original = bundle.read_bytes()
    result = bundle_aliases.apply(bundle, check_only=False)
    parsed = bundle_aliases.inspect(bundle)
    assert result["status"] == "patched"
    assert parsed["payload_sha256"] == bundle_aliases.sha256(original[:parsed["index_start"]])
    assert not parsed["aliases"]
    assert bundle.with_name(bundle.name + ".linux-shape.bak").read_bytes() == original


def test_bundle_patch_rejects_alias_collision_and_symlink_path(tmp_path):
    collision = tmp_path / "collision.ddbundle"
    write_bundle(collision, ["height_64_width_48_", "width_48_height_64_"])
    with pytest.raises(ValueError, match="collision"):
        bundle_aliases.inspect(collision)

    source = tmp_path / "source"
    source.mkdir()
    linked = source / "linked.ddbundle"
    write_bundle(linked, ["height_64_width_48_"])
    overlay = tmp_path / "overlay"
    overlay.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        bundle_aliases.apply(overlay / linked.name, check_only=False)


def test_empty_negative_patch_is_idempotent(tmp_path):
    runner = tmp_path / "runner_args.py"
    runner.write_text('if not getattr(args, "n_prompt", None):\n    args.n_prompt = "sample"\n')
    assert patch_runner(runner)
    assert not patch_runner(runner)
    assert 'if getattr(args, "n_prompt", None) is None:' in runner.read_text()


def test_cpu_t5_patch_is_idempotent_and_records_provenance(tmp_path):
    source = tmp_path / "source-linux"
    trigger = source / "src/trigger/StableDiffusion3PipelineTrigger.py"
    trigger.parent.mkdir(parents=True)
    trigger.write_text(
        'from src.utils.model_loader import ModelLoadConfig, ModelType, load_model\n'
        '        else:\n'
        '            try:\n'
        '                self.text_encoder_3 = load_model(\n'
        '                    ModelLoadConfig(\n'
        '                        model_path=os.path.join(abs_common_model_path, "text_encoder_3_gptq_v2"),\n'
        '                        model_type=ModelType.T5_NPU_MODEL,\n'
        '                        execution_providers=self.execution_providers,\n'
        '                    ),\n'
        '                    self.load_metrics_collector,\n'
        '                )\n'
        '            except Exception as e:\n'
        '                Logger.warning(\n'
        '                    f"Failed to load text_encoder_3_gptq_v2, using text_encoder_3 instead: {e}"\n'
        '                )\n'
        '                self.text_encoder_3 = load_model(\n'
        '                    ModelLoadConfig(\n'
        '                        model_path=os.path.join(abs_common_model_path, "text_encoder_3"),\n'
        '                        model_type=ModelType.ONNX_MODEL,\n'
        '                        execution_providers=self.execution_providers,\n'
        '                    ),\n'
        '                    self.load_metrics_collector,\n'
        '                )\n'
    )
    helper_source = ROOT / "sd3_t5_cache.py"
    provenance = tmp_path / "source-provenance.json"
    provenance.write_text(json.dumps({"patches": []}))
    assert patch_cpu_t5(source, helper_source)
    assert not patch_cpu_t5(source, helper_source)
    recorded = json.loads(provenance.read_text())
    assert recorded["patches"][0]["id"] == "sd3-cpu-t5-cache"
    assert (source / "src/utils/sd3_t5_cache.py").read_bytes() == helper_source.read_bytes()
