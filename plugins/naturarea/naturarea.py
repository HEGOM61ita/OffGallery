"""
NaturArea - Core logic
Lookup area protetta (API UNEP-WCMC/ArcGIS) e habitat (ESA WorldCover) per coordinate GPS.
"""

import sqlite3
import json
import logging
import math
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Directory del plugin ───────────────────────────────────────────────────
_PLUGIN_DIR  = Path(__file__).parent
_DATA_DIR    = _PLUGIN_DIR / "data"
_CONFIG_PATH = _PLUGIN_DIR / "config.json"

# ── Endpoint ArcGIS pubblico UNEP-WCMC (nessun token richiesto) ───────────
# Layer 1 = aree terrestri (306k record), Layer 0 = marine (7k record)
_WDPA_API = (
    "https://data-gis.unep-wcmc.org/server/rest/services/ProtectedSites"
    "/The_World_Database_of_Protected_Areas/FeatureServer/{layer}/query"
)
_API_TIMEOUT = 10   # secondi


# ── Interfaccia standard plugin (richiesta da PluginCard) ─────────────────

def load_config() -> dict:
    """Carica config.json del plugin, ritorna dict vuoto se assente."""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    """Salva config.json del plugin."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def is_database_present() -> bool:
    """Compatibilità: NaturArea non richiede più un DB locale — ritorna sempre True."""
    return True


def get_database_date() -> Optional[str]:
    """Compatibilità: ritorna None (nessun DB locale da costruire)."""
    return None


def download_and_build_database(progress_callback=None, status_callback=None, **kwargs) -> None:
    """Compatibilità: NaturArea usa l'API online — nessun database da costruire."""
    if status_callback:
        status_callback("NaturArea usa l'API UNEP-WCMC — nessun database locale necessario.")


# ── Mappatura classi ESA WorldCover → codici canonici habitat ──────────────
ESA_CLASS_TO_HABITAT = {
    10: "tree_cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built_up",
    60: "bare_sparse",
    70: "snow_ice",
    80: "water",
    90: "herbaceous_wetland",
    95: "mangroves",
    100: "moss_lichen",
}

# ── URL base tile ESA WorldCover 2021 ─────────────────────────────────────
ESA_BASE_URL = (
    "https://esa-worldcover.s3.amazonaws.com/v200/2021/map"
    "/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)


# ── Cache locale per lookup area protetta ─────────────────────────────────

def _get_cache_conn(cache_dir: Path) -> sqlite3.Connection:
    """Apre (o crea) il DB di cache per i lookup WDPA."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache_dir / "wdpa_cache.db"))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            lat_r  REAL NOT NULL,
            lon_r  REAL NOT NULL,
            result TEXT NOT NULL,
            PRIMARY KEY (lat_r, lon_r)
        )
    """)
    conn.commit()
    return conn


def _round_coord(v: float) -> float:
    """Arrotonda a 0.01° (~1 km) per chiave cache."""
    return round(v, 2)


# ── Lookup area protetta via API UNEP-WCMC ────────────────────────────────

def _query_wdpa_api(lat: float, lon: float, timeout: int = _API_TIMEOUT) -> str:
    """Interroga l'API ArcGIS UNEP-WCMC per le coordinate date.
    Prova prima il layer terrestre (1), poi marino (0).
    Ritorna il nome dell'area protetta o 'none'."""
    # Converti WGS84 → Web Mercator (EPSG:3857) richiesto dall'API
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    y = y * 20037508.34 / 180.0

    params = urllib.parse.urlencode({
        "geometry":     f"{x:.0f},{y:.0f}",
        "geometryType": "esriGeometryPoint",
        "spatialRel":   "esriSpatialRelIntersects",
        "outFields":    "NAME",
        "returnGeometry": "false",
        "inSR":         "102100",
        "f":            "json",
    })

    for layer in (1, 0):
        url = _WDPA_API.format(layer=layer) + "?" + params
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            features = data.get("features", [])
            if features:
                name = features[0].get("attributes", {}).get("NAME") or \
                       features[0].get("attributes", {}).get("name", "")
                if name:
                    return name
        except Exception as e:
            logger.debug(f"WDPA API layer {layer} errore: {e}")

    return "none"


