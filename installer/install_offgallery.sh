#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# OffGallery - Wizard di Installazione per Linux
# Esegui con: bash install_offgallery.sh
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# === COLORI ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # Reset

# === VARIABILI GLOBALI ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements_offgallery.txt"
LAUNCHER="$SCRIPT_DIR/offgallery_launcher.sh"
ENV_NAME="OffGallery"
PYTHON_VER="3.12"
MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
MINICONDA_INSTALLER="/tmp/miniconda_installer.sh"
MINICONDA_DIR="$HOME/miniconda3"
OLLAMA_MODEL="qwen3-vl:4b-instruct"
STEP_TOTAL=5

# Flag di stato per riepilogo
STATUS_MINICONDA="-"
STATUS_ENV="-"
STATUS_PACKAGES="-"
STATUS_OLLAMA="-"
STATUS_DESKTOP="-"

# Comando conda (determinato nello step 1)
CONDA_CMD=""

# === UTILITY ===
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
    echo -e "  ${RED}[ERRORE]${NC} $1"
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
    read -rp "  $prompt (s/n): " answer
    [[ "${answer,,}" == "s" || "${answer,,}" == "si" || "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

# Detection gestore pacchetti
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
echo -e "${BOLD}             OffGallery - Installazione Guidata (Linux)${NC}"
echo ""
echo -e "    Catalogazione automatica foto con AI - 100% Offline"
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo "   Questo wizard installerà tutti i componenti necessari."
echo "   Tempo stimato: 20-40 minuti (dipende dalla connessione)."
echo ""
echo "   Componenti:"
echo "     [1] Miniconda (gestore ambienti Python)"
echo "     [2] Ambiente Python OffGallery"
echo "     [3] Librerie Python + ExifTool"
echo "     [4] Ollama + modello LLM Vision (opzionale)"
echo "     [5] Launcher e Desktop Entry"
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   REQUISITI DI SISTEMA:"
echo "     Sistema Operativo:  Linux 64-bit (Ubuntu, Fedora, Arch...)"
echo "     RAM:                8 GB minimo, 16 GB consigliato"
echo "     Spazio Disco:       15-25 GB liberi"
echo "     GPU (opzionale):    NVIDIA con 4+ GB VRAM"
echo "     Internet:           Necessaria per l'installazione"
echo ""
echo "  ----------------------------------------------------------------"
echo ""

if ! ask_yes_no "Vuoi procedere con l'installazione?"; then
    echo ""
    echo "   Installazione annullata."
    echo ""
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 1/5: MINICONDA
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=1
print_header "$STEP_CURRENT" "Miniconda"

# --- Scenario A: conda nel PATH ---
if command -v conda &>/dev/null; then
    CONDA_VERSION=$(conda --version 2>/dev/null || echo "versione sconosciuta")
    print_ok "$CONDA_VERSION trovato nel sistema."
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="conda"

# --- Scenario B: Miniconda installato ma non nel PATH ---
elif [ -x "$MINICONDA_DIR/bin/conda" ]; then
    print_ok "Miniconda trovato in $MINICONDA_DIR"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="$MINICONDA_DIR/bin/conda"

# --- Scenario C: Anaconda ---
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
    print_ok "Anaconda trovato in $HOME/anaconda3"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="$HOME/anaconda3/bin/conda"

# --- Scenario D: Installazione necessaria ---
else
    echo "   Miniconda non trovato. Installazione in corso..."
    echo ""
    echo "   Download Miniconda (~120 MB)..."
    echo ""

    # Se esiste una installazione parziale/corrotta, chiedi se rimuoverla
    if [ -d "$MINICONDA_DIR" ]; then
        print_warn "La cartella $MINICONDA_DIR esiste già ma conda non funziona."
        echo "   Potrebbe essere un'installazione precedente incompleta."
        echo ""
        if ask_yes_no "Vuoi rimuoverla e reinstallare Miniconda?"; then
            rm -rf "$MINICONDA_DIR"
            echo "   Cartella rimossa."
        else
            print_err "Impossibile procedere con la cartella esistente."
            echo "   Rimuovila manualmente: rm -rf $MINICONDA_DIR"
            echo "   poi riesegui questo wizard."
            exit 1
        fi
    fi

    if ! curl -fSL "$MINICONDA_URL" -o "$MINICONDA_INSTALLER"; then
        print_err "Download Miniconda fallito."
        echo "   Verifica la connessione internet e riprova."
        echo ""
        echo "   In alternativa, scarica manualmente da:"
        echo "   https://docs.anaconda.com/miniconda/install/"
        echo "   poi riesegui questo wizard."
        exit 1
    fi

    # Verifica dimensione file (almeno 50MB)
    FILE_SIZE=$(stat -c%s "$MINICONDA_INSTALLER" 2>/dev/null || stat -f%z "$MINICONDA_INSTALLER" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -lt 50000000 ]; then
        print_err "File scaricato troppo piccolo ($FILE_SIZE bytes). Download probabilmente corrotto."
        rm -f "$MINICONDA_INSTALLER"
        exit 1
    fi

    print_ok "Download completato."
    echo ""
    echo "   Installazione Miniconda in $MINICONDA_DIR..."
    echo "   (Può richiedere 2-5 minuti)"
    echo ""

    if ! bash "$MINICONDA_INSTALLER" -b -p "$MINICONDA_DIR"; then
        print_err "Installazione Miniconda fallita."
        echo ""
        echo "   Possibili cause:"
        echo "     - Spazio disco insufficiente"
        echo "     - Permessi mancanti sulla cartella home"
        echo "     - Installazione precedente corrotta"
        echo ""
        echo "   Prova a rimuovere la cartella e riesegui:"
        echo "     rm -rf $MINICONDA_DIR"
        echo "     bash installer/install_offgallery.sh"
        rm -f "$MINICONDA_INSTALLER"
        exit 1
    fi

    # Pulizia installer
    rm -f "$MINICONDA_INSTALLER"

    # Verifica post-installazione
    if [ ! -x "$MINICONDA_DIR/bin/conda" ]; then
        print_err "Installazione completata ma conda non trovato."
        echo "   Percorso atteso: $MINICONDA_DIR/bin/conda"
        exit 1
    fi

    # Inizializza conda per la shell corrente
    eval "$("$MINICONDA_DIR/bin/conda" shell.bash hook)" 2>/dev/null || true

    print_ok "Miniconda installato con successo!"
    echo ""
    print_info "Per rendere conda disponibile nei prossimi terminali, esegui:"
    echo "        $MINICONDA_DIR/bin/conda init bash"
    STATUS_MINICONDA="Installato"
    CONDA_CMD="$MINICONDA_DIR/bin/conda"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 2/5: AMBIENTE OFFGALLERY
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=2
print_header "$STEP_CURRENT" "Ambiente Python"

# Verifica se l'ambiente esiste già
ENV_LIST=$("$CONDA_CMD" env list 2>/dev/null || true)
if echo "$ENV_LIST" | grep -q "$ENV_NAME"; then
    print_ok "Ambiente \"$ENV_NAME\" già presente."
    echo ""
    if ask_yes_no "Vuoi eliminarlo e ricrearlo da zero?"; then
        echo ""
        echo "   Rimozione ambiente esistente..."
        "$CONDA_CMD" env remove -n "$ENV_NAME" -y 2>&1 || {
            print_err "Impossibile rimuovere l'ambiente."
            echo "   Prova manualmente: conda env remove -n $ENV_NAME -y"
            exit 1
        }
        echo "   Ambiente rimosso. Ricreazione in corso..."
        echo ""
    else
        STATUS_ENV="Già presente"
        # Salta alla sezione pacchetti
        SKIP_ENV_CREATE=true
    fi
fi

if [ "${SKIP_ENV_CREATE:-false}" != "true" ]; then
    echo "   Accettazione Terms of Service Anaconda..."
    "$CONDA_CMD" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1 || true
    "$CONDA_CMD" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1 || true
    print_ok "Terms of Service accettati"
    echo ""

    echo "   Creazione ambiente \"$ENV_NAME\" con Python $PYTHON_VER..."
    echo "   (1-3 minuti)"
    echo ""

    if ! "$CONDA_CMD" create -n "$ENV_NAME" python="$PYTHON_VER" -y; then
        print_err "Creazione ambiente fallita."
        echo "   Possibili cause:"
        echo "     - Spazio disco insufficiente"
        echo "     - Permessi mancanti"
        echo "     - Problemi di rete durante il download di Python"
        exit 1
    fi

    # Verifica concreta
    ENV_CHECK=$("$CONDA_CMD" env list 2>/dev/null || true)
    if ! echo "$ENV_CHECK" | grep -q "$ENV_NAME"; then
        print_err "Creazione ambiente fallita (verifica post-creazione)."
        exit 1
    fi

    echo ""
    print_ok "Ambiente \"$ENV_NAME\" creato!"
    STATUS_ENV="Creato"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 3/5: DIPENDENZE PYTHON + EXIFTOOL
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=3
print_header "$STEP_CURRENT" "Dipendenze Python + ExifTool"

# Verifica file requirements
if [ ! -f "$REQUIREMENTS" ]; then
    print_err "File requirements non trovato:"
    echo "   $REQUIREMENTS"
    echo "   Assicurati che la cartella installer sia completa."
    exit 1
fi

echo "   Installazione librerie Python (PyTorch, CLIP, BioCLIP, etc.)"
echo "   Download stimato: ~3 GB"
echo "   Tempo stimato: 10-20 minuti"
echo ""
echo "   Componenti:"
echo "     - PyTorch (GPU CUDA 11.8 / CPU)"
echo "     - Transformers (HuggingFace)"
echo "     - BioCLIP (classificazione natura)"
echo "     - PyQt6 (interfaccia grafica)"
echo "     - OpenCV (elaborazione immagini)"
echo "     - Argos Translate (traduzione IT-EN)"
echo ""
echo "   NOTA: Il download di PyTorch può sembrare bloccato per"
echo "   diversi minuti. È normale, attendere pazientemente."
echo ""
echo "  ----------------------------------------------------------------"
echo ""

# Installa dipendenze di sistema per OpenCV e PyQt6
echo "   [1/3] Dipendenze di sistema (OpenCV + Qt)..."
PKG_MGR_SYS=$(detect_pkg_manager)
case "$PKG_MGR_SYS" in
    apt)
        sudo apt-get install -y -qq libgl1 libglib2.0-0 libxcb-xinerama0 libxcb-cursor0 libegl1 || true
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

# Aggiorna pip
echo "   [2/3] Aggiornamento pip..."
"$CONDA_CMD" run -n "$ENV_NAME" --no-banner python -m pip install --upgrade pip -q 2>/dev/null || true

# Installa requirements
echo "   [3/3] Installazione dipendenze Python..."
echo ""

if ! "$CONDA_CMD" run -n "$ENV_NAME" --no-banner pip install -r "$REQUIREMENTS"; then
    print_err "Installazione dipendenze fallita."
    echo ""
    echo "   Possibili cause:"
    echo "     - Connessione internet instabile"
    echo "     - Spazio disco insufficiente (~6 GB necessari)"
    echo ""
    echo "   Suggerimento: riesegui questo wizard. I pacchetti"
    echo "   già scaricati non verranno riscaricati."
    exit 1
fi

# Verifica pacchetti critici
echo ""
echo "   Verifica installazione pacchetti..."
INSTALL_OK=true

check_pkg() {
    local import_expr="$1"
    local label="$2"
    if "$CONDA_CMD" run -n "$ENV_NAME" --no-banner python -c "$import_expr" 2>/dev/null; then
        : # messaggio già stampato dall'espressione
    else
        print_err "$label non trovato"
        INSTALL_OK=false
    fi
}

check_pkg "import torch; cuda='SI' if torch.cuda.is_available() else 'NO'; print(f'  [OK] PyTorch {torch.__version__} - CUDA: {cuda}')" "torch"
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
    print_err "Installazione incompleta. Uno o più pacchetti mancano."
    echo ""
    echo "   Se l'errore riguarda librerie di sistema (libGL, libxcb, etc.):"
    case "$PKG_MGR_SYS" in
        apt)  echo "     sudo apt install libgl1 libxcb-xinerama0 libxcb-cursor0 libegl1" ;;
        dnf)  echo "     sudo dnf install mesa-libGL libxcb xcb-util-cursor mesa-libEGL" ;;
        pacman) echo "     sudo pacman -S mesa glib2 libxcb xcb-util-cursor" ;;
        *)    echo "     Installa le dipendenze Qt/OpenGL del tuo sistema" ;;
    esac
    echo ""
    echo "   Poi riesegui questo wizard. I pacchetti Python già"
    echo "   scaricati non verranno riscaricati."
    exit 1
