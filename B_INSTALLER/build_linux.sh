#!/usr/bin/env bash
# build_linux.sh — Build di OffGallerySetup per Linux
#
# Esegui da terminale dentro B_INSTALLER/:
#   conda activate OffGallery
#   bash build_linux.sh
#
# Output: dist/OffGallerySetup  (binary ELF, auto-contenuto)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== OffGallery Installer — Build Linux ==="
echo "Directory: $SCRIPT_DIR"
echo ""

# Verifica che conda sia attivo
if [[ -z "$CONDA_PREFIX" ]]; then
    echo "ERRORE: nessun ambiente conda attivo."
    echo "Esegui prima: conda activate OffGallery"
    exit 1
fi

echo "Ambiente conda: $CONDA_PREFIX"

# Verifica che pyinstaller sia installato
if ! command -v pyinstaller &>/dev/null; then
    echo "Installazione pyinstaller..."
    pip install pyinstaller
fi

# Verifica che UPX sia disponibile (compressione opzionale)
if command -v upx &>/dev/null; then
    echo "UPX trovato: $(upx --version | head -1)"
else
    echo "UPX non trovato — il binary non sarà compresso (opzionale)."
    echo "Per installarlo: sudo apt-get install upx-ucl"
fi

echo ""
echo "Avvio build PyInstaller..."
echo ""

pyinstaller OffGallerySetup_linux.spec --clean --noconfirm

echo ""
echo "=== Build completata ==="
echo "Binary:  $SCRIPT_DIR/dist/OffGallerySetup"
echo "Dimensione: $(du -sh dist/OffGallerySetup 2>/dev/null | cut -f1)"
echo ""
echo "Per testare: ./dist/OffGallerySetup"
echo ""
echo "Distribuzione:"
echo "  Copia il file 'OffGallerySetup' e rendilo eseguibile:"
echo "  chmod +x OffGallerySetup"
echo "  ./OffGallerySetup"
