#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# OffGallery - Installation Wizard for macOS
# Run with: bash install_offgallery_mac.sh
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# === COLORS ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# === GLOBAL VARIABLES ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements_offgallery.txt"
LAUNCHER="$SCRIPT_DIR/offgallery_launcher_mac.sh"
ENV_NAME="OffGallery"
PYTHON_VER="3.12"

# Detect architecture (Intel or Apple Silicon)
_ARCH=$(uname -m)
case "$_ARCH" in
    arm64) _MINICONDA_ARCH="MacOSX-arm64"   ;;
    *)     _MINICONDA_ARCH="MacOSX-x86_64"  ;;
esac
MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-${_MINICONDA_ARCH}.sh"
MINICONDA_INSTALLER="/tmp/miniconda_installer.sh"
MINICONDA_DIR="$HOME/miniconda3"
OLLAMA_MODEL="qwen3.5:4b-q4_K_M"
STEP_TOTAL=5

# Status flags for summary
STATUS_MINICONDA="-"
STATUS_ENV="-"
STATUS_PACKAGES="-"
STATUS_OLLAMA="-"
STATUS_DESKTOP="-"

CONDA_CMD=""
SKIP_ENV_CREATE=false

# === UTILITIES ===
print_header() {
    echo ""
    echo -e "${BOLD}  ================================================================${NC}"
    echo -e "${BOLD}    STEP $1/$STEP_TOTAL: $2${NC}"
    echo -e "${BOLD}  ================================================================${NC}"
    echo ""
}

print_ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
print_err()  { echo -e "  ${RED}[ERROR]${NC} $1"; }
print_warn() { echo -e "  ${YELLOW}[!!]${NC} $1"; }
print_info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

ask_yes_no() {
    local answer answer_lower
    read -rp "  $1 (y/n): " answer
    answer_lower=$(echo "$answer" | tr '[:upper:]' '[:lower:]')
    [[ "$answer_lower" == "s" || "$answer_lower" == "si" || "$answer_lower" == "y" || "$answer_lower" == "yes" ]]
}

# Check conda environment via filesystem (more reliable than 'conda env list')
env_python_exists() {
    local conda_base
    conda_base=$("$CONDA_CMD" info --base 2>/dev/null | tr -d '\r')
    [ -n "$conda_base" ] && [ -x "$conda_base/envs/$ENV_NAME/bin/python" ]
}

# Check that the conda architecture matches the system.
# On Apple Silicon (arm64), an x86_64 Miniconda runs under Rosetta 2:
# the emulated x86_64 Python process attempts to use native arm64
# Cocoa/Metal frameworks → guaranteed segfault with PyQt6/Metal.
check_conda_arch() {
    # Only on Apple Silicon: not an issue on Intel
    [ "$_ARCH" = "arm64" ] || return 0

    local conda_base python_bin python_arch
    conda_base=$("$CONDA_CMD" info --base 2>/dev/null | tr -d '[:space:]')

    # Find the conda base Python
    python_bin="$conda_base/bin/python3"
    [ -x "$python_bin" ] || python_bin="$conda_base/bin/python"
    [ -x "$python_bin" ] || return 0  # Cannot verify, proceed

    python_arch=$(file "$python_bin" 2>/dev/null | grep -oE 'arm64|x86_64' | head -1)
    [ -n "$python_arch" ] || return 0  # Cannot determine, proceed

    if [ "$python_arch" != "arm64" ]; then
        echo ""
        print_err "INCOMPATIBLE CONDA ARCHITECTURE"
        echo ""
        echo "   System:  arm64  (Apple Silicon)"
        echo "   Conda:   $python_arch  (running under Rosetta 2 — x86_64 emulation)"
        echo ""
        echo "   On Apple Silicon, Miniconda must be the native arm64 version."
        echo "   The x86_64 version causes segfaults with PyQt6/Metal"
        echo "   even when Python is called directly (not via conda run)."
        echo ""
        echo "   ── SOLUTION ──────────────────────────────────────────────────"
        echo ""
        echo "   1) Uninstall x86_64 Miniconda:"
        echo "      rm -rf $conda_base"
        echo "      sed -i.bak '/conda initialize/,/# <<< conda initialize/d' \\"
        echo "          ~/.zshrc ~/.bash_profile 2>/dev/null; true"
        echo ""
        echo "   2) Install native arm64 Miniconda:"
        echo "      curl -fsSL 'https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh' \\"
        echo "          -o /tmp/miniconda.sh"
        echo "      bash /tmp/miniconda.sh -b -p ~/miniconda3"
        echo "      ~/miniconda3/bin/conda init zsh && rm /tmp/miniconda.sh"
        echo ""
        echo "   3) Close and reopen the terminal, then run this installer again."
        echo ""
        exit 1
    fi

    print_ok "Conda architecture: arm64 (native Apple Silicon — OK)"
}