fi

# --- ExifTool ---
echo ""
echo "   Verifica ExifTool..."

if command -v exiftool &>/dev/null; then
    EXIF_VER=$(exiftool -ver 2>/dev/null || echo "?")
    print_ok "ExifTool $EXIF_VER già installato."
else
    echo "   ExifTool non trovato. Installazione..."
    PKG_MGR=$(detect_pkg_manager)
    EXIFTOOL_INSTALLED=false

    case "$PKG_MGR" in
        apt)
            print_info "Rilevato sistema Debian/Ubuntu (apt)"
            if sudo apt-get update -qq && sudo apt-get install -y -qq libimage-exiftool-perl; then
                EXIFTOOL_INSTALLED=true
            fi
            ;;
        dnf)
            print_info "Rilevato sistema Fedora/RHEL (dnf)"
            if sudo dnf install -y -q perl-Image-ExifTool; then
                EXIFTOOL_INSTALLED=true
            fi
            ;;
        pacman)
            print_info "Rilevato sistema Arch Linux (pacman)"
            if sudo pacman -S --noconfirm perl-image-exiftool; then
                EXIFTOOL_INSTALLED=true
            fi
            ;;
        zypper)
            print_info "Rilevato sistema openSUSE (zypper)"
            if sudo zypper install -y exiftool; then
                EXIFTOOL_INSTALLED=true
            fi
            ;;
        *)
            print_warn "Gestore pacchetti non riconosciuto."
            ;;
    esac

    if [ "$EXIFTOOL_INSTALLED" = true ] && command -v exiftool &>/dev/null; then
        EXIF_VER=$(exiftool -ver 2>/dev/null || echo "?")
        print_ok "ExifTool $EXIF_VER installato."
    else
        print_warn "Installazione ExifTool automatica non riuscita."
        echo "   Installa manualmente:"
        echo "     Ubuntu/Debian: sudo apt install libimage-exiftool-perl"
        echo "     Fedora:        sudo dnf install perl-Image-ExifTool"
        echo "     Arch:          sudo pacman -S perl-image-exiftool"
        echo ""
        echo "   ExifTool è necessario per leggere/scrivere metadati XMP."
    fi
