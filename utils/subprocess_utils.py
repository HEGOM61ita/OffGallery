# Utilità per subprocess cross-platform
import sys


def subprocess_creation_kwargs():
    """Restituisce kwargs extra per subprocess.run() su Windows.

    Su Windows aggiunge CREATE_NO_WINDOW (0x08000000) per evitare
    il flash della finestra console quando si eseguono processi
    come ExifTool. Su macOS/Linux restituisce un dict vuoto.
    """
    if sys.platform == 'win32':
        return {'creationflags': 0x08000000}
    return {}