# ═══════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════
clear 2>/dev/null || true
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo -e "${BOLD}             OffGallery - Guided Installation (macOS)${NC}"
echo ""
echo "    Automatic photo cataloguing with AI - 100% Offline"
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo "   This wizard will install all required components."
echo "   Estimated time: 20-40 minutes (depends on connection speed)."
echo ""
echo "   Components:"
echo "     [1] Miniconda (Python environment manager)"
echo "     [2] OffGallery Python environment"
echo "     [3] Python libraries + ExifTool"
echo "     [4] Ollama + LLM Vision model (optional)"
echo "     [5] Desktop launcher"
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   SYSTEM REQUIREMENTS:"
echo "     Operating System:  macOS 12 Monterey or later"
echo "     Architecture:      Intel x86_64 or Apple Silicon (M1/M2/M3/M4)"
echo "     RAM:               8 GB minimum, 16 GB recommended"
echo "     Disk Space:        15-25 GB free"
echo "     GPU:               Apple Silicon uses Metal/MPS (included)"
echo "     Internet:          Required for installation"
echo ""
echo "  ----------------------------------------------------------------"
echo ""

if ! ask_yes_no "Do you want to proceed with the installation?"; then
    echo ""
    echo "   Installation cancelled."
    echo ""
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 1/5: MINICONDA
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=1
print_header "$STEP_CURRENT" "Miniconda"

# --- Scenario A: conda in PATH ---
if command -v conda &>/dev/null; then
    CONDA_VERSION=$(conda --version 2>/dev/null || echo "unknown version")
    print_ok "$CONDA_VERSION found on the system."
    STATUS_MINICONDA="Already present"
    CONDA_CMD="conda"

# --- Scenario B: standard macOS paths ---
elif [ -x "$HOME/miniconda3/bin/conda" ]; then
    print_ok "Miniconda found in $HOME/miniconda3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$HOME/miniconda3/bin/conda"
elif [ -x "$HOME/opt/miniconda3/bin/conda" ]; then
    print_ok "Miniconda found in $HOME/opt/miniconda3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$HOME/opt/miniconda3/bin/conda"
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
    print_ok "Anaconda found in $HOME/anaconda3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$HOME/anaconda3/bin/conda"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
    print_ok "Miniforge found in $HOME/miniforge3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$HOME/miniforge3/bin/conda"
elif [ -x "$HOME/mambaforge/bin/conda" ]; then
    print_ok "Mambaforge found in $HOME/mambaforge"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$HOME/mambaforge/bin/conda"
# Homebrew cask (Intel and Apple Silicon)
elif [ -x "/opt/homebrew/Caskroom/miniconda/base/bin/conda" ]; then
    print_ok "Miniconda (Homebrew cask) found in /opt/homebrew/Caskroom/miniconda/base"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="/opt/homebrew/Caskroom/miniconda/base/bin/conda"
elif [ -x "/usr/local/Caskroom/miniconda/base/bin/conda" ]; then
    print_ok "Miniconda (Homebrew cask Intel) found in /usr/local/Caskroom/miniconda/base"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="/usr/local/Caskroom/miniconda/base/bin/conda"