fi

echo ""
print_ok "Dipendenze installate!"
STATUS_PACKAGES="Installato"

# ═══════════════════════════════════════════════════════════════════
# STEP 4/5: OLLAMA (OPZIONALE)
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=4
print_header "$STEP_CURRENT" "Ollama (Opzionale)"

echo "   Ollama è un programma per eseguire modelli LLM in locale."
echo "   Serve per generare descrizioni e tag automatici con AI."
echo ""
echo "   Se non lo installi ora, puoi farlo in seguito."
echo "   Le funzioni di ricerca e classificazione funzionano senza Ollama."
echo ""

if ! ask_yes_no "Vuoi installare Ollama?"; then
    echo ""
    echo "   Ollama saltato. Potrai installarlo in seguito da:"
    echo "   https://ollama.com/download"
    STATUS_OLLAMA="Saltato"
else
    # Verifica se Ollama è già installato
    if command -v ollama &>/dev/null; then
        print_ok "Ollama già installato."
    else
        echo ""
        echo "   Installazione Ollama..."
        echo ""

        if curl -fsSL https://ollama.com/install.sh | sh; then
            print_ok "Ollama installato!"
        else
            print_warn "Installazione Ollama fallita."
            echo "   Puoi installarlo manualmente da: https://ollama.com/download"
            STATUS_OLLAMA="Fallito"
        fi
    fi

    # Se Ollama è disponibile, gestisci il modello
    if command -v ollama &>/dev/null && [ "${STATUS_OLLAMA}" != "Fallito" ]; then
        echo ""
        echo "   Verifica modello $OLLAMA_MODEL..."

        # Attendi avvio servizio
        for wait_time in 5 3 3; do
            if ollama list &>/dev/null; then
                break
            fi
            sleep "$wait_time"
        done

        if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
            print_ok "Modello $OLLAMA_MODEL già installato."
            STATUS_OLLAMA="Già presente"
        else
            echo ""
            echo "   Il modello $OLLAMA_MODEL non è installato."
            echo "   Dimensione download: ~3.3 GB"
            echo ""

            if ask_yes_no "Vuoi scaricare il modello ora?"; then
                echo ""
                echo "   Download modello in corso (5-15 minuti)..."
                echo ""

                if ollama pull "$OLLAMA_MODEL"; then
                    echo ""
                    print_ok "Ollama + modello installati!"
                    STATUS_OLLAMA="Installato"
                else
                    print_warn "Download modello fallito."
                    echo "   Puoi riprovare con: ollama pull $OLLAMA_MODEL"
                    STATUS_OLLAMA="Modello non scaricato"
                fi
            else
                echo ""
                echo "   Puoi scaricarlo in seguito con:"
                echo "   ollama pull $OLLAMA_MODEL"
                STATUS_OLLAMA="Senza modello"
            fi
        fi
    fi
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 5/5: LAUNCHER E DESKTOP ENTRY
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=5
print_header "$STEP_CURRENT" "Launcher e Desktop Entry"

