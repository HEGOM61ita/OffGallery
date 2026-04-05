"""
GeoSpecies - Core logic
Costruisce un sottoinsieme geografico di specie per affinare la classificazione BioCLIP.

Tutte le specie vengono cercate per paese (Strategy A unica) tramite GBIF.
Il paese viene estratto da geo_hierarchy già presente nel DB — nessuna chiamata API real-time.

Durante l'elaborazione: solo cache locale. Mai fetch HTTP.
Il fetch HTTP avviene solo esplicitamente dal DownloadDialog.

Fonte: GBIF species/search per paese (tutti i taxon).
"""

import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Directory del plugin ───────────────────────────────────────────────────
_PLUGIN_DIR  = Path(__file__).parent
_CONFIG_PATH = _PLUGIN_DIR / "config.json"

# ── Taxon GBIF keys ────────────────────────────────────────────────────────
GBIF_TAXON_KEYS = {
    'Aves':       212,
    'Mammalia':   359,
    'Reptilia':   358,
    'Plantae':    6,
    'Fungi':      5,
    'Insecta':    216,
    'Amphibia':   131,
    'Arachnida':  367,
}

# Tutti i taxon usano Strategy A (per paese)
TAXON_STRATEGY = {t: 'A' for t in GBIF_TAXON_KEYS}

# Taxon abilitati di default
DEFAULT_TAXA = ['Aves', 'Mammalia', 'Reptilia', 'Plantae', 'Fungi', 'Insecta', 'Amphibia', 'Arachnida']

# ── Endpoint ───────────────────────────────────────────────────────────────
GBIF_SPECIES_URL    = "https://api.gbif.org/v1/species/search"
GBIF_OCCURRENCE_URL = "https://api.gbif.org/v1/occurrence/search"

# Schema versione cache
CACHE_SCHEMA = "1.0"

# Defaults configurazione
DEFAULT_CACHE_DAYS   = 90
DEFAULT_TIMEOUT      = 30
DEFAULT_MAX_SPECIES  = 5000

# Mappatura nome paese EN → ISO2 (per estrarre paese da geo_hierarchy)
# geo_hierarchy formato: "GeOFF|Europe|Italy|Sardegna|Olbia"
# Il campo paese (indice 2) è in inglese (dalla libreria reverse_geocoder/GeoNames)
_COUNTRY_NAME_TO_ISO2 = {
    "Afghanistan": "AF", "Albania": "AL", "Algeria": "DZ", "Angola": "AO",
    "Argentina": "AR", "Armenia": "AM", "Australia": "AU", "Austria": "AT",
    "Azerbaijan": "AZ", "Bangladesh": "BD", "Belarus": "BY", "Belgium": "BE",
    "Benin": "BJ", "Bolivia": "BO", "Bosnia and Herzegovina": "BA", "Botswana": "BW",
    "Brazil": "BR", "Bulgaria": "BG", "Burkina Faso": "BF", "Burundi": "BI",
    "Cambodia": "KH", "Cameroon": "CM", "Canada": "CA", "Chad": "TD",
    "Chile": "CL", "China": "CN", "Colombia": "CO", "Costa Rica": "CR",
    "Croatia": "HR", "Cuba": "CU", "Cyprus": "CY", "Czech Republic": "CZ",
    "Czechia": "CZ", "Democratic Republic of the Congo": "CD", "Denmark": "DK",
    "Dominican Republic": "DO", "Ecuador": "EC", "Egypt": "EG", "El Salvador": "SV",
    "Eritrea": "ER", "Estonia": "EE", "Ethiopia": "ET", "Finland": "FI",
    "France": "FR", "Gabon": "GA", "Georgia": "GE", "Germany": "DE",
    "Ghana": "GH", "Greece": "GR", "Guatemala": "GT", "Guinea": "GN",
    "Haiti": "HT", "Honduras": "HN", "Hungary": "HU", "Iceland": "IS",
    "India": "IN", "Indonesia": "ID", "Iran": "IR", "Iraq": "IQ",
    "Ireland": "IE", "Israel": "IL", "Italy": "IT", "Jamaica": "JM",
    "Japan": "JP", "Jordan": "JO", "Kazakhstan": "KZ", "Kenya": "KE",
    "Kosovo": "XK", "Kuwait": "KW", "Kyrgyzstan": "KG", "Laos": "LA",
    "Latvia": "LV", "Lebanon": "LB", "Libya": "LY", "Lithuania": "LT",
    "Luxembourg": "LU", "Madagascar": "MG", "Malawi": "MW", "Malaysia": "MY",
    "Mali": "ML", "Mauritania": "MR", "Mexico": "MX", "Moldova": "MD",
    "Mongolia": "MN", "Montenegro": "ME", "Morocco": "MA", "Mozambique": "MZ",
    "Myanmar": "MM", "Namibia": "NA", "Nepal": "NP", "Netherlands": "NL",
    "New Zealand": "NZ", "Nicaragua": "NI", "Niger": "NE", "Nigeria": "NG",
    "North Korea": "KP", "North Macedonia": "MK", "Norway": "NO", "Oman": "OM",
    "Pakistan": "PK", "Panama": "PA", "Papua New Guinea": "PG", "Paraguay": "PY",
    "Peru": "PE", "Philippines": "PH", "Poland": "PL", "Portugal": "PT",
    "Qatar": "QA", "Republic of the Congo": "CG", "Romania": "RO", "Russia": "RU",
    "Rwanda": "RW", "Saudi Arabia": "SA", "Senegal": "SN", "Serbia": "RS",
    "Sierra Leone": "SL", "Slovakia": "SK", "Slovenia": "SI", "Somalia": "SO",
    "South Africa": "ZA", "South Korea": "KR", "South Sudan": "SS", "Spain": "ES",
    "Sri Lanka": "LK", "Sudan": "SD", "Sweden": "SE", "Switzerland": "CH",
    "Syria": "SY", "Taiwan": "TW", "Tajikistan": "TJ", "Tanzania": "TZ",
    "Thailand": "TH", "Togo": "TG", "Tunisia": "TN", "Turkey": "TR",
    "Turkmenistan": "TM", "Uganda": "UG", "Ukraine": "UA",
    "United Arab Emirates": "AE", "United Kingdom": "GB", "United States": "US",
    "Uruguay": "UY", "Uzbekistan": "UZ", "Venezuela": "VE", "Vietnam": "VN",
    "Yemen": "YE", "Zambia": "ZM", "Zimbabwe": "ZW",
}


