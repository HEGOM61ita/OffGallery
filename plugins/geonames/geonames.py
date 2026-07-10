"""
GeoNames Plugin — Core logic.

Fornisce geolocalizzazione precisa per OffGallery:
  - Reverse geocoding da coordinate GPS → gerarchia GeOFF (milioni di luoghi)
  - Forward geocoding da nome → coordinate (ricerca nel DB locale per nazione)
  - Assegnazione manuale coordinate a immagini senza GPS
  - Ricalcolo gerarchia GeOFF per immagini con GPS esistente

Implementa GeoEnricherPlugin (plugins/base.py) — sostituisce geo_enricher builtin.
Standalone: non importa nulla da OffGallery core.

Sorgente dati: GeoNames.org (CC BY 4.0)
  - countryInfo.txt   → mapping codice ISO → paese + continente
  - admin1CodesASCII.txt → mapping admin1 code → nome regione
  - XX.zip            → luoghi per nazione (borghi, frazioni, città, ecc.)
"""
# Copyright (C) 2026  OffGallery / HEGOM — All rights reserved.
# Distributed under the OffGallery Plugins License v1.0.
# Proprietary — do NOT redistribute. See LICENSE in this directory.

import sqlite3
import json
import logging
import math
import urllib.request
import urllib.error
import zipfile
import io
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Directory del plugin ───────────────────────────────────────────────────
_PLUGIN_DIR  = Path(__file__).parent
_CONFIG_PATH = _PLUGIN_DIR / "config.json"

# ── URL GeoNames ───────────────────────────────────────────────────────────
_GEONAMES_BASE        = "https://download.geonames.org/export/dump"
_COUNTRY_INFO_URL     = f"{_GEONAMES_BASE}/countryInfo.txt"
_ADMIN1_URL           = f"{_GEONAMES_BASE}/admin1CodesASCII.txt"
_NATION_ZIP_URL       = _GEONAMES_BASE + "/{cc}.zip"

# ── Feature codes da includere nel DB luoghi ───────────────────────────────
# P = populated place, A = administrative division, L = area/region, S = spot/building
# Filtriamo per includere luoghi utili e escludere aeroporti, stazioni, ecc.
_INCLUDED_FEATURE_CLASSES = {'P', 'A', 'L'}

# ── Timeout download ───────────────────────────────────────────────────────
_DOWNLOAD_TIMEOUT = 60  # secondi per connessione
_READ_TIMEOUT     = 300 # secondi per lettura file grande


# ══════════════════════════════════════════════════════════════════════════════
# INTERFACCIA STANDARD PLUGIN (richiesta da PluginCard e DownloadWorker)
# ══════════════════════════════════════════════════════════════════════════════

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
    """Ritorna True se il DB meta (countryInfo + admin1) è presente e non vuoto."""
    cfg = load_config()
    meta_db = _get_meta_db_path(cfg)
    if not meta_db.exists():
        return False
    try:
        conn = sqlite3.connect(str(meta_db))
        n = conn.execute("SELECT COUNT(*) FROM countries").fetchone()[0]
        conn.close()
        return n > 0
    except Exception:
        return False


def get_database_date() -> Optional[str]:
    """Ritorna la data dell'ultimo download del DB meta, o None."""
    cfg = load_config()
    return cfg.get("meta_download_date")


def get_downloaded_nations(cfg: dict = None) -> list:
    """Ritorna lista codici ISO nazioni scaricate (es. ['IT', 'FR'])."""
    if cfg is None:
        cfg = load_config()
    return cfg.get("downloaded_nations", [])


