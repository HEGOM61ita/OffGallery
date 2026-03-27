"""
BioNomen — Logica core per lookup nomi comuni biologici.

Strategie di lookup (priorità decrescente):
  1. Cache/DB locale SQLite per taxon (bionomen_<taxon>_<lang>.db) — offline
  2. Ricerca online parallela (GBIF + Wikipedia + iNat + Wikidata) — primo risultato vince
     Se il vincitore è GBIF, il risultato viene salvato nel DB locale.

Questo modulo e' completamente standalone: non importa nulla da OffGallery.
Comunicazione con OffGallery tramite stdout: righe PROGRESS:n:total
"""

import sqlite3
import json
import time
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List

logger = logging.getLogger(__name__)

# Directory del plugin (stessa cartella di questo file)
_PLUGIN_DIR = Path(__file__).parent

# Percorso config.json del plugin
_CONFIG_PATH = _PLUGIN_DIR / "config.json"

# Taxa supportati: id → {label, class_key GBIF, nomi classe BioCLIP}
# class_key: chiave GBIF per il download bulk (https://api.gbif.org/v1/species?classKey=...)
# bioclip_classes: nomi che compaiono nel livello "Class" della tassonomia BioCLIP
TAXA = {
    "aves":      {"label": "Aves (Uccelli)",       "class_key": 212,    "bioclip_classes": ["Aves"]},
    "mammalia":  {"label": "Mammalia (Mammiferi)",  "class_key": 359,    "bioclip_classes": ["Mammalia"]},
    "reptilia":  {"label": "Reptilia (Rettili)",    "class_key": 358,    "bioclip_classes": ["Reptilia"]},
    "amphibia":  {"label": "Amphibia (Anfibi)",     "class_key": 131,    "bioclip_classes": ["Amphibia"]},
    "insecta":   {"label": "Insecta (Insetti)",     "class_key": 216,    "bioclip_classes": ["Insecta"]},
    "plantae":   {"label": "Plantae (Piante)",      "class_key": 6,      "bioclip_classes": ["Magnoliopsida", "Liliopsida", "Pinopsida", "Polypodiopsida"]},
}

# Termini geografici da filtrare nei nomi iNaturalist
_GEO_FILTER_TERMS = [
    "americano", "americana", "americane", "americani",
    "nordamericano", "nordamericana",
    "canadese", "canadesi",
    "australasiano", "australasiana",
    "australiano", "australiana",
    "messicano", "messicana",
    "sudamericano", "sudamericana",
    "nordafricano", "nordafricana",
    "nordeuropeo", "nordeuropea",
    "neotropicale",
    "neartico",
]

# Mappa codici lingua GBIF / iNat / Wikidata
_LANG_MAP = {
    "it": "ita",
    "en": "eng",
    "de": "deu",
    "fr": "fra",
    "es": "spa",
    "pt": "por",
}

# Mappa codici lingua → lexicon iNaturalist (campo "lexicon" in taxon_names)
_INAT_LEXICON = {
    "it": "italian",
    "en": "english",
    "fr": "french",
    "de": "german",
    "es": "spanish",
    "pt": "portuguese",
    "nl": "dutch",
    "pl": "polish",
    "sv": "swedish",
    "ja": "japanese",
    "zh": "chinese (simplified)",
}

# Etichette lingua per Wikidata SPARQL
_WIKIDATA_LANG = {
    "it": "it",
    "en": "en",
    "de": "de",
    "fr": "fr",
    "es": "es",
    "pt": "pt",
}


