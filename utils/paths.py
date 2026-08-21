"""
Path utilities per OffGallery
Funziona sia come script Python che come EXE PyInstaller
"""

import sys
from pathlib import Path


def get_app_dir() -> Path:
    """
    Ritorna la directory root dell'applicazione.

    - Come script Python: directory contenente gui_launcher.py
    - Come EXE PyInstaller: directory contenente l'eseguibile

    Returns:
        Path: Directory root dell'app
    """
    if getattr(sys, 'frozen', False):
        # Eseguito come EXE PyInstaller
        return Path(sys.executable).parent
    else:
        # Eseguito come script Python
        # Questo file è in utils/, quindi parent.parent è la root
        return Path(__file__).parent.parent


def get_resource_path(relative_path: str) -> Path:
    """
    Ritorna il path assoluto di una risorsa relativa alla root dell'app.

    Args:
        relative_path: Path relativo (es. 'assets/logo3.jpg', 'config_new.yaml')

    Returns:
        Path: Path assoluto della risorsa

    Example:
        config_path = get_resource_path('config_new.yaml')
        logo_path = get_resource_path('assets/logo3.jpg')
    """
    return get_app_dir() / relative_path


# Shortcut per directory comuni
def get_assets_dir() -> Path:
    """Directory assets/"""
    return get_app_dir() / 'assets'


def get_models_dir(config=None) -> Path:
    """Directory per i modelli AI.
    Se config contiene models_repository.models_dir, usa quello.
    Percorsi relativi sono risolti rispetto ad APP_DIR.
    Default: APP_DIR/Models
    """
    if config:
        rel = config.get('models_repository', {}).get('models_dir', 'Models')
    else:
        rel = 'Models'
    p = Path(rel)
    return p if p.is_absolute() else get_app_dir() / p


def get_config_path() -> Path:
    """Path del file config_new.yaml"""
    return get_app_dir() / 'config_new.yaml'


def get_database_dir() -> Path:
    """Directory database/"""
    return get_app_dir() / 'database'


def canonical_filepath(filepath) -> str:
    """Forma canonica di un percorso immagine, per la SCRITTURA nel database.

    Windows consegna la radice di un percorso con maiuscole variabili: la stessa
    cartella di rete arriva come '\\\\MYCLOUD-180438\\ben_Foto' da Esplora
    risorse e '\\\\mycloud-180438\\ben_Foto' dal dialogo di selezione. Sono lo
    stesso posto, ma salvate come stringhe diverse nel campo filepath il
    database le tratta come due cartelle distinte: l'albero di Export e Ricerca
    mostra due radici separate e i filtri per directory ne perdono una metà
    (segnalato da Raul il 21/08/2026: 1304 immagini sotto '\\\\MYCLOUD-...' e 11
    sotto '\\\\mycloud-...').

    Viene abbassata SOLO la radice — nome del server UNC o lettera di unità —
    perché è l'unica parte che nessun sistema operativo distingue per
    maiuscole. Il resto del percorso resta intatto: su Linux '/home/Foto' e
    '/home/foto' sono davvero due cartelle diverse e abbassarle romperebbe
    l'apertura dei file.

    Args:
        filepath: percorso da normalizzare (str o Path)

    Returns:
        str: percorso con la sola radice in minuscolo
    """
    p = Path(filepath)
    radice = p.anchor
    if not radice:
        # Percorso relativo: nessuna radice da normalizzare
        return str(p)
    return radice.lower() + str(p)[len(radice):]
