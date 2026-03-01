#!/usr/bin/env bash
set -euo pipefail

# Setup a conda environment aligned with the VPS botenv profile.
# Intended for online environments.

CONDA_ROOT="${CONDA_ROOT:-/workspace/.local/miniconda3}"
CONDA_BIN="${CONDA_BIN:-$CONDA_ROOT/bin/conda}"
ENV_NAME="${ENV_NAME:-botenv}"

if [[ ! -x "$CONDA_BIN" ]]; then
  mkdir -p "$(dirname "$CONDA_ROOT")"
  curl -fsSL -o /tmp/miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
  bash /tmp/miniconda.sh -b -p "$CONDA_ROOT"
fi

"$CONDA_BIN" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main || true
"$CONDA_BIN" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r || true
"$CONDA_BIN" config --system --remove channels defaults || true
"$CONDA_BIN" config --system --add channels conda-forge

"$CONDA_BIN" create -y -n "$ENV_NAME" --override-channels -c conda-forge \
  python=3.10.18 \
  numpy=1.26.0 \
  pandas=2.2.1 \
  ta-lib=0.4.32 \
  plotly=4.12.0 \
  requests=2.31.0 \
  websocket-client=1.1.0 \
  zstandard=0.23.0

"$CONDA_BIN" run -n "$ENV_NAME" pip install --no-cache-dir \
  pybit==5.6.2 \
  pycryptodome==3.23.0 \
  websockets==15.0.1

"$CONDA_BIN" run -n "$ENV_NAME" python - <<'PY'
import sys
import numpy, pandas, talib, plotly, requests, websocket, zstandard
import pybit, websockets, Crypto

print("python", sys.version.split()[0])
print("numpy", numpy.__version__)
print("pandas", pandas.__version__)
print("ta-lib", talib.__version__)
print("plotly", plotly.__version__)
print("requests", requests.__version__)
print("websocket-client", websocket.__version__)
print("zstandard", zstandard.__version__)
print("websockets", websockets.__version__)
print("pycryptodome", Crypto.__version__)
print("pybit", pybit.__file__)
PY

echo
printf 'Environment ready. Use: %s run -n %s <command>\n' "$CONDA_BIN" "$ENV_NAME"