# ---------------------------------------------------------------------------
# Config persistente
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Carica config.json del plugin. Ritorna defaults se assente."""
    defaults = {
        "data_dir": str(_PLUGIN_DIR / "data"),
        "taxa_enabled": ["aves"],
        "mode": "unprocessed",
        "online_lookup": True,
    }
    if not _CONFIG_PATH.exists():
        return defaults
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # Merge con defaults per chiavi mancanti
        for k, v in defaults.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return defaults


def save_config(cfg: dict):
    """Salva config.json del plugin."""
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_data_dir() -> Path:
    """Ritorna la directory dati (da config.json)."""
    cfg = load_config()
    p = Path(cfg["data_dir"])
    if not p.is_absolute():
        p = _PLUGIN_DIR / p
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Gestione DB per taxon + lingua
# ---------------------------------------------------------------------------

def get_db_path(taxon: str, language: str) -> Path:
    """Ritorna il path del database per un taxon e una lingua."""
    return get_data_dir() / f"bionomen_{taxon}_{language}.db"


def get_enabled_taxa() -> List[str]:
    """Ritorna la lista dei taxa abilitati in config."""
    return load_config().get("taxa_enabled", ["aves"])


def is_database_present(taxon: str = None, language: str = None) -> bool:
    """
    Verifica se almeno un DB è presente e inizializzato.
    Se taxon e language sono specificati, controlla solo quel DB.
    """
    if taxon and language:
        db = get_db_path(taxon, language)
        return _db_has_data(db)
    # Controlla almeno un DB tra quelli abilitati
    cfg = load_config()
    for t in cfg.get("taxa_enabled", []):
        lang = cfg.get("language", "it")
        db = get_db_path(t, lang)
        if _db_has_data(db):
            return True
    return False


def _db_has_data(db: Path) -> bool:
    """Verifica se un file DB esiste e ha la tabella vernacular_names."""
    if not db.exists():
        return False
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vernacular_names'"
        )
        exists = cur.fetchone() is not None
        conn.close()
        return exists
    except Exception:
        return False


def get_database_info() -> dict:
    """
    Ritorna un dict {taxon: {"date": str, "count": int}} per i DB presenti.
    """
    cfg = load_config()
    lang = cfg.get("language", "it")
    info = {}
    for taxon in cfg.get("taxa_enabled", []):
        db = get_db_path(taxon, lang)
        if not db.exists():
            continue
        try:
            conn = sqlite3.connect(str(db))
            date_row = conn.execute(
                "SELECT value FROM metadata WHERE key='last_updated' LIMIT 1"
            ).fetchone()
            count_row = conn.execute(
                "SELECT COUNT(*) FROM vernacular_names"
            ).fetchone()
            conn.close()
            info[taxon] = {
                "date": date_row[0] if date_row else None,
                "count": count_row[0] if count_row else 0,
            }
        except Exception:
            pass
    return info


def get_database_date() -> Optional[str]:
    """Ritorna la data di aggiornamento del DB più recente tra quelli presenti."""
    info = get_database_info()
    dates = [v["date"] for v in info.values() if v.get("date")]
    return dates[-1] if dates else None


def _init_taxon_db(taxon: str, language: str) -> sqlite3.Connection:
    """Inizializza il database per un taxon+lingua con lo schema completo."""
    db_path = get_db_path(taxon, language)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vernacular_names (
            scientific_name  TEXT NOT NULL,
            vernacular_name  TEXT NOT NULL,
            language         TEXT NOT NULL,
            source           TEXT,
            confidence       INTEGER,
            PRIMARY KEY (scientific_name, language)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scientific
        ON vernacular_names(scientific_name)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn


def _extract_taxon_class(bioclip_taxonomy_json: Optional[str]) -> Optional[str]:
    """
    Estrae il taxon id (es. 'aves', 'mammalia') dal livello Class della tassonomia BioCLIP.

    Struttura BioCLIP: [Kingdom, Phylum, Class, Order, Family, Genus, species_epithet]
    Indice 2 = Class.
    """
    if not bioclip_taxonomy_json:
        return None
    try:
        taxonomy = json.loads(bioclip_taxonomy_json)
        if not isinstance(taxonomy, list) or len(taxonomy) < 3:
            return None
        bioclip_class = taxonomy[2].strip() if isinstance(taxonomy[2], str) else ""
        for taxon_id, info in TAXA.items():
            if bioclip_class in info["bioclip_classes"]:
                return taxon_id
        return None
    except Exception:
        return None


def _open_taxon_db_readonly(taxon: str, language: str) -> Optional[sqlite3.Connection]:
    """Apre il DB del taxon in sola lettura. Ritorna None se non esiste."""
    db = get_db_path(taxon, language)
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        return conn
    except Exception:
        return None


def _lookup_in_cache(conn: sqlite3.Connection, scientific_name: str, language: str) -> Optional[str]:
    """Cerca il nome vernacolare nella cache locale, con priorita' per confidence minore."""
    lang_code = _LANG_MAP.get(language, language)
    # Cerca per language code iso-639-2 (gbif) o iso-639-1 (wikidata)
    cur = conn.execute(
        """SELECT vernacular_name, confidence FROM vernacular_names
           WHERE scientific_name = ? AND (language = ? OR language = ?)
           ORDER BY confidence ASC LIMIT 1""",
        (scientific_name, lang_code, language),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _save_to_cache(
    conn: sqlite3.Connection,
    scientific_name: str,
    vernacular_name: str,
    language: str,
    source: str,
    confidence: int,
):
    """Salva un nome vernacolare nella cache locale."""
    lang_code = _LANG_MAP.get(language, language)
    conn.execute(
        """INSERT OR REPLACE INTO vernacular_names
           (scientific_name, vernacular_name, language, source, confidence)
           VALUES (?, ?, ?, ?, ?)""",
        (scientific_name, vernacular_name, lang_code, source, confidence),
    )
    conn.commit()


def _lookup_gbif(scientific_name: str, language: str) -> Optional[str]:
    """Cerca il nome vernacolare su GBIF via API REST (online)."""
    try:
        import urllib.request
        import urllib.parse

        match_url = (
            "https://api.gbif.org/v1/species/match?"
            + urllib.parse.urlencode({"name": scientific_name, "verbose": "false"})
        )
        req = urllib.request.Request(match_url, headers={"User-Agent": "BioNomen/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())

        usage_key = data.get("usageKey") or data.get("speciesKey")
        if not usage_key:
            return None

        vern_url = f"https://api.gbif.org/v1/species/{usage_key}/vernacularNames?limit=100"
        req2 = urllib.request.Request(vern_url, headers={"User-Agent": "BioNomen/1.0"})
        with urllib.request.urlopen(req2, timeout=4) as resp2:
            vdata = json.loads(resp2.read().decode())

        results = vdata.get("results", [])
        lang_code = _LANG_MAP.get(language, language)

        for entry in results:
            entry_lang = entry.get("language", "")
            if entry_lang == lang_code and entry.get("vernacularName"):
                return entry["vernacularName"]

        for entry in results:
            entry_lang = entry.get("language", "")
            if entry_lang == language and entry.get("vernacularName"):
                return entry["vernacularName"]

        return None

    except Exception as e:
        logger.debug(f"GBIF lookup fallito per '{scientific_name}': {e}")
        print(f"LOG:warning:GBIF non raggiungibile per '{scientific_name}': {e}", flush=True)
        return None


def _contains_geo_term(name: str) -> bool:
    """Verifica se il nome contiene termini geografici da filtrare."""
    name_lower = name.lower()
    for term in _GEO_FILTER_TERMS:
        if term in name_lower:
            return True
    return False


def _lookup_inaturalist(scientific_name: str, language: str) -> Optional[str]:
    """Cerca il nome vernacolare su iNaturalist con filtro anti-geografico (online)."""
    try:
        import urllib.request
        import urllib.parse

        params = urllib.parse.urlencode({
            "q": scientific_name,
            "rank": "species",
            "locale": language,
            "per_page": 1,
        })
        url = f"https://api.inaturalist.org/v1/taxa?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "BioNomen/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("results", [])
        if not results:
            return None

        taxon = results[0]
        common = taxon.get("preferred_common_name", "")
        if common and not _contains_geo_term(common):
            return common
        elif common and _contains_geo_term(common):
            print(f"LOG:warning:iNaturalist '{scientific_name}': nome geografico filtrato ('{common}')", flush=True)

        lexicon_key = _INAT_LEXICON.get(language, language)
        for entry in taxon.get("taxon_names", []):
            if entry.get("lexicon", "").lower() == lexicon_key and entry.get("name"):
                candidate = entry["name"]
                if not _contains_geo_term(candidate):
                    return candidate

        return None

    except Exception as e:
        logger.debug(f"iNaturalist lookup fallito per '{scientific_name}': {e}")
        print(f"LOG:warning:iNaturalist non raggiungibile per '{scientific_name}': {e}", flush=True)
        return None


def _lookup_wikidata(scientific_name: str, language: str) -> Optional[str]:
    """Cerca il nome vernacolare su Wikidata via SPARQL."""
    try:
        import urllib.request
        import urllib.parse

        lang_wd = _WIKIDATA_LANG.get(language, language)
        # Query SPARQL: cerca entita' con nome scientifico → label nella lingua
        sparql = f"""
SELECT ?label WHERE {{
  ?item wdt:P225 "{scientific_name}" .
  ?item rdfs:label ?label .
  FILTER(LANG(?label) = "{lang_wd}")
}} LIMIT 1
""".strip()

        url = (
            "https://query.wikidata.org/sparql?"
            + urllib.parse.urlencode({"query": sparql, "format": "json"})
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BioNomen/1.0 (OffGallery plugin; offline biology tool)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())

        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
            return None

        label = bindings[0].get("label", {}).get("value", "")
        if not label:
            return None

        # Scarta se il risultato coincide col nome scientifico (case-insensitive)
        if label.strip().lower() == scientific_name.strip().lower():
            return None

        return label

    except Exception as e:
        logger.debug(f"Wikidata lookup fallito per '{scientific_name}': {e}")
        print(f"LOG:warning:Wikidata non raggiungibile per '{scientific_name}': {e}", flush=True)
        return None


def _lookup_wikipedia(scientific_name: str, language: str) -> Optional[str]:
    """Cerca il nome comune su Wikipedia nella lingua selezionata.

    Strategia:
      1. Search API → primo risultato che contiene il nome scientifico nello snippet
      2. Il titolo della pagina è il nome comune nella lingua target
      3. Rimuove articoli iniziali (es. "Il camaleonte velato" → "camaleonte velato")
    """
    try:
        import urllib.request
        import urllib.parse
        import re

        lang = language if language else "en"
        params = urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": scientific_name,
            "format": "json",
            "srlimit": 5,
        })
        url = f"https://{lang}.wikipedia.org/w/api.php?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "BioNomen/1.0 (OffGallery plugin)"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("query", {}).get("search", [])
        sci_lower = scientific_name.strip().lower()

        for entry in results:
            title = entry.get("title", "")
            snippet = entry.get("snippet", "")
            # Verifica che lo snippet o il titolo citino il nome scientifico
            if sci_lower not in snippet.lower() and sci_lower not in title.lower():
                continue

            title_lower = title.strip().lower()

            if title_lower != sci_lower:
                # Titolo è già il nome comune — ripulisci articoli iniziali
                clean = re.sub(
                    r"^(Il |La |Lo |L'|I |Le |Gli |Der |Die |Das |Les |El |Los |Las |O |A )",
                    "", title, flags=re.IGNORECASE
                ).strip()
                if clean and clean.lower() != sci_lower and not _contains_geo_term(clean):
                    return clean
            else:
                # Titolo == nome scientifico: estrai nome comune dallo snippet
                # Formato tipico: "Il nome comune (<span...>Genus</span> <span...>species</span>..."
                # Rimuove tag HTML dallo snippet
                plain = re.sub(r"<[^>]+>", "", snippet)
                # Cerca pattern "Nome comune (Genus species" all'inizio
                m = re.match(
                    r"^(.+?)\s*\(\s*" + re.escape(scientific_name.split()[0]),
                    plain, re.IGNORECASE
                )
                if m:
                    candidate = m.group(1).strip()
                    # Rimuove articoli iniziali
                    candidate = re.sub(
                        r"^(Il |La |Lo |L'|I |Le |Gli |Der |Die |Das |Les |El |Los |Las |O |A )",
                        "", candidate, flags=re.IGNORECASE
                    ).strip()
                    if candidate and candidate.lower() != sci_lower and not _contains_geo_term(candidate):
                        return candidate

        return None

    except Exception as e:
        logger.debug(f"Wikipedia lookup fallito per '{scientific_name}': {e}")
        print(f"LOG:warning:Wikipedia non raggiungibile per '{scientific_name}': {e}", flush=True)
        return None



def _lookup_online_parallel(
    scientific_name: str,
    language: str,
    stop_event=None,
) -> tuple[Optional[str], str]:
    """
    Esegue in parallelo le 4 ricerche online (GBIF, Wikipedia, iNaturalist, Wikidata).
    Ritorna (nome_trovato, fonte) non appena la prima risposta valida arriva.
    Le restanti vengono abbandonate (thread daemon).

    Returns:
        Tupla (vernacular_name, source_key) dove source_key è uno tra
        "gbif", "wikipedia", "inaturalist", "wikidata".
        Se nessuna fonte trova nulla, ritorna (None, "").
    """
    # Mappa: fonte → funzione di lookup
    sources = [
        ("gbif",         lambda: _lookup_gbif(scientific_name, language)),
        ("wikipedia",    lambda: _lookup_wikipedia(scientific_name, language)),
        ("inaturalist",  lambda: _lookup_inaturalist(scientific_name, language)),
        ("wikidata",     lambda: _lookup_wikidata(scientific_name, language)),
    ]

    cancel = threading.Event()
    result_holder: list = [None, ""]  # [vernacular_name, source_key]
    result_lock   = threading.Lock()
    futures_done  = threading.Event()

    def _run_source(name, fn):
        try:
            val = fn()
            if val and not cancel.is_set():
                with result_lock:
                    # Solo il primo a scrivere vince
                    if result_holder[0] is None:
                        result_holder[0] = val
                        result_holder[1] = name
                        cancel.set()
        except Exception:
            pass

    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bionomen_online")
    futs: list[Future] = [executor.submit(_run_source, name, fn) for name, fn in sources]
    executor.shutdown(wait=False)

    # Aspetta: stop_event utente o cancel (primo risultato) o tutti completati
    deadline = 12.0
    interval = 0.05
    while deadline > 0:
        if stop_event and stop_event.is_set():
            cancel.set()
            return None, ""
        if cancel.is_set():
            break
        if all(f.done() for f in futs):
            break
        deadline -= interval
        time.sleep(interval)

    return result_holder[0], result_holder[1]


def lookup_vernacular_name(
    scientific_name: str,
    language: str = "it",
    taxon: str = None,
    stop_event=None,
) -> Optional[str]:
    """
    Cerca il nome vernacolare per un nome scientifico.

    Strategia (priorita' decrescente):
      1. DB locale per taxon+lingua (bulk download + cache lookup precedenti) — offline
      2. Ricerca online parallela (GBIF + Wikipedia + iNaturalist + Wikidata) — primo vince
         Se il vincitore è GBIF, il risultato viene salvato nel DB locale per riuso futuro.
         Saltata se online_lookup=False in config.json.

    Args:
        scientific_name: Nome scientifico (es. "Columba palumbus")
        language: Codice lingua ISO 639-1 (default "it")
        taxon: Id taxon (es. "aves") per aprire il DB corretto. Se None usa cache generica.
        stop_event: threading.Event opzionale per interruzione immediata
    """
    if not scientific_name or not scientific_name.strip():
        return None

    scientific_name = scientific_name.strip()
    cfg = load_config()
    online_enabled = cfg.get("online_lookup", True)

    # Apre il DB per il taxon specificato (o None se taxon non disponibile)
    conn = _init_taxon_db(taxon, language) if taxon else None

    try:
        # 1. Cache/DB locale (bulk download + risultati online precedentemente salvati)
        if conn:
            cached = _lookup_in_cache(conn, scientific_name, language)
            if cached is not None and cached != "":
                print(f"SOURCE:DB locale (offline):{scientific_name}", flush=True)
                return cached
            # Stringa vuota = cercato prima ma non trovato → si riprova online se abilitato

        # 2. Ricerca online disabilitata → uscita immediata
        if not online_enabled:
            print(f"LOG:debug:BioNomen [{scientific_name}] → ricerca online disabilitata", flush=True)
            return None

        if stop_event and stop_event.is_set():
            return None

        # 3. Ricerca online parallela — GBIF + Wikipedia + iNaturalist + Wikidata
        print(
            f"LOG:debug:BioNomen [{scientific_name}] → "
            f"ricerca online parallela (GBIF + Wikipedia + iNat + Wikidata)...",
            flush=True,
        )
        result, source = _lookup_online_parallel(scientific_name, language, stop_event)

        if stop_event and stop_event.is_set():
            return None

        if result:
            print(f"SOURCE:{source} (online):{scientific_name}", flush=True)
            # Salva nel DB locale solo se il vincitore è GBIF (fonte più affidabile)
            if conn and source == "gbif":
                _save_to_cache(conn, scientific_name, result, language, "gbif", 2)
            elif conn:
                # Salva comunque con confidenza più bassa per evitare lookup futuri
                _save_to_cache(conn, scientific_name, result, language, source, 3)
            return result

        print(f"LOG:debug:BioNomen [{scientific_name}] → nessuna fonte ha il nome comune", flush=True)

        # Nessun risultato: salva stringa vuota per evitare lookup ripetuti
        # nella stessa sessione; nelle sessioni future verrà ritentato
        if conn:
            _save_to_cache(conn, scientific_name, "", language, "none", 9)
        return None

    finally:
        if conn:
            conn.close()


def _ensure_vernacular_column(offgallery_conn: sqlite3.Connection):
    """Aggiunge la colonna vernacular_name alla tabella images se non esiste."""
    try:
        offgallery_conn.execute(
            "ALTER TABLE images ADD COLUMN vernacular_name TEXT"
        )
        offgallery_conn.commit()
        logger.info("Colonna vernacular_name aggiunta alla tabella images")
    except sqlite3.OperationalError:
        pass  # Colonna gia' esistente


def _extract_scientific_name(bioclip_taxonomy_json: Optional[str]) -> Optional[str]:
    """
    Estrae il nome scientifico dalla tassonomia BioCLIP (JSON array 7 livelli).

    La struttura BioCLIP e':
      [Kingdom, Phylum, Class, Order, Family, Genus, species_epithet]
    es. ["Animalia", "Chordata", "Aves", ..., "Phoenicopterus", "roseus"]

    Il nome scientifico corretto e' "Genus species_epithet" = livello[-2] + " " + livello[-1].
    Entrambi devono essere stringhe non vuote con una sola parola ciascuno.
    """
    if not bioclip_taxonomy_json:
        return None
    try:
        taxonomy = json.loads(bioclip_taxonomy_json)
        if not isinstance(taxonomy, list) or len(taxonomy) < 2:
            return None

        # Filtra i livelli non vuoti
        levels = [l.strip() for l in taxonomy if isinstance(l, str) and l.strip()]
        if len(levels) < 2:
            return None

        genus = levels[-2]
        epithet = levels[-1]

        # Entrambi devono essere singole parole (non nomi composti o livelli superiori)
        if " " in genus or " " in epithet:
            return None

        # Il genere inizia con maiuscola, l'epiteto con minuscola
        if not genus[0].isupper() or not epithet[0].islower():
            return None

        return f"{genus} {epithet}"

    except Exception:
        return None


def normalize_tags(
    tags,
    scientific_name=None,
    vernacular_name=None,
):
    """
    Normalizza e deduplica una lista di tag con ordine canonico.
    NOTA: duplicata da utils.py di OffGallery — mantenere sincronizzate.

    Ordine risultante: nome scientifico → nome vernacolare → resto (ordine originale).
    Deduplicazione case-insensitive, rimuove vuoti.
    """
    seen_lower = set()
    deduped = []
    for tag in (tags or []):
        if not isinstance(tag, str) or not tag.strip():
            continue
        tl = tag.strip().lower()
        if tl not in seen_lower:
            seen_lower.add(tl)
            deduped.append(tag.strip())

    sci_lower  = scientific_name.strip().lower()  if scientific_name  else None
    vern_lower = vernacular_name.strip().lower()  if vernacular_name  else None

    rest = [
        t for t in deduped
        if t.lower() != sci_lower and t.lower() != vern_lower
    ]

    result = []
    if scientific_name and scientific_name.strip():
        result.append(scientific_name.strip())
    if vernacular_name and vernacular_name.strip():
        if vern_lower != sci_lower:
            result.append(vernacular_name.strip())
    result.extend(rest)
    return result


def _update_tags_with_vernacular(
    existing_tags_json: Optional[str],
    scientific_name: Optional[str],
    vernacular_name: str,
) -> str:
    """
    Aggiorna il JSON dei tag applicando normalize_tags con nome scientifico e vernacolare.

    Returns:
        JSON string dell'array tags aggiornato.
    """
    try:
        tags = json.loads(existing_tags_json) if existing_tags_json else []
        if not isinstance(tags, list):
            tags = []
    except Exception:
        tags = []

    normalized = normalize_tags(tags, scientific_name, vernacular_name)
    return json.dumps(normalized, ensure_ascii=False)


def process_images(
    offgallery_db_path: str,
    mode: str = "unprocessed",
    language: str = "it",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    stop_event=None,
    image_ids: Optional[List[int]] = None,
    directory_filter: Optional[str] = None,
):
    """
    Itera sulle foto nel DB OffGallery e aggiorna tags e vernacular_name.

    Args:
        offgallery_db_path: Path assoluto al database OffGallery
        mode: "unprocessed" | "all" | "ids" | "directory"
        language: Codice lingua ISO 639-1 (default "it")
        progress_callback: Funzione chiamata con (current, total) ad ogni immagine
        stop_event: threading.Event opzionale — se settato interrompe il loop
        image_ids: Lista ID immagini (solo per mode="ids")
        directory_filter: Path directory da filtrare (solo per mode="directory")
    """
    conn = sqlite3.connect(offgallery_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Aggiunge colonna vernacular_name se non esiste
    _ensure_vernacular_column(conn)

    # Seleziona le foto da elaborare in base alla modalità
    if mode == "all":
        cur = conn.execute(
            "SELECT id, tags, bioclip_taxonomy FROM images WHERE bioclip_taxonomy IS NOT NULL"
        )
    elif mode == "ids" and image_ids:
        placeholders = ",".join("?" * len(image_ids))
        cur = conn.execute(
            f"SELECT id, tags, bioclip_taxonomy FROM images "
            f"WHERE id IN ({placeholders}) AND bioclip_taxonomy IS NOT NULL",
            image_ids,
        )
    elif mode == "directory" and directory_filter:
        # directory_filter può contenere più directory separate da '|'
        directories = [d.strip() for d in directory_filter.split("|") if d.strip()]
        placeholders = " OR ".join("filepath LIKE ?" for _ in directories)
        params = [d.rstrip("/\\") + "%" for d in directories]
        cur = conn.execute(
            f"""SELECT id, tags, bioclip_taxonomy FROM images
               WHERE bioclip_taxonomy IS NOT NULL AND ({placeholders})""",
            params,
        )
    else:
        # Default: solo non processate
        cur = conn.execute(
            """SELECT id, tags, bioclip_taxonomy FROM images
               WHERE bioclip_taxonomy IS NOT NULL AND vernacular_name IS NULL"""
        )

    rows = cur.fetchall()
    total = len(rows)

    logger.info(f"BioNomen: {total} immagini da elaborare (mode={mode}, lang={language})")

    matched = 0
    not_matched = 0

    for idx, row in enumerate(rows, start=1):
        # Controlla interruzione prima di ogni specie
        if stop_event and stop_event.is_set():
            logger.info("BioNomen: elaborazione interrotta dall'utente")
            break

        image_id = row["id"]
        tags_json = row["tags"]
        bioclip_json = row["bioclip_taxonomy"]

        # Progresso
        if progress_callback:
            progress_callback(idx, total)
        # Stampa su stdout per comunicazione con OffGallery
        print(f"PROGRESS:{idx}:{total}", flush=True)

        # Estrai nome scientifico e taxon dalla tassonomia BioCLIP
        scientific_name = _extract_scientific_name(bioclip_json)
        if not scientific_name:
            not_matched += 1
            conn.execute(
                "UPDATE images SET vernacular_name=? WHERE id=?",
                ("", image_id),
            )
            conn.commit()
            continue

        # Determina il taxon per aprire il DB corretto (es. "aves", "mammalia")
        taxon_id = _extract_taxon_class(bioclip_json)

        # Lookup nome vernacolare diretto sul DB del taxon (interrompibile)
        vernacular = lookup_vernacular_name(
            scientific_name, language,
            taxon=taxon_id,
            stop_event=stop_event,
        )

        # Ricontrolla stop dopo il lookup (potrebbe essere arrivato durante la ricerca parallela)
        if stop_event and stop_event.is_set():
            break

        # Aggiorna il record
        if vernacular:
            matched += 1
            new_tags_json = _update_tags_with_vernacular(tags_json, scientific_name, vernacular)
            conn.execute(
                "UPDATE images SET tags=?, vernacular_name=? WHERE id=?",
                (new_tags_json, vernacular, image_id),
            )
        else:
            not_matched += 1
            conn.execute(
                "UPDATE images SET vernacular_name=? WHERE id=?",
                ("", image_id),
            )

        conn.commit()

        # Pausa minima per non sovraccaricare le API esterne
        time.sleep(0.1)

    conn.close()

    # Emette riepilogo su stdout per la card OffGallery (comunicazione col sottoprocesso)
    print(f"SUMMARY:{total}:{matched}:{not_matched}", flush=True)
    logger.info(f"BioNomen: completato — {total} processate, {matched} con nome, {not_matched} senza nome")

    return total, matched, not_matched


def _fetch_single_vernacular(args):
    """
    Worker per ThreadPoolExecutor: recupera il nome vernacolare di una singola specie.
    Ritorna (sci_name, vernacular_name|None, lang_code).
    """
    import urllib.request
    usage_key, sci_name, lang_code, language = args
    try:
        vurl = f"https://api.gbif.org/v1/species/{usage_key}/vernacularNames?limit=50"
        req = urllib.request.Request(vurl, headers={"User-Agent": "BioNomen/2.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            vdata = json.loads(resp.read().decode())
        for entry in vdata.get("results", []):
            entry_lang = entry.get("language", "")
            if entry_lang in (lang_code, language) and entry.get("vernacularName"):
                return (sci_name, entry["vernacularName"], lang_code)
    except Exception:
        pass
    return (sci_name, None, lang_code)


def _fetch_gbif_vernacular_bulk(
    class_key: int,
    language: str,
    conn: sqlite3.Connection,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    count_callback: Optional[Callable[[int], None]] = None,
    stop_event=None,
) -> int:
    """
    Scarica in bulk i nomi vernacolari da GBIF per una classe tassonomica.

    Strategia:
    - Pagina l'elenco specie via /v1/species?classKey=X (1000 per pagina)
    - Parallelizza le chiamate /vernacularNames con ThreadPoolExecutor (8 worker)
    - Commit ogni 200 inserimenti per ridurre I/O SQLite
    - Emette progress per ogni specie processata (non per pagina)

    Ritorna il numero di record salvati.
    """
    import urllib.request
    import urllib.parse
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    _WORKERS    = 8     # Chiamate HTTP in parallelo verso GBIF
    _BATCH_SIZE = 200   # Commit ogni N inserimenti
    _PAGE_SIZE  = 1000  # Specie per pagina dell'elenco

    lang_code      = _LANG_MAP.get(language, language)
    saved          = 0
    processed      = 0  # Specie completamente elaborate (con o senza nome)
    total_estimate = 0
    offset         = 0

    # Raccolta lock per SQLite (non thread-safe su più thread)
    db_lock = threading.Lock()

    while True:
        if stop_event and stop_event.is_set():
            break

        # --- Recupera pagina elenco specie ---
        # Usa species/search (non species) perché:
        # - supporta il campo "count" nel JSON di risposta
        # - filtra solo specie ACCEPTED del backbone (esclude sinonimi e duplicati)
        # - Aves: ~14.600 ACCEPTED vs ~90.500 totali con sinonimi
        # Nota: alcuni taxa (es. Reptilia classKey=358) sono PROPARTE_SYNONYM nel backbone
        # → per loro il fallback è classKey senza filtro status
        url = (
            "https://api.gbif.org/v1/species/search?"
            + urllib.parse.urlencode({
                "highertaxonKey": class_key,
                "rank":           "SPECIES",
                "status":         "ACCEPTED",
                "limit":          _PAGE_SIZE,
                "offset":         offset,
            })
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BioNomen/2.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f"GBIF bulk: errore fetch offset={offset}: {e}")
            break

        results = data.get("results", [])

        # Fallback per taxa problematici nel backbone (es. Reptilia = PROPARTE_SYNONYM):
        # se count=0 e offset=0 riprova con classKey senza filtro status
        if not results and offset == 0 and data.get("count", -1) == 0:
            logger.info(f"GBIF bulk: highertaxonKey={class_key} restituisce 0 → fallback classKey")
            url_fb = (
                "https://api.gbif.org/v1/species/search?"
                + urllib.parse.urlencode({
                    "classKey": class_key,
                    "rank":     "SPECIES",
                    "status":   "ACCEPTED",
                    "limit":    _PAGE_SIZE,
                    "offset":   0,
                })
            )
            try:
                req_fb = urllib.request.Request(url_fb, headers={"User-Agent": "BioNomen/2.0"})
                with urllib.request.urlopen(req_fb, timeout=15) as resp_fb:
                    data = json.loads(resp_fb.read().decode())
                results = data.get("results", [])
            except Exception as e:
                logger.warning(f"GBIF bulk: fallback classKey errore: {e}")

        if not results:
            break

        if total_estimate == 0:
            total_estimate = data.get("count", 0)
            if total_estimate > 0 and count_callback:
                count_callback(total_estimate)  # comunica il count reale al chiamante

        # --- Prepara tasks: solo specie non già in cache ---
        tasks = []
        for species in results:
            if stop_event and stop_event.is_set():
                break
            usage_key = species.get("key") or species.get("speciesKey")
            sci_name  = (
                species.get("species")
                or species.get("canonicalName")
                or species.get("scientificName", "")
            )
            if not usage_key or not sci_name:
                continue
            # Già in cache → salta la chiamata HTTP
            with db_lock:
                cur = conn.execute(
                    "SELECT 1 FROM vernacular_names WHERE scientific_name=? AND language=?",
                    (sci_name, lang_code),
                )
                if cur.fetchone():
                    processed += 1
                    if progress_callback:
                        progress_callback(
                            min(offset + processed, total_estimate),
                            max(total_estimate, 1),
                        )
                    continue
            tasks.append((usage_key, sci_name, lang_code, language))

        # --- Esegui in parallelo ---
        pending_rows = []
        with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
            futures = {executor.submit(_fetch_single_vernacular, t): t for t in tasks}
            for future in as_completed(futures):
                if stop_event and stop_event.is_set():
                    # Cancella i futures ancora in coda
                    for f in futures:
                        f.cancel()
                    break
                sci_name, vname, lc = future.result()
                processed += 1
                if vname:
                    pending_rows.append((sci_name, vname, lc))
                    saved += 1

                # Commit batch
                if len(pending_rows) >= _BATCH_SIZE:
                    with db_lock:
                        conn.executemany(
                            """INSERT OR REPLACE INTO vernacular_names
                               (scientific_name, vernacular_name, language, source, confidence)
                               VALUES (?, ?, ?, 'gbif_bulk', 1)""",
                            pending_rows,
                        )
                        conn.commit()
                    pending_rows.clear()

                if progress_callback:
                    progress_callback(
                        min(offset + processed, total_estimate),
                        max(total_estimate, 1),
                    )

        # Commit residuo
        if pending_rows:
            with db_lock:
                conn.executemany(
                    """INSERT OR REPLACE INTO vernacular_names
                       (scientific_name, vernacular_name, language, source, confidence)
                       VALUES (?, ?, ?, 'gbif_bulk', 1)""",
                    pending_rows,
                )
                conn.commit()
            pending_rows.clear()

        offset += len(results)
        if data.get("endOfRecords", True):
            break

        time.sleep(0.05)  # Pausa cortesia verso GBIF

    return saved


def download_taxon_database(
    taxon: str,
    language: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    count_callback: Optional[Callable[[int], None]] = None,
    stop_event=None,
) -> int:
    """
    Scarica il database bulk GBIF per un taxon e una lingua.
    Popola bionomen_<taxon>_<language>.db nella data_dir.

    Args:
        taxon: Id taxon (es. "aves", "mammalia")
        language: Codice lingua ISO 639-1 (es. "it", "en")
        progress_callback: Funzione (current, total)
        status_callback: Funzione (testo_descrittivo) per aggiornare label UI
        stop_event: threading.Event per interruzione

    Returns:
        Numero di record salvati.
    """
    if taxon not in TAXA:
        raise ValueError(f"Taxon sconosciuto: {taxon}. Validi: {list(TAXA.keys())}")

    class_key   = TAXA[taxon]["class_key"]
    taxon_label = TAXA[taxon]["label"]
    conn        = _init_taxon_db(taxon, language)

    logger.info(f"BioNomen: download bulk {taxon} lingua={language} classKey={class_key}")
    if status_callback:
        status_callback(f"Download {taxon_label}...")

    saved = _fetch_gbif_vernacular_bulk(
        class_key=class_key,
        language=language,
        conn=conn,
        progress_callback=progress_callback,
        count_callback=count_callback,
        stop_event=stop_event,
    )

    # Salva data aggiornamento
    now = datetime.now().strftime("%d/%m/%y %H:%M")
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)",
        (now,),
    )
    conn.commit()
    conn.close()

    logger.info(f"BioNomen: {taxon}/{language} completato — {saved} record salvati")
    if status_callback:
        status_callback(f"{taxon_label}: {saved:,} nomi salvati".replace(",", "."))
    return saved


def download_and_build_database(
    language: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    stop_event=None,
):
    """
    Scarica il database bulk GBIF per tutti i taxa abilitati.

    Args:
        language: Lingua ISO 639-1 (es. "it"). Se None legge da config.json (fallback "it").
        progress_callback: Funzione (current, total) per progress bar
        status_callback: Funzione (testo) per label descrittiva in UI
        stop_event: threading.Event per interruzione
    """
    cfg = load_config()
    if not language:
        language = cfg.get("language", "it")
    taxa_enabled = cfg.get("taxa_enabled", ["aves"])

    # Stime specie ACCEPTED nel backbone GBIF (aggiornate 2025)
    # Usato come denominatore per la progress bar prima che arrivi il count reale
    _SPECIES_ESTIMATE = {
        "aves":     15000,
        "mammalia": 21000,
        "reptilia": 10000,   # backbone problematico, stima conservativa
        "amphibia": 10000,
        "insecta":  120000,  # solo quelle con nomi vernacolari (totale ~1.1M ma 99% senza)
        "plantae":  50000,   # idem
    }

    total_taxa = len(taxa_enabled)

    # Dizionario count reali per taxon: si aggiorna appena arriva la prima pagina GBIF
    # Inizializzato con le stime, poi sostituito con il count reale
    real_counts = {t: _SPECIES_ESTIMATE.get(t, 5000) for t in taxa_enabled}

    def _total_global():
        return sum(real_counts.values())

    global_done = 0

    for idx, taxon in enumerate(taxa_enabled):
        if stop_event and stop_event.is_set():
            break

        taxon_label    = TAXA.get(taxon, {}).get("label", taxon)
        taxon_estimate = real_counts[taxon]
        logger.info(f"BioNomen: download [{idx+1}/{total_taxa}] {taxon}")

        taxon_start = global_done

        def _count_cb(real_count, _taxon=taxon):
            # Sostituisce la stima con il count reale appena arriva dalla prima pagina GBIF
            real_counts[_taxon] = real_count
            logger.info(f"BioNomen: {_taxon} count reale GBIF = {real_count}")

        def _cb(current, total, _taxon_start=taxon_start, _taxon=taxon):
            # Aggiorna real_counts con il total che arriva da _fetch_gbif_vernacular_bulk
            if total > 0:
                real_counts[_taxon] = total
            g_total   = _total_global()
            # Lascia sempre 1 unità di margine: il 100% viene raggiunto solo
            # quando download_taxon_database chiama status_callback("completato")
            # Evita che la barra sembri finita mentre le ultime chiamate HTTP sono in corso
            g_current = _taxon_start + min(current, real_counts[_taxon] - 1)
            if progress_callback:
                progress_callback(g_current, g_total)

        def _scb(text, _idx=idx):
            if status_callback:
                status_callback(f"[{_idx+1}/{total_taxa}] {text}")

        download_taxon_database(
            taxon=taxon,
            language=language,
            progress_callback=_cb,
            status_callback=_scb,
            count_callback=_count_cb,
            stop_event=stop_event,
        )
        global_done += real_counts[taxon]  # count reale aggiornato da _count_cb/_cb
        # Emette progress al 100% per questo taxon dopo che è realmente completato
        if progress_callback:
            progress_callback(global_done, _total_global())
