#!/usr/bin/env bash
# Builds the Linux app (dist/DataLabTrainer) plus a .deb and a portable .tar.gz.
# The same steps run automatically on GitHub Actions - see .github/workflows/datalab.yml
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./install.sh
.venv/bin/python -m pip install pyinstaller
.venv/bin/python -m PyInstaller --noconfirm --distpath dist --workpath build packaging/datalab.spec
packaging/build_linux.sh "$(.venv/bin/python -c 'import datalab; print(datalab.__version__)')"