# ── Interfaccia standard plugin ────────────────────────────────────────────

def load_config() -> dict:
    """Carica config.json del plugin, ritorna dict con defaults se assente."""
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
    """Salva config.json del plugin."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def is_database_present() -> bool:
    """Ritorna True se esiste almeno una cache checklist."""
    cache_dir = _get_cache_dir(load_config())
    if not cache_dir.exists():
        return False
    return any(cache_dir.glob("checklist_*.json"))


def get_database_date() -> Optional[str]:
    """Ritorna la data del file di cache più recente."""
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
    """Ritorna la lista di specie attese per le coordinate GPS.

    IMPORTANTE: usa SOLO la cache locale. Mai fetch HTTP durante elaborazione.
    Se la cache non contiene le checklist per il paese, ritorna None silenziosamente.

    Args:
        lat: Latitudine WGS84
        lon: Longitudine WGS84
        geo_hierarchy: stringa "GeOFF|Continent|Country|Region|City" già presente nel DB
                       Se fornita, estrae il paese da lì (nessuna chiamata API).
                       Se None, ritorna None (impossibile determinare il paese senza rete).
        config: Configurazione plugin (se None, carica da file)

    Returns:
        Lista di nomi scientifici o None
    """
    if lat is None or lon is None:
        return None

    if config is None:
        config = load_config()

    enabled_taxa = config.get('enabled_taxa', DEFAULT_TAXA)
    if not enabled_taxa:
        return None

    # Estrai paese ISO2 da geo_hierarchy (nessuna chiamata API)
    country_iso2 = _country_from_geo_hierarchy(geo_hierarchy)
    if not country_iso2:
        logger.debug(f"GeoSpecies: paese non determinabile da geo_hierarchy — subset non disponibile")
        return None

    cache_dir = _get_cache_dir(config)
    cache_days = int(config.get('cache_days', DEFAULT_CACHE_DAYS))

    all_species = []
    taxon_groups_used = []

    for taxon in enabled_taxa:
        cache_key = f"checklist_A_{country_iso2}_{taxon}"
        species = _load_cache(cache_dir, cache_key, cache_days)
        if species:
            all_species.extend(species)
            taxon_groups_used.append(taxon)
        else:
            logger.debug(f"GeoSpecies: cache assente per {taxon}/{country_iso2} — taxon saltato")

    if not all_species:
        logger.debug(f"GeoSpecies: nessuna cache disponibile per {country_iso2} — uso TreeOfLife")
        return None

    # Deduplicazione mantenendo ordine
    seen = set()
    unique_species = []
    for s in all_species:
        if s not in seen:
            seen.add(s)
            unique_species.append(s)

    logger.info(
        f"GeoSpecies: {len(unique_species)} specie per {country_iso2} "
        f"— taxon: {', '.join(taxon_groups_used)}"
    )
    return unique_species


def _country_from_geo_hierarchy(geo_hierarchy: Optional[str]) -> Optional[str]:
    """Estrae ISO2 paese da geo_hierarchy.
    Formato: 'GeOFF|Europe|Italy|Sardegna|Olbia' → 'IT'
    """
    if not geo_hierarchy:
        return None
    parts = geo_hierarchy.split('|')
    # Indice 2 = paese in inglese (da GeoNames/reverse_geocoder)
    if len(parts) < 3:
        return None
    country_name = parts[2].strip()
    return _COUNTRY_NAME_TO_ISO2.get(country_name)


# ── Cache checklist ────────────────────────────────────────────────────────

def _get_cache_dir(config: dict) -> Path:
    """Ritorna la directory cache configurata (default: plugin/cache/)."""
    custom = config.get("cache_dir", "")
    if custom:
        return Path(custom)
    return _PLUGIN_DIR / "cache"


def _cache_path(cache_dir: Path, cache_key: str) -> Path:
    return cache_dir / f"{cache_key}.json"


def _load_cache(cache_dir: Path, cache_key: str, cache_days: int) -> Optional[list]:
    """Carica checklist dalla cache se esiste e non è scaduta."""
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
                key: str, taxon: str, source: str = "gbif") -> None:
    """Salva checklist nella cache locale."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "offgallery_schema": CACHE_SCHEMA,
        "plugin_id": "geospecies",
        "strategy": "A",
        "key": key,
        "taxon": taxon,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat()[:19] + "Z",
        "species_count": len(species),
        "species": species,
    }
    path = _cache_path(cache_dir, cache_key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    logger.debug(f"GeoSpecies: cache salvata — {cache_key} ({len(species)} specie)")


# ── Fetch GBIF per paese ───────────────────────────────────────────────────

def _fetch_gbif_country(country_iso2: str, taxon: str,
                        max_species: int, timeout: int,
                        status_cb=None) -> Optional[list]:
    """Scarica lista specie GBIF per paese e taxon.

    Strategia:
    1. Raccoglie tutti gli speciesKey via facet (una chiamata per 1500 chiavi,
       poi facetOffset per le pagine successive). Ogni chiamata è rapida.
    2. Risolve i nomi scientifici tramite /v1/species/<key> in parallelo (10 thread).

    Questo approccio è molto più veloce di paginare le occorrenze (milioni di record).
    """
    import concurrent.futures

    taxon_key = GBIF_TAXON_KEYS.get(taxon)
    if not taxon_key:
        return None

    logger.info(f"GeoSpecies: fetch GBIF country={country_iso2} taxon={taxon}...")
    FACET_LIMIT = 1500  # massimo supportato da GBIF per facetLimit

    # ── Step 1: raccoglie tutti gli speciesKey via facet ──────────────────
    all_keys = []
    facet_offset = 0
    try:
        while True:
            params = urllib.parse.urlencode({
                "country":    country_iso2,
                "taxonKey":   taxon_key,
                "limit":      0,
                "facet":      "speciesKey",
                "facetLimit": FACET_LIMIT,
                "facetOffset": facet_offset,
            })
            url = f"{GBIF_OCCURRENCE_URL}?{params}"
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            facets = data.get("facets", [])
            counts = facets[0].get("counts", []) if facets else []
            if not counts:
                break

            for c in counts:
                all_keys.append(c["name"])
                if len(all_keys) >= max_species:
                    break

            if len(all_keys) >= max_species or len(counts) < FACET_LIMIT:
                break
            facet_offset += FACET_LIMIT

        if not all_keys:
            logger.warning(f"GeoSpecies: nessun speciesKey trovato per {country_iso2}/{taxon}")
            return None

        if status_cb:
            status_cb(f"  {taxon}/{country_iso2}: {len(all_keys)} chiavi trovate, risolvo nomi...")

        # ── Step 2: risolve speciesKey → nome scientifico in parallelo ────
        GBIF_SPECIES_LOOKUP = "https://api.gbif.org/v1/species/"

        def lookup_name(key: str) -> Optional[str]:
            try:
                url = f"{GBIF_SPECIES_LOOKUP}{key}"
                with urllib.request.urlopen(url, timeout=timeout) as resp:
                    d = json.loads(resp.read().decode("utf-8"))
                return (d.get("canonicalName") or d.get("scientificName", "")).strip() or None
            except Exception:
                return None

        species = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(lookup_name, k): k for k in all_keys}
            done = 0
            for future in concurrent.futures.as_completed(futures):
                name = future.result()
                if name:
                    species.append(name)
                done += 1
                if status_cb and done % 50 == 0:
                    status_cb(f"  {taxon}/{country_iso2}: {done}/{len(all_keys)} nomi risolti...")

        logger.info(f"GeoSpecies: GBIF {country_iso2}/{taxon} → {len(species)} specie")
        return species if species else None

    except Exception as e:
        logger.warning(f"GeoSpecies: GBIF fetch fallito ({country_iso2}/{taxon}): {e}")
        return None


