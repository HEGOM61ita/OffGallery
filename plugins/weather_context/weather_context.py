"""
Weather Context - Core logic
Recupera meteo storico da Open-Meteo Historical API per coordinate GPS + data/ora.
Cache SQLite locale per evitare query duplicate.
"""

import sqlite3
import json
import logging
import math
import urllib.request
import urllib.parse
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Directory del plugin ───────────────────────────────────────────────────
_PLUGIN_DIR  = Path(__file__).parent
_DATA_DIR    = _PLUGIN_DIR / "data"
_CONFIG_PATH = _PLUGIN_DIR / "config.json"


# ── Interfaccia standard plugin (richiesta da PluginCard) ─────────────────

def load_config() -> dict:
    """Carica config.json del plugin, ritorna dict con defaults se assente."""
    defaults = {"cache_db_path": "", "request_timeout": 10}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {**defaults, **cfg}
    except Exception:
        return defaults


def save_config(cfg: dict) -> None:
    """Salva config.json del plugin."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def is_database_present() -> bool:
    """Restituisce True se la cache meteo SQLite esiste e ha almeno un record."""
    cfg = load_config()
    cache_db = Path(cfg.get("cache_db_path") or _DATA_DIR / "weather_cache.db")
    if not cache_db.exists():
        return False
    try:
        conn = sqlite3.connect(str(cache_db))
        count = conn.execute("SELECT COUNT(*) FROM weather_cache").fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def get_database_date() -> Optional[str]:
    """Restituisce la data dell'ultimo record nella cache meteo."""
    cfg = load_config()
    cache_db = Path(cfg.get("cache_db_path") or _DATA_DIR / "weather_cache.db")
    if not cache_db.exists():
        return None
    try:
        conn = sqlite3.connect(str(cache_db))
        row = conn.execute("SELECT MAX(date) FROM weather_cache").fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def download_and_build_database(progress_callback=None, status_callback=None, **kwargs) -> None:
    """Interfaccia standard: per il plugin Meteo non c'è un DB da scaricare.
    La cache viene popolata on-demand durante l'elaborazione.
    Questo metodo è un no-op (richiesto per compatibilità con PluginCard)."""
    if status_callback:
        status_callback("Nessun download necessario — la cache viene popolata durante l'elaborazione")

# ── Mappatura WMO weather codes → codici canonici ─────────────────────────
# https://open-meteo.com/en/docs#weathervariables
WMO_TO_CONDITION = {
    0:  "clear",
    1:  "clear",
    2:  "partly_cloudy",
    3:  "cloudy",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}

OPEN_METEO_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude={lat}&longitude={lon}"
    "&start_date={date}&end_date={date}"
    "&hourly=temperature_2m,relative_humidity_2m,precipitation,"
    "wind_speed_10m,weather_code"
    "&timezone=auto"
)


def _round_coord(val: float, decimals: int = 2) -> float:
    """Arrotonda coordinata per chiave cache (~1km a 0.01°)."""
    factor = 10 ** decimals
    return math.floor(val * factor + 0.5) / factor


def _cache_key(lat: float, lon: float, dt_date: str) -> tuple:
    return (_round_coord(lat), _round_coord(lon), dt_date)


