# FLUX.2 klein 4B の準備と実行

The helper scripts are templates. Create a private work layout so the scripts
can locate the sibling `runtime/` and `sdk/` directories expected by the
environment wrappers:

```bash
REPO=/path/to/rai1.8
WORK="$HOME/rai18-work/cachyos"
mkdir -p "$WORK/flux2"
cp -a "$REPO/scripts/flux2/." "$WORK/flux2/"
# Place the isolated runtime at $WORK/runtime and SDK venv at $WORK/sdk/venv.
```

## 1. Source and Python environment

```bash
cd "$WORK/flux2"
git clone https://github.com/amd/sd-sandbox.git source
git -C source checkout e13ca6d7ac14fc415f8aa58acc027f427197e300
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
```

Install the Python dependencies from the pinned upstream environment plus the
official SDK's vendor ONNX Runtime wheel. `requirements.txt` records versions
used in the test, but the Vitis AI wheel must come from the official SDK package
and may not be available from PyPI. Review license and Python ABI compatibility.
Then prepare a separate Linux-compatible source copy:

```bash
python prepare_source.py \
  --source "$WORK/flux2/source" \
  --dest "$WORK/flux2/source-linux" \
  --provenance "$WORK/flux2/source-provenance.json"
```

The script fails closed if its expected pinned-source anchors differ.
Review the resulting provenance/diff. Do not publish either source tree.

## 2. Model and transaction data

```bash
python -m pip install huggingface_hub
python fetch_model.py "$WORK/flux2/models"
```

This downloads the fixed Hugging Face revision. Review the model card/license
before accepting its terms. The model is large and stays local.

The runtime also needs three STX transaction archives from the Ryzen AI 1.8
GenAI-SD distribution: `sd_fastpm_DiT.zip`, `sd_fastpm_Unet.zip`, and
`sd_preemption.zip`. Obtain the official distribution, inspect its contents,
and extract only the required archives to:
`$WORK/flux2/lib/transaction/stx/`. Do not run the Windows installer and do not
commit CAB/MSI/ZIP files or extracted archives.

## 3. Bundle key normalization

Check then normalize the pinned model's BXI0 index keys when required:

```bash
find "$WORK/flux2/models/amd_FLUX.2-klein-4B-amdnpu" -name '*.ddbundle' -print0 \
  | xargs -0 python "$WORK/flux2/bundle_aliases.py" --check
find "$WORK/flux2/models/amd_FLUX.2-klein-4B-amdnpu" -name '*.ddbundle' -print0 \
  | xargs -0 python "$WORK/flux2/bundle_aliases.py" \
      --manifest "$WORK/flux2/linux-bundle-aliases.json"
```

The tool recognizes only the observed BXI0 structure and equal-length known
shape-key permutations. It keeps local `.linux-shape.bak` originals, does not
change record values or model payload, and rejects unknown formats. Verify the
manifest and hashes. These are model files and backups: keep them private/local.

## 4. Check and run

Confirm that the provider library exists in the vendor venv and the expected
runtime/transaction directories are present. `run-flux2.sh` sets offline model
loading after preparation, checks the NPU and bundle state, and writes all
generated images/profiles/logs below the local `results/` directory.

```bash
cd "$WORK/flux2"
./run-flux2.sh --check
./run-flux2.sh --run
```

The reference run is 1024×1024, 4 steps, guidance 1.0, seed 0, batch 1. It
uses CPU for the text encoder and expects Ryzen AI EP execution for Transformer
and VAE. Memory sampling stops below 2 GiB `MemAvailable` or after 30 minutes.
Inspect `completed.json`, `sessions.jsonl`, ORT profiles, the image, and
`dispatch-evidence.json`; a provider name in a session alone is not proof of
actual NPU dispatch. The run does not establish long-run or reboot stability.

Do not commit `models/`, `.venv/`, `lib/`, `source/`, `source-linux/`,
`results/`, profiles, images, caches, or vendor acquisition files.
