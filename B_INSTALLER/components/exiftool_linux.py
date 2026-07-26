"""
Installazione di ExifTool su Linux da una versione congelata e verificata.
Installa in ~/.local/ — nessun sudo richiesto.

Sorgente primaria: il repo HuggingFace HEGOM/OffGallery-models, dove il tarball
è congelato insieme agli altri asset di terze parti (vedi argos-it-en/).
Motivi della scelta:
  - Riproducibilità: tutti gli utenti installano la stessa versione testata,
    non "l'ultima" che cambia sotto i piedi.
  - Un solo dominio di fiducia: l'installer dipende già da huggingface.co per
    i modelli AI; se HF è giù l'installazione non parte comunque.
  - exiftool.org è dimostrabilmente inaffidabile: a luglio 2026 DreamHost ha
    disabilitato il sito e tutti i tarball rispondono 404 (ver.txt invece
    risponde ancora, per cui l'errore si manifestava solo al download).

SourceForge e GitHub restano come fallback se HF è irraggiungibile.
"""

import os
import shutil
import stat
import tarfile
import tempfile
from typing import Optional, Callable

from utils.download import download_file, DownloadError, HashMismatchError


# ---------------------------------------------------------------------------
# Versione congelata
# ---------------------------------------------------------------------------
# Per aggiornare ExifTool:
#   1. scaricare il nuovo tarball e verificarne lo SHA-256 contro
#      https://exiftool.org/checksums-<versione>.txt (se il sito è tornato su)
#      oppure contro i checksum pubblicati su SourceForge;
#   2. caricarlo su HF in exiftool/Image-ExifTool-<versione>.tar.gz;
#   3. aggiornare le due costanti qui sotto.

EXIFTOOL_VERSION = "13.59"
EXIFTOOL_SHA256  = "668ea3acececb7235fbd0f4900e72d5f12c9b07e5c778fd36cb1e9b5828fd65a"

_HF_REPO = "HEGOM/OffGallery-models"

# Mirror in ordine di preferenza. Il primo che risponde vince.
# Entrambi servono lo stesso identico tarball firmato da Phil Harvey, quindi
# un solo hash pinnato li verifica entrambi.
#
# github.com/exiftool/exiftool/archive/refs/tags/<ver>.tar.gz è deliberatamente
# ESCLUSO: GitHub genera quell'archivio al volo dal tag, con hash diverso da
# quello ufficiale e non garantito stabile nel tempo. Pinnarlo produrrebbe un
# mirror che si rompe da solo a una data imprevedibile — una ridondanza finta,
# peggiore dell'assenza. (Testato: scaricabile e installabile, ma scartato dal
# controllo checksum, quindi sarebbe codice morto.)
_MIRRORS = [
    ("HuggingFace",
     f"https://huggingface.co/{_HF_REPO}/resolve/main/exiftool/Image-ExifTool-{{version}}.tar.gz"),
    ("SourceForge",
     "https://sourceforge.net/projects/exiftool/files/Image-ExifTool-{version}.tar.gz/download"),
]

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
    Scarica ExifTool (versione congelata) e installa in ~/.local/.
    Non richiede sudo.
    Restituisce True se l'installazione ha avuto successo.
    """
    if is_installed():
        _log(log_cb, "ExifTool già installato.")
        return True

    version = EXIFTOOL_VERSION
    _log(log_cb, f"ExifTool versione {version}")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tar_path = os.path.join(tmp_dir, f"Image-ExifTool-{version}.tar.gz")
            if not _download_from_mirrors(tar_path, version, log_cb):
                _log(log_cb, "⚠  Nessun mirror raggiungibile per ExifTool.")
                return False
            _extract_and_install(tar_path, log_cb)

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

def _download_from_mirrors(dest: str, version: str, log_cb: Optional[Callable]) -> bool:
    """Prova i mirror in ordine finché uno non produce un file con hash corretto.

    L'hash è pinnato nel sorgente e non scaricato: un checksum preso dalla stessa
    sorgente del file non proteggerebbe da nulla.
    """
    for name, template in _MIRRORS:
        url = template.format(version=version)
        _log(log_cb, f"Download da {name}...")
        try:
            download_file(
                url=url,
                dest_path=dest,
                expected_sha256=EXIFTOOL_SHA256,
                progress_cb=None,
            )
            _log(log_cb, f"  ✓ scaricato da {name} ({os.path.getsize(dest) // 1024} KB)")
            return True
        except HashMismatchError:
            # Il mirror ha servito un file diverso da quello atteso: va scartato,
            # ma l'utente deve poterlo distinguere da un guasto di rete.
            _log(log_cb, f"  ✗ {name}: checksum non corrispondente, mirror scartato")
        except DownloadError as exc:
            _log(log_cb, f"  ✗ {name}: {exc}")

        # download_file può lasciare un parziale: rimuovilo prima di passare al
        # mirror successivo, altrimenti il resume ripartirebbe da byte di
        # un'altra sorgente producendo un archivio corrotto.
        for leftover in (dest, dest + ".part"):
            if os.path.isfile(leftover):
                os.remove(leftover)
    return False


def _tar_root_prefix(tf: tarfile.TarFile) -> str:
    """Ricava il prefisso di directory dall'archivio.

    Oggi il tarball ufficiale usa 'Image-ExifTool-<ver>/', ma non lo diamo per
    scontato: se un archivio futuro cambiasse struttura, assumere il prefisso
    significherebbe estrarre zero file in silenzio e dichiarare successo su una
    directory vuota. Insieme al controllo `extracted == 0` questo rende il
    fallimento rumoroso invece che invisibile.
    """
    for member in tf.getmembers():
        parts = member.name.split("/", 1)
        if parts[0] and parts[0] not in (".", ".."):
            return parts[0] + "/"
    raise RuntimeError("archivio ExifTool vuoto o malformato")


def _extract_and_install(tar_path: str, log_cb: Optional[Callable]):
    """Estrae il tarball in _INSTALL_DIR e crea un wrapper in ~/.local/bin/."""
    os.makedirs(_INSTALL_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(_BIN_WRAPPER), exist_ok=True)

    _log(log_cb, f"Estrazione in {_INSTALL_DIR}...")
    extracted = 0

    with tarfile.open(tar_path, "r:gz") as tf:
        prefix = _tar_root_prefix(tf)
        for member in tf.getmembers():
            if not member.name.startswith(prefix):
                continue
            rel = member.name[len(prefix):]
            if not rel:
                continue
            # Difesa contro path traversal (tar slip): scarta tutto ciò che
            # finirebbe fuori da _INSTALL_DIR.
            dest = os.path.realpath(os.path.join(_INSTALL_DIR, rel))
            if not dest.startswith(os.path.realpath(_INSTALL_DIR) + os.sep):
                _log(log_cb, f"  ⚠ voce sospetta ignorata: {member.name}")
                continue
            if member.isdir():
                os.makedirs(dest, exist_ok=True)
            elif member.isfile():
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with tf.extractfile(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                extracted += 1

    if extracted == 0:
        raise RuntimeError("nessun file estratto dall'archivio ExifTool")

    # Rendi eseguibile lo script principale
    et_script = os.path.join(_INSTALL_DIR, "exiftool")
    if not os.path.isfile(et_script):
        raise RuntimeError(f"script 'exiftool' non trovato dopo l'estrazione ({extracted} file)")
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
