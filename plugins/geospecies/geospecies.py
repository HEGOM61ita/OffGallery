"""
GeoSpecies - Core logic
Costruisce un sottoinsieme geografico di specie per affinare la classificazione BioCLIP.

Strategia B (celle 1°×1°): le specie vengono cercate per cella geografica tramite GBIF,
usando bounding box decimalLatitude/decimalLongitude.
Il download è organizzato per area ecologica (Continente → Paese → Macro-area → Zona).
A runtime si usa la cella 1°×1° esatta delle coordinate GPS della foto.

Durante l'elaborazione: solo cache locale. Mai fetch HTTP.
Il fetch HTTP avviene solo esplicitamente dal DownloadDialog.
"""

import json
import logging
import math
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Directory del plugin ───────────────────────────────────────────────────
_PLUGIN_DIR  = Path(__file__).parent
_CONFIG_PATH = _PLUGIN_DIR / "config.json"

# ── Taxon GBIF keys ────────────────────────────────────────────────────────
GBIF_TAXON_KEYS = {
    'Aves':       212,
    'Mammalia':   359,
    'Reptilia':   [11592253, 11418114, 11538092],
    'Plantae':    6,
    'Fungi':      5,
    'Insecta':    216,
    'Amphibia':   131,
    'Arachnida':  367,
}

DEFAULT_TAXA = ['Aves', 'Mammalia', 'Reptilia', 'Plantae', 'Fungi', 'Insecta', 'Amphibia', 'Arachnida']

# ── Endpoint ───────────────────────────────────────────────────────────────
GBIF_OCCURRENCE_URL = "https://api.gbif.org/v1/occurrence/search"

# Schema versione cache
CACHE_SCHEMA = "2.0"

# Defaults
DEFAULT_CACHE_DAYS   = 90
DEFAULT_TIMEOUT      = 30
DEFAULT_MAX_SPECIES  = 5000
CELL_DEG             = 1.0


# ── Gerarchia ecologica: Continente → Paese → Macro-area → Zona ───────────
# Formato foglia: (lat_min, lat_max, lon_min, lon_max)
# I nodi intermedi hanno '_bbox' per la selezione aggregata.
# Le foglie sono le zone scaricabili — il sistema calcola le celle 1°×1° dal bbox.

