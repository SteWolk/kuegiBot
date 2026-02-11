#!/usr/bin/env bash
set -euxo pipefail

# --- System build deps (entspricht apt-get im Dockerfile) ---
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  gcc g++ make
sudo rm -rf /var/lib/apt/lists/*

# --- Conda initialisieren (Codex hat i.d.R. bereits conda/miniconda; falls nicht, siehe Hinweis unten) ---
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

# --- Reproduzierbares Env wie im Dockerfile ---
ENV_NAME="kuegibot"

# Env neu anlegen oder aktualisieren
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda activate "$ENV_NAME"
else
  conda create -y -n "$ENV_NAME" -c conda-forge python=3.10
  conda activate "$ENV_NAME"
fi

# Pakete exakt wie im Dockerfile (conda-forge)
conda install -y -c conda-forge \
  ta-lib=0.4.19 \
  numpy=1.26.0 \
  pandas=2.2.1

# --- Pip deps ---
python -m pip install -U pip
if [ -f requirements.txt ]; then
  pip install --no-cache-dir -r requirements.txt
fi

# Optional: kurze Smoke-Checks
python -c "import sys; print(sys.version)"
python -c "import talib, numpy, pandas; print('ta-lib', talib.__version__); print('numpy', numpy.__version__); print('pandas', pandas.__version__)"