elif [ -x "/opt/miniconda3/bin/conda" ]; then
    print_ok "Miniconda found in /opt/miniconda3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="/opt/miniconda3/bin/conda"

# --- Scenario C: installation needed ---
else
    echo "   Miniconda not found. Installing..."
    echo ""

    # Show detected architecture
    if [ "$_ARCH" = "arm64" ]; then
        print_info "Architecture: Apple Silicon (arm64)"
    else
        print_info "Architecture: Intel x86_64"
    fi
    echo ""
    echo "   Downloading Miniconda (~90 MB)..."
    echo ""

    # Remove any partial previous installation
    if [ -d "$MINICONDA_DIR" ]; then
        print_warn "Folder $MINICONDA_DIR already exists but conda does not work."
        echo "   This may be an incomplete previous installation."
        echo ""
        if ask_yes_no "Do you want to remove it and reinstall Miniconda?"; then
            rm -rf "$MINICONDA_DIR"
            echo "   Folder removed."
        else
            print_err "Cannot proceed with the existing folder."
            echo "   Remove it manually: rm -rf $MINICONDA_DIR"
            echo "   then run this wizard again."
            exit 1
        fi
    fi

    if ! curl -fSL "$MINICONDA_URL" -o "$MINICONDA_INSTALLER"; then
        print_err "Miniconda download failed."
        echo "   Check your internet connection and try again."
        echo ""
        echo "   Alternatively, download manually from:"
        echo "   https://docs.anaconda.com/miniconda/install/"
        echo "   then run this wizard again."
        exit 1
    fi

    # Check file size (at least 50 MB)
    FILE_SIZE=$(stat -f%z "$MINICONDA_INSTALLER" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -lt 50000000 ]; then
        print_err "Downloaded file is too small ($FILE_SIZE bytes). Download is probably corrupted."
        rm -f "$MINICONDA_INSTALLER"
        exit 1
    fi

    print_ok "Download completed."
    echo ""
    echo "   Installing Miniconda in $MINICONDA_DIR..."
    echo "   (This may take 2-5 minutes)"
    echo ""

    if ! bash "$MINICONDA_INSTALLER" -b -p "$MINICONDA_DIR"; then
        print_err "Miniconda installation failed."
        echo ""
        echo "   Possible causes:"
        echo "     - Insufficient disk space"
        echo "     - Missing permissions on the home folder"
        echo "     - Corrupted previous installation"
        echo ""
        echo "   Try removing the folder and running again:"
        echo "     rm -rf $MINICONDA_DIR"
        echo "     bash installer/install_offgallery_mac.sh"
        rm -f "$MINICONDA_INSTALLER"
        exit 1
    fi

    rm -f "$MINICONDA_INSTALLER"

    if [ ! -x "$MINICONDA_DIR/bin/conda" ]; then
        print_err "Installation completed but conda not found."
        echo "   Expected path: $MINICONDA_DIR/bin/conda"
        exit 1
    fi

    # Initialize conda for the current session
    eval "$("$MINICONDA_DIR/bin/conda" shell.bash hook)" 2>/dev/null || true

    # Initialize for bash and zsh (zsh is the default shell on macOS since 2019)
    "$MINICONDA_DIR/bin/conda" init bash 2>/dev/null || true
    "$MINICONDA_DIR/bin/conda" init zsh  2>/dev/null || true

    print_ok "Miniconda installed successfully!"
    echo ""
    print_info "Conda has been initialized for bash and zsh."
    print_info "To make conda available in future terminals, reopen the terminal."
    STATUS_MINICONDA="Installed"
    CONDA_CMD="$MINICONDA_DIR/bin/conda"
fi

# Check conda architecture (blocks if x86_64 on Apple Silicon)
check_conda_arch

# ═══════════════════════════════════════════════════════════════════
# STEP 2/5: OFFGALLERY ENVIRONMENT
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=2
print_header "$STEP_CURRENT" "Python Environment"

