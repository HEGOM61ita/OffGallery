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

# Estensioni RAW — le anteprime estratte da ExifTool sono già pre-ruotate
# dalla camera, quindi NON leggiamo orientazione dal file principale
_RAW_EXT = {'.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2',
            '.pef', '.dng', '.nrw', '.srf', '.sr2', '.raf', '.rw1'}

# Mappatura EXIF Orientation → operazioni PIL da applicare
_EXIF_OPS = {
    2: ['FLIP_LEFT_RIGHT'],
    3: ['ROTATE_180'],
    4: ['FLIP_TOP_BOTTOM'],
    5: ['FLIP_LEFT_RIGHT', 'ROTATE_90'],
    6: ['ROTATE_270'],
    7: ['FLIP_LEFT_RIGHT', 'ROTATE_270'],
    8: ['ROTATE_90'],
}


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


def _read_orientation_from_file(filepath: Path) -> int:
    """
    Legge il tag EXIF Orientation (0x0112) dal file originale.

    Strategia:
    - File RAW: restituisce 1 senza lettura — le anteprime estratte da ExifTool
      sono già pre-ruotate dalla camera; leggere dal file principale causerebbe
      doppia rotazione.
    - JPEG/TIFF: PIL legge solo l'header (lazy, ~1ms), nessun subprocess.
    - Fallback ExifTool se PIL non riesce (es. HEIC, formati esotici).

    Returns:
        Valore EXIF Orientation (1 = nessuna rotazione, 6 = 90° CW, ecc.)
    """
    if filepath.suffix.lower() in _RAW_EXT:
        return 1  # Anteprima RAW già pre-ruotata dalla camera

    # PIL lazy-open: legge solo header/EXIF senza decodificare i pixel
    try:
        from PIL import Image
        with Image.open(str(filepath)) as img:
            orientation = img.getexif().get(0x0112, 1)
            if orientation:
                return int(orientation)
    except Exception:
        pass

    # Fallback ExifTool per formati che PIL non legge (HEIC, ecc.)
    try:
        import subprocess
        result = subprocess.run(
            ['exiftool', '-Orientation#', '-s3', str(filepath)],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except Exception:
        pass

    return 1


def _apply_orientation(img, orientation: int):
    """Applica rotazione PIL corrispondente al valore EXIF Orientation."""
    from PIL import Image
    ops = _EXIF_OPS.get(orientation, [])
    for op_name in ops:
        img = img.transpose(getattr(Image.Transpose, op_name))
    return img


def save_gallery_thumb(filepath: Path, pil_image) -> bool:
    """
    Salva thumbnail 150px da PIL Image nella cache.
    Chiamato durante il processing dopo estrazione cached_thumbnail,
    oppure dal fallback asincrono in gallery_widgets.

    La correzione orientazione EXIF viene applicata leggendo il tag
    direttamente dal FILE ORIGINALE (non dal pil_image, che spesso non ha
    EXIF dopo l'estrazione via ExifTool/rawpy/convert).

    Args:
        filepath: Path assoluto del file originale (chiave cache + sorgente EXIF)
        pil_image: PIL.Image già estratta (qualsiasi dimensione, EXIF non necessario)

    Returns:
        True se salvato con successo, False altrimenti
    """
    try:
        from PIL import Image
        img = pil_image.copy()
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        # Corregge orientazione leggendo dal file originale.
        # Non usiamo ImageOps.exif_transpose(pil_image) perché il pil_image
        # estratto da RAW processor / ExifTool spesso non porta EXIF con sé.
        orientation = _read_orientation_from_file(filepath)
        if orientation and orientation != 1:
            img = _apply_orientation(img, orientation)
            logger.debug(f"Orientazione EXIF corretta: tag={orientation} → {filepath.name}")

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
