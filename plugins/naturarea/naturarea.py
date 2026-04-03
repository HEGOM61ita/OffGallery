"""
NaturArea - Core logic
Lookup area protetta (WDPA) e habitat (ESA WorldCover) per coordinate GPS.
"""

import sqlite3
import json
import logging
import math
import os
import struct
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Directory del plugin ───────────────────────────────────────────────────
_PLUGIN_DIR = Path(__file__).parent
_DATA_DIR   = _PLUGIN_DIR / "data"
_CONFIG_PATH = _PLUGIN_DIR / "config.json"


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
    """Restituisce True se il DB WDPA è presente e non vuoto."""
    cfg = load_config()
    wdpa_db = Path(cfg.get("wdpa_db_path") or _DATA_DIR / "wdpa.db")
    return wdpa_db.exists() and wdpa_db.stat().st_size > 1024


def get_database_date() -> Optional[str]:
    """Restituisce la data di build del DB WDPA (da metadata nel DB) o stringa mtime."""
    cfg = load_config()
    wdpa_db = Path(cfg.get("wdpa_db_path") or _DATA_DIR / "wdpa.db")
    if not wdpa_db.exists():
        return None
    try:
        conn = sqlite3.connect(str(wdpa_db))
        row = conn.execute("SELECT value FROM metadata WHERE key='build_date'").fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
    # Fallback: data modifica file
    try:
        mtime = wdpa_db.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except Exception:
        return None


def download_and_build_database(progress_callback=None, status_callback=None, **kwargs) -> None:
    """Interfaccia standard: scarica e costruisce il DB WDPA.
    Nota: NaturArea richiede che l'utente fornisca un file GeoJSON sorgente
    tramite ConfigDialog — questo metodo viene chiamato DOPO che l'utente
    ha scelto il file sorgente e impostato il percorso in config.json.
    """
    cfg = load_config()
    source_path = cfg.get("wdpa_source_path", "")
    output_db   = Path(cfg.get("wdpa_db_path") or _DATA_DIR / "wdpa.db")

    if not source_path or not Path(source_path).exists():
        if status_callback:
            status_callback("Errore: file sorgente WDPA non configurato")
        raise FileNotFoundError(f"File sorgente WDPA non trovato: {source_path}")

    if status_callback:
        status_callback("Costruzione database WDPA...")

    output_db.parent.mkdir(parents=True, exist_ok=True)
    ok = build_wdpa_sqlite(
        source_path=Path(source_path),
        output_db=output_db,
        progress_cb=progress_callback,
    )

    if ok:
        # Salva data di build nel DB
        try:
            conn = sqlite3.connect(str(output_db))
            conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR REPLACE INTO metadata VALUES ('build_date', ?)",
                         (datetime.now().strftime("%Y-%m-%d"),))
            conn.commit()
            conn.close()
        except Exception:
            pass
        if status_callback:
            status_callback("Database WDPA costruito con successo")
    else:
        raise RuntimeError("Errore durante la costruzione del database WDPA")

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

# ── URL base per download tile ESA WorldCover 2021 ─────────────────────────
# Tile naming: ESA_WorldCover_10m_2021_v200_<LAT><LON>_Map.tif
ESA_BASE_URL = "https://esa-worldcover.s3.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"

# ── URL WDPA (versione CSV semplificata, più leggera del GDB) ──────────────
WDPA_SQLITE_URL = "https://d1gam3xoknrgr2.cloudfront.net/current/WDPA_WDOECM_marine0_Oct2024_Public_shp.zip"


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
    """Percorso locale del file tile GeoTIFF."""
    return tiles_dir / f"ESA_WorldCover_{_tile_name(lat, lon)}.tif"


