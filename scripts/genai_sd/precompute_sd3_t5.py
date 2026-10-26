#!/usr/bin/env python3
"""Encode SD3 positive/negative prompts with the pinned T5-XXL on CPU."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import torch
from safetensors.torch import save_file
from transformers import T5EncoderModel, T5TokenizerFast


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--tokenizer-path", required=True, type=Path)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--sequence-length", required=True, type=int)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative-prompt", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    args = parser.parse_args()

    if not args.model_path.is_dir():
        raise SystemExit(f"CPU T5 model directory does not exist: {args.model_path}")
    if args.sequence_length < 1 or args.sequence_length > 512:
        raise SystemExit("T5 sequence length must be between 1 and 512")

    threads = max(1, min(8, os.cpu_count() or 1))
    torch.set_num_threads(threads)
    started = time.perf_counter()
    tokenizer = T5TokenizerFast.from_pretrained(
        args.tokenizer_path,
        local_files_only=True,
    )
    model = T5EncoderModel.from_pretrained(
        args.model_path,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        use_safetensors=True,
        local_files_only=True,
    ).eval()

    tensors = {}
    records = {}
    with torch.inference_mode():
        for name, text in (("positive", args.prompt), ("negative", args.negative_prompt)):
            encoded = tokenizer(
                text,
                padding="max_length",
                max_length=args.sequence_length,
                truncation=True,
                add_special_tokens=True,
                return_tensors="pt",
            )
            t0 = time.perf_counter()
            hidden = model(input_ids=encoded.input_ids).last_hidden_state.detach().cpu().contiguous()
            elapsed = time.perf_counter() - t0
            if hidden.shape != (1, args.sequence_length, 4096):
                raise RuntimeError(f"unexpected {name} T5 output shape: {tuple(hidden.shape)}")
            if not torch.isfinite(hidden).all():
                raise RuntimeError(f"T5 produced non-finite {name} embeddings")
            tensors[f"{name}_input_ids"] = encoded.input_ids.cpu().contiguous()
            tensors[f"{name}_hidden_state"] = hidden
            records[name] = {
                "shape": list(hidden.shape),
                "dtype": str(hidden.dtype),
                "seconds": round(elapsed, 3),
                "finite": True,
            }
            print(json.dumps({"event": "encoded", "name": name, **records[name]}), flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_file(
        tensors,
        str(args.output),
        metadata={
            "schema": "sd3-cpu-t5-embeddings-v1",
            "model_revision": args.model_revision,
            "sequence_length": str(args.sequence_length),
        },
    )
    args.metrics.write_text(
        json.dumps(
            {
                "model_revision": args.model_revision,
                "sequence_length": args.sequence_length,
                "dtype": "bfloat16",
                "threads": threads,
                "components": records,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "embedding_file_bytes": args.output.stat().st_size,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"event": "complete", "path": str(args.output), "seconds": round(time.perf_counter() - started, 3)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
