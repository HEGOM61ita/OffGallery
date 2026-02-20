#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# OffGallery Launcher (Linux)
# Avvia OffGallery trovando conda automaticamente
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFGALLERY_PATH="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_NAME="OffGallery"

# --- Cerca conda ---
CONDA_CMD=""

# 1. conda nel PATH
if command -v conda &>/dev/null; then
    CONDA_CMD="conda"

# 2. Percorsi noti Miniconda
elif [ -x "$HOME/miniconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/miniconda3/bin/conda"

elif [ -x "$HOME/.miniconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/.miniconda3/bin/conda"

# 3. Percorsi noti Anaconda
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/anaconda3/bin/conda"

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
    echo "    - $HOME/anaconda3"
    echo "    - /opt/miniconda3"
    echo ""
    echo "  Se hai appena installato Miniconda, apri un nuovo terminale."
    echo "  Altrimenti esegui: bash installer/install_offgallery.sh"
    echo ""
    exit 1
fi

# --- Avvia OffGallery ---
cd "$OFFGALLERY_PATH"
"$CONDA_CMD" run -n "$ENV_NAME" --no-banner python gui_launcher.py

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "  [ERRORE] L'applicazione si è chiusa con errore (codice: $EXIT_CODE)."
    echo ""
fi

exit $EXIT_CODE
