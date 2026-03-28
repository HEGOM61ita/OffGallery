#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# OffGallery - Installation Wizard for Linux
# Run with: bash install_offgallery_linux_en.sh
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# === COLORS ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # Reset

# === GLOBAL VARIABLES ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements_offgallery.txt"
LAUNCHER="$SCRIPT_DIR/offgallery_launcher_linux.sh"
ENV_NAME="OffGallery"
PYTHON_VER="3.12"
# Detect architecture for correct Miniconda URL (x86_64 or aarch64/ARM)
_ARCH=$(uname -m)
case "$_ARCH" in
    aarch64|arm64) _MINICONDA_ARCH="Linux-aarch64" ;;
    *)             _MINICONDA_ARCH="Linux-x86_64"   ;;
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

# Conda command (determined in step 1)
CONDA_CMD=""
# Flag: skip environment creation if already present and user does not want to recreate it
SKIP_ENV_CREATE=false

# === UTILITIES ===
print_header() {
    echo ""
    echo -e "${BOLD}  ================================================================${NC}"
    echo -e "${BOLD}    STEP $1/$STEP_TOTAL: $2${NC}"
    echo -e "${BOLD}  ================================================================${NC}"
    echo ""
}

print_ok() {
    echo -e "  ${GREEN}[OK]${NC} $1"
}

print_err() {
    echo -e "  ${RED}[ERROR]${NC} $1"
}

print_warn() {
    echo -e "  ${YELLOW}[!!]${NC} $1"
}

print_info() {
    echo -e "  ${CYAN}[INFO]${NC} $1"
}