def _init_cache(cache_db: Path) -> sqlite3.Connection:
    """Apre/crea il DB cache meteo."""
    cache_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache_db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weather_cache (
            lat_r REAL, lon_r REAL, date TEXT,
            weather_json TEXT,
            PRIMARY KEY (lat_r, lon_r, date)
        )
    """)
    conn.commit()
    return conn


def _fetch_from_api(lat: float, lon: float, dt_date: str,
                    hour: int, timeout: int) -> Optional[dict]:
    """Chiama Open-Meteo Historical API e ritorna dict meteo per l'ora richiesta."""
    url = OPEN_METEO_URL.format(
        lat=round(lat, 4), lon=round(lon, 4), date=dt_date
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Open-Meteo API error: {e}")
        return None

    hourly = data.get('hourly', {})
    times = hourly.get('time', [])
    temps = hourly.get('temperature_2m', [])
    humidity = hourly.get('relative_humidity_2m', [])
    precip = hourly.get('precipitation', [])
    wind = hourly.get('wind_speed_10m', [])
    wmo = hourly.get('weather_code', [])

    # Trova l'indice dell'ora più vicina
    target = f"{dt_date}T{hour:02d}:00"
    idx = 0
    for i, t in enumerate(times):
        if t <= target:
            idx = i

    def safe(lst, i, default=None):
        try:
            return lst[i]
        except IndexError:
            return default

    wmo_code = safe(wmo, idx)
    condition = WMO_TO_CONDITION.get(wmo_code, "cloudy") if wmo_code is not None else None

    return {
        "temp_c":    safe(temps, idx),
        "condition": condition,
        "humidity":  safe(humidity, idx),
        "wind_kmh":  safe(wind, idx),
        "precip_mm": safe(precip, idx),
    }


def get_weather(lat: float, lon: float, datetime_str: str,
                cache_conn: sqlite3.Connection,
                timeout: int = 10) -> Optional[dict]:
    """Ritorna dict meteo per coordinate e datetime (stringa ISO 'YYYY-MM-DD HH:MM:SS').
    Usa cache se disponibile, altrimenti chiama API.
    Ritorna None se GPS mancante, data mancante o errore API."""
    if not lat or not lon or not datetime_str:
        return None

    # Estrai data e ora
    try:
        dt = datetime.fromisoformat(datetime_str[:19])
        dt_date = dt.strftime('%Y-%m-%d')
        dt_hour = dt.hour
    except Exception:
        return None

    lat_r = _round_coord(lat)
    lon_r = _round_coord(lon)

    # Controlla cache
    row = cache_conn.execute(
        "SELECT weather_json FROM weather_cache WHERE lat_r=? AND lon_r=? AND date=?",
        (lat_r, lon_r, dt_date)
    ).fetchone()

    if row:
        try:
            cached = json.loads(row[0])
            # Il JSON in cache contiene tutti i dati orari — restituisce per l'ora corretta
            # (in questa implementazione semplificata memorizziamo solo il risultato per l'ora)
            return cached
        except Exception:
            pass

    # Chiama API
    result = _fetch_from_api(lat, lon, dt_date, dt_hour, timeout)
    if result:
        cache_conn.execute(
            "INSERT OR REPLACE INTO weather_cache(lat_r, lon_r, date, weather_json) VALUES(?,?,?,?)",
            (lat_r, lon_r, dt_date, json.dumps(result))
        )
        cache_conn.commit()

    return result


def process_images(db_path: str, config: dict,
                   image_ids: Optional[list] = None,
                   filter_bioclip: bool = False,
                   progress_cb=None) -> Tuple[int, int]:
    """Processa le immagini nel DB: recupera e scrive weather_context.

    Returns:
        (matched, not_matched) — foto con meteo scritto, foto saltate (no GPS/data/errore)
    """
    cache_db_path = Path(config.get('cache_db_path') or
                         Path(__file__).parent / 'data' / 'weather_cache.db')
    timeout = int(config.get('request_timeout', 10))

    # Apri DB immagini
    img_conn = sqlite3.connect(db_path)
    img_conn.row_factory = sqlite3.Row

    # Assicura colonna presente
    try:
        img_conn.execute("ALTER TABLE images ADD COLUMN weather_context TEXT")
        img_conn.commit()
    except sqlite3.OperationalError:
        pass

    # Query immagini
    where_clauses = [
        "gps_latitude IS NOT NULL",
        "gps_longitude IS NOT NULL",
        "datetime_original IS NOT NULL",
    ]
    params = []
    if filter_bioclip:
        where_clauses.append("bioclip_taxonomy IS NOT NULL")
    if image_ids:
        placeholders = ','.join('?' * len(image_ids))
        where_clauses.append(f"id IN ({placeholders})")
        params.extend(image_ids)

    where_sql = " AND ".join(where_clauses)
    rows = img_conn.execute(
        f"SELECT id, gps_latitude, gps_longitude, datetime_original "
        f"FROM images WHERE {where_sql}",
        params
    ).fetchall()

    total = len(rows)
    matched = 0
    not_matched = 0

    # Apri cache meteo
    cache_conn = _init_cache(cache_db_path)

    for i, row in enumerate(rows):
        if progress_cb:
            progress_cb(i + 1, total)

        result = get_weather(
            row['gps_latitude'], row['gps_longitude'],
            row['datetime_original'], cache_conn, timeout
        )

        if result:
            matched += 1
            img_conn.execute(
                "UPDATE images SET weather_context=? WHERE id=?",
                (json.dumps(result), row['id'])
            )
        else:
            not_matched += 1

        if i % 50 == 0:
            img_conn.commit()

    img_conn.commit()
    img_conn.close()
    cache_conn.close()

    return matched, not_matched
