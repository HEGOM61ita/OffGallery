#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# OffGallery Launcher (macOS)
# Starts OffGallery by locating conda automatically
# ═══════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFGALLERY_PATH="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_NAME="OffGallery"

# --- Search for conda in standard macOS paths ---
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
    echo "  [ERROR] Conda not found."
    echo ""
    echo "  Paths searched:"
    echo "    - system PATH"
    echo "    - $HOME/miniconda3"
    echo "    - $HOME/opt/miniconda3"
    echo "    - $HOME/anaconda3"
    echo "    - $HOME/miniforge3"
    echo "    - /opt/homebrew/Caskroom/miniconda/base"
    echo "    - /opt/miniconda3"
    echo ""
    echo "  If you just installed Miniconda, open a new terminal window."
    echo "  Otherwise run: bash installer/install_offgallery_mac_en.sh"
    echo ""
    exit 1
fi

# --- Launch OffGallery ---
cd "$OFFGALLERY_PATH" || { echo "  [ERROR] Folder not found: $OFFGALLERY_PATH"; exit 1; }

# Include ~/.local/bin in PATH (ExifTool installed locally without brew)
export PATH="$HOME/.local/bin:$PATH"

# On macOS, PyQt6 uses the native Cocoa backend — no DISPLAY variable needed.
# QT_MAC_WANTS_LAYER=1 enables Metal layer rendering (avoids graphical artefacts
# on some Macs with macOS 11+).
export QT_MAC_WANTS_LAYER=1

# Check conda architecture on Apple Silicon: a Miniconda x86_64 running under Rosetta 2
# causes segfaults with PyQt6/Metal even when Python is called directly.
_SYS_ARCH=$(uname -m)
if [ "$_SYS_ARCH" = "arm64" ]; then
    _CONDA_BASE_TMP=$("$CONDA_CMD" info --base 2>/dev/null | tr -d '[:space:]')
    _PY_BIN="$_CONDA_BASE_TMP/bin/python3"
    [ -x "$_PY_BIN" ] || _PY_BIN="$_CONDA_BASE_TMP/bin/python"
    if [ -x "$_PY_BIN" ]; then
        _PY_ARCH=$(file "$_PY_BIN" 2>/dev/null | grep -oE 'arm64|x86_64' | head -1)
        if [ "$_PY_ARCH" = "x86_64" ]; then
            echo ""
            echo "  [ERROR] x86_64 Conda detected on Apple Silicon (arm64)."
            echo ""
            echo "  The installed Miniconda is running under Rosetta 2 (x86_64 emulation)."
            echo "  This causes segfaults with PyQt6/Metal on M1/M2/M3/M4."
            echo ""
            echo "  Solution: reinstall native arm64 Miniconda."
            echo "  Run:"
            echo "    bash \"$SCRIPT_DIR/install_offgallery_mac_en.sh\""
            echo ""
            echo "  The installation wizard will provide detailed instructions."
            echo ""
            exit 1
        fi
    fi
fi

# Retrieve the conda environment path (needed to call python directly).
# On macOS, 'conda run' launches the app as a subprocess: the Cocoa/Qt framework requires
# running in the main process → segfault. We call the env's python directly instead.
CONDA_ENV_PATH=""

# 1. Primary method: conda info --base → builds the path directly (more reliable)
_CONDA_BASE=$("$CONDA_CMD" info --base 2>/dev/null | tr -d '[:space:]')
if [ -n "$_CONDA_BASE" ] && [ -x "$_CONDA_BASE/envs/$ENV_NAME/bin/python" ]; then
    CONDA_ENV_PATH="$_CONDA_BASE/envs/$ENV_NAME"
fi

# 2. Fallback: conda info --envs with name-based parsing
if [ -z "$CONDA_ENV_PATH" ] || [ ! -x "$CONDA_ENV_PATH/bin/python" ]; then
    CONDA_ENV_PATH=$(
        "$CONDA_CMD" info --envs 2>/dev/null \
        | grep -E "^$ENV_NAME[[:space:]]" \
        | awk '{print $NF}'
    )
fi

# 3. Filesystem fallback: search in standard paths
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
    # Properly activate the conda env: set CONDA_PREFIX, PATH and all
    # package activation hooks (e.g. Qt6, torch) via the official script.
    export CONDA_PREFIX="$CONDA_ENV_PATH"
    export PATH="$CONDA_ENV_PATH/bin:$PATH"
    if [ -f "$_CONDA_BASE/etc/profile.d/conda.sh" ]; then
        # shellcheck disable=SC1091
        source "$_CONDA_BASE/etc/profile.d/conda.sh"
        conda activate "$ENV_NAME" 2>/dev/null
    fi

    # Download AI models BEFORE launching Qt if they are not already present.
    # On macOS, downloading inside the Qt process causes segfaults due to conflicts
    # between native libraries (torch/transformers) and the Cocoa/Metal framework.
    MODELS_DIR="$OFFGALLERY_PATH/Models"
    if [ ! -f "$MODELS_DIR/clip/config.json" ] || [ ! -f "$MODELS_DIR/dinov2/config.json" ]; then
        echo ""
        echo "  First launch: downloading AI models..."
        echo "  (one-time operation, requires an internet connection)"
        echo ""
        "$CONDA_ENV_PATH/bin/python" gui_launcher.py --download-models
        if [ $? -ne 0 ]; then
            echo ""
            echo "  [ERROR] Model download failed. Check your connection and try again."
            echo ""
            exit 1
        fi
        echo ""
        echo "  Download complete. Starting OffGallery..."
        echo ""
    fi

    # 'exec' replaces the bash process with python instead of spawning a child.
    # On macOS, Cocoa/Metal requires the Qt app to be the original process
    # (not a subprocess): even a single bash→python level can cause
    # SIGSEGV on the first render on macOS Ventura/Sonoma/Sequoia with Apple Silicon.
    exec "$CONDA_ENV_PATH/bin/python" gui_launcher.py

else
    # If we reach this point, the OffGallery environment was not found: show diagnostics.
    echo ""
    echo "  [ERROR] Python environment 'OffGallery' not found."
    echo ""
    echo "  Diagnostics:"
    echo "    Conda base: ${_CONDA_BASE:-not detected}"
    echo "    Available environments:"
    "$CONDA_CMD" env list 2>/dev/null | sed 's/^/      /' || echo "      (none)"
    echo ""
    echo "  Solution: run the installation wizard:"
    echo "    bash \"$OFFGALLERY_PATH/installer/install_offgallery_mac_en.sh\""
    echo ""
    exit 1
fi