if env_python_exists; then
    print_ok "Environment \"$ENV_NAME\" already present."
    echo ""
    if ask_yes_no "Do you want to delete it and recreate it from scratch?"; then
        echo ""
        echo "   Removing existing environment..."
        "$CONDA_CMD" env remove -n "$ENV_NAME" -y 2>&1 || {
            print_err "Unable to remove the environment."
            echo "   Try manually: conda env remove -n $ENV_NAME -y"
            exit 1
        }
        echo "   Environment removed. Recreating..."
        echo ""
    else
        STATUS_ENV="Already present"
        SKIP_ENV_CREATE=true
    fi
fi

if [ "$SKIP_ENV_CREATE" != "true" ]; then
    echo "   Creating environment \"$ENV_NAME\" with Python $PYTHON_VER..."
    echo "   (1-3 minutes)"
    echo ""

    if ! "$CONDA_CMD" create -n "$ENV_NAME" python="$PYTHON_VER" -y \
            --override-channels \
            --channel conda-forge; then
        print_err "Environment creation failed."
        echo "   Possible causes:"
        echo "     - Insufficient disk space"
        echo "     - Missing permissions"
        echo "     - Network issues while downloading Python"
        exit 1
    fi

    if ! env_python_exists; then
        print_err "Environment creation failed (python not found after creation)."
        exit 1
    fi

    echo ""
    print_ok "Environment \"$ENV_NAME\" created!"
    STATUS_ENV="Created"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 3/5: PYTHON DEPENDENCIES + EXIFTOOL
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=3
print_header "$STEP_CURRENT" "Python Dependencies + ExifTool"

if [ ! -f "$REQUIREMENTS" ]; then
    print_err "Requirements file not found: $REQUIREMENTS"
    echo "   Make sure the installer folder is complete."
    exit 1
fi

# Show GPU information for the user
if [ "$_ARCH" = "arm64" ]; then
    GPU_NOTE="Apple Silicon (M-series) — GPU acceleration via Metal/MPS included"
else
    GPU_NOTE="Intel Mac — CPU mode (no NVIDIA GPU available on Mac)"
fi

echo "   Installing Python libraries (PyTorch, CLIP, BioCLIP, etc.)"
echo "   Estimated download: ~3 GB"
echo "   Estimated time: 10-20 minutes"
echo ""
echo "   Components:"
echo "     - PyTorch ($GPU_NOTE)"
echo "     - Transformers (HuggingFace)"
echo "     - BioCLIP (nature classification)"
echo "     - PyQt6 (graphical interface)"
echo "     - OpenCV (image processing)"
echo "     - Argos Translate (IT-EN translation)"
echo ""
echo "   NOTE: The PyTorch download may appear stuck for"
echo "   several minutes. This is normal, please wait patiently."
echo ""
echo "  ----------------------------------------------------------------"
echo ""

# Check Xcode Command Line Tools (required to compile some dependencies)
echo "   Checking Xcode Command Line Tools..."
if ! xcode-select -p &>/dev/null; then
    print_warn "Xcode Command Line Tools not found."
    echo "   They are required to install some Python libraries."
    echo ""
    echo "   Installing (a dialog window may open)..."
    xcode-select --install 2>/dev/null || true
    echo ""
    echo "   If a window appears, click 'Install' and wait for it to complete."
    echo "   When done, press ENTER to continue."
    read -r
else
    print_ok "Xcode Command Line Tools present."
fi
echo ""

# Upgrade pip
echo "   [1/2] Upgrading pip..."
"$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python -m pip install --upgrade pip -q 2>/dev/null || true

# Install requirements
echo "   [2/2] Installing Python dependencies..."
echo ""

# On Mac, PyTorch installs from the standard channel (includes MPS for Apple Silicon)
# No special index-url needed as on Linux/Windows for CUDA
if ! "$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" pip install -r "$REQUIREMENTS"; then
    print_err "Dependency installation failed."
    echo ""
    echo "   Possible causes:"
    echo "     - Unstable internet connection"
    echo "     - Insufficient disk space (~6 GB required)"
    echo "     - Missing Xcode Command Line Tools (run: xcode-select --install)"
    echo ""
    echo "   Suggestion: run this wizard again. Already downloaded"
    echo "   packages will not be re-downloaded."
    exit 1
