#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# OffGallery - Wizard di Installazione per macOS
# Esegui con: bash install_offgallery_mac.sh
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# === COLORI ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# === VARIABILI GLOBALI ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQUIREMENTS="$SCRIPT_DIR/requirements_offgallery.txt"
LAUNCHER="$SCRIPT_DIR/offgallery_launcher_mac.sh"
ENV_NAME="OffGallery"
PYTHON_VER="3.12"

# Rileva architettura (Intel o Apple Silicon)
_ARCH=$(uname -m)
case "$_ARCH" in
    arm64) _MINICONDA_ARCH="MacOSX-arm64"   ;;
    *)     _MINICONDA_ARCH="MacOSX-x86_64"  ;;
esac
MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-${_MINICONDA_ARCH}.sh"
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

CONDA_CMD=""
SKIP_ENV_CREATE=false

# === UTILITY ===
print_header() {
    echo ""
    echo -e "${BOLD}  ================================================================${NC}"
    echo -e "${BOLD}    STEP $1/$STEP_TOTAL: $2${NC}"
    echo -e "${BOLD}  ================================================================${NC}"
    echo ""
}

print_ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
print_err()  { echo -e "  ${RED}[ERRORE]${NC} $1"; }
print_warn() { echo -e "  ${YELLOW}[!!]${NC} $1"; }
print_info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

