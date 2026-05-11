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
    echo "  Altrimenti esegui: bash installer/install_offgallery_mac_it.sh"
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

# Verifica architettura conda su Apple Silicon: un Miniconda x86_64 sotto Rosetta 2
# causa segfault con PyQt6/Metal anche quando Python è chiamato direttamente.
_SYS_ARCH=$(uname -m)
if [ "$_SYS_ARCH" = "arm64" ]; then
    _CONDA_BASE_TMP=$("$CONDA_CMD" info --base 2>/dev/null | tr -d '[:space:]')
    _PY_BIN="$_CONDA_BASE_TMP/bin/python3"
    [ -x "$_PY_BIN" ] || _PY_BIN="$_CONDA_BASE_TMP/bin/python"
    if [ -x "$_PY_BIN" ]; then
        _PY_ARCH=$(file "$_PY_BIN" 2>/dev/null | grep -oE 'arm64|x86_64' | head -1)
        if [ "$_PY_ARCH" = "x86_64" ]; then
            echo ""
            echo "  [ERRORE] Conda x86_64 rilevato su Apple Silicon (arm64)."
            echo ""
            echo "  Il Miniconda installato gira sotto Rosetta 2 (emulazione x86_64)."
            echo "  Questo causa segfault con PyQt6/Metal su M1/M2/M3/M4."
            echo ""
            echo "  Soluzione: reinstalla Miniconda arm64 nativo."
            echo "  Esegui:"
            echo "    bash \"$SCRIPT_DIR/install_offgallery_mac_it.sh\""
            echo ""
            echo "  Il wizard di installazione fornirà le istruzioni dettagliate."
            echo ""
            exit 1
        fi
    fi
fi

# Ricava il percorso dell'ambiente conda (necessario per chiamare python direttamente).
# Su macOS, 'conda run' lancia l'app in un subprocess: il framework Cocoa/Qt richiede
# di girare nel processo principale → segfault. Chiamiamo il python dell'env direttamente.
CONDA_ENV_PATH=""

# 1. Metodo primario: conda info --base → costruisce il path direttamente (più affidabile)
_CONDA_BASE=$("$CONDA_CMD" info --base 2>/dev/null | tr -d '[:space:]')
if [ -n "$_CONDA_BASE" ] && [ -x "$_CONDA_BASE/envs/$ENV_NAME/bin/python" ]; then
    CONDA_ENV_PATH="$_CONDA_BASE/envs/$ENV_NAME"
fi

# 2. Fallback: conda info --envs con parsing per nome
if [ -z "$CONDA_ENV_PATH" ] || [ ! -x "$CONDA_ENV_PATH/bin/python" ]; then
    CONDA_ENV_PATH=$(
        "$CONDA_CMD" info --envs 2>/dev/null \
        | grep -E "^$ENV_NAME[[:space:]]" \
        | awk '{print $NF}'
    )
fi

# 3. Fallback filesystem: cerca nei percorsi standard
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
    # Attiva correttamente l'env conda: setta CONDA_PREFIX, PATH e tutti gli
    # activation hook dei pacchetti (es. Qt6, torch) tramite lo script ufficiale.
    export CONDA_PREFIX="$CONDA_ENV_PATH"
    export PATH="$CONDA_ENV_PATH/bin:$PATH"
    if [ -f "$_CONDA_BASE/etc/profile.d/conda.sh" ]; then
        # shellcheck disable=SC1091
        source "$_CONDA_BASE/etc/profile.d/conda.sh"
        conda activate "$ENV_NAME" 2>/dev/null
    fi

    # Scarica i modelli AI PRIMA di avviare Qt se non sono già presenti.
    # Su macOS, il download dentro il processo Qt causa segfault per conflitti
    # tra le librerie native (torch/transformers) e il framework Cocoa/Metal.
    MODELS_DIR="$OFFGALLERY_PATH/Models"
    if [ ! -f "$MODELS_DIR/clip/config.json" ] || [ ! -f "$MODELS_DIR/dinov2/config.json" ]; then
        echo ""
        echo "  Primo avvio: download modelli AI in corso..."
        echo "  (operazione unica, richiede connessione internet)"
        echo ""
        "$CONDA_ENV_PATH/bin/python" gui_launcher.py --download-models
        if [ $? -ne 0 ]; then
            echo ""
            echo "  [ERRORE] Download modelli fallito. Verifica la connessione e riprova."
            echo ""
            exit 1
        fi
        echo ""
        echo "  Download completato. Avvio OffGallery..."
        echo ""
    fi

    # 'exec' sostituisce il processo bash con python invece di crearne un figlio.
    # Su macOS, Cocoa/Metal richiede che l'app Qt sia il processo originale
    # (non un subprocess): anche un singolo livello bash→python può causare
    # SIGSEGV al primo rendering su macOS Ventura/Sonoma/Sequoia con Apple Silicon.
    exec "$CONDA_ENV_PATH/bin/python" gui_launcher.py

else
    # Se arriviamo qui, l'ambiente OffGallery non è stato trovato: mostrare diagnostica.
    echo ""
    echo "  [ERRORE] Ambiente Python 'OffGallery' non trovato."
    echo ""
    echo "  Diagnosi:"
    echo "    Base conda: ${_CONDA_BASE:-non rilevata}"
    echo "    Ambienti disponibili:"
    "$CONDA_CMD" env list 2>/dev/null | sed 's/^/      /' || echo "      (nessuno)"
    echo ""
    echo "  Soluzione: esegui il wizard di installazione:"
    echo "    bash \"$OFFGALLERY_PATH/installer/install_offgallery_mac_it.sh\""
    echo ""
    exit 1
fi