fi

# Check critical packages
echo ""
echo "   Verifying package installation..."
INSTALL_OK=true

check_pkg() {
    local import_expr="$1"
    local label="$2"
    if "$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python -c "$import_expr" 2>/dev/null; then
        : # message is already included in the expression
    else
        print_err "$label not found"
        INSTALL_OK=false
    fi
}

check_pkg "import torch; mps='YES' if torch.backends.mps.is_available() else 'NO'; print(f'  [OK] PyTorch {torch.__version__} - MPS (Apple Silicon GPU): {mps}')" "torch"
check_pkg "import yaml; print(f'  [OK] PyYAML {yaml.__version__}')" "pyyaml"
check_pkg "from PyQt6.QtWidgets import QApplication; print('  [OK] PyQt6')" "PyQt6"
check_pkg "import numpy; print(f'  [OK] NumPy {numpy.__version__}')" "numpy"
check_pkg "import cv2; print(f'  [OK] OpenCV {cv2.__version__}')" "opencv"
check_pkg "import PIL; print(f'  [OK] Pillow {PIL.__version__}')" "Pillow"
check_pkg "import transformers; print(f'  [OK] transformers {transformers.__version__}')" "transformers"
check_pkg "import open_clip; print('  [OK] open-clip-torch')" "open-clip-torch"
check_pkg "import rawpy; print(f'  [OK] rawpy {rawpy.__version__}')" "rawpy"

if [ "$INSTALL_OK" = false ]; then
    echo ""
    print_err "Incomplete installation. One or more packages are missing."
    echo ""
    echo "   Try installing Xcode Command Line Tools if you haven't already:"
    echo "     xcode-select --install"
    echo ""
    echo "   Then run this wizard again. Already downloaded"
    echo "   packages will not be re-downloaded."
    exit 1
fi

# --- ExifTool ---
echo ""
echo "   Checking ExifTool..."

if command -v exiftool &>/dev/null; then
    EXIF_VER=$(exiftool -ver 2>/dev/null || echo "?")
    print_ok "ExifTool $EXIF_VER already installed."
else
    echo "   ExifTool not found. Installing..."
    EXIFTOOL_INSTALLED=false

    # Attempt 1: Homebrew (standard package manager on Mac)
    if command -v brew &>/dev/null; then
        print_info "Homebrew found — installing ExifTool via brew..."
        if brew install exiftool 2>/dev/null; then
            EXIFTOOL_INSTALLED=true
        else
            print_warn "ExifTool installation via brew failed."
        fi
    else
        print_info "Homebrew not found — trying direct installation..."
    fi

    # Attempt 2: Fallback — download tar.gz from exiftool.org (pure Perl, works on Mac)
    if [ "$EXIFTOOL_INSTALLED" = false ]; then
        if ! command -v perl &>/dev/null; then
            print_warn "perl not found — local ExifTool installation not possible."
        elif ! command -v curl &>/dev/null; then
            print_warn "curl not found — local ExifTool installation not possible."
        else
            _ET_DIR="$HOME/.local/share/exiftool"
            _ET_BIN="$HOME/.local/bin/exiftool"
            mkdir -p "$HOME/.local/bin" "$_ET_DIR"
            echo "   Downloading ExifTool from exiftool.org..."
            _ET_VER=$(curl -fsSL "https://exiftool.org/ver.txt" 2>/dev/null | tr -d '[:space:]')
            if [ -n "$_ET_VER" ] && curl -fsSL "https://exiftool.org/Image-ExifTool-${_ET_VER}.tar.gz" \
                    -o /tmp/exiftool.tar.gz; then
                if tar -xzf /tmp/exiftool.tar.gz -C "$_ET_DIR" --strip-components=1; then
                    ln -sf "$_ET_DIR/exiftool" "$_ET_BIN"
                    chmod +x "$_ET_BIN"
                    rm -f /tmp/exiftool.tar.gz
                    export PATH="$HOME/.local/bin:$PATH"
                    # Add to zsh profile (default on Mac) and bash
                    for _RC in "$HOME/.zshrc" "$HOME/.bash_profile"; do
                        if ! grep -q 'local/bin' "$_RC" 2>/dev/null; then
                            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$_RC"
                        fi
                    done
                    if "$_ET_BIN" -ver &>/dev/null; then
                        EXIF_VER=$("$_ET_BIN" -ver 2>/dev/null || echo "?")
                        print_ok "ExifTool $EXIF_VER installed in ~/.local/bin"
                        EXIFTOOL_INSTALLED=true
                    fi
                else
                    rm -f /tmp/exiftool.tar.gz
                    print_warn "ExifTool extraction failed."
                fi
            else
                rm -f /tmp/exiftool.tar.gz
                print_warn "ExifTool download from exiftool.org failed."
            fi
        fi
    fi

    if [ "$EXIFTOOL_INSTALLED" != true ]; then
        print_warn "ExifTool installation unsuccessful."
        echo "   Install manually using one of these methods:"
        echo "     Homebrew: brew install exiftool"
        echo "     Official site: https://exiftool.org  (download the .pkg for macOS)"
        echo ""
        echo "   ExifTool is required to read/write XMP metadata."
    fi