def download_esa_tile(lat: float, lon: float, tiles_dir: Path) -> Optional[Path]:
    """Scarica la tile ESA WorldCover se non già presente in cache.
    Ritorna il percorso locale o None se errore."""
    tile_file = _tile_path(tiles_dir, lat, lon)
    if tile_file.exists():
        return tile_file

    tile_name = _tile_name(lat, lon)
    url = ESA_BASE_URL.format(tile=tile_name)
    tiles_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Download tile ESA WorldCover: {tile_name} da {url}")
    try:
        tmp_path = tile_file.with_suffix('.tmp')
        with urllib.request.urlopen(url, timeout=60) as resp, open(tmp_path, 'wb') as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        tmp_path.rename(tile_file)
        logger.info(f"Tile salvata: {tile_file}")
        return tile_file
    except Exception as e:
        logger.error(f"Errore download tile {tile_name}: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return None


def _read_geotiff_pixel(tif_path: Path, lat: float, lon: float) -> Optional[int]:
    """Legge il valore del pixel in un GeoTIFF per coordinate lat/lon.
    Implementazione minimale senza rasterio/gdal: legge header GeoTIFF
    e calcola l'offset pixel usando i tag di geotrasformazione.
    Ritorna il valore intero del pixel o None se errore."""
    try:
        # Usa rasterio se disponibile (più robusto)
        try:
            import rasterio
            with rasterio.open(tif_path) as src:
                row, col = src.index(lon, lat)
                if 0 <= row < src.height and 0 <= col < src.width:
                    val = src.read(1)[row, col]
                    return int(val)
                return None
        except ImportError:
            pass

        # Fallback: usa GDAL via osgeo se disponibile
        try:
            from osgeo import gdal
            ds = gdal.Open(str(tif_path))
            gt = ds.GetGeoTransform()
            # gt[0]=lon_min, gt[1]=pixel_width, gt[3]=lat_max, gt[5]=pixel_height (negativo)
            col = int((lon - gt[0]) / gt[1])
            row = int((lat - gt[3]) / gt[5])
            band = ds.GetRasterBand(1)
            if 0 <= col < ds.RasterXSize and 0 <= row < ds.RasterYSize:
                val = band.ReadAsArray(col, row, 1, 1)[0][0]
                return int(val)
            return None
        except ImportError:
            pass

        logger.warning("rasterio e gdal non disponibili — lookup habitat non possibile")
        return None

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


def lookup_protected_area(lat: float, lon: float, wdpa_db: Path,
                           tolerance_m: float = 50.0) -> str:
    """Lookup area protetta WDPA per coordinate.
    Ritorna il nome dell'area o 'none' se il punto non cade in nessuna area.
    Usa R-tree spaziale nel DB SQLite per lookup efficiente."""
    if not wdpa_db.exists():
        return "none"

    try:
        conn = sqlite3.connect(str(wdpa_db))
        # Converti tolleranza in gradi (~111km per grado latitudine)
        tol_deg = tolerance_m / 111000.0

        # Ricerca con bounding box prima (veloce), poi point-in-polygon (precisa)
        cursor = conn.execute("""
            SELECT name, geom_wkt
            FROM protected_areas
            WHERE min_lat <= ? AND max_lat >= ?
              AND min_lon <= ? AND max_lon >= ?
            LIMIT 50
        """, (lat + tol_deg, lat - tol_deg,
              lon + tol_deg, lon - tol_deg))

        candidates = cursor.fetchall()
        conn.close()

        if not candidates:
            return "none"

        # Point-in-polygon con shapely se disponibile
        try:
            from shapely.geometry import Point
            from shapely import wkt as shapely_wkt
            pt = Point(lon, lat)
            for name, geom_wkt in candidates:
                if geom_wkt:
                    try:
                        poly = shapely_wkt.loads(geom_wkt)
                        if poly.buffer(tol_deg).contains(pt):
                            return name
                    except Exception:
                        continue
            return "none"
        except ImportError:
            # Senza shapely: usa solo bounding box (meno preciso)
            if candidates:
                return candidates[0][0]
            return "none"

    except Exception as e:
        logger.error(f"Errore lookup WDPA: {e}")
        return "none"


def build_wdpa_sqlite(source_path: Path, output_db: Path,
                      progress_cb=None) -> bool:
    """Costruisce il DB SQLite ottimizzato da sorgente WDPA (GeoJSON o CSV).
    Crea tabella con bounding box pre-calcolati per lookup rapido.
    progress_cb(current, total) chiamato periodicamente."""
    try:
        import json as _json

        conn = sqlite3.connect(str(output_db))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS protected_areas (
                id INTEGER PRIMARY KEY,
                name TEXT,
                wdpaid TEXT,
                iucn_cat TEXT,
                geom_wkt TEXT,
                min_lat REAL, max_lat REAL,
                min_lon REAL, max_lon REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bbox ON protected_areas(min_lat,max_lat,min_lon,max_lon)")

        # Carica da GeoJSON
        logger.info(f"Costruzione WDPA DB da {source_path}...")
        with open(source_path, 'r', encoding='utf-8') as f:
            data = _json.load(f)

        features = data.get('features', [])
        total = len(features)
        inserted = 0

        for i, feat in enumerate(features):
            if progress_cb and i % 1000 == 0:
                progress_cb(i, total)
            try:
                props = feat.get('properties', {})
                name = props.get('NAME', props.get('name', ''))
                wdpaid = str(props.get('WDPAID', ''))
                iucn_cat = props.get('IUCN_CAT', '')
                geom = feat.get('geometry')
                if not geom or not name:
                    continue

                # Calcola bounding box dalla geometria
                coords = _extract_coords(geom)
                if not coords:
                    continue
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]

                # WKT semplificato (solo per point-in-polygon di shapely)
                from shapely.geometry import shape as shapely_shape
                try:
                    geom_wkt = shapely_shape(geom).wkt
                except Exception:
                    geom_wkt = None

                conn.execute(
                    "INSERT INTO protected_areas(name,wdpaid,iucn_cat,geom_wkt,min_lat,max_lat,min_lon,max_lon) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (name, wdpaid, iucn_cat, geom_wkt,
                     min(lats), max(lats), min(lons), max(lons))
                )
                inserted += 1
                if inserted % 5000 == 0:
                    conn.commit()
            except Exception:
                continue

        conn.commit()
        conn.close()
        logger.info(f"WDPA DB costruito: {inserted} aree protette in {output_db}")
        if progress_cb:
            progress_cb(total, total)
        return True

    except Exception as e:
        logger.error(f"Errore build_wdpa_sqlite: {e}")
        return False


