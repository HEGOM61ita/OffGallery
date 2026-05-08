"""
Rilevamento, download e installazione silenziosa di Miniconda.
Supporta Windows, macOS (arm64 e x86_64) e Linux.
"""

import os
import platform
import subprocess
import tempfile
from typing import Optional

from utils.download import download_file, DownloadProgress, ProgressCallback

_CNW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

# ---------------------------------------------------------------------------
# URL ufficiali Miniconda (latest)
# ---------------------------------------------------------------------------

_BASE_URL = "https://repo.anaconda.com/miniconda/"

_INSTALLER = {
    ("Windows", "AMD64"):   "Miniconda3-latest-Windows-x86_64.exe",
    ("Windows", "x86_64"):  "Miniconda3-latest-Windows-x86_64.exe",
    ("Darwin",  "arm64"):   "Miniconda3-latest-MacOSX-arm64.sh",
    ("Darwin",  "x86_64"):  "Miniconda3-latest-MacOSX-x86_64.sh",
    ("Linux",   "x86_64"):  "Miniconda3-latest-Linux-x86_64.sh",
    ("Linux",   "aarch64"): "Miniconda3-latest-Linux-aarch64.sh",
}

# Percorsi di installazione default per piattaforma
_DEFAULT_INSTALL_PATH = {
    "Windows": os.path.join("C:\\", "miniconda3"),
    "Darwin":  os.path.join(os.path.expanduser("~"), "miniconda3"),
    "Linux":   os.path.join(os.path.expanduser("~"), "miniconda3"),
}


# ---------------------------------------------------------------------------
# Rilevamento
# ---------------------------------------------------------------------------

def find_conda() -> Optional[str]:
    """
    Cerca conda nel sistema. Restituisce il percorso dell'eseguibile conda
    oppure None se non trovato.

    Cerca in ordine:
    1. PATH di sistema
    2. Percorsi di installazione standard per piattaforma
    3. Variabile d'ambiente CONDA_EXE
    """
    # 1. Dalla variabile d'ambiente impostata da conda init
    conda_exe = os.environ.get("CONDA_EXE")
    if conda_exe and os.path.isfile(conda_exe):
        return conda_exe

    # 2. PATH di sistema
    import shutil
    found = shutil.which("conda")
    if found:
        return found

    # 3. Percorsi standard
    system = platform.system()
    for candidate in _standard_conda_paths(system):
        if os.path.isfile(candidate):
            return candidate

    return None


def conda_version(conda_exe: str) -> Optional[str]:
    """Restituisce la versione di conda (es. '24.1.2') o None se non leggibile."""
    try:
        out = subprocess.check_output(
            [conda_exe, "--version"],
            text=True, stderr=subprocess.STDOUT, timeout=15,
            creationflags=_CNW,
        )
        # Output: "conda 24.1.2"
        parts = out.strip().split()
        return parts[1] if len(parts) >= 2 else out.strip()
    except Exception:
        return None


def default_install_path() -> str:
    return _DEFAULT_INSTALL_PATH.get(platform.system(), os.path.expanduser("~/miniconda3"))


def conda_executable(miniconda_path: str) -> str:
    """Restituisce il percorso dell'eseguibile conda dato il path di Miniconda."""
    system = platform.system()
    if system == "Windows":
        return os.path.join(miniconda_path, "Scripts", "conda.exe")
    return os.path.join(miniconda_path, "bin", "conda")


def is_installed_at(miniconda_path: str) -> bool:
    """Verifica che Miniconda sia installato nella cartella indicata."""
    return os.path.isfile(conda_executable(miniconda_path))


# ---------------------------------------------------------------------------
# Download e installazione
# ---------------------------------------------------------------------------

def download_installer(
    dest_dir: str,
    progress_cb: Optional[ProgressCallback] = None,
) -> str:
    """
    Scarica l'installer Miniconda corretto per la piattaforma corrente.
    Restituisce il percorso del file scaricato.
    """
    system  = platform.system()
    machine = platform.machine()
    key     = (system, machine)

    if key not in _INSTALLER:
        raise RuntimeError(
            f"Piattaforma non supportata: {system} {machine}. "
            f"Supportate: {list(_INSTALLER.keys())}"
        )

    filename = _INSTALLER[key]
    url      = _BASE_URL + filename
    dest     = os.path.join(dest_dir, filename)

    download_file(url=url, dest_path=dest, progress_cb=progress_cb)
    return dest


