#!/usr/bin/env bash
# Build script per OffGallery Manager (macOS / Linux)
# Richiede: pip install pyinstaller
#
# Uso: bash build.sh
#
# Output: dist/OffGallerySetup  (Linux)
#         dist/OffGallerySetup.app  (macOS)

set -e
cd "$(dirname "$0")"

echo ""
echo " OffGallery Manager -- Build"
echo " ============================"
echo ""

# Verifica pyinstaller
if ! python -m pyinstaller --version &>/dev/null; then
    echo "[!!] PyInstaller non trovato. Installalo con:"
    echo "     pip install pyinstaller"
    exit 1
fi

# Pulisci build precedente
rm -rf build dist/__pycache__

echo "[..] Build in corso..."
python -m pyinstaller OffGallerySetup.spec

echo ""
if [[ "$(uname)" == "Darwin" ]]; then
    echo "[OK] Build completata: dist/OffGallerySetup.app"
else
    echo "[OK] Build completata: dist/OffGallerySetup"
    ls -lh dist/OffGallerySetup
fi
echo ""
