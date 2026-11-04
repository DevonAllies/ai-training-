#!/usr/bin/env bash
# Builds the Linux packages from the PyInstaller output in dist/DataLabTrainer:
#   dist/DataLabTrainer-<version>-linux-x86_64.tar.gz   portable, unpack anywhere
#   dist/datalab-trainer_<version>_amd64.deb            for Ubuntu/Debian: sudo apt install ./<file>.deb
# Usage (from the datalab_trainer folder):  packaging/build_linux.sh <version>
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:?version}"
APP=dist/DataLabTrainer
[ -x "$APP/DataLabTrainer" ] || { echo "Run pyinstaller packaging/datalab.spec first" >&2; exit 1; }

# portable tar.gz
cp packaging/linux/datalab-trainer.desktop packaging/linux/install-desktop-entry.sh "$APP/"
cp packaging/datalab.png "$APP/datalab-trainer.png"
tar -C dist -czf "dist/DataLabTrainer-$VERSION-linux-x86_64.tar.gz" DataLabTrainer

# .deb
DEB=$(mktemp -d)
mkdir -p "$DEB/DEBIAN" "$DEB/opt" "$DEB/usr/bin" "$DEB/usr/share/applications" \
         "$DEB/usr/share/icons/hicolor/512x512/apps"
cp -a "$APP" "$DEB/opt/datalab-trainer"
rm -f "$DEB/opt/datalab-trainer/install-desktop-entry.sh" "$DEB/opt/datalab-trainer/datalab-trainer.desktop"
ln -s /opt/datalab-trainer/DataLabTrainer "$DEB/usr/bin/datalab-trainer"
cp packaging/linux/datalab-trainer.desktop "$DEB/usr/share/applications/"
cp packaging/datalab.png "$DEB/usr/share/icons/hicolor/512x512/apps/datalab-trainer.png"
SIZE=$(du -sk "$DEB" | cut -f1)
cat > "$DEB/DEBIAN/control" <<CONTROL
Package: datalab-trainer
Version: $VERSION
Section: education
Priority: optional
Architecture: amd64
Installed-Size: $SIZE
Recommends: r-base, xdg-utils
Maintainer: DataLab Trainer <noreply@users.noreply.github.com>
Homepage: https://github.com/DevonAllies/ai-training-
Description: Hands-on data analysis and data science training
 Learn the analytics workflow (import, clean, EDA, visualisation,
 statistics, modelling, forecasting, SHAP and report writing) in SQL,
 Python and R. Python and all libraries are bundled; install r-base for
 the R exercises.
CONTROL
dpkg-deb --build --root-owner-group "$DEB" "dist/datalab-trainer_${VERSION}_amd64.deb"
rm -rf "$DEB"
ls -lh dist/*.tar.gz dist/*.deb
