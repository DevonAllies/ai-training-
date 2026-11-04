#!/usr/bin/env bash
# DataLab Trainer - one-time setup on Ubuntu / Debian (and other Linux).
#   sudo apt install python3 python3-venv r-base     # once
#   ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null; then
  echo "python3 not found. Install it with: sudo apt install python3 python3-venv" >&2; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv .venv || { echo "Creating the virtual environment failed. Try: sudo apt install python3-venv" >&2; exit 1; }
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
if ! command -v Rscript >/dev/null; then
  echo
  echo "R was not found. For the R exercises install it with:  sudo apt install r-base"
fi
echo
echo "DataLab Trainer is installed. Start it with ./run.sh"
