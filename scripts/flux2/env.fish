# Source from fish to use the isolated FLUX.2 environment.
set -l _flux_root (realpath (dirname (status --current-filename)))
set -l _venv "$_flux_root/.venv"
set -l _sp "$_venv/lib/python3.12/site-packages"
source "$_flux_root/../runtime/env.fish"
if test "$VIRTUAL_ENV" != "$_venv"
    source "$_venv/bin/activate.fish"
end
set -gx RYZEN_AI_INSTALLATION_PATH "$_venv"
set -gx RYZENAI_GENAI_SD_MODELS_ROOT "$_flux_root/models"
set -gx DD_PLUGINS_ROOT "$_flux_root/lib/transaction/stx"
set -gx DD_ROOT "$_flux_root/lib"
set -gx LD_LIBRARY_PATH \
    "$XILINX_XRT/lib" \
    "$_flux_root/../sdk/libcompat" \
    "$_sp/flexml/flexml_extras/lib" \
    "$_sp/onnxruntime/capi" \
    "$_sp/voe/lib" \
    "$_venv/deployment/lib" \
    $LD_LIBRARY_PATH
set -gx PYTHONPATH "$_flux_root/source-linux" "$XILINX_XRT/python" $PYTHONPATH
set -e _flux_root _venv _sp
