"""
Cache locale per thumbnail gallery (150px JPEG).
Popolata durante il processing, letta in gallery per evitare ExifTool.
"""
import hashlib
import logging
from pathlib import Path
from typing import Optional
from utils.paths import get_app_dir

logger = logging.getLogger(__name__)

# Dimensione thumbnail gallery — deve corrispondere a ImageCard.THUMB_SIZE
THUMB_CACHE_SIZE = 150


def get_thumb_cache_dir() -> Path:
    """Directory cache thumbnail: {app_dir}/cache/thumbs/"""
    cache_dir = get_app_dir() / "cache" / "thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_path(filepath: Path) -> Path:
    """
    Percorso file cache per un'immagine.

    Chiave = SHA256(percorso_assoluto_completo) → univocità garantita.
    Due file con lo stesso nome in directory diverse producono hash diversi:
        /foto/2024/IMG_001.NEF → sha256("/foto/2024/IMG_001.NEF")[:24] → a3f8c2d9b1e4...jpg
        /backup/IMG_001.NEF   → sha256("/backup/IMG_001.NEF")[:24]    → 7b2e4f8a1c3d...jpg

    filepath.resolve() normalizza a percorso assoluto canonico (segue symlink).
    Nessuna dipendenza dal nome file, nessun conflitto tra directory diverse.
    """
    key = hashlib.sha256(str(filepath.resolve()).encode()).hexdigest()[:24]
    return get_thumb_cache_dir() / f"{key}.jpg"


def save_gallery_thumb(filepath: Path, pil_image) -> bool:
    """
    Salva thumbnail 150px da PIL Image nella cache.
    Chiamato durante il processing dopo estrazione cached_thumbnail.

    Args:
        filepath: Path assoluto del file originale (usato come chiave cache)
        pil_image: PIL.Image già estratta dal processing (qualsiasi dimensione)

    Returns:
        True se salvato con successo, False altrimenti
    """
    try:
        from PIL import Image
        img = pil_image.copy()
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.thumbnail((THUMB_CACHE_SIZE, THUMB_CACHE_SIZE), Image.Resampling.LANCZOS)
        dest = _cache_path(filepath)
        img.save(str(dest), 'JPEG', quality=82, optimize=True)
        logger.debug(f"Thumbnail cache salvata: {filepath.name} → {dest.name}")
        return True
    except Exception as e:
        logger.warning(f"Impossibile salvare thumbnail cache per {filepath.name}: {e}")
        return False


def load_gallery_thumb_bytes(filepath: Path) -> Optional[bytes]:
    """
    Legge bytes JPEG dalla cache (veloce, ~5ms).

    Args:
        filepath: Path assoluto del file originale

    Returns:
        bytes JPEG se in cache, None altrimenti (cache miss)
    """
    try:
        dest = _cache_path(filepath)
        if dest.exists():
            return dest.read_bytes()
    except Exception as e:
        logger.debug(f"Cache miss o errore per {filepath.name}: {e}")
    return None