REGIONS = {
    "Europa": {
        "_bbox": (34, 72, -25, 45),
        "Italia": {
            "_bbox": (36, 48, 6, 19),
            "Alpi Occidentali":  (44, 46,  6, 10),
            "Alpi Orientali":    (45, 48,  9, 14),
            "Pianura Padana":    (44, 46,  8, 14),
            "Appennino Nord":    (43, 45,  9, 13),
            "Appennino Centro":  (41, 44, 11, 15),
            "Appennino Sud":     (37, 41, 14, 17),
            "Costa Adriatica":   (41, 46, 13, 16),
            "Costa Tirrenica":   (37, 44,  9, 13),
            "Puglia e Salento":  (39, 42, 14, 19),
            "Sardegna":          (38, 42,  8, 10),
            "Sicilia":           (36, 39, 11, 16),
        },
        "Francia": {
            "_bbox": (41, 52, -6, 10),
            "Bretagna e Normandia":    (47, 52, -5,  2),
            "Nord e Ile-de-France":    (48, 52,  0,  6),
            "Alpi e Giura":            (44, 48,  4,  8),
            "Massiccio Centrale":      (44, 47,  1,  5),
            "Aquitania e Pirenei":     (42, 46, -2,  4),
            "Provenza e Linguadoca":   (42, 45,  3,  8),
            "Corsica":                 (41, 44,  8, 10),
        },
        "Spagna e Portogallo": {
            "_bbox": (35, 44, -10, 5),
            "Pirenei":              (41, 44, -2,  4),
            "Galizia e Cantabria":  (41, 44, -9, -2),
            "Meseta Nord":          (40, 43, -6,  0),
            "Meseta Sud":           (37, 41, -7,  0),
            "Andalusia":            (35, 39, -8,  0),
            "Costa Est e Valencia": (37, 42, -1,  4),
            "Portogallo":           (36, 42,-10, -6),
            "Baleari":              (38, 41,  1,  5),
            "Canarie":              (27, 30,-18,-13),
        },
        "Germania Austria Svizzera": {
            "_bbox": (45, 56, 5, 18),
            "Alpi e Prealpi":   (46, 49,  8, 16),
            "Altopiano Centro": (49, 53,  8, 15),
            "Nord e Coste":     (52, 56,  8, 15),
            "Austria Est":      (46, 50, 13, 18),
        },
        "Gran Bretagna e Irlanda": {
            "_bbox": (49, 61, -11, 2),
            "Irlanda":          (51, 56, -11, -5),
            "Galles e Inghilterra Sud": (50, 54, -5,  2),
            "Inghilterra Nord": (53, 56, -3,  2),
            "Scozia":           (54, 61, -8,  0),
        },
        "Penisola Balcanica": {
            "_bbox": (35, 47, 13, 30),
            "Slovenia e Croazia":  (44, 47, 13, 20),
            "Bosnia e Serbia":     (42, 46, 15, 23),
            "Bulgaria e Romania":  (43, 49, 22, 30),
            "Grecia Nord":         (39, 43, 19, 27),
            "Grecia Sud e Isole":  (35, 40, 19, 28),
        },
        "Paesi Nordici": {
            "_bbox": (54, 72, 3, 32),
            "Danimarca":       (54, 58,  8, 16),
            "Norvegia Sud":    (57, 63,  3, 15),
            "Norvegia Nord":   (63, 72,  5, 32),
            "Svezia Sud":      (55, 61, 10, 20),
            "Svezia Nord":     (61, 70, 10, 25),
            "Finlandia":       (59, 70, 19, 32),
        },
        "Europa Orientale": {
            "_bbox": (44, 57, 14, 42),
            "Polonia":          (49, 55, 14, 25),
            "Repubblica Ceca e Slovacchia": (47, 52, 12, 23),
            "Ungheria":         (45, 49, 15, 23),
            "Romania":          (43, 49, 21, 30),
            "Ucraina":          (44, 53, 22, 41),
            "Paesi Baltici":    (53, 60, 20, 30),
        },
        "Russia Europea": {
            "_bbox": (50, 70, 28, 60),
            "Russia Ovest":  (50, 60, 28, 45),
            "Russia Nord":   (60, 70, 28, 60),
        },
    },

    "Africa": {
        "_bbox": (-36, 38, -18, 52),
        "Nord Africa": {
            "_bbox": (18, 38, -18, 38),
            "Marocco":          (27, 36, -14,  0),
            "Algeria e Tunisia":(30, 38,  -3, 12),
            "Libia":            (19, 34,   9, 26),
            "Egitto e Sinai":   (22, 32,  24, 37),
        },
        "Africa Orientale": {
            "_bbox": (-12, 16, 28, 52),
            "Etiopia e Eritrea": ( 8, 16, 32, 48),
            "Kenya e Tanzania":  (-12,  5, 29, 42),
            "Uganda e Rwanda":   ( -3,  5, 28, 36),
            "Mozambico":         (-27,-10, 32, 41),
        },
        "Africa Meridionale": {
            "_bbox": (-36, -14, 10, 36),
            "Sud Africa Ovest": (-36,-22, 16, 23),
            "Sud Africa Est":   (-36,-22, 23, 34),
            "Namibia":          (-29,-16, 11, 26),
            "Botswana e Zimbabwe": (-27,-14, 19, 34),
            "Zambia":           (-19, -7, 21, 34),
        },
        "Africa Occidentale": {
            "_bbox": ( 4, 20, -18, 16),
            "Senegal e Gambia": (12, 17, -18, -11),
            "Guinea e Sierra Leone": ( 6, 13, -16,  -7),
            "Ghana e Costa d'Avorio": ( 4, 12,  -8,   2),
            "Nigeria e Benin":  ( 4, 14,   2,  15),
            "Camerun":          ( 1, 13,   8,  17),
        },
        "Africa Centrale": {
            "_bbox": (-6, 8, 8, 32),
            "Congo e Gabon":    (-6,  4,  8, 19),
            "Rep. Dem. Congo":  (-14,  6, 12, 32),
        },
        "Madagascar": {
            "_bbox": (-26, -11, 43, 51),
            "Madagascar Nord":  (-15,-11, 47, 51),
            "Madagascar Centro":(-21,-15, 43, 50),
            "Madagascar Sud":   (-26,-21, 43, 48),
        },
    },

    "Asia": {
        "_bbox": (0, 55, 25, 146),
        "Medio Oriente": {
            "_bbox": (12, 43, 25, 63),
            "Turchia":              (35, 43, 25, 45),
            "Israele e Giordania":  (29, 34, 34, 40),
            "Iraq e Siria":         (29, 38, 35, 49),
            "Penisola Arabica":     (12, 30, 34, 60),
            "Iran":                 (25, 40, 44, 64),
        },
        "Asia Centrale": {
            "_bbox": (36, 56, 49, 88),
            "Kazakhstan":   (40, 56, 50, 88),
            "Mongolia":     (41, 53, 87,120),
            "Afghanistan":  (29, 39, 60, 75),
        },
        "India e Sri Lanka": {
            "_bbox": ( 5, 37, 68, 98),
            "India Nord e Himalaya": (27, 37, 72, 98),
            "India Centro":          (18, 27, 72, 86),
            "India Sud":             ( 8, 18, 73, 82),
            "Sri Lanka":             ( 5, 10, 79, 82),
        },
        "Sud-Est Asiatico": {
            "_bbox": (-10, 25, 92, 142),
            "Thailandia e Cambogia": ( 5, 21, 97,106),
            "Vietnam e Laos":        (10, 24,100,110),
            "Malaysia e Singapore":  (-3,  8, 99,120),
            "Indonesia Ovest":       (-8,  6, 95,120),
            "Indonesia Est e Papua": (-9,  1,119,142),
            "Filippine":             ( 4, 22,116,128),
        },
        "Estremo Oriente": {
            "_bbox": (20, 55, 99, 146),
            "Cina Sud":    (18, 32, 99,122),
            "Cina Nord":   (32, 54,73, 135),
            "Giappone":    (24, 46,122,146),
            "Corea":       (33, 43,124,132),
        },
    },

    "Americhe": {
        "_bbox": (-56, 84, -168, -34),
        "Nord America": {
            "_bbox": (24, 84, -168, -52),
            "Alaska e Canada Ovest":  (48, 72,-141, -90),
            "Canada Est":             (42, 72, -90, -52),
            "USA Nord-Ovest":         (40, 50,-125, -95),
            "USA Nord-Est":           (37, 48, -95, -65),
            "USA Sud-Ovest e Grandi Pianure": (25, 40,-125, -95),
            "USA Sud-Est":            (25, 37, -95, -75),
            "Florida e Caraibi":      (19, 32, -85, -65),
        },
        "Centro America": {
            "_bbox": ( 7, 25, -95, -60),
            "Messico Nord":      (20, 33,-118, -95),
            "Messico Sud":       (14, 20, -97, -86),
            "Costa Rica e Panama": ( 7, 12, -86, -76),
            "Caraibi":           (10, 25, -85, -60),
        },
        "Sud America": {
            "_bbox": (-56, 13, -82, -34),
            "Colombia e Venezuela": ( 0, 13, -74, -59),
            "Amazzonia":            (-16,  6, -74, -44),
            "Brasile Costa":        (-25,  0, -50, -34),
            "Andes":                (-23,  0, -82, -65),
            "Cono Sud":             (-42,-22, -72, -53),
            "Patagonia":            (-56,-42, -76, -63),
        },
    },

    "Oceania": {
        "_bbox": (-48, -8, 110, 180),
        "Australia": {
            "_bbox": (-44,-10, 113,154),
            "Australia Nord-Ovest": (-26,-10,113,130),
            "Australia Nord-Est":   (-20,-10,130,154),
            "Australia Centro":     (-36,-20,125,142),
            "Australia Sud-Ovest":  (-36,-26,113,125),
            "Australia Est":        (-38,-26,138,154),
            "Tasmania":             (-44,-38,143,149),
            "Queensland":           (-30,-10,138,154),
        },
        "Nuova Zelanda": {
            "_bbox": (-48,-33,166,179),
            "Isola Nord": (-42,-33,172,179),
            "Isola Sud":  (-48,-42,166,174),
        },
    },
}


