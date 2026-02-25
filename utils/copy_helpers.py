"""
Helper per la copia di foto con struttura directory originale.

Compatibile con Windows (drive letter), Linux (/mnt/, /media/) e macOS (/Volumes/).
Non dipende da Qt — logica pura, testabile in isolamento.
"""

import os
import re
import logging
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


def _sanitize_label(name: str) -> str:
    """Rimuove caratteri non sicuri per un nome di directory."""
    sanitized = re.sub(r'[^\w\-.]', '_', name)
    return sanitized or 'volume'


def _get_drive_label(path: Path, dev_id: int) -> str:
    """
    Determina un label leggibile per il device che contiene il path.

    Strategia per sistema operativo:
    - Windows:  usa la drive letter  →  'C_drive', 'D_drive'
    - macOS:    /Volumes/<Nome>       →  '<Nome>'
    - Linux:    /mnt/<nome>           →  '<nome>'
                /media/<user>/<nome>  →  '<nome>'
    - Fallback: 'device_<dev_id>'
    """
    # Windows: path.drive = 'C:', 'D:', ecc.
    if path.drive:
        label = path.drive.replace(':', '').upper()
        return f"{label}_drive"

    parts = path.parts  # Es. ('/', 'Volumes', 'SSD', 'Foto', ...)

    # macOS: /Volumes/<NomeDisco>/...
    if len(parts) >= 3 and parts[1] == 'Volumes':
        return _sanitize_label(parts[2])

    # Linux: /mnt/<nome>/...
    if len(parts) >= 3 and parts[1] == 'mnt':
        return _sanitize_label(parts[2])

    # Linux: /media/<user>/<nome>/...
    if len(parts) >= 4 and parts[1] == 'media':
        return _sanitize_label(parts[3])

    return f"device_{dev_id}"


def compute_common_roots(image_items) -> dict:
    """
    Raggruppa i file per device fisico e calcola la radice comune per ciascun gruppo.

    Usa os.stat().st_dev come identificatore di device — funziona su Windows,
    Linux e macOS senza dipendere da drive letter o mount point.

    Args:
        image_items: Lista di ImageCard con image_data['filepath']

    Returns:
        dict: { st_dev (int): {'common_root': Path, 'drive_label': str} }
              Chiave = device id, valore = info sul gruppo.
    """
    groups: dict[int, list[Path]] = defaultdict(list)

    for item in image_items:
        filepath = item.image_data.get('filepath', '')
        if not filepath:
            continue
        p = Path(filepath)
        if not p.exists():
            logger.warning(f"File non trovato, escluso dal calcolo struttura: {p}")
            continue
        try:
            dev = os.stat(p).st_dev
        except OSError as e:
            logger.warning(f"Impossibile leggere st_dev per {p}: {e}")
            dev = 0
        groups[dev].append(p)

    result = {}
    for dev, paths in groups.items():
        # Radice comune tra le directory dei file di questo device
        dirs = [p.parent for p in paths]
        if len(dirs) == 1:
            common_root = dirs[0]
        else:
            try:
                common_root = Path(os.path.commonpath([str(d) for d in dirs]))
            except ValueError:
                # Impossibile trovare radice comune (es. drive diversi su Windows
                # finiti nello stesso gruppo — caso anomalo)
                common_root = Path(paths[0].anchor)

        drive_label = _get_drive_label(paths[0], dev)

        result[dev] = {
            'common_root': common_root,
            'drive_label': drive_label,
        }
        logger.debug(
            f"Device {dev}: label='{drive_label}', "
            f"radice comune='{common_root}', {len(paths)} file"
        )

    return result


def compute_dest_path(source_path: Path, output_dir: Path, common_roots_info: dict) -> Path:
    """
    Calcola il path di destinazione mantenendo la struttura originale.

    - Un solo device  →  output_dir / percorso_relativo_dalla_radice_comune
    - Più device      →  output_dir / drive_label / percorso_relativo_dalla_radice_comune

    Args:
        source_path:        Path assoluto del file sorgente (deve esistere)
        output_dir:         Directory radice di destinazione
        common_roots_info:  dict ritornato da compute_common_roots()

    Returns:
        Path di destinazione (le directory intermedie non vengono create qui).
    """
    try:
        dev = os.stat(source_path).st_dev
    except OSError:
        dev = 0

    info = common_roots_info.get(dev)
    if not info:
        # Caso anomalo: device non registrato (es. file aggiunto dopo il calcolo)
        logger.warning(
            f"Device non trovato in common_roots_info per {source_path}, "
            "uso nome file nella root di destinazione"
        )
        return output_dir / source_path.name

    common_root: Path = info['common_root']
    drive_label: str = info['drive_label']
    multi_device: bool = len(common_roots_info) > 1

    try:
        rel = source_path.relative_to(common_root)
    except ValueError:
        # Il file non è sotto la radice comune (caso anomalo)
        logger.warning(
            f"File {source_path} non è sotto la radice comune {common_root}, "
            "uso solo il nome file"
        )
        rel = Path(source_path.name)

    if multi_device:
        return output_dir / drive_label / rel
    else:
        return output_dir / rel
