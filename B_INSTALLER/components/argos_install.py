"""
Installazione di Argos Translate IT→EN tramite argostranslate.package.
Installa in ~/.local/share/argos-translate/packages/ — nessun sudo richiesto.
"""

import subprocess
from typing import Optional, Callable

# Script Python eseguito nell'env OffGallery per installare argos.
# Separato come subprocess per evitare import argostranslate nell'installer.
_INSTALL_SCRIPT = """
import sys, shutil, pathlib

try:
    import argostranslate.package
except ImportError:
    print("IMPORT_ERROR")
    sys.exit(1)

pkg_dir = pathlib.Path.home() / ".local" / "share" / "argos-translate" / "packages"

# Controlla se già installato; se la directory è corrotta la pulisce
try:
    installed = argostranslate.package.get_installed_packages()
    if any(p.from_code == "it" and p.to_code == "en" for p in installed):
        print("ALREADY_INSTALLED")
        sys.exit(0)
except Exception as e:
    print(f"CORRUPTED: {e} — pulizia directory pacchetti")
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)

# Scarica indice e pacchetto IT→EN
try:
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    pkg = next((p for p in available if p.from_code == "it" and p.to_code == "en"), None)
    if not pkg:
        print("NOT_FOUND")
        sys.exit(1)
    download_path = pkg.download()
    argostranslate.package.install_from_path(download_path)
    print("INSTALLED")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
"""


def is_installed(python_exe: str) -> bool:
    """True se Argos IT→EN è già installato nell'env OffGallery."""
    check = (
        "import argostranslate.package; "
        "installed = argostranslate.package.get_installed_packages(); "
        "print('YES' if any(p.from_code=='it' and p.to_code=='en' for p in installed) else 'NO')"
    )
    try:
        out = subprocess.check_output(
            [python_exe, "-c", check],
            text=True, stderr=subprocess.DEVNULL, timeout=15,
        ).strip()
        return out == "YES"
    except Exception:
        return False


def install_argos(
    python_exe: str,
    log_cb:     Optional[Callable] = None,
) -> bool:
    """
    Installa Argos Translate IT→EN nell'env OffGallery.
    Scarica dal server Argos ufficiale (~92 MB).
    Restituisce True se l'installazione ha avuto successo.
    """
    _log(log_cb, "Installazione Argos Translate IT→EN...")

    try:
        proc = subprocess.Popen(
            [python_exe, "-c", _INSTALL_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _log(log_cb, line)
        proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        _log(log_cb, "⚠  Timeout durante l'installazione di Argos.")
        return False
    except Exception as exc:
        _log(log_cb, f"⚠  Errore: {exc}")
        return False

    if proc.returncode == 0:
        _log(log_cb, "✓  Argos Translate IT→EN installato.")
        return True

    _log(log_cb, "⚠  Installazione Argos fallita — la traduzione automatica non sarà disponibile.")
    return False


def _log(cb: Optional[Callable], msg: str):
    if cb:
        cb(msg)
