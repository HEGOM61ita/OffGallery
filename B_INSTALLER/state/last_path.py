"""
Ricorda l'ultima cartella di installazione usata, fuori da install_path.

Il problema
-----------
Il Manager cerca l'installazione SOLO nella cartella predefinita
(~/OffGallery). Chi installa altrove ottiene comunque un installer_state.json
valido, ma dentro la propria cartella: al riavvio il Manager non sa dove
guardare, non lo trova, e ripropone il wizard da capo chiedendo la cartella
a mano — anche se l'installazione c'e' ed e' completa (segnalazione utente
2026-09-03).

La cartella di installazione non e' un posto affidabile per questa nota: se
un giorno sparisce (spostata, cancellata) il file sparirebbe con lei. Serve
un posto fuori da install_path, stabile, che sopravviva anche se l'utente
sposta o rinomina la cartella OffGallery.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_FILENAME = "last_install_path.json"


def _prefs_dir() -> str:
    """Cartella di preferenze del Manager, fuori da qualsiasi install_path."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "OffGallery")


def _prefs_file() -> str:
    return os.path.join(_prefs_dir(), _FILENAME)


def load_last_path() -> str:
    """Ultima cartella di installazione salvata, o stringa vuota se assente/illeggibile."""
    try:
        with open(_prefs_file(), encoding="utf-8") as f:
            data = json.load(f)
        path = data.get("install_path", "")
        return path if isinstance(path, str) else ""
    except (OSError, json.JSONDecodeError, AttributeError) as e:
        logger.debug("Nessuna cartella precedente salvata: %s", e)
        return ""


def save_last_path(install_path: str) -> None:
    """Salva la cartella di installazione corrente per i prossimi avvii."""
    try:
        prefs_dir = _prefs_dir()
        os.makedirs(prefs_dir, exist_ok=True)
        tmp = _prefs_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"install_path": install_path}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, _prefs_file())
    except OSError as e:
        # Non deve mai bloccare il resto del Manager: nel peggiore dei casi
        # al prossimo avvio si ricadra' sulla cartella predefinita, come oggi.
        logger.warning("Impossibile salvare l'ultima cartella di installazione", exc_info=True)
