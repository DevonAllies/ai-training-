#!/usr/bin/env bash
# Adds DataLab Trainer (portable tar.gz version) to your applications menu.
# Run it from the unpacked DataLabTrainer folder:   ./install-desktop-entry.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/512x512/apps"
mkdir -p "$apps" "$icons" "$HOME/.local/bin"
cp "$here/datalab-trainer.png" "$icons/datalab-trainer.png"
ln -sf "$here/DataLabTrainer" "$HOME/.local/bin/datalab-trainer"
sed "s|^Exec=.*|Exec=\"$here/DataLabTrainer\"|" "$here/datalab-trainer.desktop" > "$apps/datalab-trainer.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$apps" || true
echo "Added DataLab Trainer to your applications menu (and ~/.local/bin/datalab-trainer)."
