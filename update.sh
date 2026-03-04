#!/bin/bash
# OffGallery - Aggiornamento automatico (Linux)
# Eseguire con: bash update.sh

cd "$(dirname "$0")"

ENV_NAME="OffGallery"
PYTHON_EXE=""

find_conda_python() {
    local conda_cmd
    for cmd in conda "$HOME/miniconda3/bin/conda" "$HOME/anaconda3/bin/conda" \
               "/opt/miniconda3/bin/conda" "/opt/anaconda3/bin/conda" \
               "/usr/local/bin/conda"; do
        if command -v "$cmd" &>/dev/null; then
            conda_cmd="$cmd"
            break
        fi
    done

    if [ -n "$conda_cmd" ]; then
        local base
        base=$("$conda_cmd" info --base 2>/dev/null | tr -d '[:space:]')
        if [ -n "$base" ] && [ -x "$base/envs/$ENV_NAME/bin/python" ]; then
            echo "$base/envs/$ENV_NAME/bin/python"
            return
        fi
    fi

    # Fallback: percorsi comuni Linux
    for p in \
        "$HOME/miniconda3/envs/$ENV_NAME/bin/python" \
        "$HOME/anaconda3/envs/$ENV_NAME/bin/python" \
        "/opt/miniconda3/envs/$ENV_NAME/bin/python" \
        "/opt/anaconda3/envs/$ENV_NAME/bin/python"; do
        if [ -x "$p" ]; then
            echo "$p"
            return
        fi
    done
}

PYTHON_EXE=$(find_conda_python)

if [ -z "$PYTHON_EXE" ]; then
    echo "================================================================"
    echo "  [ERRORE] Ambiente conda '$ENV_NAME' non trovato."
    echo "  Assicurati che OffGallery sia installato correttamente."
    echo "================================================================"
    read -r -p "  Premi INVIO per chiudere."
    exit 1
fi

echo "Avvio aggiornamento OffGallery..."
echo ""
"$PYTHON_EXE" "$(dirname "$0")/update.py"
