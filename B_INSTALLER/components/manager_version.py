"""
Versione di OffGallery Manager e controllo della sua obsolescenza.

Il Manager non si aggiorna da solo: il suo eseguibile resta quello scaricato
la prima volta, mentre la Release GitHub ne pubblica uno nuovo ad ogni versione.
Quando una correzione riguarda il Manager stesso (come la scrittura del file
VERSION, arrivata con la 1.0.29) chi ha una copia anteriore resta bloccato per
sempre: preme Aggiorna, l'app si aggiorna, ma il difetto non se ne va perché
sta nel programma che sta premendo il pulsante (segnalazione 2026-08-17).

Qui il Manager confronta la propria versione con l'ultima pubblicata e, se è
indietro, lo dice offrendo la pagina di download.
"""

from typing import Optional

from components.core import RELEASE_API, GITHUB_USER, GITHUB_REPO
from utils.download import download_text

# Versione di questo Manager. Va allineata a mano al tag della release in cui
# viene pubblicato: è l'unico modo per un eseguibile di sapere quanto è vecchio.
MANAGER_VERSION = "v1.0.51"

# Pagina da cui scaricare l'eseguibile aggiornato
RELEASES_PAGE = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"


def _numeri(versione: str) -> Optional[tuple]:
    """Converte "v1.0.29" in (1, 0, 29). None se non è un formato riconoscibile."""
    testo = versione.strip().lstrip("vV")
    parti = testo.split(".")
    try:
        return tuple(int(p) for p in parti)
    except ValueError:
        return None


def manager_update_available() -> Optional[str]:
    """
    Versione del Manager pubblicata su GitHub, se è più recente di questa.
    None se è pari, più vecchia, non confrontabile o se la rete non risponde.
    """
    try:
        import json
        data = json.loads(download_text(RELEASE_API))
        tag = (data.get("tag_name") or "").strip()
    except Exception:
        return None

    if not tag:
        return None

    remota = _numeri(tag)
    locale = _numeri(MANAGER_VERSION)
    # Senza due numeri confrontabili è meglio tacere che avvisare a sproposito.
    if remota is None or locale is None:
        return None

    return tag if remota > locale else None
