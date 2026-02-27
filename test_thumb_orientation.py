"""
Test standalone: estrazione e correzione orientazione thumbnail.

Legge da:  INPUT_CACHE/   (metti qui le immagini da testare)
Salva in:  TEST_CASH/     (thumbnail 150px, corretti o no)

Output per ogni file:
  - Orientazione EXIF rilevata
  - Se la correzione è stata applicata
  - Dimensione del thumbnail risultante
  - Eventuale errore

Uso:
    conda activate OffGallery
    python test_thumb_orientation.py
"""

import subprocess
import sys
from pathlib import Path
from io import BytesIO

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------
INPUT_DIR  = Path("INPUT_CACHE")
OUTPUT_DIR = Path("TEST_CASH")
THUMB_SIZE = 150

RAW_EXT = {'.cr2', '.cr3', '.nef', '.arw', '.orf', '.rw2',
           '.pef', '.dng', '.nrw', '.srf', '.sr2', '.raf', '.rw1'}
JPEG_EXT = {'.jpg', '.jpeg', '.tif', '.tiff', '.png', '.heic', '.webp'}
ALL_EXT  = RAW_EXT | JPEG_EXT

# Mappatura EXIF Orientation → operazioni PIL
from PIL import Image
_OPS = {
    2: [Image.Transpose.FLIP_LEFT_RIGHT],
    3: [Image.Transpose.ROTATE_180],
    4: [Image.Transpose.FLIP_TOP_BOTTOM],
    5: [Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_90],
    6: [Image.Transpose.ROTATE_270],
    7: [Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_270],
    8: [Image.Transpose.ROTATE_90],
}
_OPS_DESC = {
    1: "normale",
    2: "flip orizzontale",
    3: "180°",
    4: "flip verticale",
    5: "flip + 90° CW",
    6: "90° CW (portrait)",
    7: "flip + 90° CCW",
    8: "90° CCW (portrait)",
}


# ---------------------------------------------------------------------------
# Estrazione thumbnail
# ---------------------------------------------------------------------------

def extract_jpeg_thumbnail(filepath: Path) -> tuple:
    """
    Estrae thumbnail da file JPEG/PNG/TIFF con PIL.
    Ritorna (pil_image, orientation, source_desc).
    """
    img = Image.open(str(filepath))
    img.load()

    # Leggi orientazione EXIF
    orientation = 1
    try:
        orientation = int(img.getexif().get(0x0112, 1) or 1)
    except Exception:
        pass

    return img, orientation, "PIL direct"


