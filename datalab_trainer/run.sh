#!/usr/bin/env bash
# Starts DataLab Trainer and opens it in your browser. Press Ctrl+C to stop.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./install.sh
exec .venv/bin/python -m datalab "$@"