def lookup_protected_area(lat: float, lon: float,
                           cache_dir: Path,
                           timeout: int = _API_TIMEOUT) -> str:
    """Lookup area protetta con cache locale.
    Prima controlla la cache; se manca, chiama l'API e salva il risultato.
    Ritorna il nome dell'area o 'none'."""
    lat_r = _round_coord(lat)
    lon_r = _round_coord(lon)

    try:
        conn = _get_cache_conn(cache_dir)
        row = conn.execute(
            "SELECT result FROM cache WHERE lat_r=? AND lon_r=?",
            (lat_r, lon_r)
        ).fetchone()

        if row is not None:
            conn.close()
            return row[0]

        # Cache miss — interroga l'API
        result = _query_wdpa_api(lat, lon, timeout)

        conn.execute(
            "INSERT OR REPLACE INTO cache(lat_r, lon_r, result) VALUES (?,?,?)",
            (lat_r, lon_r, result)
        )
        conn.commit()
        conn.close()
        return result

    except Exception as e:
        logger.error(f"Errore lookup area protetta ({lat},{lon}): {e}")
        return "none"


# ── Tile ESA WorldCover ────────────────────────────────────────────────────

def _tile_name(lat: float, lon: float) -> str:
    """Calcola nome tile ESA WorldCover per coordinate.
    Le tile sono 3°×3°, allineate a multipli di 3.
    Formato: S09E039 o N42E012."""
    tile_lat = int(math.floor(lat / 3) * 3)
    tile_lon = int(math.floor(lon / 3) * 3)
    lat_str = f"{'S' if tile_lat < 0 else 'N'}{abs(tile_lat):02d}"
    lon_str = f"{'W' if tile_lon < 0 else 'E'}{abs(tile_lon):03d}"
    return f"{lat_str}{lon_str}"


def _tile_path(tiles_dir: Path, lat: float, lon: float) -> Path:
    """Percorso locale del file tile GeoTIFF.
    Cerca prima nella root del plugin (tile pre-incluse), poi in tiles_dir."""
    filename = f"ESA_WorldCover_{_tile_name(lat, lon)}.tif"
    bundled = _PLUGIN_DIR / filename
    if bundled.exists():
        return bundled
    return tiles_dir / filename


