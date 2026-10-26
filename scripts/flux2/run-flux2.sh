#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/source-linux"
MODEL="$ROOT/models/amd_FLUX.2-klein-4B-amdnpu"
MODEL_ID="amd/FLUX.2-klein-4B-amdnpu"
REVISION="45aeffe92ecf5ce0169c511c232c2f100be3cbe1"

usage() { echo "Usage: $0 --check | --run [--prompt TEXT]"; }
mode=""
prompt="A small red cabin beside a lake, mountains in the background, morning light, detailed photograph"
while (($#)); do
  case "$1" in
    --check|--run) mode="${1#--}"; shift ;;
    --prompt) (($# >= 2)) || { usage >&2; exit 2; }; prompt="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ -n "$mode" ]] || { usage >&2; exit 2; }
source "$ROOT/env.sh"

check() {
  [[ -x "$ROOT/.venv/bin/python" && -d "$SOURCE/src" ]] || { echo "ERROR: FLUX environment/source missing" >&2; return 1; }
  [[ "$(<"$MODEL/.revision")" == "$REVISION" ]] || { echo "ERROR: pinned model revision mismatch" >&2; return 1; }
  [[ -r /dev/accel/accel0 && -w /dev/accel/accel0 ]] || { echo "ERROR: /dev/accel/accel0 inaccessible" >&2; return 1; }
  [[ $(find "$MODEL" -name '*.ddbundle' -type f | wc -l) -eq 4 ]] || { echo "ERROR: expected 4 ddbundles" >&2; return 1; }
  for f in sd_fastpm_DiT.zip sd_fastpm_Unet.zip sd_preemption.zip; do
    [[ -f "$ROOT/lib/transaction/stx/$f" ]] || { echo "ERROR: missing transaction $f" >&2; return 1; }
  done
  local -a bundle_paths=()
  mapfile -d '' bundle_paths < <(find "$MODEL" -name '*.ddbundle' -type f -print0)
  "$VIRTUAL_ENV/bin/python" "$ROOT/tools/genai_sd/bundle_aliases.py" --check "${bundle_paths[@]}" || { echo "ERROR: bundle shape-key normalization is incomplete" >&2; return 1; }
  "$VIRTUAL_ENV/bin/python" -c 'import onnxruntime as o, torch, diffusers, transformers; assert "VitisAIExecutionProvider" in o.get_available_providers(); print("Python imports/providers OK:", o.__version__, o.get_available_providers())'
  [[ -f "$VIRTUAL_ENV/lib/python3.12/site-packages/voe/lib/libonnxruntime_providers_ryzenai.so" ]] || { echo "ERROR: RyzenAI custom EP library missing" >&2; return 1; }
  LC_ALL=C LANGUAGE=C "$XILINX_XRT/bin/xrt-smi" examine --batch
  echo "CHECK PASS"
}

if [[ "$mode" == check ]]; then check; exit $?; fi
check
exec 9>"$ROOT/.genai_sd.lock"
flock -x 9
STAMP="$(date +%Y%m%d-%H%M%S)-$$"
OUT="$ROOT/results/$STAMP"
mkdir -p "$OUT/images" "$OUT/profiles"
printf '%s\n' "$OUT" > "$ROOT/.last-result"
printf '%s\n' "$REVISION" > "$OUT/model-revision.txt"
cp "$ROOT/source-provenance.json" "$OUT/"
cp "$ROOT/linux-bundle-aliases.json" "$OUT/" 2>/dev/null || true

export LC_ALL=C LANGUAGE=C HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export FLUX2_ORT_PROFILE=1 FLUX2_PROFILE_DIR="$OUT/profiles"
export FLUX2_SESSION_LOG="$OUT/sessions.jsonl" FLUX2_PROFILE_LOG="$OUT/profile-files.jsonl"
cmd=("$VIRTUAL_ENV/bin/python" "$SOURCE/test/run.py" --model_id "$MODEL_ID" --revision "$REVISION" --model_path "$MODEL" --width 1024 --height 1024 --num_inference_steps 4 --guidance_scale 1.0 --seed 0 --num_images_per_prompt 1 --prompt "$prompt" --output_path "$OUT/images")
{
  echo "=== START $(date --iso-8601=seconds) ==="
  echo "Result: $OUT"
  echo "Model: $MODEL_ID@$REVISION; 1024x1024; steps=4; guidance=1; seed=0; batch=1"
  echo "Text encoder: CPU; Transformer/VAE: NPU expected"
} | tee "$OUT/run.log"
start=$(date +%s)
set +e
"$VIRTUAL_ENV/bin/python" "$ROOT/tools/genai_sd/measure_memory.py" \
  --csv "$OUT/memory.csv" --summary "$OUT/memory-summary.json" \
  --interval 0.2 --min-available-gib 2 --timeout 1800 -- "${cmd[@]}" \
  2>&1 | tee -a "$OUT/run.log"
rc=${PIPESTATUS[0]}
set -e
elapsed=$(( $(date +%s) - start ))
echo "=== exit=$rc duration=${elapsed}s END $(date --iso-8601=seconds) ===" | tee -a "$OUT/run.log"
if ((rc != 0)); then
  printf '{"status":"inference_failed","exit_code":%d,"duration_seconds":%d}\n' "$rc" "$elapsed" > "$OUT/completed.json"
  exit "$rc"
fi
if ! "$VIRTUAL_ENV/bin/python" "$ROOT/tools/genai_sd/evidence.py" "$OUT"; then
  printf '{"status":"image_generated_npu_dispatch_unverified","exit_code":1,"duration_seconds":%d}\n' "$elapsed" > "$OUT/completed.json"
  exit 1
fi
printf '{"status":"image_generated_npu_dispatch_verified","exit_code":0,"duration_seconds":%d}\n' "$elapsed" > "$OUT/completed.json"
echo "PASS: $OUT"