# --- Rendi eseguibile il launcher ---
if [ -f "$LAUNCHER" ]; then
    chmod +x "$LAUNCHER"
    print_ok "Launcher reso eseguibile: $LAUNCHER"
else
    print_warn "File launcher non trovato: $LAUNCHER"
    STATUS_DESKTOP="Fallito"
fi

# --- Crea .desktop entry ---
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/offgallery.desktop"

mkdir -p "$DESKTOP_DIR"

# Cerca un'icona (se disponibile)
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
Comment=Catalogazione automatica foto con AI - 100% Offline
Exec=bash "$LAUNCHER"
Path=$APP_ROOT
Terminal=false
Categories=Graphics;Photography;
StartupNotify=true
DESKTOP_EOF

# Aggiungi icona solo se trovata
if [ -n "$ICON_PATH" ]; then
    echo "Icon=$ICON_PATH" >> "$DESKTOP_FILE"
fi

# Rendi eseguibile il .desktop
chmod +x "$DESKTOP_FILE"

# Aggiorna database desktop
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

print_ok "Desktop entry creato: $DESKTOP_FILE"
echo "   OffGallery apparirà nel menu applicazioni."
STATUS_DESKTOP="Creato"

# ═══════════════════════════════════════════════════════════════════
# RIEPILOGO FINALE
# ═══════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo -e "${BOLD}              INSTALLAZIONE COMPLETATA${NC}"
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo "   Riepilogo:"
echo ""
echo "     Miniconda:          $STATUS_MINICONDA"
echo "     Ambiente Python:    $STATUS_ENV"
echo "     Librerie + ExifTool:$STATUS_PACKAGES"
echo "     Ollama:             $STATUS_OLLAMA"
echo "     Desktop Entry:      $STATUS_DESKTOP"
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   IMPORTANTE - PRIMO AVVIO:"
echo ""
echo "   Al primo avvio, OffGallery scaricherà automaticamente"
echo "   circa 7 GB di modelli AI. Questo è normale e avviene"
echo "   una sola volta:"
echo ""
echo "     - CLIP (ricerca semantica):           ~580 MB"
echo "     - DINOv2 (similarità visiva):         ~330 MB"
echo "     - Aesthetic (valutazione estetica):    ~1.6 GB"
echo "     - BioCLIP + TreeOfLife (natura):       ~4.2 GB"
echo "     - Argos Translate (traduzione):        ~92 MB"
echo ""
echo "   Dopo il primo avvio, l'app funzionerà completamente OFFLINE."
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   PER AVVIARE OFFGALLERY:"
echo ""
echo "     Dal menu applicazioni: cerca \"OffGallery\""
echo "     Da terminale: bash $LAUNCHER"
echo ""

if [ "$STATUS_MINICONDA" = "Installato" ]; then
    echo "   NOTA: Hai appena installato Miniconda."
    echo "   Per usare conda dai prossimi terminali, esegui:"
    echo "     $MINICONDA_DIR/bin/conda init bash"
    echo "   e riapri il terminale."
    echo ""
fi

echo -e "${BOLD}  ================================================================${NC}"
echo ""