def download_esa_tile(lat: float, lon: float, tiles_dir: Path) -> Optional[Path]:
    """Scarica la tile ESA WorldCover se non già presente in cache.
    Ritorna il percorso locale o None se errore."""
    tile_file = _tile_path(tiles_dir, lat, lon)
    if tile_file.exists():
        return tile_file

    tile_name = _tile_name(lat, lon)
    url = ESA_BASE_URL.format(tile=tile_name)
    tiles_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Download tile ESA WorldCover: {tile_name}")
    tmp_path = tile_file.with_suffix('.tmp')
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(tmp_path, 'wb') as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        tmp_path.rename(tile_file)
        return tile_file
    except Exception as e:
        logger.error(f"Errore download tile {tile_name}: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return None


def _read_geotiff_pixel(tif_path: Path, lat: float, lon: float) -> Optional[int]:
    """Legge il valore del pixel in un GeoTIFF per coordinate lat/lon.
    Implementazione nativa senza dipendenze esterne: usa solo struct e stdlib.
    Supporta GeoTIFF stripped (come ESA WorldCover) con pixel a 1 byte."""
    import struct

    try:
        with open(tif_path, 'rb') as f:

            # ── Intestazione TIFF ─────────────────────────────────────────
            byte_order = f.read(2)
            if byte_order == b'II':
                endian = '<'   # little-endian
            elif byte_order == b'MM':
                endian = '>'   # big-endian
            else:
                logger.error(f"GeoTIFF {tif_path.name}: byte order non valido")
                return None

            magic = struct.unpack(endian + 'H', f.read(2))[0]
            if magic != 42:
                logger.error(f"GeoTIFF {tif_path.name}: magic number non valido ({magic})")
                return None

            ifd_offset = struct.unpack(endian + 'I', f.read(4))[0]

            # ── Lettura IFD ───────────────────────────────────────────────
            f.seek(ifd_offset)
            num_entries = struct.unpack(endian + 'H', f.read(2))[0]

            # Tag TIFF rilevanti
            TAG_IMAGE_WIDTH        = 256
            TAG_IMAGE_LENGTH       = 257
            TAG_BITS_PER_SAMPLE    = 258
            TAG_COMPRESSION        = 259
            TAG_STRIP_OFFSETS      = 273
            TAG_ROWS_PER_STRIP     = 278
            TAG_STRIP_BYTE_COUNTS  = 279
            TAG_SAMPLE_FORMAT      = 339
            TAG_MODEL_PIXEL_SCALE  = 33550   # GeoTIFF
            TAG_MODEL_TIEPOINT     = 33922   # GeoTIFF

            tags = {}
            for _ in range(num_entries):
                entry = f.read(12)
                tag, dtype, count = struct.unpack(endian + 'HHI', entry[:8])
                value_bytes = entry[8:12]

                # Tipo TIFF: 1=BYTE,2=ASCII,3=SHORT,4=LONG,5=RATIONAL,
                #            11=FLOAT,12=DOUBLE
                type_sizes = {1:1, 2:1, 3:2, 4:4, 5:8, 11:4, 12:8}
                type_fmts  = {1:'B', 2:'s', 3:'H', 4:'I', 5:'II', 11:'f', 12:'d'}

                t_size = type_sizes.get(dtype, 0)
                total_bytes = count * t_size

                if total_bytes <= 4:
                    raw = value_bytes[:total_bytes]
                else:
                    offset = struct.unpack(endian + 'I', value_bytes)[0]
                    pos = f.tell()
                    f.seek(offset)
                    raw = f.read(total_bytes)
                    f.seek(pos)

                # Decodifica valore
                fmt = type_fmts.get(dtype)
                if fmt and fmt != 's':
                    vals = struct.unpack(endian + fmt * count, raw)
                    if dtype == 5:   # RATIONAL = coppia numeratore/denominatore
                        vals = tuple(vals[i] / vals[i+1] for i in range(0, len(vals), 2))
                    tags[tag] = vals[0] if count == 1 else list(vals)
                else:
                    tags[tag] = raw

            # ── Parametri immagine ────────────────────────────────────────
            width       = tags.get(TAG_IMAGE_WIDTH)
            height      = tags.get(TAG_IMAGE_LENGTH)
            compression = tags.get(TAG_COMPRESSION, 1)
            bits        = tags.get(TAG_BITS_PER_SAMPLE, 8)

            if compression not in (1, 8):
                logger.warning(f"GeoTIFF {tif_path.name}: compressione {compression} non supportata (solo uncompressed/DEFLATE)")
                return None

            if bits not in (8, 16):
                logger.warning(f"GeoTIFF {tif_path.name}: {bits} bit/pixel non supportati")
                return None

            bytes_per_pixel = bits // 8
            pixel_fmt = endian + ('B' if bits == 8 else 'H')

            # ── Geotrasformazione ─────────────────────────────────────────
            # ModelPixelScaleTag: (ScaleX, ScaleY, ScaleZ)
            # ModelTiepointTag:   (I, J, K, X, Y, Z) — uno o più tiepoint
            pixel_scale = tags.get(TAG_MODEL_PIXEL_SCALE)
            tiepoint    = tags.get(TAG_MODEL_TIEPOINT)

            if not pixel_scale or not tiepoint:
                logger.error(f"GeoTIFF {tif_path.name}: tag geotrasformazione mancanti")
                return None

            if isinstance(pixel_scale, (int, float)):
                pixel_scale = [pixel_scale]
            if isinstance(tiepoint, (int, float)):
                tiepoint = [tiepoint]

            scale_x =  pixel_scale[0]
            scale_y =  pixel_scale[1]
            tie_i   =  tiepoint[0]    # colonna pixel del tiepoint
            tie_j   =  tiepoint[1]    # riga pixel del tiepoint
            tie_x   =  tiepoint[3]    # longitudine del tiepoint
            tie_y   =  tiepoint[4]    # latitudine del tiepoint

            # Converti coordinate geografiche → pixel
            col = int((lon - tie_x) / scale_x + tie_i)
            row = int((tie_y - lat) / scale_y + tie_j)

            if not (0 <= col < width and 0 <= row < height):
                logger.debug(f"Coordinate ({lat},{lon}) fuori dalla tile {tif_path.name}")
                return None

            # ── Lettura pixel da strip ────────────────────────────────────
            rows_per_strip   = tags.get(TAG_ROWS_PER_STRIP, height)
            strip_offsets    = tags.get(TAG_STRIP_OFFSETS)
            strip_bytecounts = tags.get(TAG_STRIP_BYTE_COUNTS)

            if strip_offsets is None:
                logger.error(f"GeoTIFF {tif_path.name}: StripOffsets mancante")
                return None

            # strip_offsets può essere un singolo int o una lista
            if isinstance(strip_offsets, (int, float)):
                strip_offsets = [int(strip_offsets)]
            if isinstance(strip_bytecounts, (int, float)):
                strip_bytecounts = [int(strip_bytecounts)]

            strip_idx    = row // rows_per_strip
            row_in_strip = row % rows_per_strip

            if strip_idx >= len(strip_offsets):
                logger.error(f"GeoTIFF {tif_path.name}: strip index {strip_idx} fuori range")
                return None

            if compression == 1:
                # Uncompressed — lettura diretta con offset
                pixel_offset = (strip_offsets[strip_idx]
                                + (row_in_strip * width + col) * bytes_per_pixel)
                f.seek(pixel_offset)
                raw_pixel = f.read(bytes_per_pixel)
                return struct.unpack(pixel_fmt, raw_pixel)[0]
            else:
                # DEFLATE (compression=8) — decomprimi l'intera strip con zlib
                import zlib
                f.seek(strip_offsets[strip_idx])
                compressed = f.read(strip_bytecounts[strip_idx])
                raw_strip = zlib.decompress(compressed)
                pixel_offset = (row_in_strip * width + col) * bytes_per_pixel
                raw_pixel = raw_strip[pixel_offset: pixel_offset + bytes_per_pixel]
                return struct.unpack(pixel_fmt, raw_pixel)[0]

    except Exception as e:
        logger.error(f"Errore lettura GeoTIFF {tif_path}: {e}")
        return None


def lookup_habitat(lat: float, lon: float, tiles_dir: Path) -> Optional[str]:
    """Lookup habitat ESA WorldCover per coordinate.
    Scarica la tile se necessario. Ritorna codice canonico o None."""
    tile_path = _tile_path(tiles_dir, lat, lon)
    if not tile_path.exists():
        tile_path = download_esa_tile(lat, lon, tiles_dir)
    if not tile_path:
        return None
    pixel_val = _read_geotiff_pixel(tile_path, lat, lon)
    if pixel_val is None:
        return None
    return ESA_CLASS_TO_HABITAT.get(pixel_val)


# ── Elaborazione immagini ──────────────────────────────────────────────────

def process_images(db_path: str, config: dict,
                   image_ids: Optional[list] = None,
                   filter_bioclip: bool = False,
                   unprocessed_only: bool = False,
                   progress_cb=None) -> Tuple[int, int]:
    """Processa le immagini nel DB: lookup area protetta + habitat.

    Returns:
        (matched, not_matched) — foto con almeno un campo scritto, foto senza GPS
    """
    # Cache WDPA nella stessa directory delle tile ESA (o configurabile)
    esa_tiles_dir = Path(config.get("esa_tiles_dir") or _DATA_DIR / "esa_tiles")
    wdpa_cache_dir = Path(config.get("wdpa_cache_dir") or _DATA_DIR)
    tolerance_m = float(config.get("gps_tolerance_m", 50))
    api_timeout = int(config.get("api_timeout", _API_TIMEOUT))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Assicura colonne plugin presenti
    for col_def in ("protected_area TEXT", "habitat TEXT"):
        try:
            conn.execute(f"ALTER TABLE images ADD COLUMN {col_def}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Costruisce query in base ai filtri
    where_clauses = ["gps_latitude IS NOT NULL", "gps_longitude IS NOT NULL"]
    params: list = []
    if filter_bioclip:
        where_clauses.append("bioclip_taxonomy IS NOT NULL")
    if unprocessed_only:
        where_clauses.append("(protected_area IS NULL AND habitat IS NULL)")
    if image_ids:
        placeholders = ','.join('?' * len(image_ids))
        where_clauses.append(f"id IN ({placeholders})")
        params.extend(image_ids)

    where_sql = " AND ".join(where_clauses)
    rows = conn.execute(
        f"SELECT id, gps_latitude, gps_longitude FROM images WHERE {where_sql}",
        params
    ).fetchall()

    total = len(rows)
    matched = 0
    not_matched = 0

    for i, row in enumerate(rows):
        if progress_cb:
            progress_cb(i + 1, total)

        lat = row["gps_latitude"]
        lon = row["gps_longitude"]
        img_id = row["id"]

        area = lookup_protected_area(lat, lon, wdpa_cache_dir, api_timeout)
        hab  = lookup_habitat(lat, lon, esa_tiles_dir)

        if area != "none" or hab is not None:
            matched += 1
        else:
            not_matched += 1

        conn.execute(
            "UPDATE images SET protected_area=?, habitat=? WHERE id=?",
            (area, hab, img_id)
        )

        if i % 50 == 0:
            conn.commit()

    conn.commit()
    conn.close()
    return matched, not_matched