def download_and_build_database(progress_callback=None, status_callback=None,
                                 nation_code: str = None, **kwargs) -> None:
    """Scarica e indicizza i dati GeoNames.

    Se nation_code è specificato, scarica quella nazione.
    Scarica sempre i dati meta (countryInfo + admin1) se non presenti.

    Chiamato da DownloadWorker in plugins_tab.
    """
    cfg = load_config()
    data_dir = _get_data_dir(cfg)
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Scarica dati meta se assenti
    meta_db = _get_meta_db_path(cfg)
    if not meta_db.exists():
        if status_callback:
            status_callback("Scarico dati base GeoNames (paesi e regioni)...")
        _download_meta(meta_db, status_callback)
        cfg["meta_download_date"] = datetime.now().strftime("%Y-%m-%d")
        save_config(cfg)

    # 2. Scarica nazione richiesta
    if nation_code:
        nation_code = nation_code.upper()
        if status_callback:
            status_callback(f"Scarico dati GeoNames per {nation_code}...")
        nation_db = data_dir / f"{nation_code}.db"
        _download_nation(nation_code, nation_db, progress_callback, status_callback)
        # Registra nazione come scaricata
        nations = cfg.get("downloaded_nations", [])
        if nation_code not in nations:
            nations.append(nation_code)
            cfg["downloaded_nations"] = nations
        cfg[f"nation_download_date_{nation_code}"] = datetime.now().strftime("%Y-%m-%d")
        save_config(cfg)

    if status_callback:
        status_callback("Download completato.")


# ══════════════════════════════════════════════════════════════════════════════
# CLASSE GeoNamesEnricher — implementa GeoEnricherPlugin
# ══════════════════════════════════════════════════════════════════════════════

class GeoNamesEnricher:
    """
    Implementa l'interfaccia GeoEnricherPlugin.
    Caricata da ProcessingWorker in fase 0 al posto del builtin geo_enricher.
    """

    def __init__(self, config: dict):
        self._cfg = config
        self._meta_db_path = _get_meta_db_path(config)
        self._data_dir     = _get_data_dir(config)
        # Cache in memoria per evitare query ripetute sulle stesse coordinate
        self._hierarchy_cache: dict[tuple, Optional[str]] = {}

    def is_ready(self) -> bool:
        """Verifica che il DB meta sia presente e accessibile."""
        if not self._meta_db_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(self._meta_db_path))
            n = conn.execute("SELECT COUNT(*) FROM countries").fetchone()[0]
            conn.close()
            return n > 0
        except Exception:
            return False

    def get_hierarchy(self, lat: float, lon: float) -> Optional[str]:
        """
        Reverse geocoding: coordinate → gerarchia GeOFF.
        Cerca il luogo più vicino nel DB delle nazioni scaricate.
        Fallback: usa reverse_geocoder builtin se disponibile.
        """
        key = (round(lat, 5), round(lon, 5))
        if key in self._hierarchy_cache:
            return self._hierarchy_cache[key]

        result = self._reverse_geocode(lat, lon)
        self._hierarchy_cache[key] = result
        return result

    def search_location(self, query: str, nation_codes: list = None) -> list:
        """
        Forward geocoding: nome luogo → lista risultati con coordinate.
        Cerca nel DB delle nazioni scaricate.

        Returns:
            Lista di dict: {name, admin1, admin2, country_code, country,
                            continent, latitude, longitude, altitude, population,
                            hierarchy}
        """
        if not query or len(query.strip()) < 2:
            return []

        results = []
        nations_to_search = nation_codes or get_downloaded_nations(self._cfg)

        for cc in nations_to_search:
            nation_db = self._data_dir / f"{cc.upper()}.db"
            if not nation_db.exists():
                continue
            try:
                partial = _search_in_nation_db(nation_db, self._meta_db_path, query.strip(), limit=20)
                results.extend(partial)
            except Exception as e:
                logger.warning(f"Errore ricerca in {cc}.db: {e}")

        # Ordina per rilevanza: match esatto prima, poi per popolazione decrescente
        query_low = query.strip().lower()
        results.sort(key=lambda r: (
            0 if r['name'].lower() == query_low else 1,
            -(r.get('population') or 0)
        ))
        return results[:50]

    def get_location_hint(self, geo_hierarchy: str) -> Optional[str]:
        """Stringa leggibile per il LLM: 'Firenze, Toscana, Italy'"""
        if not geo_hierarchy:
            return None
        try:
            parts = [p for p in geo_hierarchy.split('|') if p and p != 'GeOFF']
            if not parts:
                return None
            return ', '.join(reversed(parts[-3:]))
        except Exception:
            return None

    def get_geo_leaf(self, geo_hierarchy: str) -> Optional[str]:
        """Nodo foglia della gerarchia (città o luogo più specifico)."""
        if not geo_hierarchy:
            return None
        try:
            parts = [p for p in geo_hierarchy.split('|') if p and p != 'GeOFF']
            return parts[-1] if parts else None
        except Exception:
            return None

    # ── Reverse geocoding interno ──────────────────────────────────────────

    def _reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """
        Trova il luogo più vicino alle coordinate nelle nazioni scaricate.
        Se nessuna nazione è scaricata o le coordinate sono fuori dai DB,
        tenta il fallback con reverse_geocoder builtin.
        """
        nations = get_downloaded_nations(self._cfg)
        best = None
        best_dist = float('inf')

        for cc in nations:
            nation_db = self._data_dir / f"{cc.upper()}.db"
            if not nation_db.exists():
                continue
            try:
                row = _find_nearest(nation_db, lat, lon, radius_deg=1.0)
                if row:
                    dist = _haversine(lat, lon, row['latitude'], row['longitude'])
                    if dist < best_dist:
                        best_dist = dist
                        best = row
            except Exception as e:
                logger.debug(f"Errore reverse geocode in {cc}.db: {e}")

        # Soglia: max 50 km dal punto più vicino trovato
        if best and best_dist <= 50000:
            return _build_hierarchy(best, self._meta_db_path)

        # Fallback: reverse_geocoder builtin (130k città)
        return _fallback_reverse_geocoder(lat, lon)


