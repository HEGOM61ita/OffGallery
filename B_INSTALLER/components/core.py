"""
Download ed estrazione del codice sorgente di OffGallery da GitHub.
Gestisce installazione iniziale e aggiornamenti.
"""

import io
import os
import shutil
import zipfile
from typing import Optional, Callable

from utils.download import download_file, download_text, ProgressCallback


# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

GITHUB_USER    = "HEGOM61ita"
GITHUB_REPO    = "OffGallery"
GITHUB_BRANCH  = "main"

# URL ZIP del branch principale
ZIP_URL = (
    f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}"
    f"/archive/refs/heads/{GITHUB_BRANCH}.zip"
)

# URL raw del file versione nel repo
VERSION_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}"
    f"/{GITHUB_BRANCH}/VERSION"
)

# File locale dove viene salvata la versione installata
VERSION_FILE = "VERSION"

# Prefisso che GitHub aggiunge dentro lo ZIP (es. "OffGallery-main/")
_ZIP_PREFIX = f"{GITHUB_REPO}-{GITHUB_BRANCH}/"

# Cartelle e file da NON sovrascrivere durante un aggiornamento
# (contengono dati utente o configurazione locale)
_PRESERVE_ON_UPDATE = {
    "database/",
    "Models/",
    "INPUT/",
    "plugins/",
    "config.yaml",
    "config_new.yaml",
    "installer_state.json",
}


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

def installed_version(install_path: str) -> Optional[str]:
    """Legge la versione installata da VERSION nella cartella di installazione."""
    path = os.path.join(install_path, VERSION_FILE)
    if not os.path.isfile(path):
        return None
    try:
        return open(path, encoding="utf-8").read().strip()
    except OSError:
        return None


def remote_version() -> Optional[str]:
    """Scarica la versione disponibile su GitHub. None se offline o errore."""
    try:
        return download_text(VERSION_URL).strip()
    except Exception:
        return None


def update_available(install_path: str) -> Optional[str]:
    """
    Confronta versione installata con quella remota.
    Restituisce la versione remota se è diversa, None se uguale o non verificabile.
    """
    local  = installed_version(install_path)
    remote = remote_version()
    if remote and local and remote != local:
        return remote
    return None


# ---------------------------------------------------------------------------
# Installazione e aggiornamento
# ---------------------------------------------------------------------------

def install_core(
    install_path: str,
    progress_cb:  Optional[ProgressCallback] = None,
    log_cb:       Optional[Callable]          = None,
) -> str:
    """
    Scarica ed estrae OffGallery in `install_path`.
    Se la cartella esiste già, fa un aggiornamento preservando i dati utente.

    Restituisce la versione installata.
    """
    is_update = _has_existing_install(install_path)
    action    = "Aggiornamento" if is_update else "Installazione"
    _log(log_cb, f"{action} OffGallery Core in: {install_path}")

    os.makedirs(install_path, exist_ok=True)

    # Download ZIP in memoria (evita file temporanei su disco)
    _log(log_cb, f"Download sorgente da GitHub ({GITHUB_USER}/{GITHUB_REPO})...")

    zip_path = os.path.join(install_path, ".core_download.zip")
    try:
        download_file(
            url=ZIP_URL,
            dest_path=zip_path,
            progress_cb=progress_cb,
        )
        _extract_zip(zip_path, install_path, is_update=is_update, log_cb=log_cb)
    finally:
        if os.path.isfile(zip_path):
            os.remove(zip_path)

    version = installed_version(install_path) or "sconosciuta"
    _log(log_cb, f"OffGallery Core installato. Versione: {version}")
    return version


def _extract_zip(
    zip_path:     str,
    install_path: str,
    is_update:    bool,
    log_cb:       Optional[Callable],
):
    """
    Estrae il ZIP di GitHub in install_path, stripping il prefisso
    'OffGallery-main/' che GitHub aggiunge automaticamente.

    Durante un aggiornamento salta i file in _PRESERVE_ON_UPDATE.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        total   = len(members)

        for i, member in enumerate(members, 1):
            # Salta la cartella radice dello ZIP (OffGallery-main/)
            if member.filename == _ZIP_PREFIX:
                continue

            # Rimuovi il prefisso per ottenere il percorso relativo reale
            if not member.filename.startswith(_ZIP_PREFIX):
                continue
            rel_path = member.filename[len(_ZIP_PREFIX):]

            if not rel_path:
                continue

            # Durante aggiornamento: preserva dati utente
            if is_update and _should_preserve(rel_path):
                _log(log_cb, f"  preservato: {rel_path}")
                continue

            dest = os.path.join(install_path, rel_path)

            if member.is_dir():
                os.makedirs(dest, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)

            if i % 50 == 0 or i == total:
                _log(log_cb, f"  estratti {i}/{total} file...")


# ---------------------------------------------------------------------------
# Verifica integrità
# ---------------------------------------------------------------------------

def verify_install(install_path: str) -> tuple[bool, list[str]]:
    """
    Verifica che i file essenziali di OffGallery siano presenti.
    Restituisce (ok, lista_file_mancanti).
    """
    required = [
        "gui_launcher.py",
        "gui",
        "utils",
        "installer",
        "VERSION",
    ]
    missing = [
        f for f in required
        if not os.path.exists(os.path.join(install_path, f))
    ]
    return len(missing) == 0, missing


# ---------------------------------------------------------------------------
# Punto di ingresso principale
# ---------------------------------------------------------------------------

def ensure_core(
    install_path: str,
    force_update: bool = False,
    progress_cb:  Optional[ProgressCallback] = None,
    log_cb:       Optional[Callable]          = None,
) -> dict:
    """
    Garantisce che il codice OffGallery sia installato e aggiornato.

    - Prima installazione: scarica e installa.
    - Se già presente e `force_update=False`: verifica integrità, non aggiorna.
    - Se già presente e `force_update=True`: aggiorna preservando dati utente.

    Restituisce un dict con:
        version:        str | None
        updated:        bool
        missing_files:  list[str]
        ok:             bool
    """
    result = {
        "version":       None,
        "updated":       False,
        "missing_files": [],
        "ok":            False,
    }

    has_install = _has_existing_install(install_path)

    if has_install and not force_update:
        ok, missing = verify_install(install_path)
        result["version"]       = installed_version(install_path)
        result["missing_files"] = missing
        result["ok"]            = ok
        if ok:
            _log(log_cb, f"OffGallery Core già presente (v{result['version']}).")
        else:
            _log(log_cb,
                 f"Installazione incompleta. File mancanti: {missing}. "
                 "Reinstallazione in corso...")
            result["version"] = install_core(install_path, progress_cb, log_cb)
            result["updated"]  = True
            result["ok"]       = True
        return result

    result["version"] = install_core(install_path, progress_cb, log_cb)
    result["updated"] = True
    ok, missing       = verify_install(install_path)
    result["ok"]            = ok
    result["missing_files"] = missing
    return result


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _has_existing_install(install_path: str) -> bool:
    """True se gui_launcher.py esiste nella cartella — segno di installazione precedente."""
    return os.path.isfile(os.path.join(install_path, "gui_launcher.py"))


def _should_preserve(rel_path: str) -> bool:
    """True se il file/cartella non va sovrascritto durante un aggiornamento."""
    for pattern in _PRESERVE_ON_UPDATE:
        if rel_path == pattern or rel_path.startswith(pattern):
            return True
    return False


def _log(cb: Optional[Callable], msg: str):
    if cb:
        cb(msg)
