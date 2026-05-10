"""
Installazione, avvio e gestione di Ollama.
Supporta Windows, macOS e Linux.
"""

import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from typing import Optional, Callable

from utils.download import download_file, DownloadProgress, ProgressCallback

_CNW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

OLLAMA_MODEL   = "qwen3-vl:8b-instruct-q4_K_M"
OLLAMA_PORT    = 11434
OLLAMA_API     = f"http://localhost:{OLLAMA_PORT}"

# URL di download per piattaforma
_DOWNLOAD_URLS = {
    "Windows": "https://ollama.com/download/OllamaSetup.exe",
    "Darwin":  "https://ollama.com/download/Ollama-darwin.zip",
}

# Binari Linux da GitHub releases (no sudo, installati in ~/.local/bin/)
# Nota: Ollama distribuisce un binario diretto, non più un .tgz
_LINUX_URLS = {
    "x86_64":  "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64",
    "aarch64": "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-arm64",
}

# Percorsi standard dell'eseguibile ollama
_OLLAMA_PATHS = {
    "Windows": [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
    ],
    "Darwin": [
        "/usr/local/bin/ollama",
        "/opt/homebrew/bin/ollama",
        os.path.join(os.path.expanduser("~"), "Applications", "Ollama.app",
                     "Contents", "MacOS", "ollama"),
    ],
    "Linux": [
        os.path.join(os.path.expanduser("~"), ".local", "bin", "ollama"),
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
    ],
}


# ---------------------------------------------------------------------------
# Rilevamento
# ---------------------------------------------------------------------------

def find_ollama() -> Optional[str]:
    """
    Cerca l'eseguibile ollama nel sistema.
    Restituisce il percorso o None se non trovato.
    """
    found = shutil.which("ollama")
    if found:
        return found

    system = platform.system()
    for path in _OLLAMA_PATHS.get(system, []):
        if path and os.path.isfile(path):
            return path

    return None


def ollama_version(ollama_exe: str) -> Optional[str]:
    """Restituisce la versione di ollama (es. '0.6.2') o None."""
    try:
        out = subprocess.check_output(
            [ollama_exe, "--version"],
            text=True, encoding="utf-8", errors="replace",
            stderr=subprocess.STDOUT, timeout=10,
            creationflags=_CNW,
        )
        # Output: "ollama version 0.6.2"
        parts = out.strip().split()
        return parts[-1] if parts else None
    except Exception:
        return None


def is_running() -> bool:
    """True se il server Ollama risponde sull'API locale."""
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_API}/api/version", timeout=3
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def api_version() -> Optional[str]:
    """Restituisce la versione riportata dall'API Ollama o None."""
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_API}/api/version", timeout=5
        ) as resp:
            data = json.loads(resp.read())
            return data.get("version")
    except Exception:
        return None