# ══════════════════════════════════════════════════════════════════════════════
# ELABORAZIONE IMMAGINI (chiamata come subprocess da processing_tab / gallery)
# ══════════════════════════════════════════════════════════════════════════════

def process_images(db_path: str, config: dict,
                   image_ids: list = None,
                   mode: str = "no_gps",
                   location: dict = None,
                   overwrite: bool = False,
                   progress_cb=None) -> tuple:
    """
    Elabora immagini nel DB OffGallery.

    Modalità:
      'no_gps'    → assegna coordinate da `location` a immagini senza GPS
      'overwrite' → ricalcola geo_hierarchy per immagini con GPS esistente

    Args:
        db_path:    percorso DB OffGallery
        config:     config del plugin
        image_ids:  lista ID specifici (None = tutte)
        mode:       'no_gps' o 'overwrite'
        location:   dict con 'latitude', 'longitude', 'altitude' (solo per no_gps)
        overwrite:  se True sovrascrive dati esistenti
        progress_cb: callback(current, total)

    Returns:
        (processed, skipped) — foto aggiornate, foto saltate
    """
    enricher = GeoNamesEnricher(config)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Costruisce WHERE in base alla modalità
    where_clauses = []
    params = []

    if mode == "no_gps":
        if not overwrite:
            where_clauses.append("gps_latitude IS NULL")
        # Con overwrite in no_gps: agisce comunque solo su no_gps
        # (overwrite qui significa: riscrivi anche geo_hierarchy se già presente)
        else:
            where_clauses.append("gps_latitude IS NULL")
    elif mode == "overwrite":
        where_clauses.append("gps_latitude IS NOT NULL")
        where_clauses.append("gps_longitude IS NOT NULL")
        if not overwrite:
            where_clauses.append("(geo_hierarchy IS NULL OR geo_hierarchy = '')")

    if image_ids:
        placeholders = ','.join('?' * len(image_ids))
        where_clauses.append(f"id IN ({placeholders})")
        params.extend(image_ids)

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = conn.execute(
        f"SELECT id, gps_latitude, gps_longitude FROM images{where_sql}", params
    ).fetchall()

    total     = len(rows)
    processed = 0
    skipped   = 0

    for i, row in enumerate(rows):
        if progress_cb:
            progress_cb(i + 1, total)

        img_id = row["id"]

        if mode == "no_gps" and location:
            lat = location.get("latitude")
            lon = location.get("longitude")
            alt = location.get("altitude")
            if lat is None or lon is None:
                skipped += 1
                continue
            # Usa la gerarchia pre-selezionata se disponibile (es. frazione scelta dalla ricerca)
            # altrimenti ricalcola via reverse geocoding
            preset = location.get("preset_hierarchy")
            hierarchy = preset if preset else enricher.get_hierarchy(float(lat), float(lon))
            conn.execute(
                """UPDATE images
                   SET gps_latitude=?, gps_longitude=?, gps_altitude=?, geo_hierarchy=?
                   WHERE id=?""",
                (lat, lon, alt, hierarchy, img_id)
            )
            processed += 1

        elif mode == "overwrite":
            lat = row["gps_latitude"]
            lon = row["gps_longitude"]
            if lat is None or lon is None:
                skipped += 1
                continue
            hierarchy = enricher.get_hierarchy(float(lat), float(lon))
            if hierarchy:
                conn.execute(
                    "UPDATE images SET geo_hierarchy=? WHERE id=?",
                    (hierarchy, img_id)
                )
                processed += 1
            else:
                skipped += 1

        if i % 100 == 0:
            conn.commit()

    conn.commit()
    conn.close()
    return processed, skipped