def install(
    installer_path: str,
    install_path:   str,
    progress_cb:    Optional[ProgressCallback] = None,
    log_cb:         Optional[callable]         = None,
) -> str:
    """
    Esegue l'installer Miniconda in modalità silenziosa.
    Restituisce il percorso dell'eseguibile conda installato.

    Su Windows: installer .exe con /S /D=<path>
    Su macOS/Linux: script .sh con -b -p <path>
    """
    system = platform.system()
    os.makedirs(install_path, exist_ok=True)

    if system == "Windows":
        cmd = [
            installer_path,
            "/S",                      # silent
            "/D=" + install_path,      # destinazione (deve essere ultimo argomento)
        ]
    else:
        # Rendi eseguibile lo script
        os.chmod(installer_path, 0o755)
        cmd = [
            "bash", installer_path,
            "-b",                      # batch (non interattivo)
            "-p", install_path,        # prefix
        ]

    _log(log_cb, f"Installazione Miniconda in: {install_path}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=_CNW,
        )
        for line in proc.stdout:
            _log(log_cb, line.rstrip())
        proc.wait(timeout=300)

        if proc.returncode != 0:
            raise RuntimeError(
                f"Installer Miniconda terminato con codice {proc.returncode}."
            )
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError("Timeout: l'installer Miniconda ha impiegato più di 5 minuti.")

    conda_exe = conda_executable(install_path)
    if not os.path.isfile(conda_exe):
        raise RuntimeError(
            f"Installazione completata ma conda non trovato in: {conda_exe}"
        )

    _log(log_cb, f"Miniconda installato. conda: {conda_exe}")
    return conda_exe


def ensure_miniconda(
    install_path:    str,
    user_conda_path: Optional[str]          = None,
    progress_cb:     Optional[ProgressCallback] = None,
    log_cb:          Optional[callable]         = None,
) -> tuple[str, bool]:
    """
    Punto di ingresso principale per i componenti di livello superiore.

    Ordine di ricerca:
    1. Percorso indicato manualmente dall'utente (`user_conda_path`)
    2. PATH di sistema e percorsi standard
    3. Cartella di installazione locale (`install_path`)
    4. Download e installazione automatica

    Restituisce (percorso_conda_exe, trovato_nel_sistema).
    `trovato_nel_sistema=True` significa che non abbiamo installato nulla.
    """
    # 1. Percorso manuale indicato dall'utente dalla UI
    if user_conda_path:
        conda_exe = conda_executable(user_conda_path)
        if os.path.isfile(conda_exe):
            ver = conda_version(conda_exe) or "?"
            _log(log_cb, f"Conda indicato dall'utente: {conda_exe} (v{ver})")
            return conda_exe, True
        else:
            raise RuntimeError(
                f"Conda non trovato nel percorso indicato: {user_conda_path}\n"
                f"Atteso: {conda_exe}"
            )

    # 2. Già nel sistema (PATH + percorsi standard)?
    system_conda = find_conda()
    if system_conda:
        ver = conda_version(system_conda) or "?"
        _log(log_cb, f"Conda trovato nel sistema: {system_conda} (v{ver})")
        return system_conda, True

    # 3. Già installato nella nostra cartella da un run precedente?
    if is_installed_at(install_path):
        conda_exe = conda_executable(install_path)
        ver = conda_version(conda_exe) or "?"
        _log(log_cb, f"Miniconda già installato in: {install_path} (v{ver})")
        return conda_exe, True

    # 4. Scarica e installa
    _log(log_cb, "Miniconda non trovato. Avvio download...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        installer = download_installer(tmp_dir, progress_cb=progress_cb)
        conda_exe = install(installer, install_path,
                            progress_cb=progress_cb, log_cb=log_cb)

    return conda_exe, False


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _standard_conda_paths(system: str) -> list[str]:
    """Percorsi dove conda potrebbe essere installato al di fuori del PATH."""
    home = os.path.expanduser("~")
    candidates = []

    if system == "Windows":
        appdata = os.environ.get("LOCALAPPDATA", "")
        userprofile = os.environ.get("USERPROFILE", home)
        roots = [
            "C:\\miniconda3",
            "C:\\anaconda3",
            os.path.join(userprofile, "miniconda3"),
            os.path.join(userprofile, "anaconda3"),
            os.path.join(userprofile, "AppData", "Local", "miniconda3"),
            os.path.join(appdata, "miniconda3"),
        ]
        for r in roots:
            candidates.append(os.path.join(r, "Scripts", "conda.exe"))

    else:  # Darwin / Linux
        roots = [
            os.path.join(home, "miniconda3"),
            os.path.join(home, "anaconda3"),
            os.path.join(home, "opt", "miniconda3"),
            "/opt/miniconda3",
            "/opt/anaconda3",
            "/usr/local/miniconda3",
        ]
        for r in roots:
            candidates.append(os.path.join(r, "bin", "conda"))

    return candidates


def _log(cb: Optional[callable], msg: str):
    if cb:
        cb(msg)