# ── Celle geografiche 1°×1° ────────────────────────────────────────────────

def cell_from_coords(lat: float, lon: float) -> Tuple[int, int]:
    """Calcola la cella 1°×1° di appartenenza di una coordinata."""
    return (int(math.floor(lat)), int(math.floor(lon)))


def cell_key(lat_min: int, lon_min: int) -> str:
    """Chiave stringa univoca per una cella, es. '+38_+008'."""
    return f"{lat_min:+04d}_{lon_min:+05d}"


def cell_label(lat_min: int, lon_min: int) -> str:
    """Etichetta leggibile per la cella, es. '38°N, 8°E'."""
    lat_dir = "N" if lat_min >= 0 else "S"
    lon_dir = "E" if lon_min >= 0 else "W"
    return f"{abs(lat_min)}°{lat_dir}, {abs(lon_min)}°{lon_dir}"


def cells_for_bbox(lat_min: int, lat_max: int, lon_min: int, lon_max: int) -> list:
    """Restituisce tutte le celle 1°×1° che coprono il bounding box dato."""
    return [
        (lat, lon)
        for lat in range(lat_min, lat_max)
        for lon in range(lon_min, lon_max)
    ]


# ── Navigazione gerarchia ──────────────────────────────────────────────────

def get_leaves(node) -> list:
    """Restituisce tutte le foglie (bbox tuple) di un nodo della gerarchia."""
    if isinstance(node, tuple):
        return [node]
    leaves = []
    for k, v in node.items():
        if k == "_bbox":
            continue
        leaves.extend(get_leaves(v))
    return leaves