# ── Download esplicito (usato da DownloadDialog) ───────────────────────────

def download_area(country_iso2: str, taxon: str,
                  config: dict,
                  status_cb=None) -> bool:
    """Scarica e salva la checklist per un paese e un taxon.
    Chiamato esplicitamente dal DownloadDialog, mai durante elaborazione.

    Per Aves: usa eBird se configurato, altrimenti GBIF.
    Per tutti gli altri: GBIF.

    Returns:
        True se successo, False se errore
    """
    cache_dir = _get_cache_dir(config)
    timeout = int(config.get('request_timeout', DEFAULT_TIMEOUT))
    max_species = int(config.get('max_species_per_taxon', DEFAULT_MAX_SPECIES))
    cache_key = f"checklist_A_{country_iso2}_{taxon}"

    if status_cb:
        status_cb(f"Download {taxon} per {country_iso2}...")

    source = "gbif"
    species = _fetch_gbif_country(country_iso2, taxon, max_species, timeout, status_cb=status_cb)

    if species is not None:
        _save_cache(cache_dir, cache_key, species, key=country_iso2,
                    taxon=taxon, source=source)
        if status_cb:
            status_cb(f"✓ {taxon} per {country_iso2}: {len(species)} specie [{source}]")
        return True
    else:
        if status_cb:
            status_cb(f"✗ {taxon} per {country_iso2}: nessuna specie trovata o errore di rete")
        return False


