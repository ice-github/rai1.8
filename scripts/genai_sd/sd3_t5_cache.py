"""Load precomputed CPU T5 embeddings in the AMD SD3 inference process."""

from __future__ import annotations

from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import load_file


class CachedT5Encoder:
    """Small CPU facade matching the T5 encoder call used by the SD3 pipeline."""

    model_name = "T5EncoderModelCPUPrecomputed"
    perf_device = "CPU"

    def __init__(self, embeddings: dict[tuple[int, ...], torch.Tensor]):
        self._embeddings = embeddings

    def __call__(self, input_ids: torch.Tensor) -> dict[str, torch.Tensor]:
        if input_ids.ndim == 1:
            input_ids = input_ids.unsqueeze(0)
        keys = [tuple(row) for row in input_ids.detach().to("cpu").tolist()]
        missing = [key for key in keys if key not in self._embeddings]
        if missing:
            raise RuntimeError(
                "CPU T5 embeddings were not precomputed for this prompt/sequence; "
                "refusing to substitute empty embeddings"
            )
        return {"last_hidden_state": torch.stack([self._embeddings[key] for key in keys])}


def load_cached_t5_encoder(
    path: str | Path,
    *,
    expected_revision: str,
    expected_sequence_length: int,
) -> CachedT5Encoder:
    """Load and validate precomputed prompt embeddings without loading T5 weights."""

    path = Path(path)
    with safe_open(path, framework="pt", device="cpu") as tensors:
        metadata = tensors.metadata() or {}
    if metadata.get("schema") != "sd3-cpu-t5-embeddings-v1":
        raise RuntimeError(f"unsupported CPU T5 embedding file: {path}")
    if metadata.get("model_revision") != expected_revision:
        raise RuntimeError("CPU T5 embedding revision does not match the configured pin")
    if metadata.get("sequence_length") != str(expected_sequence_length):
        raise RuntimeError("CPU T5 embedding length does not match the requested length")

    values = load_file(str(path), device="cpu")
    result: dict[tuple[int, ...], torch.Tensor] = {}
    for name in ("positive", "negative"):
        ids = values.get(f"{name}_input_ids")
        hidden = values.get(f"{name}_hidden_state")
        if ids is None or hidden is None:
            raise RuntimeError(f"CPU T5 embedding file is missing {name} tensors")
        if ids.ndim != 2 or ids.shape[0] != 1 or ids.shape[1] != expected_sequence_length:
            raise RuntimeError(f"invalid CPU T5 {name} input-id shape: {tuple(ids.shape)}")
        if hidden.ndim != 3 or hidden.shape[:2] != ids.shape or hidden.shape[2] != 4096:
            raise RuntimeError(f"invalid CPU T5 {name} hidden-state shape: {tuple(hidden.shape)}")
        if hidden.dtype not in (torch.bfloat16, torch.float16) or not torch.isfinite(hidden).all():
            raise RuntimeError(f"invalid CPU T5 {name} embedding values")
        result[tuple(ids[0].tolist())] = hidden[0].contiguous()

    return CachedT5Encoder(result)