fi

echo ""
print_ok "Dependencies installed!"
STATUS_PACKAGES="Installed"

# ═══════════════════════════════════════════════════════════════════
# STEP 4/5: OLLAMA (OPTIONAL)
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=4
print_header "$STEP_CURRENT" "Ollama (Optional)"

echo "   Ollama is a program to run LLM models locally."
echo "   It is used to generate automatic descriptions and tags with AI."
echo ""
echo "   If you skip it now, you can install it later."
echo "   Search and classification functions work without Ollama."
echo ""

if ! ask_yes_no "Do you want to install Ollama?"; then
    echo ""
    echo "   Ollama skipped. You can install it later from:"
    echo "   https://ollama.com/download"
    STATUS_OLLAMA="Skipped"
else
    # Check if Ollama is already installed
    if command -v ollama &>/dev/null; then
        print_ok "Ollama already installed."
    else
        echo ""
        echo "   Installing Ollama..."
        echo ""
        OLLAMA_INSTALLED=false

        # Attempt 1: Homebrew
        if command -v brew &>/dev/null; then
            print_info "Attempting installation via Homebrew..."
            if brew install ollama 2>/dev/null; then
                OLLAMA_INSTALLED=true
                print_ok "Ollama installed via Homebrew!"
            else
                print_warn "Installation via Homebrew failed. Trying official script..."
            fi
        fi

        # Attempt 2: official Ollama script
        if [ "$OLLAMA_INSTALLED" = false ]; then
            print_info "Downloading official installation script..."
            if curl -fsSL https://ollama.com/install.sh | sh; then
                OLLAMA_INSTALLED=true
                print_ok "Ollama installed!"
            else
                print_warn "Ollama installation failed."
                echo "   Install manually from: https://ollama.com/download"
                STATUS_OLLAMA="Failed"
            fi
        fi
    fi

    # Model management
    if command -v ollama &>/dev/null && [ "${STATUS_OLLAMA:-}" != "Failed" ]; then
        echo ""
        echo "   Checking model $OLLAMA_MODEL..."

        OLLAMA_READY=false
        if ollama list &>/dev/null; then
            OLLAMA_READY=true
        else
            print_info "Starting Ollama server in background..."
            ollama serve &>/dev/null &
            for wait_time in 5 5 5; do
                sleep "$wait_time"
                if ollama list &>/dev/null; then
                    OLLAMA_READY=true
                    break
                fi
            done
        fi

        if [ "$OLLAMA_READY" = false ]; then
            print_warn "Ollama server unreachable after 15 seconds."
            echo "   Start it manually with: ollama serve"
            echo "   Then download the model with: ollama pull $OLLAMA_MODEL"
            STATUS_OLLAMA="Server not started"
        elif OLLAMA_MODELS=$(ollama list 2>/dev/null || true) && \
             echo "$OLLAMA_MODELS" | awk -v m="$OLLAMA_MODEL" '$1 == m { found=1 } END { exit !found }'; then
            print_ok "Model $OLLAMA_MODEL already installed."
            STATUS_OLLAMA="Already present"
        else
            echo ""
            echo "   Model $OLLAMA_MODEL is not installed."
            echo "   Download size: ~3.3 GB"
            echo ""

            if ask_yes_no "Do you want to download the model now?"; then
                echo ""
                echo "   Downloading model (5-15 minutes)..."
                echo ""
                if ollama pull "$OLLAMA_MODEL"; then
                    echo ""
                    print_ok "Ollama + model installed!"
                    STATUS_OLLAMA="Installed"
                else
                    print_warn "Model download failed."
                    echo "   You can retry with: ollama pull $OLLAMA_MODEL"
                    STATUS_OLLAMA="Model not downloaded"
                fi
            else
                echo ""
                echo "   You can download it later with:"
                echo "   ollama pull $OLLAMA_MODEL"
                STATUS_OLLAMA="Without model"
            fi
        fi
    fi
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 5/5: LAUNCHER AND DESKTOP SHORTCUT
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=5
print_header "$STEP_CURRENT" "Launcher and Desktop Shortcut"

