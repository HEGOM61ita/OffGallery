#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# OffGallery Launcher (macOS)
# Avvia OffGallery trovando conda automaticamente
# ═══════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFGALLERY_PATH="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_NAME="OffGallery"

# --- Cerca conda nei percorsi standard macOS ---
CONDA_CMD=""

if command -v conda &>/dev/null; then
    CONDA_CMD="conda"
elif [ -x "$HOME/miniconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/miniconda3/bin/conda"
elif [ -x "$HOME/opt/miniconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/opt/miniconda3/bin/conda"
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/anaconda3/bin/conda"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
    CONDA_CMD="$HOME/miniforge3/bin/conda"
elif [ -x "$HOME/mambaforge/bin/conda" ]; then
    CONDA_CMD="$HOME/mambaforge/bin/conda"
elif [ -x "/opt/homebrew/Caskroom/miniconda/base/bin/conda" ]; then
    CONDA_CMD="/opt/homebrew/Caskroom/miniconda/base/bin/conda"
elif [ -x "/usr/local/Caskroom/miniconda/base/bin/conda" ]; then
    CONDA_CMD="/usr/local/Caskroom/miniconda/base/bin/conda"
elif [ -x "/opt/miniconda3/bin/conda" ]; then
    CONDA_CMD="/opt/miniconda3/bin/conda"
fi

if [ -z "$CONDA_CMD" ]; then
    echo ""
    echo "  [ERRORE] Conda non trovato."
    echo ""
    echo "  Percorsi cercati:"
    echo "    - PATH di sistema"
    echo "    - $HOME/miniconda3"
    echo "    - $HOME/opt/miniconda3"
    echo "    - $HOME/anaconda3"
    echo "    - $HOME/miniforge3"
    echo "    - /opt/homebrew/Caskroom/miniconda/base"
    echo "    - /opt/miniconda3"
    echo ""
    echo "  Se hai appena installato Miniconda, apri un nuovo terminale."
    echo "  Altrimenti esegui: bash installer/install_offgallery_mac.sh"
    echo ""
    exit 1
fi

# --- Avvia OffGallery ---
cd "$OFFGALLERY_PATH" || { echo "  [ERRORE] Cartella non trovata: $OFFGALLERY_PATH"; exit 1; }

# Includi ~/.local/bin nel PATH (ExifTool installato localmente senza brew)
export PATH="$HOME/.local/bin:$PATH"

# Su macOS, PyQt6 usa il backend Cocoa nativo — nessuna variabile DISPLAY necessaria.
# QT_MAC_WANTS_LAYER=1 abilita il rendering su layer Metal (evita artefatti grafici
# su alcuni Mac con macOS 11+).
export QT_MAC_WANTS_LAYER=1

"$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python gui_launcher.py

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "  [ERRORE] L'applicazione si è chiusa con errore (codice: $EXIT_CODE)."
    echo ""
fi

exit $EXIT_CODE