def get_available_countries(timeout: int = DEFAULT_TIMEOUT) -> list:
    """Recupera la lista dei paesi disponibili in GBIF."""
    try:
        url = "https://api.gbif.org/v1/enumeration/country"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        countries = [
            {"iso2": item["iso2"], "name": item["title"]}
            for item in data
            if item.get("iso2") and item.get("title")
        ]
        countries.sort(key=lambda x: x["name"])
        return countries
    except Exception as e:
        logger.warning(f"GeoSpecies: impossibile recuperare lista paesi: {e}")
        return []


def get_cached_checklists(config: dict) -> list:
    """Ritorna la lista delle checklist in cache con metadati."""
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
                "strategy": data.get("strategy", "A"),
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
    """Cancella un file di cache specifico."""
    cache_dir = _get_cache_dir(config)
    path = cache_dir / filename
    if path.exists() and path.suffix == ".json" and path.name.startswith("checklist_"):
        path.unlink()
        return True
    return False


def clear_all_cache(config: dict) -> int:
    """Cancella tutta la cache. Ritorna il numero di file rimossi."""
    cache_dir = _get_cache_dir(config)
    count = 0
    if cache_dir.exists():
        for path in cache_dir.glob("checklist_*.json"):
            path.unlink()
            count += 1
    return count