# Make the launcher executable
if [ -f "$LAUNCHER" ]; then
    chmod +x "$LAUNCHER" || true
    xattr -c "$LAUNCHER" 2>/dev/null || true
    print_ok "Launcher made executable: $LAUNCHER"
else
    print_warn "Launcher file not found: $LAUNCHER"
    STATUS_DESKTOP="Failed"
fi

# --- .command on the Desktop (immediate double-click fallback) ---
DESKTOP="$HOME/Desktop"
COMMAND_FILE="$DESKTOP/OffGallery.command"

cat > "$COMMAND_FILE" << COMMAND_EOF
#!/usr/bin/env bash
# OffGallery Launcher — generated by the installer
bash "${LAUNCHER}"
COMMAND_EOF

chmod +x "$COMMAND_FILE"
xattr -c "$COMMAND_FILE" 2>/dev/null || true
print_ok "Desktop shortcut created: OffGallery.command"
STATUS_DESKTOP="Created"

# --- .app bundle in ~/Applications (Spotlight + Launchpad + Dock) ---
USER_APPS="$HOME/Applications"
APP_BUNDLE="$USER_APPS/OffGallery.app"
_AS_TMP="/tmp/offgallery_launcher.applescript"

mkdir -p "$USER_APPS"

# AppleScript: opens a Terminal window and runs the launcher
cat > "$_AS_TMP" << APPLESCRIPT_EOF
tell application "Terminal"
    do script "bash '${LAUNCHER}'"
    activate
end tell
APPLESCRIPT_EOF

