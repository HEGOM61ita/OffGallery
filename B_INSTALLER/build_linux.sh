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

# Cerca CONDA_PREFIX: variabile d'ambiente oppure percorso standard Windows/WSL2
if [[ -z "$CONDA_PREFIX" ]]; then
    # Prova a ricavarlo da 'conda info' se conda è nel PATH
    if command -v conda &>/dev/null; then
        CONDA_PREFIX=$(conda info --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('active_prefix',''))" 2>/dev/null)
    fi
fi

# Ultimi fallback: percorsi standard WSL2 per env OffGallery su Windows
if [[ -z "$CONDA_PREFIX" || "$CONDA_PREFIX" == "null" || "$CONDA_PREFIX" == "None" ]]; then
    for candidate in \
        "/mnt/c/Users/$USER/anaconda3/envs/OffGallery" \
        "/mnt/c/Users/$USER/miniconda3/envs/OffGallery" \
        "/mnt/d/anaconda3/envs/OffGallery" \
        "/mnt/d/miniconda3/envs/OffGallery" \
        "$HOME/anaconda3/envs/OffGallery" \
        "$HOME/miniconda3/envs/OffGallery"
    do
        if [[ -d "$candidate" ]]; then
            CONDA_PREFIX="$candidate"
            break
        fi
    done
fi

if [[ -z "$CONDA_PREFIX" || "$CONDA_PREFIX" == "null" || "$CONDA_PREFIX" == "None" ]]; then
    echo "ERRORE: ambiente conda OffGallery non trovato."
    echo "Specifica il percorso manualmente:"
    echo "  CONDA_PREFIX=/path/to/envs/OffGallery bash build_linux.sh"
    exit 1
fi

echo "Ambiente conda: $CONDA_PREFIX"

# Python dell'ambiente (su Windows via WSL2 è python.exe)
PYTHON_EXE=""
for py in "$CONDA_PREFIX/bin/python" "$CONDA_PREFIX/python.exe"; do
    if [[ -f "$py" ]]; then
        PYTHON_EXE="$py"
        break
    fi
done

if [[ -z "$PYTHON_EXE" ]]; then
    echo "ERRORE: Python non trovato in $CONDA_PREFIX"
    exit 1
fi
echo "Python: $PYTHON_EXE"

# Percorso pyinstaller nell'ambiente
PYINSTALLER_EXE=""
for pi in "$CONDA_PREFIX/bin/pyinstaller" "$CONDA_PREFIX/Scripts/pyinstaller.exe" "$CONDA_PREFIX/Scripts/pyinstaller"; do
    if [[ -f "$pi" ]]; then
        PYINSTALLER_EXE="$pi"
        break
    fi
done

if [[ -z "$PYINSTALLER_EXE" ]]; then
    echo "Installazione pyinstaller..."
    "$PYTHON_EXE" -m pip install pyinstaller --quiet
    for pi in "$CONDA_PREFIX/bin/pyinstaller" "$CONDA_PREFIX/Scripts/pyinstaller.exe" "$CONDA_PREFIX/Scripts/pyinstaller"; do
        if [[ -f "$pi" ]]; then
            PYINSTALLER_EXE="$pi"
            break
        fi
    done
fi

if [[ -z "$PYINSTALLER_EXE" ]]; then
    # Fallback: usa python -m PyInstaller
    PYINSTALLER_EXE="$PYTHON_EXE -m PyInstaller"
fi

echo "PyInstaller: $PYINSTALLER_EXE"

# Verifica che UPX sia disponibile (compressione opzionale)
if command -v upx &>/dev/null; then
    echo "UPX trovato: $(upx --version | head -1)"
else
    echo "UPX non trovato — il binary non sarà compresso (opzionale)."
fi

echo ""
echo "Avvio build PyInstaller..."
echo ""

"$PYTHON_EXE" -m PyInstaller OffGallerySetup_linux.spec --clean --noconfirm

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
