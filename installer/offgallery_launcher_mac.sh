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

# Ricava il percorso dell'ambiente conda (necessario per chiamare python direttamente).
# Su macOS, 'conda run' lancia l'app in un subprocess: il framework Cocoa/Qt richiede
# di girare nel processo principale → segfault. Chiamiamo il python dell'env direttamente.
CONDA_ENV_PATH=""

# 1. Prova con 'conda info --envs' (il più affidabile)
CONDA_ENV_PATH=$(
    "$CONDA_CMD" info --envs 2>/dev/null \
    | grep -E "^$ENV_NAME[[:space:]]" \
    | awk '{print $NF}'
)

# 2. Fallback filesystem: cerca nei percorsi standard
if [ -z "$CONDA_ENV_PATH" ] || [ ! -x "$CONDA_ENV_PATH/bin/python" ]; then
    for base in \
        "$HOME/miniconda3" "$HOME/opt/miniconda3" "$HOME/anaconda3" \
        "$HOME/miniforge3" "$HOME/mambaforge" \
        "/opt/homebrew/Caskroom/miniconda/base" \
        "/usr/local/Caskroom/miniconda/base" \
        "/opt/miniconda3"
    do
        if [ -x "$base/envs/$ENV_NAME/bin/python" ]; then
            CONDA_ENV_PATH="$base/envs/$ENV_NAME"
            break
        fi
    done
fi

if [ -n "$CONDA_ENV_PATH" ] && [ -x "$CONDA_ENV_PATH/bin/python" ]; then
    # Attiva le variabili d'ambiente dell'env senza usare conda run
    export CONDA_PREFIX="$CONDA_ENV_PATH"
    export PATH="$CONDA_ENV_PATH/bin:$PATH"
    "$CONDA_ENV_PATH/bin/python" gui_launcher.py
else
    # Ultimo fallback: conda run (può causare segfault su alcune configurazioni macOS)
    echo "  [ATTENZIONE] Python dell'env non trovato direttamente, uso conda run..."
    "$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python gui_launcher.py
fi

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "  [ERRORE] L'applicazione si è chiusa con errore (codice: $EXIT_CODE)."
    echo ""
fi

exit $EXIT_CODE