def clear_gps(db_path: str, image_ids: list) -> int:
    """
    Azzera i dati di localizzazione derivati per le immagini specificate.
    Le coordinate GPS (gps_latitude, gps_longitude) non vengono toccate:
    rispecchiano gli EXIF del file fisico e devono restare nel DB.
    Usato dall'azione gallery 'Cancella dati localizzazione'.

    Returns:
        Numero di righe aggiornate.
    """
    if not image_ids:
        return 0
    conn = sqlite3.connect(db_path)
    placeholders = ','.join('?' * len(image_ids))
    conn.execute(
        f"""UPDATE images
            SET geo_hierarchy=NULL,
                weather_context=NULL,
                protected_area=NULL,
                habitat=NULL,
                gps_modified=0
            WHERE id IN ({placeholders})""",
        image_ids
    )
    updated = conn.total_changes
    conn.commit()
    conn.close()
    return updated


# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD E COSTRUZIONE DB
# ══════════════════════════════════════════════════════════════════════════════

def _download_meta(meta_db_path: Path, status_callback=None) -> None:
    """
    Scarica countryInfo.txt e admin1CodesASCII.txt da GeoNames
    e li indicizza in meta_db (SQLite).
    """
    meta_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(meta_db_path))

    # Tabella paesi: ISO → nome + continente
    conn.execute("""
        CREATE TABLE IF NOT EXISTS countries (
            iso        TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            continent  TEXT NOT NULL
        )
    """)
    # Tabella regioni admin1: 'IT.09' → 'Sardegna'
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin1 (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    conn.commit()

    # ── Scarica countryInfo.txt ────────────────────────────────────────────
    if status_callback:
        status_callback("Scarico informazioni paesi...")
    try:
        req = urllib.request.Request(_COUNTRY_INFO_URL, headers={'User-Agent': 'OffGallery/1.0'})
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            lines = resp.read().decode("utf-8").splitlines()

        count = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 9:
                continue
            # Colonne countryInfo.txt:
            # 0=ISO, 1=ISO3, 2=ISO-Numeric, 3=fips, 4=Country, 5=Capital,
            # 6=Area, 7=Population, 8=Continent, ...
            iso       = parts[0].strip().upper()
            name      = parts[4].strip()
            continent_code = parts[8].strip()
            continent = _continent_code_to_name(continent_code)
            if iso and name:
                conn.execute(
                    "INSERT OR REPLACE INTO countries(iso, name, continent) VALUES (?,?,?)",
                    (iso, name, continent)
                )
                count += 1
        conn.commit()
        logger.info(f"GeoNames meta: {count} paesi indicizzati")
    except Exception as e:
        logger.error(f"Errore download countryInfo.txt: {e}")
        raise

    # ── Scarica admin1CodesASCII.txt ───────────────────────────────────────
    if status_callback:
        status_callback("Scarico codici regioni (admin1)...")
    try:
        req = urllib.request.Request(_ADMIN1_URL, headers={'User-Agent': 'OffGallery/1.0'})
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            lines = resp.read().decode("utf-8").splitlines()

        count = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            # Formato: IT.09\tSardegna\tSardegna\t<geonameid>
            code = parts[0].strip()   # es. 'IT.09'
            name = parts[1].strip()   # es. 'Sardegna'
            if code and name:
                conn.execute(
                    "INSERT OR REPLACE INTO admin1(code, name) VALUES (?,?)",
                    (code, name)
                )
                count += 1
        conn.commit()
        logger.info(f"GeoNames meta: {count} regioni admin1 indicizzate")
    except Exception as e:
        logger.error(f"Errore download admin1CodesASCII.txt: {e}")
        raise

    conn.close()


def _download_nation(nation_code: str, nation_db_path: Path,
                     progress_callback=None, status_callback=None) -> None:
    """
    Scarica XX.zip da GeoNames, estrae XX.txt e lo indicizza in SQLite.
    """
    url = _NATION_ZIP_URL.format(cc=nation_code.upper())
    nation_db_path.parent.mkdir(parents=True, exist_ok=True)

    if status_callback:
        status_callback(f"Scarico {nation_code}.zip da GeoNames...")

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OffGallery/1.0'})
        with urllib.request.urlopen(req, timeout=_READ_TIMEOUT) as resp:
            zip_data = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Nazione '{nation_code}' non trovata su GeoNames (HTTP {e.code})") from e
    except Exception as e:
        raise RuntimeError(f"Errore download {nation_code}.zip: {e}") from e

    if status_callback:
        status_callback(f"Estrazione e indicizzazione {nation_code}...")

    # Estrai il file TXT principale dall'archivio ZIP
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            txt_name = f"{nation_code.upper()}.txt"
            if txt_name not in zf.namelist():
                # Alcuni ZIP hanno il nome in minuscolo
                txt_name = next((n for n in zf.namelist() if n.lower() == f"{nation_code.lower()}.txt"), None)
            if not txt_name:
                raise RuntimeError(f"File TXT non trovato nell'archivio {nation_code}.zip")
            txt_data = zf.read(txt_name).decode("utf-8", errors="replace")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Errore estrazione {nation_code}.zip: {e}") from e

    # Indicizza in SQLite
    _build_nation_db(txt_data, nation_db_path, nation_code, progress_callback, status_callback)


def _build_nation_db(txt_data: str, db_path: Path, nation_code: str,
                     progress_callback=None, status_callback=None) -> None:
    """
    Converte il TXT GeoNames in un DB SQLite indicizzato per nome e coordinate.

    Schema GeoNames TXT (tab-separated):
    0  geonameid
    1  name
    2  asciiname
    3  alternatenames
    4  latitude
    5  longitude
    6  feature_class   (A, H, L, P, R, S, T, U, V)
    7  feature_code
    8  country_code
    9  cc2
    10 admin1_code
    11 admin2_code
    12 admin3_code
    13 admin4_code
    14 population
    15 elevation
    16 dem
    17 timezone
    18 modification_date
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS places (
            geonameid    INTEGER PRIMARY KEY,
            name         TEXT NOT NULL,
            asciiname    TEXT,
            latitude     REAL NOT NULL,
            longitude    REAL NOT NULL,
            feature_class TEXT,
            feature_code TEXT,
            country_code TEXT,
            admin1_code  TEXT,
            admin2_code  TEXT,
            population   INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name      ON places(name COLLATE NOCASE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asciiname ON places(asciiname COLLATE NOCASE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_latlon    ON places(latitude, longitude)")
    conn.commit()

    lines = txt_data.splitlines()
    total = len(lines)
    batch = []
    inserted = 0

    for i, line in enumerate(lines):
        if progress_callback and i % 5000 == 0:
            progress_callback(i, total)

        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) < 9:
            continue

        feature_class = parts[6].strip()
        if feature_class not in _INCLUDED_FEATURE_CLASSES:
            continue

        try:
            lat = float(parts[4])
            lon = float(parts[5])
        except ValueError:
            continue

        try:
            pop = int(parts[14]) if parts[14].strip() else 0
        except ValueError:
            pop = 0

        batch.append((
            int(parts[0]),
            parts[1].strip(),
            parts[2].strip(),
            lat, lon,
            feature_class,
            parts[7].strip(),
            parts[8].strip().upper(),
            parts[10].strip(),
            parts[11].strip(),
            pop,
        ))
        inserted += 1

        if len(batch) >= 10000:
            conn.executemany(
                """INSERT OR IGNORE INTO places
                   (geonameid, name, asciiname, latitude, longitude,
                    feature_class, feature_code, country_code,
                    admin1_code, admin2_code, population)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                batch
            )
            conn.commit()
            batch.clear()

    if batch:
        conn.executemany(
            """INSERT OR IGNORE INTO places
               (geonameid, name, asciiname, latitude, longitude,
                feature_class, feature_code, country_code,
                admin1_code, admin2_code, population)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            batch
        )
        conn.commit()

    conn.close()
    if progress_callback:
        progress_callback(total, total)
    if status_callback:
        status_callback(f"{nation_code}: {inserted} luoghi indicizzati.")
    logger.info(f"GeoNames {nation_code}: {inserted} luoghi nel DB")


# ══════════════════════════════════════════════════════════════════════════════
# RICERCA E GERARCHIA
# ══════════════════════════════════════════════════════════════════════════════

def _search_in_nation_db(nation_db: Path, meta_db: Path,
                          query: str, limit: int = 20) -> list:
    """Ricerca per nome nel DB di una nazione. Ritorna lista dict."""
    conn = sqlite3.connect(str(nation_db))
    conn.row_factory = sqlite3.Row

    # Ricerca case-insensitive: prima match esatto, poi LIKE
    rows = conn.execute(
        """SELECT * FROM places
           WHERE name LIKE ? OR asciiname LIKE ?
           ORDER BY
             CASE WHEN name = ? THEN 0 ELSE 1 END,
             population DESC
           LIMIT ?""",
        (f"%{query}%", f"%{query}%", query, limit)
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        meta = _get_meta(row["country_code"], row["admin1_code"], meta_db)
        results.append({
            "name":         row["name"],
            "admin1":       meta.get("admin1", ""),
            "admin2":       row["admin2_code"] or "",
            "country_code": row["country_code"],
            "country":      meta.get("country", row["country_code"]),
            "continent":    meta.get("continent", ""),
            "latitude":     row["latitude"],
            "longitude":    row["longitude"],
            "altitude":     None,
            "population":   row["population"] or 0,
            "hierarchy":    _build_hierarchy_from_parts(
                                row["name"],
                                meta.get("admin1", ""),
                                meta.get("country", row["country_code"]),
                                meta.get("continent", "")
                            ),
        })
    return results


def _find_nearest(nation_db: Path, lat: float, lon: float,
                  radius_deg: float = 1.0) -> Optional[dict]:
    """
    Trova il luogo più vicino alle coordinate nel DB della nazione.
    Usa un bounding box iniziale per limitare le righe scansionate,
    poi calcola la distanza esatta con Haversine.
    """
    conn = sqlite3.connect(str(nation_db))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT * FROM places
           WHERE latitude  BETWEEN ? AND ?
             AND longitude BETWEEN ? AND ?""",
        (lat - radius_deg, lat + radius_deg,
         lon - radius_deg, lon + radius_deg)
    ).fetchall()
    conn.close()

    if not rows:
        return None

    best = None
    best_dist = float('inf')
    for row in rows:
        d = _haversine(lat, lon, row["latitude"], row["longitude"])
        if d < best_dist:
            best_dist = d
            best = dict(row)

    return best


