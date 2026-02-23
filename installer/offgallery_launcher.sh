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

if command -v conda &>/dev/null; then
    CONDA_CMD="conda"
elif [ -x "$HOME/miniconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/miniconda3/bin/conda"
elif [ -x "$HOME/.miniconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/.miniconda3/bin/conda"
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/anaconda3/bin/conda"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
    CONDA_CMD="$HOME/miniforge3/bin/conda"
elif [ -x "$HOME/mambaforge/bin/conda" ]; then
    CONDA_CMD="$HOME/mambaforge/bin/conda"
elif [ -x "/opt/conda/bin/conda" ]; then
    CONDA_CMD="/opt/conda/bin/conda"
elif [ -x "/opt/miniconda3/bin/conda" ]; then
    CONDA_CMD="/opt/miniconda3/bin/conda"
elif [ -x "/opt/anaconda3/bin/conda" ]; then
    CONDA_CMD="/opt/anaconda3/bin/conda"
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
    echo "    - /opt/anaconda3"
    echo ""
    echo "  Se hai appena installato Miniconda, apri un nuovo terminale."
    echo "  Altrimenti esegui: bash installer/install_offgallery.sh"
    echo ""
    exit 1
fi

# --- Avvia OffGallery ---
cd "$OFFGALLERY_PATH" || { echo "  [ERRORE] Cartella non trovata: $OFFGALLERY_PATH"; exit 1; }

# Includi ~/.local/bin nel PATH (ExifTool installato localmente senza sudo)
export PATH="$HOME/.local/bin:$PATH"

# Variabili display per WSL2 / sessioni senza ambiente grafico ereditato
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
fi
# XDG_RUNTIME_DIR: necessario per Qt/xcb. Usa /run/user/<uid> se esiste,
# altrimenti crea una directory temporanea scrivibile dall'utente corrente.
if [ -z "$XDG_RUNTIME_DIR" ]; then
    _XDG_STD="/run/user/$(id -u)"
    if [ -d "$_XDG_STD" ]; then
        export XDG_RUNTIME_DIR="$_XDG_STD"
    else
        _XDG_TMP="/tmp/runtime-$(id -u)"
        mkdir -p "$_XDG_TMP"
        chmod 700 "$_XDG_TMP"
        export XDG_RUNTIME_DIR="$_XDG_TMP"
    fi
fi

# Rilevamento WSL: in WSL il socket Wayland appartiene all'utente principale
# e non è accessibile ad altri utenti. Si forza XCB (X11) e il rendering
# software per evitare crash xcb e finestre nere per OpenGL non supportato.
if grep -qi microsoft /proc/version 2>/dev/null; then
    export QT_QPA_PLATFORM=xcb
    export LIBGL_ALWAYS_SOFTWARE=1
    export QT_OPENGL=software
fi

"$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python gui_launcher.py

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "  [ERRORE] L'applicazione si è chiusa con errore (codice: $EXIT_CODE)."
    echo ""
fi

exit $EXIT_CODE
