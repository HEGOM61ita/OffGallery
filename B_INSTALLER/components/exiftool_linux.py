"""
Installazione di ExifTool su Linux scaricando il tarball standalone da exiftool.org.
Installa in ~/.local/ — nessun sudo richiesto.
"""

import os
import shutil
import stat
import tarfile
import tempfile
import urllib.request
from typing import Optional, Callable


_VER_URL     = "https://exiftool.org/ver.txt"
_TAR_URL     = "https://exiftool.org/Image-ExifTool-{version}.tar.gz"
_INSTALL_DIR = os.path.expanduser("~/.local/lib/exiftool")
_BIN_WRAPPER = os.path.expanduser("~/.local/bin/exiftool")


def is_installed() -> bool:
    """True se exiftool è disponibile nel PATH o nel percorso locale."""
    return shutil.which("exiftool") is not None or os.path.isfile(_BIN_WRAPPER)


def detect_package_manager():
    """Mantenuto per compatibilità con dashboard.py — non più usato."""
    return None


def install_exiftool(log_cb: Optional[Callable] = None) -> bool:
    """
    Scarica ExifTool standalone da exiftool.org e installa in ~/.local/.
    Non richiede sudo.
    Restituisce True se l'installazione ha avuto successo.
    """
    if is_installed():
        _log(log_cb, "ExifTool già installato.")
        return True

    try:
        version = _latest_version()
        _log(log_cb, f"ExifTool ultima versione: {version}")

        url = _TAR_URL.format(version=version)
        _log(log_cb, f"Download da: {url}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tar_path = os.path.join(tmp_dir, f"Image-ExifTool-{version}.tar.gz")
            _download(url, tar_path, log_cb)
            _extract_and_install(tar_path, version, log_cb)

    except Exception as exc:
        _log(log_cb, f"⚠  Errore installazione ExifTool: {exc}")
        return False

    if is_installed():
        _log(log_cb, f"✓  ExifTool installato: {_BIN_WRAPPER}")
        return True

    _log(log_cb, "⚠  Installazione completata ma exiftool non trovato nel PATH.")
    return False


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _latest_version() -> str:
    with urllib.request.urlopen(_VER_URL, timeout=10) as resp:
        return resp.read().decode().strip()


def _download(url: str, dest: str, log_cb: Optional[Callable]):
    with urllib.request.urlopen(url, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done  = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
    _log(log_cb, f"  scaricati {done // 1024} KB")


def _extract_and_install(tar_path: str, version: str, log_cb: Optional[Callable]):
    """Estrae il tarball in _INSTALL_DIR e crea un wrapper in ~/.local/bin/."""
    os.makedirs(_INSTALL_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(_BIN_WRAPPER), exist_ok=True)

    prefix = f"Image-ExifTool-{version}/"
    _log(log_cb, f"Estrazione in {_INSTALL_DIR}...")

    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.name.startswith(prefix):
                continue
            rel = member.name[len(prefix):]
            if not rel:
                continue
            dest = os.path.join(_INSTALL_DIR, rel)
            if member.isdir():
                os.makedirs(dest, exist_ok=True)
            elif member.isfile():
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with tf.extractfile(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)

    # Rendi eseguibile lo script principale
    et_script = os.path.join(_INSTALL_DIR, "exiftool")
    if os.path.isfile(et_script):
        os.chmod(et_script,
                 os.stat(et_script).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Wrapper in ~/.local/bin/ che richiama lo script con perl
    with open(_BIN_WRAPPER, "w") as f:
        f.write(f'#!/bin/sh\nexec perl "{_INSTALL_DIR}/exiftool" "$@"\n')
    os.chmod(_BIN_WRAPPER, 0o755)
    _log(log_cb, f"  wrapper: {_BIN_WRAPPER}")


def _log(cb: Optional[Callable], msg: str):
    if cb:
        cb(msg)
