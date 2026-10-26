#!/usr/bin/env python3
"""Install the project-owned CPU T5 cache into a prepared GenAI-SD source tree."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


IMPORT_OLD = "from src.utils.model_loader import ModelLoadConfig, ModelType, load_model\n"
IMPORT_NEW = IMPORT_OLD + "from src.utils.sd3_t5_cache import load_cached_t5_encoder\n"

OLD_BLOCK = '''        else:
            try:
                self.text_encoder_3 = load_model(
                    ModelLoadConfig(
                        model_path=os.path.join(abs_common_model_path, "text_encoder_3_gptq_v2"),
                        model_type=ModelType.T5_NPU_MODEL,
                        execution_providers=self.execution_providers,
                    ),
                    self.load_metrics_collector,
                )
            except Exception as e:
                Logger.warning(
                    f"Failed to load text_encoder_3_gptq_v2, using text_encoder_3 instead: {e}"
                )
                self.text_encoder_3 = load_model(
                    ModelLoadConfig(
                        model_path=os.path.join(abs_common_model_path, "text_encoder_3"),
                        model_type=ModelType.ONNX_MODEL,
                        execution_providers=self.execution_providers,
                    ),
                    self.load_metrics_collector,
                )
'''

NEW_BLOCK = '''        else:
            cached_t5_path = os.environ.get("SD3_T5_EMBEDDINGS_PATH")
            if cached_t5_path:
                self.text_encoder_3 = load_cached_t5_encoder(
                    cached_t5_path,
                    expected_revision=os.environ["SD3_T5_CPU_REVISION"],
                    expected_sequence_length=t5_sequence_len,
                )
            else:
                try:
                    self.text_encoder_3 = load_model(
                        ModelLoadConfig(
                            model_path=os.path.join(abs_common_model_path, "text_encoder_3_gptq_v2"),
                            model_type=ModelType.T5_NPU_MODEL,
                            execution_providers=self.execution_providers,
                        ),
                        self.load_metrics_collector,
                    )
                except Exception as e:
                    Logger.warning(
                        f"Failed to load text_encoder_3_gptq_v2, using text_encoder_3 instead: {e}"
                    )
                    self.text_encoder_3 = load_model(
                        ModelLoadConfig(
                            model_path=os.path.join(abs_common_model_path, "text_encoder_3"),
                            model_type=ModelType.ONNX_MODEL,
                            execution_providers=self.execution_providers,
                        ),
                        self.load_metrics_collector,
                    )
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch(source_root: Path, helper_source: Path) -> bool:
    trigger = source_root / "src/trigger/StableDiffusion3PipelineTrigger.py"
    helper = source_root / "src/utils/sd3_t5_cache.py"
    provenance = source_root.parent / "source-provenance.json"
    original_hash = sha256(trigger)
    source = trigger.read_text(encoding="utf-8")
    changed = False

    if IMPORT_NEW not in source:
        if source.count(IMPORT_OLD) != 1:
            raise SystemExit(f"expected one GenAI-SD model-loader import in {trigger}")
        source = source.replace(IMPORT_OLD, IMPORT_NEW, 1)
        changed = True
    if NEW_BLOCK not in source:
        if source.count(OLD_BLOCK) != 1:
            raise SystemExit(f"expected one unpatched SD3 T5 load block in {trigger}")
        source = source.replace(OLD_BLOCK, NEW_BLOCK, 1)
        changed = True
    if changed:
        trigger.write_text(source, encoding="utf-8")

    helper_source = helper_source.resolve()
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(helper_source, helper)

    if provenance.is_file():
        data = json.loads(provenance.read_text(encoding="utf-8"))
        patches = data.setdefault("patches", [])
        entry = next((item for item in patches if item.get("id") == "sd3-cpu-t5-cache"), None)
        final_hash = sha256(trigger)
        if entry is None:
            entry = {
                "id": "sd3-cpu-t5-cache",
                "file": "src/trigger/StableDiffusion3PipelineTrigger.py",
                "result": "applied",
                "reason": "Load precomputed CPU T5 embeddings so the 9.5 GB T5-XXL process exits before NPU Transformer/VAE model loading.",
                "sha256_before": original_hash,
                "sha256_after": final_hash,
            }
            patches.append(entry)
        elif entry.get("sha256_after") != final_hash:
            raise SystemExit("SD3 CPU T5 patch provenance hash does not match the runtime source")
        provenance.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"Usage: {sys.argv[0]} PATH_TO_source-linux PATH_TO_sd3_t5_cache.py")
    changed = patch(Path(sys.argv[1]), Path(sys.argv[2]))
    print("patched SD3 CPU T5 cache" if changed else "already patched SD3 CPU T5 cache")


if __name__ == "__main__":
    main()