def cells_for_node(node) -> list:
    """Restituisce tutte le celle 1°×1° coperte da un nodo (foglia o sottoalbero)."""
    cells = set()
    for bbox in get_leaves(node):
        lat_min, lat_max, lon_min, lon_max = bbox
        for lat in range(lat_min, lat_max):
            for lon in range(lon_min, lon_max):
                cells.add((lat, lon))
    return sorted(cells)


# ── Interfaccia standard plugin ────────────────────────────────────────────

def load_config() -> dict:
    defaults = {
        "cache_dir": "",
        "cache_days": DEFAULT_CACHE_DAYS,
        "max_species_per_taxon": DEFAULT_MAX_SPECIES,
        "enabled_taxa": DEFAULT_TAXA,
        "request_timeout": DEFAULT_TIMEOUT,
    }
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {**defaults, **cfg}
    except Exception:
        return defaults


def save_config(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def is_database_present() -> bool:
    cache_dir = _get_cache_dir(load_config())
    if not cache_dir.exists():
        return False
    return any(cache_dir.glob("checklist_*.json"))


def get_database_date() -> Optional[str]:
    cache_dir = _get_cache_dir(load_config())
    files = list(cache_dir.glob("checklist_*.json")) if cache_dir.exists() else []
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    try:
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("fetched_at", "")[:10]
    except Exception:
        return None


def download_and_build_database(progress_callback=None, status_callback=None, **kwargs) -> None:
    """Interfaccia standard no-op — download avviene dal DownloadDialog."""
    if status_callback:
        status_callback("Usa il pannello di configurazione GeoSpecies per scaricare le checklist.")


# ── Funzione principale: sottoinsieme specie per BioCLIP ───────────────────

def get_species_subset(lat: float, lon: float,
                       geo_hierarchy: Optional[str] = None,
                       config: Optional[dict] = None) -> Optional[list]:
    """Ritorna la lista di specie per la cella 1°×1° delle coordinate GPS.

    Usa solo cache locale. Mai fetch HTTP durante elaborazione.
    """
    if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
        return None

    if config is None:
        config = load_config()

    enabled_taxa = config.get('enabled_taxa', DEFAULT_TAXA)
    if not enabled_taxa:
        return None

    lat_min, lon_min = cell_from_coords(lat, lon)
    c_key = cell_key(lat_min, lon_min)
    c_label = cell_label(lat_min, lon_min)

    cache_dir = _get_cache_dir(config)
    cache_days = int(config.get('cache_days', DEFAULT_CACHE_DAYS))

    all_species = []
    taxon_groups_used = []

    for taxon in enabled_taxa:
        cache_key_str = f"checklist_B_{c_key}_{taxon}"
        species = _load_cache(cache_dir, cache_key_str, cache_days)
        if species:
            all_species.extend(species)
            taxon_groups_used.append(taxon)
        else:
            logger.debug(f"GeoSpecies: cache assente per {taxon}/{c_label}")

    if not all_species:
        logger.warning(
            f"⚠️ GeoSpecies: nessuna checklist per la cella {c_label} — "
            f"BioCLIP usa TreeOfLife completo."
        )
        return None

    seen = set()
    unique_species = []
    for s in all_species:
        if s not in seen:
            seen.add(s)
            unique_species.append(s)

    logger.info(
        f"GeoSpecies: {len(unique_species)} specie per cella {c_label} "
        f"— taxon: {', '.join(taxon_groups_used)}"
    )
    return unique_species


# ── Cache ──────────────────────────────────────────────────────────────────

def _get_cache_dir(config: dict) -> Path:
    custom = config.get("cache_dir", "")
    if custom:
        return Path(custom)
    return _PLUGIN_DIR / "cache"


def _cache_path(cache_dir: Path, cache_key: str) -> Path:
    return cache_dir / f"{cache_key}.json"


def _load_cache(cache_dir: Path, cache_key: str, cache_days: int) -> Optional[list]:
    path = _cache_path(cache_dir, cache_key)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("offgallery_schema") != CACHE_SCHEMA:
            return None
        fetched_at = data.get("fetched_at", "")
        if fetched_at:
            fetched_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - fetched_dt).days
            if age_days > cache_days:
                logger.debug(f"GeoSpecies: cache scaduta ({age_days}gg) — {cache_key}")
                return None
        return data.get("species", [])
    except Exception as e:
        logger.debug(f"GeoSpecies: errore lettura cache {cache_key}: {e}")
        return None


