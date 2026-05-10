"""
Creazione, verifica e riparazione dell'ambiente conda 'OffGallery'.
"""

import os
import platform
import subprocess
from typing import Optional


ENV_NAME       = "OffGallery"
PYTHON_VERSION = "3.12"

_PROGRESS_CHARS = frozenset("━█▉▊▋▌▍▎▏▕◼◾#|")

def _is_progress_line(line: str) -> bool:
    if "\x1b" in line:
        return True
    stripped = line.strip()
    if not stripped:
        return True
    if len(stripped) > 4 and all(c in _PROGRESS_CHARS or c == " " for c in stripped):
        return True
    return False


# ---------------------------------------------------------------------------
# Ispezione
# ---------------------------------------------------------------------------

def python_executable(conda_exe: str) -> str:
    """Percorso del Python nell'env OffGallery."""
    system = platform.system()
    env_path = _env_path(conda_exe)
    if system == "Windows":
        return os.path.join(env_path, "python.exe")
    return os.path.join(env_path, "bin", "python")


def env_exists(conda_exe: str) -> bool:
    """True se l'ambiente OffGallery esiste già."""
    return os.path.isdir(_env_path(conda_exe))


def python_version_ok(conda_exe: str) -> bool:
    """
    True se il Python nell'env ha la versione attesa (PYTHON_VERSION).
    Restituisce False anche se l'env esiste ma il Python non è raggiungibile.
    """
    py = python_executable(conda_exe)
    if not os.path.isfile(py):
        return False
    try:
        out = subprocess.check_output(
            [py, "--version"],
            text=True, stderr=subprocess.STDOUT, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        # Output: "Python 3.12.4"
        ver = out.strip().split()[-1]          # "3.12.4"
        major_minor = ".".join(ver.split(".")[:2])  # "3.12"
        return major_minor == PYTHON_VERSION
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Creazione e rimozione
# ---------------------------------------------------------------------------

def create_env(
    conda_exe: str,
    log_cb:    Optional[callable] = None,
    force:     bool = False,
) -> str:
    """
    Crea l'ambiente conda OffGallery con Python PYTHON_VERSION.

    Se `force=True` rimuove l'env esistente prima di crearlo.
    Restituisce il percorso dell'eseguibile Python nell'env.
    """
    if force and env_exists(conda_exe):
        _log(log_cb, f"Rimozione ambiente esistente '{ENV_NAME}'...")
        _run(conda_exe, ["env", "remove", "-n", ENV_NAME, "-y"], log_cb, timeout=120)

    if env_exists(conda_exe) and python_version_ok(conda_exe):
        _log(log_cb, f"Ambiente '{ENV_NAME}' già presente con Python {PYTHON_VERSION}.")
        return python_executable(conda_exe)

    _log(log_cb, f"Creazione ambiente '{ENV_NAME}' con Python {PYTHON_VERSION}...")

    _run(conda_exe, [
        "create",
        "-n", ENV_NAME,
        f"python={PYTHON_VERSION}",
        "pip",
        "--override-channels",
        "-c", "conda-forge",
        "-y",
    ], log_cb, timeout=300)

    py = python_executable(conda_exe)
    if not os.path.isfile(py):
        raise RuntimeError(
            f"Ambiente creato ma Python non trovato in: {py}"
        )

    _log(log_cb, f"Ambiente '{ENV_NAME}' pronto. Python: {py}")
    return py


def remove_env(conda_exe: str, log_cb: Optional[callable] = None):
    """Rimuove completamente l'ambiente OffGallery."""
    if not env_exists(conda_exe):
        _log(log_cb, f"Ambiente '{ENV_NAME}' non presente, nulla da rimuovere.")
        return
    _log(log_cb, f"Rimozione ambiente '{ENV_NAME}'...")
    _run(conda_exe, ["env", "remove", "-n", ENV_NAME, "-y"], log_cb, timeout=180)
    _log(log_cb, "Ambiente rimosso.")


# ---------------------------------------------------------------------------
# Punto di ingresso principale
# ---------------------------------------------------------------------------

def pip_exists(conda_exe: str) -> bool:
    """True se pip è disponibile nell'env OffGallery."""
    py = python_executable(conda_exe)
    if not os.path.isfile(py):
        return False
    try:
        subprocess.check_output(
            [py, "-m", "pip", "--version"],
            stderr=subprocess.DEVNULL,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        return True
    except Exception:
        return False


def ensure_env(
    conda_exe: str,
    log_cb:    Optional[callable] = None,
) -> str:
    """
    Garantisce che l'ambiente OffGallery esista e abbia il Python corretto.

    - Se esiste già con la versione giusta e pip: non fa nulla.
    - Se esiste ma manca pip: installa pip.
    - Se esiste ma con versione sbagliata: lo ricrea.
    - Se non esiste: lo crea.

    Restituisce il percorso dell'eseguibile Python.
    """
    if env_exists(conda_exe):
        if python_version_ok(conda_exe):
            py = python_executable(conda_exe)
            if not pip_exists(conda_exe):
                _log(log_cb, "pip mancante nell'env — installazione...")
                _run(conda_exe, ["install", "-n", ENV_NAME, "pip", "-y",
                                 "--override-channels", "-c", "conda-forge"],
                     log_cb, timeout=120)
            _log(log_cb, f"Ambiente '{ENV_NAME}' OK (Python {PYTHON_VERSION}).")
            return py
        else:
            _log(log_cb,
                 f"Ambiente '{ENV_NAME}' esiste ma con versione Python errata. "
                 f"Ricreo...")
            return create_env(conda_exe, log_cb=log_cb, force=True)

    return create_env(conda_exe, log_cb=log_cb)


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _env_path(conda_exe: str) -> str:
    """
    Ricava il percorso della cartella dell'env dato l'eseguibile conda.
    Es: C:\miniconda3\Scripts\conda.exe  →  C:\miniconda3\envs\OffGallery
    """
    system = platform.system()
    if system == "Windows":
        # conda.exe sta in <miniconda>\Scripts\conda.exe
        miniconda = os.path.dirname(os.path.dirname(conda_exe))
    else:
        # conda sta in <miniconda>/bin/conda
        miniconda = os.path.dirname(os.path.dirname(conda_exe))

    return os.path.join(miniconda, "envs", ENV_NAME)


def _run(
    conda_exe: str,
    args:      list,
    log_cb:    Optional[callable],
    timeout:   int = 300,
):
    cmd = [conda_exe] + args
    if "--quiet" not in args and "-q" not in args:
        cmd = cmd + ["--quiet"]
    _log(log_cb, f"$ {' '.join(cmd)}")

    flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=_clean_env(),
            creationflags=flags,
        )
        for line in proc.stdout:
            line = line.replace("\r", "").rstrip()
            if line and not _is_progress_line(line):
                _log(log_cb, line)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(
            f"Timeout ({timeout}s) durante: conda {' '.join(args)}"
        )

    if proc.returncode != 0:
        raise RuntimeError(
            f"conda {args[0]} terminato con codice {proc.returncode}."
        )


def _clean_env() -> dict:
    """
    Restituisce le variabili d'ambiente del processo corrente senza
    CONDA_DEFAULT_ENV e CONDA_PREFIX, che possono confondere conda
    se l'installer gira già dentro un env attivo.
    """
    env = os.environ.copy()
    for key in ("CONDA_DEFAULT_ENV", "CONDA_PREFIX", "CONDA_SHLVL"):
        env.pop(key, None)
    # Accetta automaticamente il TOS di Anaconda (richiesto da conda 24+)
    env["CONDA_TOS_ACCEPTED"] = "true"
    env["CONDA_REPORT_ERRORS"] = "false"
    return env


def _log(cb: Optional[callable], msg: str):
    if cb:
        cb(msg)