ask_yes_no() {
    local prompt="$1"
    local answer
    read -rp "  $prompt (y/n): " answer
    [[ "${answer,,}" == "s" || "${answer,,}" == "si" || "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

# Check conda environment via filesystem (more reliable than 'conda env list')
# 'conda env list' can fail on Anaconda profiles with unaccepted ToS.
env_python_exists() {
    local conda_base
    conda_base=$("$CONDA_CMD" info --base 2>/dev/null | tr -d '\r')
    [ -n "$conda_base" ] && [ -x "$conda_base/envs/$ENV_NAME/bin/python" ]
}

# Package manager detection
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    elif command -v zypper &>/dev/null; then
        echo "zypper"
    else
        echo "unknown"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════
clear 2>/dev/null || true
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo -e "${BOLD}             OffGallery - Guided Installation (Linux)${NC}"
echo ""
echo -e "    Automatic photo cataloguing with AI - 100% Offline"
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo "   This wizard will install all required components."
echo "   Estimated time: 20-40 minutes (depends on connection speed)."
echo ""
echo "   Components:"
echo "     [1] Miniconda (Python environment manager)"
echo "     [2] OffGallery Python Environment"
echo "     [3] Python Libraries + ExifTool"
echo "     [4] Ollama + LLM Vision model (optional)"
echo "     [5] Launcher and Desktop Entry"
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   SYSTEM REQUIREMENTS:"
echo "     Operating System:   Linux 64-bit (Ubuntu, Fedora, Arch...)"
echo "     RAM:                8 GB minimum, 16 GB recommended"
echo "     Disk Space:         15-25 GB free"
echo "     GPU (optional):     NVIDIA with 4+ GB VRAM"
echo "     Internet:           Required for installation"
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

# --- Scenario B: Miniconda in home directory (installed by this script) ---
elif [ -x "$MINICONDA_DIR/bin/conda" ]; then
    print_ok "Miniconda found at $MINICONDA_DIR"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$MINICONDA_DIR/bin/conda"

# --- Scenario C: Anaconda/Miniconda/Miniforge at standard paths ---
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
    print_ok "Anaconda found at $HOME/anaconda3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$HOME/anaconda3/bin/conda"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
    print_ok "Miniforge found at $HOME/miniforge3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$HOME/miniforge3/bin/conda"
elif [ -x "$HOME/mambaforge/bin/conda" ]; then
    print_ok "Mambaforge found at $HOME/mambaforge"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="$HOME/mambaforge/bin/conda"
elif [ -x "/opt/conda/bin/conda" ]; then
    print_ok "Conda found at /opt/conda (system installation)"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="/opt/conda/bin/conda"
elif [ -x "/opt/miniconda3/bin/conda" ]; then
    print_ok "Miniconda found at /opt/miniconda3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="/opt/miniconda3/bin/conda"
elif [ -x "/opt/anaconda3/bin/conda" ]; then
    print_ok "Anaconda found at /opt/anaconda3"
    STATUS_MINICONDA="Already present"
    CONDA_CMD="/opt/anaconda3/bin/conda"

# --- Scenario D: Installation required ---
else
    echo "   Miniconda not found. Installing..."
    echo ""
    echo "   Downloading Miniconda (~120 MB)..."
    echo ""

    # If a partial/corrupted installation exists, ask whether to remove it
    if [ -d "$MINICONDA_DIR" ]; then
        print_warn "The folder $MINICONDA_DIR already exists but conda is not working."
        echo "   It may be a previous incomplete installation."
        echo ""
        if ask_yes_no "Do you want to remove it and reinstall Miniconda?"; then
            rm -rf "$MINICONDA_DIR"
            echo "   Folder removed."
        else
            print_err "Cannot proceed with the existing folder."
            echo "   Remove it manually: rm -rf $MINICONDA_DIR"
            echo "   then re-run this wizard."
            exit 1
        fi
    fi

    if ! curl -fSL "$MINICONDA_URL" -o "$MINICONDA_INSTALLER"; then
        print_err "Miniconda download failed."
        echo "   Check your internet connection and try again."
        echo ""
        echo "   Alternatively, download manually from:"
        echo "   https://docs.anaconda.com/miniconda/install/"
        echo "   then re-run this wizard."
        exit 1
    fi

    # Check file size (at least 50 MB)
    FILE_SIZE=$(stat -c%s "$MINICONDA_INSTALLER" 2>/dev/null || stat -f%z "$MINICONDA_INSTALLER" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -lt 50000000 ]; then
        print_err "Downloaded file is too small ($FILE_SIZE bytes). Download is probably corrupted."
        rm -f "$MINICONDA_INSTALLER"
        exit 1
    fi

    print_ok "Download complete."
    echo ""
    echo "   Installing Miniconda to $MINICONDA_DIR..."
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
        echo "   Try removing the folder and re-run:"
        echo "     rm -rf $MINICONDA_DIR"
        echo "     bash installer/install_offgallery_linux_en.sh"
        rm -f "$MINICONDA_INSTALLER"
        exit 1
    fi

    # Cleanup installer
    rm -f "$MINICONDA_INSTALLER"

    # Post-installation check
    if [ ! -x "$MINICONDA_DIR/bin/conda" ]; then
        print_err "Installation completed but conda not found."
        echo "   Expected path: $MINICONDA_DIR/bin/conda"
        exit 1
    fi

    # Initialise conda for the current shell
    eval "$("$MINICONDA_DIR/bin/conda" shell.bash hook)" 2>/dev/null || true

    print_ok "Miniconda installed successfully!"
    echo ""
    print_info "To make conda available in future terminals, run:"
    echo "        $MINICONDA_DIR/bin/conda init bash"
    STATUS_MINICONDA="Installed"
    CONDA_CMD="$MINICONDA_DIR/bin/conda"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 2/5: OFFGALLERY ENVIRONMENT
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=2
print_header "$STEP_CURRENT" "Python Environment"

# Check whether the environment already exists via filesystem (more reliable than 'conda env list')
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
    # --override-channels -c conda-forge: avoids Anaconda channels that require
    # ToS acceptance — conda-forge is public and unrestricted.
    if ! "$CONDA_CMD" create -n "$ENV_NAME" python="$PYTHON_VER" -y \
            --override-channels \
            --channel conda-forge; then
        print_err "Environment creation failed."
        echo "   Possible causes:"
        echo "     - Insufficient disk space"
        echo "     - Missing permissions"
        echo "     - Network issues during Python download"
        exit 1
    fi

    # Check via filesystem (not 'conda env list' which can fail with ToS errors)
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

# Check requirements file
if [ ! -f "$REQUIREMENTS" ]; then
    print_err "Requirements file not found:"
    echo "   $REQUIREMENTS"
    echo "   Make sure the installer folder is complete."
    exit 1
fi

echo "   Installing Python libraries (PyTorch, CLIP, BioCLIP, etc.)"
echo "   Estimated download: ~3 GB"
echo "   Estimated time: 10-20 minutes"
echo ""
echo "   Components:"
echo "     - PyTorch (GPU CUDA 11.8 / CPU)"
echo "     - Transformers (HuggingFace)"
echo "     - BioCLIP (nature classification)"
echo "     - PyQt6 (graphical interface)"
echo "     - OpenCV (image processing)"
echo "     - Argos Translate (IT-EN translation)"
echo ""
echo "   NOTE: The PyTorch download may appear to be stalled for"
echo "   several minutes. This is normal — please wait patiently."
echo ""
echo "  ----------------------------------------------------------------"
echo ""

# Install system dependencies for OpenCV and PyQt6
echo "   [1/3] System dependencies (OpenCV + Qt)..."
PKG_MGR_SYS=$(detect_pkg_manager)
case "$PKG_MGR_SYS" in
    apt)
        sudo apt-get install -y -qq \
            libgl1 libglib2.0-0 libegl1 \
            libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0 \
            libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
            libxcb-render-util0 libxcb-xfixes0 libxcb-shape0 libxcb-util1 \
            libxcb-xkb1 || true
        ;;
    dnf)
        sudo dnf install -y -q mesa-libGL glib2 libxcb xcb-util-cursor mesa-libEGL || true
        ;;
    pacman)
        sudo pacman -S --noconfirm mesa glib2 libxcb xcb-util-cursor || true
        ;;
    zypper)
        sudo zypper install -y libGL1 glib2 libxcb-xinerama0 libxcb-cursor0 || true
        ;;