if command -v osacompile &>/dev/null; then
    rm -rf "$APP_BUNDLE"
    if osacompile -o "$APP_BUNDLE" "$_AS_TMP" 2>/dev/null; then
        rm -f "$_AS_TMP"
        # Remove quarantine recursively on the bundle (directory)
        xattr -cr "$APP_BUNDLE" 2>/dev/null || true

        # Apply custom icon to the bundle using sips + iconutil (built-in macOS)
        # Look for the best available source in assets/
        _ICON_SRC=""
        for _IC in "$APP_ROOT/assets/icon.icns" \
                   "$APP_ROOT/assets/icon.png" \
                   "$APP_ROOT/assets/logo3.jpg" \
                   "$APP_ROOT/assets/logo3.png"; do
            [ -f "$_IC" ] && _ICON_SRC="$_IC" && break
        done

        if [ -n "$_ICON_SRC" ] && command -v sips &>/dev/null && command -v iconutil &>/dev/null; then
            _ICONSET="/tmp/OffGallery.iconset"
            _ICNS_OUT="/tmp/OffGallery.icns"
            rm -rf "$_ICONSET"
            mkdir -p "$_ICONSET"

            # Generate all sizes required by the macOS iconset format
            _ICON_OK=true
            for _SPEC in "16x16:16" "16x16@2x:32" "32x32:32" "32x32@2x:64" \
                         "128x128:128" "128x128@2x:256" \
                         "256x256:256" "256x256@2x:512" \
                         "512x512:512" "512x512@2x:1024"; do
                _NAME="${_SPEC%%:*}"
                _PX="${_SPEC##*:}"
                sips -z "$_PX" "$_PX" "$_ICON_SRC" \
                    --out "$_ICONSET/icon_${_NAME}.png" &>/dev/null || { _ICON_OK=false; break; }
            done

            if [ "$_ICON_OK" = true ] && iconutil -c icns "$_ICONSET" -o "$_ICNS_OUT" 2>/dev/null; then
                # Copy the ICNS into the bundle Resources folder
                cp "$_ICNS_OUT" "$APP_BUNDLE/Contents/Resources/OffGallery.icns"
                # Register the icon name in Info.plist
                defaults write "$APP_BUNDLE/Contents/Info" CFBundleIconFile "OffGallery" 2>/dev/null || true
                # Update timestamp to force Finder to reload the icon
                touch "$APP_BUNDLE"
                print_ok "Icon applied to the .app bundle"
            else
                print_warn "Icon conversion failed — bundle uses the default icon."
            fi
            rm -rf "$_ICONSET" "$_ICNS_OUT" 2>/dev/null || true
        fi

        print_ok "App created: $APP_BUNDLE"
        print_info "Searchable via Spotlight (Cmd+Space → OffGallery) and in Launchpad"
        STATUS_DESKTOP="Created (.command + .app)"
    else
        rm -f "$_AS_TMP"
        print_warn "App creation failed. The .command shortcut on the Desktop is still available."
    fi
else
    rm -f "$_AS_TMP" 2>/dev/null || true
    print_warn "osacompile not found — .app not created."
    print_info "Install Xcode Command Line Tools to enable app creation: xcode-select --install"
fi

# Create working folders required by the app
mkdir -p "$APP_ROOT/database" "$APP_ROOT/INPUT" "$APP_ROOT/logs"

# ═══════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo -e "${BOLD}              INSTALLATION COMPLETE${NC}"
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo "   Summary:"
echo ""
echo "     Miniconda:           $STATUS_MINICONDA"
echo "     Python Environment:  $STATUS_ENV"
echo "     Libraries + ExifTool:$STATUS_PACKAGES"
echo "     Ollama:              $STATUS_OLLAMA"
echo "     Desktop:             $STATUS_DESKTOP"
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   IMPORTANT - FIRST LAUNCH:"
echo ""
echo "   On the first launch, OffGallery will automatically download"
echo "   approximately 7 GB of AI models. This is normal and happens"
echo "   only once:"
echo ""
echo "     - CLIP (semantic search):              ~580 MB"
echo "     - DINOv2 (visual similarity):          ~330 MB"
echo "     - Aesthetic (aesthetic evaluation):    ~1.6 GB"
echo "     - BioCLIP + TreeOfLife (nature):       ~4.2 GB"
echo "     - Argos Translate (translation):       ~92 MB"
echo ""
echo "   After the first launch, the app will work completely OFFLINE."
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   TO LAUNCH OFFGALLERY:"
echo ""
echo "     Spotlight:   Cmd+Space → type 'OffGallery' → Enter"
echo "     Launchpad:   search for 'OffGallery' among the apps"
echo "     Desktop:     double-click 'OffGallery.command'"
echo "     Terminal:    bash $LAUNCHER"
echo ""

if [ "$STATUS_MINICONDA" = "Installed" ]; then
    echo "   NOTE: You have just installed Miniconda."
    echo "   Conda has already been initialized for zsh and bash."
    echo "   Reopen the terminal to use the 'conda' command."
    echo ""
fi

echo -e "${BOLD}  ================================================================${NC}"
echo ""