def extract_raw_thumbnail(filepath: Path) -> tuple:
    """
    Estrae thumbnail da file RAW via ExifTool (stesso ordine di OffGallery).
    Prova: PreviewImage → ThumbnailImage.
    Ritorna (pil_image, orientation, source_desc).
    """
    # Leggi orientazione dal file RAW via ExifTool
    orientation = 1
    try:
        res = subprocess.run(
            ['exiftool', '-Orientation#', '-s3', str(filepath)],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            orientation = int(res.stdout.strip())
    except Exception:
        pass

    # Estrai preview JPEG embedded
    for tag, desc in [('-PreviewImage', 'PreviewImage'), ('-ThumbnailImage', 'ThumbnailImage')]:
        try:
            res = subprocess.run(
                ['exiftool', '-b', tag, str(filepath)],
                capture_output=True, timeout=15
            )
            if res.returncode == 0 and res.stdout and len(res.stdout) > 500:
                img = Image.open(BytesIO(res.stdout))
                img.load()

                # Controlla se la preview ha già la propria orientazione
                preview_orientation = 1
                try:
                    preview_orientation = int(img.getexif().get(0x0112, 1) or 1)
                except Exception:
                    pass

                print(f"    Preview orientation tag: {preview_orientation} "
                      f"| RAW main orientation: {orientation}")

                # Se la preview ha già la propria orientazione, usala
                # (alcune camere pre-ruotano la preview: orientation tag = 1)
                # Se la preview non ha orientazione, usa quella del file RAW
                effective_orientation = preview_orientation if preview_orientation != 1 else orientation

                return img, effective_orientation, desc
        except Exception as e:
            print(f"    ExifTool {tag} fallito: {e}")
            continue

    raise RuntimeError("Nessuna preview estraibile dal RAW")


# ---------------------------------------------------------------------------
# Correzione orientazione
# ---------------------------------------------------------------------------

def apply_orientation(img: Image.Image, orientation: int) -> Image.Image:
    """Applica rotazione PIL corrispondente al tag EXIF Orientation."""
    ops = _OPS.get(orientation, [])
    for op in ops:
        img = img.transpose(op)
    return img


# ---------------------------------------------------------------------------
# Pipeline principale
# ---------------------------------------------------------------------------

def process_file(filepath: Path, output_dir: Path) -> dict:
    """
    Elabora un file: estrae thumbnail, corregge orientazione, salva.
    Ritorna dict con risultati.
    """
    result = {
        'file': filepath.name,
        'orientation': 1,
        'corrected': False,
        'source': '',
        'output_size': None,
        'error': None,
    }

    try:
        is_raw = filepath.suffix.lower() in RAW_EXT

        if is_raw:
            img, orientation, source = extract_raw_thumbnail(filepath)
        else:
            img, orientation, source = extract_jpeg_thumbnail(filepath)

        result['orientation'] = orientation
        result['source'] = source

        # Correggi se necessario
        if orientation and orientation != 1:
            img = apply_orientation(img, orientation)
            result['corrected'] = True

        # Converti e ridimensiona
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)

        # Salva — nome file = originale + suffisso _thumb
        out_name = filepath.stem + "_thumb.jpg"
        out_path = output_dir / out_name
        img.save(str(out_path), 'JPEG', quality=85)

        result['output_size'] = img.size

    except Exception as e:
        result['error'] = str(e)

    return result


def main():
    print("=" * 60)
    print("  Test Estrazione Thumbnail + Orientazione EXIF")
    print("=" * 60)

    # Crea/verifica directory
    if not INPUT_DIR.exists():
        INPUT_DIR.mkdir(parents=True)
        print(f"\n[ATTENZIONE] Creata {INPUT_DIR}/ — metti qui le immagini da testare.")
        print("Poi rilancia lo script.")
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Scansiona INPUT_CACHE
    files = sorted([f for f in INPUT_DIR.iterdir()
                    if f.is_file() and f.suffix.lower() in ALL_EXT])

    if not files:
        print(f"\nNessun file supportato in {INPUT_DIR}/")
        print(f"Estensioni supportate: {', '.join(sorted(ALL_EXT))}")
        sys.exit(0)

    print(f"\nFile trovati: {len(files)}")
    print(f"Output:       {OUTPUT_DIR}/\n")

    ok = 0
    errors = 0

    for filepath in files:
        print(f"▶ {filepath.name}")
        print(f"    Tipo: {'RAW' if filepath.suffix.lower() in RAW_EXT else 'JPEG/altro'}")

        result = process_file(filepath, OUTPUT_DIR)

        ori = result['orientation']
        ori_desc = _OPS_DESC.get(ori, f"sconosciuto ({ori})")
        print(f"    Orientazione EXIF: {ori} ({ori_desc})")
        print(f"    Sorgente preview:  {result['source']}")

        if result['error']:
            print(f"    ❌ ERRORE: {result['error']}")
            errors += 1
        else:
            corrected = "✅ corretta" if result['corrected'] else "— nessuna rotazione"
            print(f"    Correzione:  {corrected}")
            print(f"    Output:      {filepath.stem}_thumb.jpg  {result['output_size']}")
            ok += 1

        print()

    print("=" * 60)
    print(f"  Completato: {ok} OK, {errors} errori")
    print(f"  Thumbnail in: {OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == '__main__':
    main()
