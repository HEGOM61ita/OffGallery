"""
Installazione di ExifTool su Linux tramite package manager di sistema.
Rileva automaticamente apt, dnf o pacman e installa il pacchetto corretto.
Richiede sudo — la password viene chiesta dal terminale sottostante.
"""

import os
import shutil
import subprocess
from typing import Optional, Callable


# Pacchetti ExifTool per distribution family
_PACKAGE_MANAGERS = [
    # (eseguibile pm, comando install, nome pacchetto)
    ("apt-get", ["sudo", "apt-get", "install", "-y", "libimage-exiftool-perl"], "libimage-exiftool-perl"),
    ("dnf",     ["sudo", "dnf",     "install", "-y", "perl-Image-ExifTool"],    "perl-Image-ExifTool"),
    ("yum",     ["sudo", "yum",     "install", "-y", "perl-Image-ExifTool"],    "perl-Image-ExifTool"),
    ("pacman",  ["sudo", "pacman",  "-S",      "--noconfirm", "perl-image-exiftool"], "perl-image-exiftool"),
    ("zypper",  ["sudo", "zypper",  "install", "-y", "perl-Image-ExifTool"],    "perl-Image-ExifTool"),
]


def is_installed() -> bool:
    """True se exiftool è disponibile nel PATH."""
    return shutil.which("exiftool") is not None


def detect_package_manager() -> Optional[tuple[str, list[str], str]]:
    """
    Rileva il primo package manager disponibile nel sistema.
    Restituisce (nome_pm, comando_install, nome_pacchetto) o None.
    """
    for pm, cmd, pkg in _PACKAGE_MANAGERS:
        if shutil.which(pm):
            return pm, cmd, pkg
    return None


def install_exiftool(log_cb: Optional[Callable] = None) -> bool:
    """
    Installa ExifTool tramite il package manager di sistema.
    Restituisce True se l'installazione ha avuto successo.

    Richiede sudo: la password viene richiesta direttamente al terminale
    dal processo sudo — l'installer non gestisce credenziali.
    """
    if is_installed():
        _log(log_cb, "ExifTool già installato.")
        return True

    pm_info = detect_package_manager()
    if pm_info is None:
        _log(log_cb,
             "⚠  Package manager non rilevato (apt/dnf/pacman/zypper).\n"
             "   Installa ExifTool manualmente:\n"
             "   - Debian/Ubuntu: sudo apt-get install libimage-exiftool-perl\n"
             "   - Fedora/RHEL:   sudo dnf install perl-Image-ExifTool\n"
             "   - Arch Linux:    sudo pacman -S perl-image-exiftool\n"
             "   - openSUSE:      sudo zypper install perl-Image-ExifTool")
        return False

    pm_name, cmd, pkg = pm_info
    _log(log_cb, f"Installazione ExifTool tramite {pm_name} (richiede sudo)...")
    _log(log_cb, f"$ {' '.join(cmd)}")

    try:
        # stdin=None: sudo può leggere la password dal terminale reale
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            stdin=None,
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _log(log_cb, line)
        proc.wait(timeout=120)

        if proc.returncode != 0:
            _log(log_cb,
                 f"⚠  {pm_name} terminato con codice {proc.returncode}.\n"
                 f"   Installa manualmente: sudo {pm_name} install {pkg}")
            return False

    except subprocess.TimeoutExpired:
        proc.kill()
        _log(log_cb, "⚠  Timeout durante l'installazione di ExifTool.")
        return False
    except Exception as exc:
        _log(log_cb, f"⚠  Errore installazione ExifTool: {exc}")
        return False

    if is_installed():
        _log(log_cb, "✓  ExifTool installato correttamente.")
        return True
    else:
        _log(log_cb,
             "⚠  Installazione completata ma 'exiftool' non trovato nel PATH.\n"
             "   Potrebbe essere necessario riaprire il terminale.")
        return False


def _log(cb: Optional[Callable], msg: str):
    if cb:
        cb(msg)