ask_yes_no() {
    local answer
    read -rp "  $1 (s/n): " answer
    [[ "${answer,,}" == "s" || "${answer,,}" == "si" || "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

# Verifica ambiente conda via filesystem (più affidabile di 'conda env list')
env_python_exists() {
    local conda_base
    conda_base=$("$CONDA_CMD" info --base 2>/dev/null | tr -d '\r')
    [ -n "$conda_base" ] && [ -x "$conda_base/envs/$ENV_NAME/bin/python" ]
}

# ═══════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════
clear 2>/dev/null || true
echo ""
echo -e "${BOLD}  ================================================================${NC}"
echo ""
echo -e "${BOLD}             OffGallery - Installazione Guidata (macOS)${NC}"
echo ""
echo "    Catalogazione automatica foto con AI - 100% Offline"
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
echo "     [5] Launcher sul Desktop"
echo ""
echo "  ----------------------------------------------------------------"
echo ""
echo "   REQUISITI DI SISTEMA:"
echo "     Sistema Operativo:  macOS 12 Monterey o successivo"
echo "     Architettura:       Intel x86_64 o Apple Silicon (M1/M2/M3/M4)"
echo "     RAM:                8 GB minimo, 16 GB consigliato"
echo "     Spazio Disco:       15-25 GB liberi"
echo "     GPU:                Apple Silicon usa Metal/MPS (incluso)"
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

# --- Scenario B: percorsi standard macOS ---
elif [ -x "$HOME/miniconda3/bin/conda" ]; then
    print_ok "Miniconda trovato in $HOME/miniconda3"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="$HOME/miniconda3/bin/conda"
elif [ -x "$HOME/opt/miniconda3/bin/conda" ]; then
    print_ok "Miniconda trovato in $HOME/opt/miniconda3"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="$HOME/opt/miniconda3/bin/conda"
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
    print_ok "Anaconda trovato in $HOME/anaconda3"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="$HOME/anaconda3/bin/conda"
elif [ -x "$HOME/miniforge3/bin/conda" ]; then
    print_ok "Miniforge trovato in $HOME/miniforge3"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="$HOME/miniforge3/bin/conda"
elif [ -x "$HOME/mambaforge/bin/conda" ]; then
    print_ok "Mambaforge trovato in $HOME/mambaforge"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="$HOME/mambaforge/bin/conda"
# Homebrew cask (Intel e Apple Silicon)
elif [ -x "/opt/homebrew/Caskroom/miniconda/base/bin/conda" ]; then
    print_ok "Miniconda (Homebrew cask) trovato in /opt/homebrew/Caskroom/miniconda/base"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="/opt/homebrew/Caskroom/miniconda/base/bin/conda"
elif [ -x "/usr/local/Caskroom/miniconda/base/bin/conda" ]; then
    print_ok "Miniconda (Homebrew cask Intel) trovato in /usr/local/Caskroom/miniconda/base"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="/usr/local/Caskroom/miniconda/base/bin/conda"
elif [ -x "/opt/miniconda3/bin/conda" ]; then
    print_ok "Miniconda trovato in /opt/miniconda3"
    STATUS_MINICONDA="Già presente"
    CONDA_CMD="/opt/miniconda3/bin/conda"

# --- Scenario C: installazione necessaria ---
else
    echo "   Miniconda non trovato. Installazione in corso..."
    echo ""

    # Mostra architettura rilevata
    if [ "$_ARCH" = "arm64" ]; then
        print_info "Architettura: Apple Silicon (arm64)"
    else
        print_info "Architettura: Intel x86_64"
    fi
    echo ""
    echo "   Download Miniconda (~90 MB)..."
    echo ""

    # Rimozione eventuale installazione parziale
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

    # Verifica dimensione (almeno 50 MB)
    FILE_SIZE=$(stat -f%z "$MINICONDA_INSTALLER" 2>/dev/null || echo "0")
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
        echo "     bash installer/install_offgallery_mac.sh"
        rm -f "$MINICONDA_INSTALLER"
        exit 1
    fi

    rm -f "$MINICONDA_INSTALLER"

    if [ ! -x "$MINICONDA_DIR/bin/conda" ]; then
        print_err "Installazione completata ma conda non trovato."
        echo "   Percorso atteso: $MINICONDA_DIR/bin/conda"
        exit 1
    fi

    # Inizializza conda per la sessione corrente
    eval "$("$MINICONDA_DIR/bin/conda" shell.bash hook)" 2>/dev/null || true

    # Inizializza per bash e zsh (zsh è la shell di default su macOS dal 2019)
    "$MINICONDA_DIR/bin/conda" init bash 2>/dev/null || true
    "$MINICONDA_DIR/bin/conda" init zsh  2>/dev/null || true

    print_ok "Miniconda installato con successo!"
    echo ""
    print_info "Conda è stato inizializzato per bash e zsh."
    print_info "Per rendere conda disponibile nei prossimi terminali, riaprilo."
    STATUS_MINICONDA="Installato"
    CONDA_CMD="$MINICONDA_DIR/bin/conda"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 2/5: AMBIENTE OFFGALLERY
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=2
print_header "$STEP_CURRENT" "Ambiente Python"

if env_python_exists; then
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
        SKIP_ENV_CREATE=true
    fi
fi

if [ "$SKIP_ENV_CREATE" != "true" ]; then
    echo "   Creazione ambiente \"$ENV_NAME\" con Python $PYTHON_VER..."
    echo "   (1-3 minuti)"
    echo ""

    if ! "$CONDA_CMD" create -n "$ENV_NAME" python="$PYTHON_VER" -y \
            --override-channels \
            --channel conda-forge; then
        print_err "Creazione ambiente fallita."
        echo "   Possibili cause:"
        echo "     - Spazio disco insufficiente"
        echo "     - Permessi mancanti"
        echo "     - Problemi di rete durante il download di Python"
        exit 1
    fi

    if ! env_python_exists; then
        print_err "Creazione ambiente fallita (python non trovato dopo la creazione)."
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

if [ ! -f "$REQUIREMENTS" ]; then
    print_err "File requirements non trovato: $REQUIREMENTS"
    echo "   Assicurati che la cartella installer sia completa."
    exit 1
fi

# Mostra informazioni GPU per l'utente
if [ "$_ARCH" = "arm64" ]; then
    GPU_NOTE="Apple Silicon (M-series) — accelerazione GPU via Metal/MPS inclusa"
else
    GPU_NOTE="Intel Mac — modalità CPU (nessuna GPU NVIDIA disponibile su Mac)"
fi

echo "   Installazione librerie Python (PyTorch, CLIP, BioCLIP, etc.)"
echo "   Download stimato: ~3 GB"
echo "   Tempo stimato: 10-20 minuti"
echo ""
echo "   Componenti:"
echo "     - PyTorch ($GPU_NOTE)"
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

# Verifica Xcode Command Line Tools (necessari per compilare alcune dipendenze)
echo "   Verifica Xcode Command Line Tools..."
if ! xcode-select -p &>/dev/null; then
    print_warn "Xcode Command Line Tools non trovati."
    echo "   Sono necessari per installare alcune librerie Python."
    echo ""
    echo "   Installazione in corso (potrebbe aprire una finestra di dialogo)..."
    xcode-select --install 2>/dev/null || true
    echo ""
    echo "   Se appare una finestra, clicca 'Installa' e attendi il completamento."
    echo "   Al termine, premi INVIO per continuare."
    read -r
else
    print_ok "Xcode Command Line Tools presenti."
fi
echo ""

# Aggiorna pip
echo "   [1/2] Aggiornamento pip..."
"$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python -m pip install --upgrade pip -q 2>/dev/null || true

# Installa requirements
echo "   [2/2] Installazione dipendenze Python..."
echo ""

# Su Mac, PyTorch si installa dal canale standard (include MPS per Apple Silicon)
# Nessun index-url speciale necessario come su Linux/Windows per CUDA
if ! "$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" pip install -r "$REQUIREMENTS"; then
    print_err "Installazione dipendenze fallita."
    echo ""
    echo "   Possibili cause:"
    echo "     - Connessione internet instabile"
    echo "     - Spazio disco insufficiente (~6 GB necessari)"
    echo "     - Xcode Command Line Tools mancanti (esegui: xcode-select --install)"
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
    if "$CONDA_CMD" run --no-capture-output -n "$ENV_NAME" python -c "$import_expr" 2>/dev/null; then
        : # il messaggio è già incluso nell'espressione
    else
        print_err "$label non trovato"
        INSTALL_OK=false
    fi
}

check_pkg "import torch; mps='SI' if torch.backends.mps.is_available() else 'NO'; print(f'  [OK] PyTorch {torch.__version__} - MPS (Apple Silicon GPU): {mps}')" "torch"
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
    echo "   Prova a installare Xcode Command Line Tools se non lo hai fatto:"
    echo "     xcode-select --install"
    echo ""
    echo "   Poi riesegui questo wizard. I pacchetti già"
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
    EXIFTOOL_INSTALLED=false

    # Tentativo 1: Homebrew (gestore pacchetti standard su Mac)
    if command -v brew &>/dev/null; then
        print_info "Homebrew trovato — installazione ExifTool tramite brew..."
        if brew install exiftool 2>/dev/null; then
            EXIFTOOL_INSTALLED=true
        else
            print_warn "Installazione ExifTool via brew fallita."
        fi
    else
        print_info "Homebrew non trovato — tentativo installazione diretta..."
    fi

    # Tentativo 2: Fallback — scarica tar.gz da exiftool.org (Perl puro, funziona su Mac)
    if [ "$EXIFTOOL_INSTALLED" = false ]; then
        if ! command -v perl &>/dev/null; then
            print_warn "perl non trovato — installazione locale ExifTool non possibile."
        elif ! command -v curl &>/dev/null; then
            print_warn "curl non trovato — installazione locale ExifTool non possibile."
        else
            _ET_DIR="$HOME/.local/share/exiftool"
            _ET_BIN="$HOME/.local/bin/exiftool"
            mkdir -p "$HOME/.local/bin" "$_ET_DIR"
            echo "   Download ExifTool da exiftool.org..."
            _ET_VER=$(curl -fsSL "https://exiftool.org/ver.txt" 2>/dev/null | tr -d '[:space:]')
            if [ -n "$_ET_VER" ] && curl -fsSL "https://exiftool.org/Image-ExifTool-${_ET_VER}.tar.gz" \
                    -o /tmp/exiftool.tar.gz; then
                if tar -xzf /tmp/exiftool.tar.gz -C "$_ET_DIR" --strip-components=1; then
                    ln -sf "$_ET_DIR/exiftool" "$_ET_BIN"
                    chmod +x "$_ET_BIN"
                    rm -f /tmp/exiftool.tar.gz
                    export PATH="$HOME/.local/bin:$PATH"
                    # Aggiungi al profilo zsh (default su Mac) e bash
                    for _RC in "$HOME/.zshrc" "$HOME/.bash_profile"; do
                        if ! grep -q 'local/bin' "$_RC" 2>/dev/null; then
                            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$_RC"
                        fi
                    done
                    if "$_ET_BIN" -ver &>/dev/null; then
                        EXIF_VER=$("$_ET_BIN" -ver 2>/dev/null || echo "?")
                        print_ok "ExifTool $EXIF_VER installato in ~/.local/bin"
                        EXIFTOOL_INSTALLED=true
                    fi
                else
                    rm -f /tmp/exiftool.tar.gz
                    print_warn "Estrazione ExifTool fallita."
                fi
            else
                rm -f /tmp/exiftool.tar.gz
                print_warn "Download ExifTool da exiftool.org fallito."
            fi
        fi
    fi

    if [ "$EXIFTOOL_INSTALLED" != true ]; then
        print_warn "Installazione ExifTool non riuscita."
        echo "   Installa manualmente con uno di questi metodi:"
        echo "     Homebrew: brew install exiftool"
        echo "     Sito ufficiale: https://exiftool.org  (scarica il .pkg per macOS)"
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
        OLLAMA_INSTALLED=false

        # Tentativo 1: Homebrew
        if command -v brew &>/dev/null; then
            print_info "Tentativo installazione via Homebrew..."
            if brew install ollama 2>/dev/null; then
                OLLAMA_INSTALLED=true
                print_ok "Ollama installato via Homebrew!"
            else
                print_warn "Installazione via Homebrew fallita. Provo con script ufficiale..."
            fi
        fi

        # Tentativo 2: script ufficiale Ollama
        if [ "$OLLAMA_INSTALLED" = false ]; then
            print_info "Download script di installazione ufficiale..."
            if curl -fsSL https://ollama.com/install.sh | sh; then
                OLLAMA_INSTALLED=true
                print_ok "Ollama installato!"
            else
                print_warn "Installazione Ollama fallita."
                echo "   Installa manualmente da: https://ollama.com/download"
                STATUS_OLLAMA="Fallito"
            fi
        fi
    fi

    # Gestione modello
    if command -v ollama &>/dev/null && [ "${STATUS_OLLAMA:-}" != "Fallito" ]; then
        echo ""
        echo "   Verifica modello $OLLAMA_MODEL..."

        OLLAMA_READY=false
        if ollama list &>/dev/null; then
            OLLAMA_READY=true
        else
            print_info "Avvio server Ollama in background..."
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
            print_warn "Server Ollama non raggiungibile dopo 15 secondi."
            echo "   Avvialo manualmente con: ollama serve"
            echo "   Poi scarica il modello con: ollama pull $OLLAMA_MODEL"
            STATUS_OLLAMA="Server non avviato"
        elif OLLAMA_MODELS=$(ollama list 2>/dev/null || true) && \
             echo "$OLLAMA_MODELS" | awk -v m="$OLLAMA_MODEL" '$1 == m { found=1 } END { exit !found }'; then
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
# STEP 5/5: LAUNCHER E COLLEGAMENTO DESKTOP
# ═══════════════════════════════════════════════════════════════════
STEP_CURRENT=5
print_header "$STEP_CURRENT" "Launcher e Collegamento Desktop"

# Rendi eseguibile il launcher
if [ -f "$LAUNCHER" ]; then
    chmod +x "$LAUNCHER" || true
    xattr -c "$LAUNCHER" 2>/dev/null || true
    print_ok "Launcher reso eseguibile: $LAUNCHER"
else
    print_warn "File launcher non trovato: $LAUNCHER"
    STATUS_DESKTOP="Fallito"
fi

# --- .command sul Desktop (fallback doppio-click immediato) ---
DESKTOP="$HOME/Desktop"
COMMAND_FILE="$DESKTOP/OffGallery.command"

cat > "$COMMAND_FILE" << COMMAND_EOF
#!/usr/bin/env bash
# OffGallery Launcher — generato dall'installer
bash "${LAUNCHER}"
COMMAND_EOF

chmod +x "$COMMAND_FILE"
xattr -c "$COMMAND_FILE" 2>/dev/null || true
print_ok "Collegamento Desktop creato: OffGallery.command"
STATUS_DESKTOP="Creato"

# --- .app bundle in ~/Applications (Spotlight + Launchpad + Dock) ---
USER_APPS="$HOME/Applications"
APP_BUNDLE="$USER_APPS/OffGallery.app"
_AS_TMP="/tmp/offgallery_launcher.applescript"

mkdir -p "$USER_APPS"

# AppleScript: apre una finestra Terminale ed esegue il launcher
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
        # Rimuovi quarantine ricorsivo sul bundle (directory)
        xattr -cr "$APP_BUNDLE" 2>/dev/null || true

        # Applica icona personalizzata al bundle usando sips + iconutil (built-in macOS)
        # Cerca la sorgente migliore disponibile in assets/
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

            # Genera tutte le dimensioni richieste dal formato iconset macOS
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
                # Copia l'ICNS nella cartella Resources del bundle
                cp "$_ICNS_OUT" "$APP_BUNDLE/Contents/Resources/OffGallery.icns"
                # Registra il nome icona in Info.plist
                defaults write "$APP_BUNDLE/Contents/Info" CFBundleIconFile "OffGallery" 2>/dev/null || true
                # Aggiorna timestamp per far ricaricare l'icona al Finder
                touch "$APP_BUNDLE"
                print_ok "Icona applicata al bundle .app"
            else
                print_warn "Conversione icona fallita — il bundle usa l'icona di default."
            fi
            rm -rf "$_ICONSET" "$_ICNS_OUT" 2>/dev/null || true
        fi

        print_ok "App creata: $APP_BUNDLE"
        print_info "Cercabile via Spotlight (Cmd+Space → OffGallery) e nel Launchpad"
        STATUS_DESKTOP="Creato (.command + .app)"
    else
        rm -f "$_AS_TMP"
        print_warn "Creazione .app fallita. Il collegamento .command sul Desktop è comunque disponibile."
    fi
else
    rm -f "$_AS_TMP" 2>/dev/null || true
    print_warn "osacompile non trovato — .app non creata."
    print_info "Installa Xcode Command Line Tools per abilitare la creazione dell'app: xcode-select --install"
fi

# Crea cartelle di lavoro necessarie all'app
mkdir -p "$APP_ROOT/database" "$APP_ROOT/INPUT" "$APP_ROOT/logs"

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
echo "     Desktop:            $STATUS_DESKTOP"
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
echo "     Spotlight:   Cmd+Space → digita 'OffGallery' → Invio"
echo "     Launchpad:   cerca 'OffGallery' tra le app"
echo "     Desktop:     doppio click su 'OffGallery.command'"
echo "     Terminale:   bash $LAUNCHER"
echo ""

if [ "$STATUS_MINICONDA" = "Installato" ]; then
    echo "   NOTA: Hai appena installato Miniconda."
    echo "   Conda è già stato inizializzato per zsh e bash."
    echo "   Riapri il terminale per usare il comando 'conda'."
    echo ""
fi

echo -e "${BOLD}  ================================================================${NC}"
echo ""