def _build_hierarchy(place: dict, meta_db: Path) -> Optional[str]:
    """Costruisce la stringa GeOFF da un record place + meta DB."""
    cc       = place.get("country_code", "")
    admin1   = place.get("admin1_code", "")
    name     = place.get("name", "")
    meta     = _get_meta(cc, admin1, meta_db)
    return _build_hierarchy_from_parts(
        name,
        meta.get("admin1", ""),
        meta.get("country", cc),
        meta.get("continent", "World")
    )


def _build_hierarchy_from_parts(name: str, admin1: str,
                                  country: str, continent: str) -> str:
    """Assembla la stringa 'GeOFF|Continent|Country|Admin1|Name'."""
    parts = ["GeOFF"]
    if continent:
        parts.append(continent)
    if country:
        parts.append(country)
    if admin1 and admin1.lower() not in (country.lower(), ""):
        parts.append(admin1)
    if name and name.lower() not in (admin1.lower(), country.lower(), ""):
        parts.append(name)
    return "|".join(parts)


def _get_meta(country_code: str, admin1_code: str, meta_db: Path) -> dict:
    """Recupera nome paese, continente e nome regione dal DB meta."""
    result = {"country": country_code, "continent": "World", "admin1": ""}
    if not meta_db.exists():
        return result
    try:
        conn = sqlite3.connect(str(meta_db))
        row = conn.execute(
            "SELECT name, continent FROM countries WHERE iso=?",
            (country_code.upper(),)
        ).fetchone()
        if row:
            result["country"]   = row[0]
            result["continent"] = row[1]

        if admin1_code:
            adm_key = f"{country_code.upper()}.{admin1_code}"
            row2 = conn.execute(
                "SELECT name FROM admin1 WHERE code=?", (adm_key,)
            ).fetchone()
            if row2:
                result["admin1"] = row2[0]
        conn.close()
    except Exception as e:
        logger.debug(f"Errore lettura meta DB: {e}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY
# ══════════════════════════════════════════════════════════════════════════════

def _get_data_dir(cfg: dict) -> Path:
    """Ritorna la directory dati: custom se specificata, altrimenti plugin/data."""
    raw = cfg.get("data_dir", "")
    if raw and raw != "__plugin_dir__":
        return Path(raw)
    return _PLUGIN_DIR / "data"


def _get_meta_db_path(cfg: dict) -> Path:
    return _get_data_dir(cfg) / "geonames_meta.db"


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanza in metri tra due coordinate geografiche."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _fallback_reverse_geocoder(lat: float, lon: float) -> Optional[str]:
    """
    Fallback: usa reverse_geocoder builtin (130k città).
    Chiamato quando le coordinate non ricadono in nessuna nazione scaricata.
    """
    try:
        import reverse_geocoder as rg
        results = rg.search((lat, lon), mode=1, verbose=False)
        if not results:
            return None
        r = results[0]
        city   = (r.get('name') or '').strip()
        admin1 = (r.get('admin1') or '').strip()
        cc     = (r.get('cc') or '').upper()
        cfg    = load_config()
        meta   = _get_meta(cc, "", _get_meta_db_path(cfg))
        country   = meta.get("country", cc)
        continent = meta.get("continent", "World")
        return _build_hierarchy_from_parts(city, admin1, country, continent)
    except ImportError:
        logger.debug("reverse_geocoder non disponibile per fallback")
        return None
    except Exception as e:
        logger.debug(f"Errore fallback reverse_geocoder: {e}")
        return None


def _continent_code_to_name(code: str) -> str:
    """Converte codice continente GeoNames (2 lettere) in nome esteso."""
    _map = {
        'AF': 'Africa',
        'AS': 'Asia',
        'EU': 'Europe',
        'NA': 'North America',
        'SA': 'South America',
        'OC': 'Oceania',
        'AN': 'Antarctica',
    }
    return _map.get(code.upper(), 'World')


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT SUBPROCESS (chiamato da processing_tab come script)
# ══════════════════════════════════════════════════════════════════════════════

def _main():
    """
    Entry point quando il plugin è lanciato come subprocess.
    Argomenti:
      --db <path>          percorso DB OffGallery
      --mode <no_gps|overwrite>
      --lat <float>        (solo mode=no_gps)
      --lon <float>        (solo mode=no_gps)
      --alt <float>        (opzionale, solo mode=no_gps)
      --overwrite          flag sovrascrittura
      --ids <id,id,...>    lista image_id (opzionale)
    """
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db",        required=True)
    parser.add_argument("--mode",      default="no_gps", choices=["no_gps", "overwrite"])
    parser.add_argument("--lat",       type=float, default=None)
    parser.add_argument("--lon",       type=float, default=None)
    parser.add_argument("--alt",       type=float, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--ids",       default="")
    args = parser.parse_args()

    cfg = load_config()

    image_ids = None
    if args.ids:
        try:
            image_ids = [int(x) for x in args.ids.split(",") if x.strip()]
        except ValueError:
            pass

    location = None
    if args.mode == "no_gps" and args.lat is not None and args.lon is not None:
        location = {"latitude": args.lat, "longitude": args.lon, "altitude": args.alt}

    def _progress(current, total):
        print(f"PROGRESS:{current}:{total}", flush=True)

    try:
        processed, skipped = process_images(
            db_path=args.db,
            config=cfg,
            image_ids=image_ids,
            mode=args.mode,
            location=location,
            overwrite=args.overwrite,
            progress_cb=_progress,
        )
        not_matched = skipped
        print(f"DONE:{processed + skipped}:{processed}:{not_matched}", flush=True)
    except Exception as e:
        print(f"ERROR:{e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    _main()
