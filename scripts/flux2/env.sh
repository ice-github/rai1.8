# Source from bash/sh: . /path/to/cachyos/flux2/env.sh
_flux_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
_venv="$_flux_root/.venv"
_sp="$_venv/lib/python3.12/site-packages"
. "$_flux_root/../runtime/env.sh"
if [ "${VIRTUAL_ENV:-}" != "$_venv" ]; then . "$_venv/bin/activate"; fi
export RYZEN_AI_INSTALLATION_PATH="$_venv"
export RYZENAI_GENAI_SD_MODELS_ROOT="$_flux_root/models"
export DD_PLUGINS_ROOT="$_flux_root/lib/transaction/stx"
export DD_ROOT="$_flux_root/lib"
export LD_LIBRARY_PATH="$XILINX_XRT/lib:$_flux_root/../sdk/libcompat:$_sp/flexml/flexml_extras/lib:$_sp/onnxruntime/capi:$_sp/voe/lib:$_venv/deployment/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONPATH="$_flux_root/source-linux:$XILINX_XRT/python${PYTHONPATH:+:$PYTHONPATH}"
unset _flux_root _venv _sp