def _save_cache(cache_dir: Path, cache_key: str, species: list,
                lat_min: int, lon_min: int, taxon: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "offgallery_schema": CACHE_SCHEMA,
        "plugin_id": "geospecies",
        "strategy": "B",
        "key": cell_label(lat_min, lon_min),
        "lat_min": lat_min,
        "lon_min": lon_min,
        "taxon": taxon,
        "source": "gbif",
        "fetched_at": datetime.now(timezone.utc).isoformat()[:19] + "Z",
        "species_count": len(species),
        "species": species,
    }
    path = _cache_path(cache_dir, cache_key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    logger.debug(f"GeoSpecies: cache salvata — {cache_key} ({len(species)} specie)")


# ── Fetch GBIF per cella 1°×1° ────────────────────────────────────────────

def _fetch_gbif_cell(lat_min: int, lon_min: int, taxon: str,
                     max_species: int, timeout: int,
                     status_cb=None, abort=None) -> Optional[list]:
    """Scarica lista specie per cella via facet speciesKey + lookup parallelo.

    Fase 1: raccoglie speciesKey distinti via facet (poche chiamate).
    Fase 2: risolve speciesKey → nome canonico in parallelo (10 thread).
    """
    import concurrent.futures
    import time as _time

    req_timeout = min(timeout, 15)
    MAX_RETRIES = 3
    RETRY_WAIT  = 3
    FACET_LIMIT = 1000

    taxon_keys_raw = GBIF_TAXON_KEYS.get(taxon)
    if not taxon_keys_raw:
        return None
    taxon_keys = taxon_keys_raw if isinstance(taxon_keys_raw, list) else [taxon_keys_raw]

    lat_max = lat_min + CELL_DEG
    lon_max = lon_min + CELL_DEG
    label = cell_label(lat_min, lon_min)

    def _aborted():
        return abort is not None and abort.is_set()

    def _get(url: str) -> Optional[dict]:
        for attempt in range(1, MAX_RETRIES + 1):
            if _aborted():
                return None
            try:
                with urllib.request.urlopen(url, timeout=req_timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                if attempt < MAX_RETRIES:
                    _time.sleep(RETRY_WAIT)
                else:
                    logger.warning(f"GeoSpecies: GET fallito: {e}")
                    return None
        return None

    # ── Fase 1: facet speciesKey ──────────────────────────────────────────
    all_keys: list = []
    keys_set: set  = set()
    try:
        for taxon_key in taxon_keys:
            if _aborted():
                return None
            facet_offset = 0
            while True:
                if _aborted():
                    return None
                params = urllib.parse.urlencode({
                    "decimalLatitude":  f"{lat_min},{lat_max}",
                    "decimalLongitude": f"{lon_min},{lon_max}",
                    "taxonKey":         taxon_key,
                    "limit":            0,
                    "facet":            "speciesKey",
                    "facetLimit":       FACET_LIMIT,
                    "facetOffset":      facet_offset,
                })
                data = _get(f"{GBIF_OCCURRENCE_URL}?{params}")
                if data is None:
                    break
                facets = data.get("facets", [])
                counts = facets[0].get("counts", []) if facets else []
                if not counts:
                    break
                for c in counts:
                    k = c["name"]
                    if k not in keys_set:
                        keys_set.add(k)
                        all_keys.append(k)
                    if len(all_keys) >= max_species:
                        break
                if len(all_keys) >= max_species or len(counts) < FACET_LIMIT:
                    break
                facet_offset += FACET_LIMIT
            if len(all_keys) >= max_species:
                break
    except Exception as e:
        logger.warning(f"GeoSpecies: facet fallito ({label}/{taxon}): {e}")
        return None

    if not all_keys:
        return None

    if status_cb:
        status_cb(f"  {taxon} / {label}: {len(all_keys)} specie, risolvo nomi...")

    # ── Fase 2: lookup parallelo ──────────────────────────────────────────
    GBIF_SPECIES_LOOKUP = "https://api.gbif.org/v1/species/"

    def lookup_name(key: str) -> Optional[str]:
        if _aborted():
            return None
        data = _get(f"{GBIF_SPECIES_LOOKUP}{key}")
        if data is None:
            return None
        return (data.get("canonicalName") or data.get("scientificName", "")).strip() or None

    species = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(lookup_name, k): k for k in all_keys}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            if _aborted():
                for f in futures:
                    f.cancel()
                break
            name = future.result()
            if name:
                species.append(name)
            done += 1
            if status_cb and done % 20 == 0:
                status_cb(
                    f"  {taxon} / {label}: {done}/{len(all_keys)} nomi, "
                    f"{len(species)} specie..."
                )

    if not species:
        return None

    species.sort()
    logger.info(f"GeoSpecies: {label}/{taxon} → {len(species)} specie")
    return species


# ── Download esplicito ────────────────────────────────────────────────────

def download_cell(lat_min: int, lon_min: int, taxon: str,
                  config: dict, status_cb=None, abort=None) -> bool:
    """Scarica e salva la checklist per una cella 1°×1° e un taxon."""
    cache_dir = _get_cache_dir(config)
    timeout = int(config.get('request_timeout', DEFAULT_TIMEOUT))
    max_species = int(config.get('max_species_per_taxon', DEFAULT_MAX_SPECIES))
    cache_days = int(config.get('cache_days', DEFAULT_CACHE_DAYS))
    c_key = cell_key(lat_min, lon_min)
    cache_key_str = f"checklist_B_{c_key}_{taxon}"
    label = cell_label(lat_min, lon_min)

    existing = _load_cache(cache_dir, cache_key_str, cache_days)
    if existing is not None:
        if status_cb:
            status_cb(f"✓ {taxon} / {label}: già in cache ({len(existing)} specie)")
        return True

    if status_cb:
        status_cb(f"Download {taxon} / {label}...")

    species = _fetch_gbif_cell(lat_min, lon_min, taxon, max_species, timeout,
                               status_cb=status_cb, abort=abort)
    if species is not None:
        _save_cache(cache_dir, cache_key_str, species,
                    lat_min=lat_min, lon_min=lon_min, taxon=taxon)
        if status_cb:
            status_cb(f"✓ {taxon} / {label}: {len(species)} specie")
        return True
    else:
        if abort and abort.is_set():
            return False
        if status_cb:
            status_cb(f"✗ {taxon} / {label}: nessuna specie o errore")
        return False


def download_zone(bbox: tuple, zone_name: str, taxon: str,
                  config: dict, status_cb=None, cell_cb=None, abort=None) -> bool:
    """Scarica tutte le celle 1°×1° di un bbox per il taxon dato.

    cell_cb: callable(done, total) — chiamato dopo ogni cella.
    """
    lat_min, lat_max, lon_min, lon_max = bbox
    cells = cells_for_bbox(lat_min, lat_max, lon_min, lon_max)
    if not cells:
        return False

    total = len(cells)
    ok = 0
    for i, (lat, lon) in enumerate(cells):
        if abort and abort.is_set():
            break
        result = download_cell(lat, lon, taxon, config,
                               status_cb=status_cb, abort=abort)
        if result:
            ok += 1
        if cell_cb:
            cell_cb(i + 1, total)

    return ok > 0


def get_cached_checklists(config: dict) -> list:
    cache_dir = _get_cache_dir(config)
    result = []
    if not cache_dir.exists():
        return result
    for path in sorted(cache_dir.glob("checklist_*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result.append({
                "filename": path.name,
                "strategy": data.get("strategy", "B"),
                "key": data.get("key", "?"),
                "taxon": data.get("taxon", "?"),
                "source": data.get("source", "gbif"),
                "species_count": data.get("species_count", 0),
                "fetched_at": data.get("fetched_at", "")[:10],
            })
        except Exception:
            continue
    return result


def delete_checklist(filename: str, config: dict) -> bool:
    cache_dir = _get_cache_dir(config)
    path = cache_dir / filename
    if path.exists() and path.suffix == ".json" and path.name.startswith("checklist_"):
        path.unlink()
        return True
    return False


def clear_all_cache(config: dict) -> int:
    cache_dir = _get_cache_dir(config)
    count = 0
    if cache_dir.exists():
        for path in cache_dir.glob("checklist_*.json"):
            path.unlink()
            count += 1
    return count
