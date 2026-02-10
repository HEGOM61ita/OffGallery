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


def get_models_dir() -> Path:
    """Directory per modelli AI (aesthetic/, brisque_models/)"""
    return get_app_dir()


def get_config_path() -> Path:
    """Path del file config_new.yaml"""
    return get_app_dir() / 'config_new.yaml'


def get_database_dir() -> Path:
    """Directory database/"""
    return get_app_dir() / 'database'
