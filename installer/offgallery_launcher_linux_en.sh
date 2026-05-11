#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# OffGallery Launcher (Linux)
# Starts OffGallery by automatically locating conda
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFGALLERY_PATH="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_NAME="OffGallery"

# --- Search for conda ---
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
    echo "  [ERROR] Conda not found."
    echo ""
    echo "  Paths searched:"
    echo "    - System PATH"
    echo "    - $HOME/miniconda3"
    echo "    - $HOME/anaconda3"
    echo "    - /opt/miniconda3"
    echo "    - /opt/anaconda3"
    echo ""
    echo "  If you just installed Miniconda, open a new terminal."
    echo "  Otherwise run: bash installer/install_offgallery_linux_en.sh"
    echo ""
    exit 1
fi

# --- Start OffGallery ---
cd "$OFFGALLERY_PATH" || { echo "  [ERROR] Folder not found: $OFFGALLERY_PATH"; exit 1; }

# Include ~/.local/bin in PATH (ExifTool installed locally without sudo)
export PATH="$HOME/.local/bin:$PATH"

# Display variables for WSL2 / sessions without an inherited graphical environment
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:0
fi
# XDG_RUNTIME_DIR: required for Qt/xcb. Uses /run/user/<uid> if it exists,
# otherwise creates a temporary directory writable by the current user.
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

# WSL detection: in WSL the Wayland socket belongs to the primary user
# and is not accessible to other users. XCB (X11) and software rendering
# are forced to avoid xcb crashes and black windows due to unsupported OpenGL.
if grep -qi microsoft /proc/version 2>/dev/null; then
    export QT_QPA_PLATFORM=xcb
    export LIBGL_ALWAYS_SOFTWARE=1
    export QT_OPENGL=software
fi

"$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python gui_launcher.py

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "  [ERROR] The application closed with an error (code: $EXIT_CODE)."
    echo ""
fi

exit $EXIT_CODE