esac

# Update pip
echo "   [2/3] Updating pip..."
"$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python -m pip install --upgrade pip -q 2>/dev/null || true

# Install requirements
echo "   [3/3] Installing Python dependencies..."
echo ""

if ! "$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" pip install -r "$REQUIREMENTS"; then
    print_err "Dependency installation failed."
    echo ""
    echo "   Possible causes:"
    echo "     - Unstable internet connection"
    echo "     - Insufficient disk space (~6 GB required)"
    echo ""
    echo "   Tip: re-run this wizard. Packages"
    echo "   already downloaded will not be re-downloaded."
    exit 1
fi

# Verify critical packages
echo ""
echo "   Verifying package installation..."
INSTALL_OK=true

check_pkg() {
    local import_expr="$1"
    local label="$2"
    if "$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python -c "$import_expr" 2>/dev/null; then
        : # message already printed by the expression
    else
        print_err "$label not found"
        INSTALL_OK=false
    fi
}

check_pkg "import torch; cuda='YES' if torch.cuda.is_available() else 'NO'; print(f'  [OK] PyTorch {torch.__version__} - CUDA: {cuda}')" "torch"
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
    echo "   If the error involves system libraries (libGL, libxcb, etc.):"
    case "$PKG_MGR_SYS" in
        apt)  echo "     sudo apt install libgl1 libxcb-xinerama0 libxcb-cursor0 libegl1" ;;
        dnf)  echo "     sudo dnf install mesa-libGL libxcb xcb-util-cursor mesa-libEGL" ;;
        pacman) echo "     sudo pacman -S mesa glib2 libxcb xcb-util-cursor" ;;
        *)    echo "     Install the Qt/OpenGL dependencies for your system" ;;
    esac
    echo ""
    echo "   Then re-run this wizard. Python packages already"
    echo "   downloaded will not be re-downloaded."
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
    PKG_MGR=$(detect_pkg_manager)
    EXIFTOOL_INSTALLED=false

    case "$PKG_MGR" in
        apt)
            print_info "Detected Debian/Ubuntu system (apt)"
            if sudo apt-get update -qq && sudo apt-get install -y -qq libimage-exiftool-perl; then
                EXIFTOOL_INSTALLED=true
            fi
            ;;
        dnf)
            print_info "Detected Fedora/RHEL system (dnf)"
            if sudo dnf install -y -q perl-Image-ExifTool; then
                EXIFTOOL_INSTALLED=true
            fi
            ;;
        pacman)
            print_info "Detected Arch Linux system (pacman)"
            if sudo pacman -S --noconfirm perl-image-exiftool; then
                EXIFTOOL_INSTALLED=true
            fi
            ;;
        zypper)
            print_info "Detected openSUSE system (zypper)"
            if sudo zypper install -y exiftool; then
                EXIFTOOL_INSTALLED=true
            fi
            ;;
        *)
            print_warn "Unrecognised package manager."
            ;;
    esac

    if [ "$EXIFTOOL_INSTALLED" = true ] && command -v exiftool &>/dev/null; then
        EXIF_VER=$(exiftool -ver 2>/dev/null || echo "?")
        print_ok "ExifTool $EXIF_VER installed."
    else
        # Fallback: install ExifTool locally in ~/.local/bin without root.
        # Works on any Linux user with perl and curl available.
        print_info "Attempting local ExifTool installation (without sudo)..."
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
            if [ -z "$_ET_VER" ]; then
                print_warn "Unable to retrieve ExifTool version from exiftool.org/ver.txt"
                _ET_VER=""
            fi
            if [ -n "$_ET_VER" ] && curl -fsSL "https://exiftool.org/Image-ExifTool-${_ET_VER}.tar.gz" \
                    -o /tmp/exiftool.tar.gz; then
                if tar -xzf /tmp/exiftool.tar.gz -C "$_ET_DIR" \
                        --strip-components=1; then
                    ln -sf "$_ET_DIR/exiftool" "$_ET_BIN"
                    chmod +x "$_ET_BIN"
                    rm -f /tmp/exiftool.tar.gz
                    # Add ~/.local/bin to PATH for the current session
                    export PATH="$HOME/.local/bin:$PATH"
                    # Make permanent in ~/.bashrc if not already present
                    if ! grep -q 'local/bin' "$HOME/.bashrc" 2>/dev/null; then
                        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
                    fi
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

        if [ "$EXIFTOOL_INSTALLED" != true ]; then
            print_warn "ExifTool installation unsuccessful."
            echo "   Install manually (requires sudo):"
            echo "     Ubuntu/Debian: sudo apt install libimage-exiftool-perl"
            echo "     Fedora:        sudo dnf install perl-Image-ExifTool"
            echo "     Arch:          sudo pacman -S perl-image-exiftool"
            echo ""
            echo "   ExifTool is required to read/write XMP metadata."
        fi
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