def is_model_pulled(model: str = OLLAMA_MODEL) -> bool:
    """True se il modello è già presente nella libreria locale di Ollama."""
    try:
        req = urllib.request.Request(
            f"{OLLAMA_API}/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        models = [m.get("name", "") for m in data.get("models", [])]
        return any(model in m for m in models)
    except Exception:
        return False


def port_in_use(port: int = OLLAMA_PORT) -> bool:
    """True se la porta è già occupata da un altro processo."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


# ---------------------------------------------------------------------------
# Installazione
# ---------------------------------------------------------------------------

def install_ollama(
    progress_cb: Optional[ProgressCallback] = None,
    log_cb:      Optional[Callable]         = None,
) -> str:
    """
    Scarica e installa Ollama per la piattaforma corrente.
    Restituisce il percorso dell'eseguibile ollama.
    """
    system = platform.system()

    if system == "Linux":
        machine = platform.machine()
        url = _LINUX_URLS.get(machine)
        if not url:
            raise RuntimeError(f"Architettura Linux non supportata: {machine}")
    elif system in _DOWNLOAD_URLS:
        url = _DOWNLOAD_URLS[system]
    else:
        raise RuntimeError(f"Piattaforma non supportata per Ollama: {system}")

    _log(log_cb, f"Download Ollama da: {url}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        filename = url.split("/")[-1]
        dest     = os.path.join(tmp_dir, filename)

        download_file(url=url, dest_path=dest, progress_cb=progress_cb)

        if system == "Windows":
            _install_windows(dest, log_cb)
        elif system == "Darwin":
            _install_macos(dest, log_cb)
        elif system == "Linux":
            _install_linux(dest, log_cb)

    ollama_exe = find_ollama()
    if not ollama_exe:
        raise RuntimeError(
            "Installazione Ollama completata ma eseguibile non trovato. "
            "Potrebbe essere necessario riavviare il sistema."
        )

    ver = ollama_version(ollama_exe) or "?"
    _log(log_cb, f"Ollama installato: {ollama_exe} (v{ver})")
    return ollama_exe


def _install_windows(installer_path: str, log_cb: Optional[Callable]):
    """Installa OllamaSetup.exe in modalità silenziosa."""
    _log(log_cb, "Installazione Ollama (Windows)...")
    try:
        proc = subprocess.run(
            [installer_path, "/SILENT", "/NORESTART"],
            timeout=300, capture_output=True, text=True,
            creationflags=_CNW,
        )
        if proc.returncode not in (0, 3010):   # 3010 = riavvio richiesto ma ok
            raise RuntimeError(
                f"Installer Ollama terminato con codice {proc.returncode}.\n"
                f"{proc.stderr}"
            )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout durante l'installazione di Ollama.")

    # OllamaSetup.exe avvia automaticamente Ollama in system tray dopo
    # l'installazione — lo terminiamo subito per non disorientare l'utente.
    # Sarà riavviato da start_server() quando serve.
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "ollama.exe", "/T"],
            capture_output=True, creationflags=_CNW, timeout=10,
        )
        subprocess.run(
            ["taskkill", "/F", "/IM", "ollama app.exe", "/T"],
            capture_output=True, creationflags=_CNW, timeout=10,
        )
    except Exception:
        pass


def _install_macos(zip_path: str, log_cb: Optional[Callable]):
    """
    Installa Ollama su macOS estraendo il .zip nella cartella Applications.
    Alternativa: brew install ollama se Homebrew è disponibile.
    """
    # Prova prima con Homebrew
    if shutil.which("brew"):
        _log(log_cb, "Installazione Ollama tramite Homebrew...")
        try:
            subprocess.run(
                ["brew", "install", "ollama"],
                timeout=300, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            _log(log_cb, "Homebrew fallito, uso installer diretto...")

    # Fallback: estrai .zip in /Applications
    import zipfile
    apps_dir = os.path.join(os.path.expanduser("~"), "Applications")
    os.makedirs(apps_dir, exist_ok=True)
    _log(log_cb, f"Estrazione Ollama.app in {apps_dir}...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(apps_dir)

    # Rimuovi quarantine attribute (Gatekeeper)
    app_path = os.path.join(apps_dir, "Ollama.app")
    if os.path.isdir(app_path):
        subprocess.run(["xattr", "-cr", app_path], capture_output=True)


def _install_linux(bin_path: str, log_cb: Optional[Callable]):
    """
    Installa Ollama su Linux copiando il binario in ~/.local/bin/ (senza sudo).
    """
    bin_dir    = os.path.expanduser("~/.local/bin")
    os.makedirs(bin_dir, exist_ok=True)

    ollama_bin = os.path.join(bin_dir, "ollama")
    shutil.copy2(bin_path, ollama_bin)
    os.chmod(ollama_bin, 0o755)
    _log(log_cb, f"Ollama installato in: {ollama_bin}")


# ---------------------------------------------------------------------------
# Avvio e gestione servizio
# ---------------------------------------------------------------------------

def start_server(
    ollama_exe: str,
    log_cb:     Optional[Callable] = None,
) -> bool:
    """
    Avvia il server Ollama se non è già in esecuzione.
    Restituisce True se il server risponde entro il timeout.
    """
    if is_running():
        _log(log_cb, "Ollama già in esecuzione.")
        return True

    if port_in_use(OLLAMA_PORT):
        _log(log_cb,
             f"Porta {OLLAMA_PORT} occupata da un altro processo. "
             "Ollama potrebbe non avviarsi correttamente.")

    _log(log_cb, "Avvio server Ollama...")
    subprocess.Popen(
        [ollama_exe, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        creationflags=_CNW,
    )

    # Attendi fino a 30 secondi che risponda
    for _ in range(30):
        time.sleep(1)
        if is_running():
            _log(log_cb, "Server Ollama avviato.")
            return True

    _log(log_cb, "Timeout: il server Ollama non risponde.")
    return False


# ---------------------------------------------------------------------------
# Pull del modello
# ---------------------------------------------------------------------------

def pull_model(
    ollama_exe:  str,
    model:       str = OLLAMA_MODEL,
    log_cb:      Optional[Callable] = None,
    progress_cb: Optional[Callable] = None,
) -> bool:
    """
    Scarica il modello Ollama con `ollama pull`.
    Chiama progress_cb(bytes_done, bytes_total, layer_name) durante il download.
    Restituisce True se completato con successo.
    """
    if is_model_pulled(model):
        _log(log_cb, f"Modello '{model}' già presente.")
        return True

    if not is_running():
        if not start_server(ollama_exe, log_cb):
            raise RuntimeError("Impossibile avviare Ollama per il download del modello.")

    _log(log_cb, f"Download modello '{model}' (~5.2 GB)...")

    try:
        proc = subprocess.Popen(
            [ollama_exe, "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_CNW,
        )

        for line in proc.stdout:
            line = line.rstrip()
            _log(log_cb, line)

            # Parsing del progresso da output ollama
            # Formato tipico: "pulling sha256:abc... 45% ▕████    ▏ 2.3 GB/5.1 GB"
            progress = _parse_pull_progress(line)
            if progress and progress_cb:
                progress_cb(*progress)

        proc.wait(timeout=7200)   # 2 ore max
        if proc.returncode != 0:
            raise RuntimeError(f"ollama pull terminato con codice {proc.returncode}.")

    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError("Timeout: il download del modello ha impiegato più di 2 ore.")

    _log(log_cb, f"Modello '{model}' scaricato.")
    return True


# ---------------------------------------------------------------------------
# Punto di ingresso principale
# ---------------------------------------------------------------------------

def ensure_ollama(
    install_if_missing: bool = True,
    pull_model_flag:    bool = True,
    progress_cb:        Optional[ProgressCallback] = None,
    log_cb:             Optional[Callable]          = None,
) -> dict:
    """
    Garantisce che Ollama sia installato e il modello sia disponibile.

    Restituisce un dict con:
        installed: bool
        running:   bool
        model_ok:  bool
        version:   str | None
    """
    result = {"installed": False, "running": False,
              "model_ok": False, "version": None}

    ollama_exe = find_ollama()

    if not ollama_exe:
        if not install_if_missing:
            _log(log_cb, "Ollama non trovato e installazione non richiesta.")
            return result
        ollama_exe = install_ollama(progress_cb=progress_cb, log_cb=log_cb)

    result["installed"] = True
    result["version"]   = ollama_version(ollama_exe)

    if not is_running():
        result["running"] = start_server(ollama_exe, log_cb)
    else:
        result["running"] = True

    if result["running"] and pull_model_flag:
        result["model_ok"] = pull_model(
            ollama_exe, progress_cb=progress_cb, log_cb=log_cb
        )

    return result


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _parse_pull_progress(line: str) -> Optional[tuple[int, int, str]]:
    """
    Parsa una riga di output di `ollama pull` e restituisce
    (bytes_done, bytes_total, layer_name) o None.
    """
    import re
    # Es: "pulling abc123... 2.3 GB/5.1 GB"
    match = re.search(
        r"([\d.]+)\s*(GB|MB|KB)/([\d.]+)\s*(GB|MB|KB)", line
    )
    if not match:
        return None

    def to_bytes(val: str, unit: str) -> int:
        v = float(val)
        return int(v * {"GB": 1024**3, "MB": 1024**2, "KB": 1024}[unit])

    done  = to_bytes(match.group(1), match.group(2))
    total = to_bytes(match.group(3), match.group(4))

    # Estrai nome layer se presente
    layer_match = re.search(r"pulling\s+([\w:]+)", line)
    layer = layer_match.group(1) if layer_match else OLLAMA_MODEL

    return done, total, layer


def _log(cb: Optional[Callable], msg: str):
    if cb:
        cb(msg)
