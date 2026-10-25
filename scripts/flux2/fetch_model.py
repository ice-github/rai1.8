#!/usr/bin/env python3
"""Download the pinned FLUX.2 klein 4B NPU model into the isolated tree.

The sd-sandbox runtime uses RYZENAI_GENAI_SD_MODELS_ROOT and stores a model as
<root>/<model_id with / replaced by _>. This script reproduces that layout so
the runtime finds the model without downloading anything at run time.

Revision is pinned; `main` is never used.
"""

from __future__ import annotations

import sys
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL_ID = "amd/FLUX.2-klein-4B-amdnpu"
REVISION = "45aeffe92ecf5ce0169c511c232c2f100be3cbe1"

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
target = root / MODEL_ID.replace("/", "_")

print(f"model_id : {MODEL_ID}")
print(f"revision : {REVISION}")
print(f"target   : {target}", flush=True)

path = snapshot_download(
    repo_id=MODEL_ID,
    revision=REVISION,
    local_dir=str(target),
    max_workers=8,
)
print(f"downloaded: {path}", flush=True)

rev_file = target / ".revision"
rev_file.write_text(REVISION, encoding="utf-8")
print(f"wrote {rev_file}", flush=True)