def _extract_coords(geom: dict) -> list:
    """Estrae lista di (lon, lat) da geometria GeoJSON (qualsiasi tipo)."""
    gtype = geom.get('type', '')
    coords = geom.get('coordinates', [])

    def _flatten(c, depth=0):
        if not c:
            return []
        if isinstance(c[0], (int, float)):
            return [c[:2]]
        result = []
        for item in c:
            result.extend(_flatten(item, depth + 1))
        return result

    return _flatten(coords)


def process_images(db_path: str, config: dict,
                   image_ids: Optional[list] = None,
                   filter_bioclip: bool = False,
                   unprocessed_only: bool = False,
                   progress_cb=None) -> Tuple[int, int]:
    """Processa le immagini nel DB: lookup area protetta + habitat.

    Args:
        db_path: percorso database OffGallery
        config: dizionario configurazione plugin
        image_ids: lista ID specifici (None = tutte le immagini con GPS)
        filter_bioclip: se True, processa solo foto con bioclip_taxonomy non NULL
        progress_cb: callback(current, total)

    Returns:
        (matched, not_matched) — foto con almeno un campo scritto, foto senza GPS
    """
    wdpa_db_path = Path(config.get('wdpa_db_path') or
                        Path(__file__).parent / 'data' / 'wdpa.db')
    esa_tiles_dir = Path(config.get('esa_tiles_dir') or
                         Path(__file__).parent / 'data' / 'esa_tiles')
    tolerance_m = float(config.get('gps_tolerance_m', 50))

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
    params = []
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

        lat = row['gps_latitude']
        lon = row['gps_longitude']
        img_id = row['id']

        area = lookup_protected_area(lat, lon, wdpa_db_path, tolerance_m)
        hab = lookup_habitat(lat, lon, esa_tiles_dir)

        if area or hab:
            matched += 1
        else:
            not_matched += 1

        conn.execute(
            "UPDATE images SET protected_area=?, habitat=? WHERE id=?",
            (area or "none", hab, img_id)
        )

        if i % 50 == 0:
            conn.commit()

    conn.commit()
    conn.close()
    return matched, not_matched