echo "   Ollama is a program for running LLM models locally."
echo "   It is used to generate automatic descriptions and tags with AI."
echo ""
echo "   If you skip it now, you can install it later."
echo "   Search and classification features work without Ollama."
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

        if curl -fsSL https://ollama.com/install.sh | sh; then
            print_ok "Ollama installed!"
        else
            print_warn "Ollama installation failed."
            echo "   You can install it manually from: https://ollama.com/download"
            STATUS_OLLAMA="Failed"
        fi
    fi

    # If Ollama is available, manage the model
    if command -v ollama &>/dev/null && [ "${STATUS_OLLAMA}" != "Failed" ]; then
        echo ""
        echo "   Checking model $OLLAMA_MODEL..."

        # In environments without systemd (WSL2, containers) the server does not start automatically.
        # First check if it is already running; if it does not respond, start it in the background.
        OLLAMA_READY=false
        if ollama list &>/dev/null; then
            OLLAMA_READY=true
        else
            print_info "Starting Ollama server in the background..."
            ollama serve &>/dev/null &
            OLLAMA_SERVE_PID=$!
            for wait_time in 5 5 5; do
                sleep "$wait_time"
                if ollama list &>/dev/null; then
                    OLLAMA_READY=true
                    break
                fi
            done
        fi

        # Exact match on model name (awk column 1) to avoid partial matches
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
                    echo "   You can try again with: ollama pull $OLLAMA_MODEL"
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
# STEP 5/5: LAUNCHER AND DESKTOP ENTRY
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=5
print_header "$STEP_CURRENT" "Launcher and Desktop Entry"

# --- Make the launcher executable ---
if [ -f "$LAUNCHER" ]; then
    # || true: chmod can fail on NTFS filesystems (WSL with /mnt/d, /mnt/c, etc.)
    chmod +x "$LAUNCHER" || true
    print_ok "Launcher made executable: $LAUNCHER"
else
    print_warn "Launcher file not found: $LAUNCHER"
    STATUS_DESKTOP="Failed"
fi

# --- Create .desktop entry ---
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/offgallery.desktop"

mkdir -p "$DESKTOP_DIR"

# Look for an icon (if available)
ICON_PATH=""
if [ -f "$APP_ROOT/assets/icon.png" ]; then
    ICON_PATH="$APP_ROOT/assets/icon.png"
elif [ -f "$APP_ROOT/assets/icon.ico" ]; then
    ICON_PATH="$APP_ROOT/assets/icon.ico"
fi

cat > "$DESKTOP_FILE" << DESKTOP_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=OffGallery
Comment=Automatic photo cataloguing with AI - 100% Offline
Exec=bash "$LAUNCHER"
Path=$APP_ROOT
Terminal=false
Categories=Graphics;Photography;
StartupNotify=true
DESKTOP_EOF

# Add icon only if found
if [ -n "$ICON_PATH" ]; then
    echo "Icon=$ICON_PATH" >> "$DESKTOP_FILE"
fi

# Make the .desktop file executable
chmod +x "$DESKTOP_FILE"

# Update desktop database
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

print_ok "Desktop entry created: $DESKTOP_FILE"
echo "   OffGallery will appear in the applications menu."
STATUS_DESKTOP="Created"

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
echo "     Miniconda:              $STATUS_MINICONDA"
echo "     Python Environment:     $STATUS_ENV"
echo "     Libraries + ExifTool:   $STATUS_PACKAGES"
echo "     Ollama:                 $STATUS_OLLAMA"
echo "     Desktop Entry:          $STATUS_DESKTOP"
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   IMPORTANT - FIRST LAUNCH:"
echo ""
echo "   On first launch, OffGallery will automatically download"
echo "   approximately 7 GB of AI models. This is normal and happens"
echo "   only once:"
echo ""
echo "     - CLIP (semantic search):              ~580 MB"
echo "     - DINOv2 (visual similarity):          ~330 MB"
echo "     - Aesthetic (aesthetic scoring):        ~1.6 GB"
echo "     - BioCLIP + TreeOfLife (nature):        ~4.2 GB"
echo "     - Argos Translate (translation):        ~92 MB"
echo ""
echo "   After the first launch, the app will work completely OFFLINE."
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   TO LAUNCH OFFGALLERY:"
echo ""
echo "     From the applications menu: search for \"OffGallery\""
echo "     From terminal: bash $LAUNCHER"
echo ""

if [ "$STATUS_MINICONDA" = "Installed" ]; then
    echo "   NOTE: You have just installed Miniconda."
    echo "   To use conda in future terminals, run:"
    echo "     $MINICONDA_DIR/bin/conda init bash"
    echo "   and reopen the terminal."
    echo ""
fi

echo -e "${BOLD}  ================================================================${NC}"
echo ""
