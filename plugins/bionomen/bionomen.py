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

# Taxa supportati: id → {label, class_keys GBIF, nomi classe BioCLIP}
# class_keys: LISTA di chiavi GBIF da cui scaricare (highertaxonKey nella species/search).
#   È una lista e non un singolo valore perché nel backbone GBIF moderno "Reptilia"
#   non esiste più come classe accettata: la key storica 358 è PROPARTE_SYNONYM e
#   restituisce count=0, mentre i rettili vivono in classi separate (Squamata,
#   Testudines, Crocodylia, Sphenodontia). Vedi commento in download_taxon_database.
# bioclip_classes: nomi che compaiono nel livello "Class" della tassonomia BioCLIP
TAXA = {
    "aves":      {"label": "Aves (Uccelli)",       "class_keys": [212],   "bioclip_classes": ["Aves"]},
    "mammalia":  {"label": "Mammalia (Mammiferi)",  "class_keys": [359],   "bioclip_classes": ["Mammalia"]},
    # Reptilia: 4 classi GBIF distinte (~14.150 specie in totale).
    #   11592253 Squamata (12.784) — sauri e serpenti
    #   11418114 Testudines (1.136) — tartarughe
    #   11493978 Crocodylia (238) — coccodrilli
    #   11569602 Sphenodontia (tuatara)
    # BioCLIP continua a etichettarli "Reptilia", quindi bioclip_classes resta invariato.
    "reptilia":  {"label": "Reptilia (Rettili)",
                  "class_keys": [11592253, 11418114, 11493978, 11569602],
                  "bioclip_classes": ["Reptilia"]},
    "amphibia":  {"label": "Amphibia (Anfibi)",     "class_keys": [131],   "bioclip_classes": ["Amphibia"]},
    "insecta":   {"label": "Insecta (Insetti)",     "class_keys": [216],   "bioclip_classes": ["Insecta"]},
    "plantae":   {"label": "Plantae (Piante)",      "class_keys": [6],     "bioclip_classes": ["Magnoliopsida", "Liliopsida", "Pinopsida", "Polypodiopsida"]},
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

# Normalizzazione nome lingua interfaccia OffGallery → codice ISO 639-1
_UI_LANG_MAP = {
    "italiano": "it", "italian": "it",
    "english": "en", "inglese": "en",
    "deutsch": "de", "tedesco": "de",
    "francese": "fr", "french": "fr",
    "spagnolo": "es", "spanish": "es",
    "portoghese": "pt", "portuguese": "pt",
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
        # "auto" = eredita la lingua dall'interfaccia OffGallery (llm_output_language);
        # un codice ISO 639-1 (es. "en") = lingua nome comune forzata, indipendente dai testi LLM
        "language_mode": "auto",
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


def _find_offgallery_config() -> Optional[str]:
    """Localizza il config_new.yaml di OffGallery risalendo dalla posizione del plugin.

    Serve ai chiamanti che NON hanno il path sottomano: le funzioni di sola
    lettura dello stato (is_database_present, get_database_info,
    get_database_report) sono invocate anche dalla ConfigDialog e dalla card,
    che non lo propagano. Senza questo fallback, con language_mode="auto" la
    lingua cadeva sul default "it" e si cercavano DB bionomen_<taxon>_it.db
    inesistenti mentre il download — che il path ce l'ha — aveva scritto _en.db:
    da qui "Database non presente" a fronte di database perfettamente validi.

    Il plugin resta standalone: si risale il filesystem, non si importa OffGallery.
    """
    # plugins/bionomen/bionomen.py → plugins/bionomen → plugins → root app
    candidate = _PLUGIN_DIR.parent.parent / "config_new.yaml"
    if candidate.exists():
        return str(candidate)
    return None


def _ui_language_from_offgallery(offgallery_config_path: Optional[str]) -> str:
    """Legge la lingua interfaccia (llm_output_language) dal config_new.yaml di OffGallery.

    Se il path non viene passato lo si cerca da soli (vedi _find_offgallery_config).
    Ritorna un codice ISO 639-1 (default "it") se il file non è leggibile.
    """
    if not offgallery_config_path:
        offgallery_config_path = _find_offgallery_config()
    if not offgallery_config_path:
        return "it"
    try:
        import yaml  # type: ignore
        with open(offgallery_config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        lang = config.get("ui", {}).get("llm_output_language", "it")
        return _UI_LANG_MAP.get(lang.lower(),
                                lang[:2].lower() if len(lang) >= 2 else "it")
    except Exception:
        return "it"


def resolve_language(offgallery_config_path: Optional[str] = None,
                     plugin_cfg: Optional[dict] = None) -> str:
    """Risolve la lingua effettiva del nome comune.

    Regola:
      - language_mode == "auto"  → eredita dalla lingua interfaccia OffGallery
        (llm_output_language nel config_new.yaml passato).
      - language_mode == <codice> → usa quel codice ISO 639-1 (indipendente dai testi LLM).

    Args:
        offgallery_config_path: path al config_new.yaml di OffGallery (per il caso auto).
        plugin_cfg: config del plugin già caricato (evita riletture); se None viene caricato.

    Returns:
        Codice lingua ISO 639-1 (es. "it", "en").
    """
    cfg = plugin_cfg if plugin_cfg is not None else load_config()
    mode = (cfg.get("language_mode") or "auto").strip().lower()
    if mode and mode != "auto":
        return mode
    return _ui_language_from_offgallery(offgallery_config_path)


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
    # Controlla almeno un DB tra quelli abilitati, NELLA LINGUA RISOLTA.
    # Nota: la chiave di config è "language_mode" (auto o codice ISO), non
    # "language" — leggere "language" dava sempre il default "it", quindi la
    # card dichiarava "database presente" guardando l'italiano anche quando la
    # lingua richiesta era un'altra e il suo DB non esisteva.
    # Con language_mode="auto" la lingua arriva dal config_new.yaml di
    # OffGallery, che resolve_language localizza da sé: qui il path non c'è.
    cfg = load_config()
    lang = resolve_language(plugin_cfg=cfg)
    for t in cfg.get("taxa_enabled", []):
        db = get_db_path(t, lang)
        if _db_has_data(db):
            return True
    return False


# Sotto questa soglia il DB è considerato non scaricato: il lookup online crea il
# file e ci scrive qualche nome man mano che elabora le foto, quindi "esiste la
# tabella" non significa "database scaricato". Un download bulk reale produce
# migliaia di righe anche per il taxon più piccolo.
_MIN_ROWS_DOWNLOADED = 500


def _db_has_data(db: Path) -> bool:
    """Verifica se il DB esiste ed è stato effettivamente popolato dal download."""
    if not db.exists():
        return False
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vernacular_names'"
        )
        if cur.fetchone() is None:
            conn.close()
            return False
        # Contare le righe, non fermarsi all'esistenza della tabella: un file creato
        # dal lookup online ne ha una manciata e NON è un database scaricato.
        n = conn.execute("SELECT COUNT(*) FROM vernacular_names").fetchone()[0]
        conn.close()
        return n >= _MIN_ROWS_DOWNLOADED
    except Exception:
        logger.warning("BioNomen: verifica dati DB fallita per %s", db, exc_info=True)
        return False


def get_database_info() -> dict:
    """
    Ritorna un dict {taxon: {"date": str, "count": int}} per i DB presenti.
    """
    cfg = load_config()
    # "language" è una chiave morta (la config ha "language_mode"): usare
    # resolve_language, altrimenti si riportano sempre i DB italiani.
    lang = resolve_language(plugin_cfg=cfg)
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


# Specie ACCEPTED note per taxon nel backbone GBIF (misurate 2026-07-17).
# Servono come denominatore per dire all'utente "quanto è completo" un DB.
# NOTA: non tutte le specie hanno un nome comune — per insecta/plantae la
# stragrande maggioranza non ce l'ha in nessuna lingua, quindi la copertura
# attesa è bassissima per natura e non indica un download fallito.
_SPECIES_TOTAL_GBIF = {
    "aves":       14641,
    "mammalia":   21100,
    "reptilia":   14204,
    "amphibia":    9815,
    "insecta":  1105104,
    "plantae":   446842,
}

# Copertura tipica attesa (nomi comuni trovati / specie totali) per un download
# completo. Sotto questa soglia il DB è probabilmente incompleto.
# Insecta e plantae sono bassissime perché le specie con nome comune sono poche:
# è una proprietà della natura, non un sintomo di download fallito. La prova di
# completezza NON è questa stima ma il flag 'incomplete' scritto dal download.
_EXPECTED_COVERAGE = {
    "aves":     0.55,
    "mammalia": 0.30,
    "reptilia": 0.20,
    "amphibia": 0.45,
    "insecta":  0.005,
    "plantae":  0.005,
}


# Taxa per cui ha senso il filtro geografico: gli unici sopra il tetto GBIF.
# Gli altri (9.815-21.100 specie) si scaricano interi in pochi minuti, un filtro
# per paese aggiungerebbe complessità senza guadagno.
COUNTRY_FILTERABLE = ("insecta", "plantae")


def get_taxon_countries(taxon: str, plugin_cfg: Optional[dict] = None) -> List[str]:
    """Paesi ISO-3166-alpha2 configurati per un taxon; lista vuota = tutto il mondo.

    Il filtro vale solo per i taxa in COUNTRY_FILTERABLE: se qualcuno mettesse a
    mano dei paesi su aves, verrebbero ignorati invece di produrre un DB monco.
    """
    if taxon not in COUNTRY_FILTERABLE:
        return []
    cfg = plugin_cfg if plugin_cfg is not None else load_config()
    countries = (cfg.get("taxa_countries") or {}).get(taxon) or []
    return [str(c).strip().upper() for c in countries if str(c).strip()]


def get_downloaded_countries(taxon: str, language: str) -> List[str]:
    """Paesi già presenti nel DB di un taxon (dai metadata). Vuoto = nessuno/mondiale."""
    db = get_db_path(taxon, language)
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT value FROM metadata WHERE key='countries' LIMIT 1"
        ).fetchone()
        conn.close()
    except Exception:
        logger.warning("BioNomen: lettura paesi fallita per %s", db, exc_info=True)
        return []
    if not row or not row[0]:
        return []
    return [c for c in row[0].split(",") if c]


def get_database_report(language: Optional[str] = None) -> List[dict]:
    """Report leggibile sullo stato dei DB, pensato per la UI (non per la CLI).

    Per ogni taxon abilitato ritorna un dict:
        {taxon, label, exists, rows, expected_total, status, detail}
    dove status è uno tra "ok" | "incomplete" | "missing".

    Serve a rispondere alla domanda "come faccio a sapere se i database sono
    completi?" senza che l'utente debba aprire un terminale: la dimensione in KB
    non è un indicatore utile, il numero di righe sì.
    """
    cfg = load_config()
    lang = language or resolve_language(plugin_cfg=cfg)
    report = []
    for taxon in cfg.get("taxa_enabled", []):
        label = TAXA.get(taxon, {}).get("label", taxon)
        db = get_db_path(taxon, lang)
        expected = _SPECIES_TOTAL_GBIF.get(taxon, 0)
        entry = {
            "taxon": taxon,
            "label": label,
            "language": lang,
            "exists": db.exists(),
            "rows": 0,
            "expected_total": expected,
            "status": "missing",
            "detail": "",
        }
        if not db.exists():
            entry["detail"] = "database non scaricato"
            report.append(entry)
            continue
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT COUNT(*) FROM vernacular_names WHERE vernacular_name != ''"
            ).fetchone()[0]
            # Il download stesso dichiara se si è interrotto: è un'informazione
            # certa, mentre la soglia di copertura è solo una stima.
            inc_row = conn.execute(
                "SELECT value FROM metadata WHERE key='incomplete' LIMIT 1"
            ).fetchone()
            conn.close()
        except Exception:
            logger.warning("BioNomen: report DB fallito per %s", db, exc_info=True)
            entry["detail"] = "database illeggibile"
            report.append(entry)
            continue

        entry["rows"] = rows
        # Un DB scaricato per paesi non va misurato col metro mondiale: le sue
        # righe sono poche per scelta, non per difetto. Si dice cosa contiene.
        dl_countries = get_downloaded_countries(taxon, lang)
        entry["countries"] = dl_countries
        if dl_countries and not inc_row:
            entry["status"] = "ok"
            # Il separatore migliaia si sostituisce PRIMA di unire i paesi:
            # un replace(",", ".") sull'intera stringa rovinerebbe "IT, FR".
            entry["detail"] = (f"{rows:,} nomi".replace(",", ".")
                               + f" — {', '.join(dl_countries)}")
            report.append(entry)
            continue

        if inc_row:
            entry["status"] = "incomplete"
            entry["detail"] = (
                f"{rows:,} nomi — {inc_row[0]}: rilanciare il download"
            ).replace(",", ".")
            report.append(entry)
            continue

        min_expected = int(expected * _EXPECTED_COVERAGE.get(taxon, 0.1))
        if rows < _MIN_ROWS_DOWNLOADED or rows < min_expected:
            entry["status"] = "incomplete"
            entry["detail"] = (
                f"{rows:,} nomi — sembra incompleto, "
                f"attesi almeno ~{min_expected:,}".replace(",", ".")
            )
        else:
            entry["status"] = "ok"
            entry["detail"] = f"{rows:,} nomi comuni".replace(",", ".")
        report.append(entry)
    return report


def get_database_date() -> Optional[str]:
    """Ritorna la data di aggiornamento del DB più recente tra quelli presenti."""
    info = get_database_info()
    dates = [v["date"] for v in info.values() if v.get("date")]
    return dates[-1] if dates else None


def _init_taxon_db(taxon: str, language: str) -> sqlite3.Connection:
    """Inizializza il database per un taxon+lingua con lo schema completo."""
    db_path = get_db_path(taxon, language)
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    # WAL mode: scritture non bloccano letture concorrenti su Windows
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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
    # Specie GBIF già interrogate, incluse quelle risultate senza nome comune.
    # Serve al download per paese: senza, aggiungere un paese ri-interrogherebbe
    # da zero tutte le specie in comune coi paesi già scaricati (e la maggior
    # parte delle specie un nome comune non ce l'ha, quindi non lascia traccia
    # in vernacular_names). CREATE IF NOT EXISTS = i DB esistenti si adeguano da
    # soli alla prima apertura, senza migrazioni.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vernacular_keys (
            taxon_key INTEGER NOT NULL,
            language  TEXT NOT NULL,
            PRIMARY KEY (taxon_key, language)
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
        lexicon_key = _INAT_LEXICON.get(language, language)

        # PRIORITA' 1: nome nel lexicon della lingua richiesta.
        # `preferred_common_name` NON e' garantito nella lingua del locale
        # (iNaturalist puo' restituire il nome "preferito" globale, spesso in
        # un'altra lingua) → prima cerchiamo esplicitamente nel lexicon corretto,
        # cosi' evitiamo ibridi tipo nome italiano in testo inglese.
        for entry in taxon.get("taxon_names", []):
            if entry.get("lexicon", "").lower() == lexicon_key and entry.get("name"):
                candidate = entry["name"]
                if not _contains_geo_term(candidate):
                    return candidate

        # PRIORITA' 2: `preferred_common_name` come ripiego, ma SOLO se la sua
        # lingua coincide con quella richiesta. iNaturalist marca il preferito
        # con `preferred_common_name` e il relativo lexicon in taxon_names: se
        # non troviamo conferma della lingua, non lo usiamo (meglio nessun nome
        # che un nome nella lingua sbagliata).
        common = taxon.get("preferred_common_name", "")
        if common and not _contains_geo_term(common):
            for entry in taxon.get("taxon_names", []):
                if (entry.get("name") == common
                        and entry.get("lexicon", "").lower() == lexicon_key):
                    return common
        elif common and _contains_geo_term(common):
            print(f"LOG:warning:iNaturalist '{scientific_name}': nome geografico filtrato ('{common}')", flush=True)

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
            print(f"LOG:debug:BioNomen [{scientific_name}] -> ricerca online disabilitata", flush=True)
            return None

        if stop_event and stop_event.is_set():
            return None

        # 3. Ricerca online parallela — GBIF + Wikipedia + iNaturalist + Wikidata
        print(
            f"LOG:debug:BioNomen [{scientific_name}] -> "
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

        print(f"LOG:debug:BioNomen [{scientific_name}] -> nessuna fonte ha il nome comune", flush=True)

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

    # Verifica presenza dei DB nomi comuni per la lingua richiesta.
    # Se un taxon abilitato non ha il DB scaricato in questa lingua, avvisa:
    # senza DB locale il lookup ricade sull'online (se attivo) o non trova nulla.
    # Il warning è visibile anche nella finestra del Process Tab (intercetta LOG: su stdout).
    try:
        cfg = load_config()
        for _tx in cfg.get("taxa_enabled", []):
            if not get_db_path(_tx, language).exists():
                print(
                    f"LOG:warning:BioNomen: database nomi comuni '{_tx}' in lingua "
                    f"'{language}' non presente — scaricalo dal plugin BioNomen "
                    f"(altrimenti i nomi comuni in questa lingua non verranno assegnati)",
                    flush=True,
                )
    except Exception:
        logger.warning("BioNomen: verifica presenza DB per lingua fallita", exc_info=True)

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
    Usa requests invece di urllib per gestire correttamente il timeout HTTPS su Windows.
    Ritorna (sci_name, vernacular_name|None, lang_code).
    """
    import requests
    usage_key, sci_name, lang_code, language = args
    try:
        vurl = f"https://api.gbif.org/v1/species/{usage_key}/vernacularNames?limit=50"
        resp = requests.get(vurl, timeout=8, headers={"User-Agent": "BioNomen/2.0"})
        resp.raise_for_status()
        vdata = resp.json()
        for entry in vdata.get("results", []):
            entry_lang = entry.get("language", "")
            if entry_lang in (lang_code, language) and entry.get("vernacularName"):
                return (sci_name, entry["vernacularName"], lang_code)
    except Exception:
        pass
    return (sci_name, None, lang_code)


class _GbifPageCapError(Exception):
    """GBIF ha rifiutato la pagina perché oltre il tetto di paginazione (100.000).

    Va distinta da un errore di rete: non ha senso ritentarla, e non significa
    che i dati siano finiti. Significa che il ramo andava spezzato in shard.
    """


def _gbif_get_json(url: str, retries: int = 4) -> dict:
    """GET su GBIF con retry a backoff esponenziale.

    Distingue tre esiti, che prima erano confusi in uno solo:
    - successo → dict JSON;
    - tetto di paginazione → _GbifPageCapError (inutile ritentare);
    - errore di rete/server → riprova, e solo se insiste solleva l'eccezione.

    Un errore transitorio di rete non deve mai essere scambiato per "dati finiti":
    era il difetto che rendeva invisibili i download troncati.
    """
    import requests as _req
    last_exc = None
    for attempt in range(retries):
        try:
            resp = _req.get(url, timeout=20, headers={"User-Agent": "BioNomen/2.0"})
            # 500/400 su offset alti = tetto di Elasticsearch, non errore transitorio
            if resp.status_code in (400, 500) and "offset=" in url:
                try:
                    off = int(url.split("offset=")[1].split("&")[0])
                except (ValueError, IndexError):
                    off = 0
                if off + 1000 > _GBIF_PAGE_CAP:
                    raise _GbifPageCapError(f"offset {off} oltre il tetto GBIF")
            resp.raise_for_status()
            return resp.json()
        except _GbifPageCapError:
            raise
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
    raise last_exc


def _gbif_species_count(class_key: int) -> int:
    """Ritorna il numero di specie ACCEPTED sotto una chiave GBIF (0 se non determinabile).

    Serve a conoscere il denominatore REALE della progress bar prima di iniziare:
    è il campo "count" di species/search con gli stessi filtri usati dal download.
    """
    import urllib.parse
    try:
        import requests as _req
        url = (
            "https://api.gbif.org/v1/species/search?"
            + urllib.parse.urlencode({
                "highertaxonKey": class_key,
                "rank":           "SPECIES",
                "status":         "ACCEPTED",
                "limit":          0,
            })
        )
        resp = _req.get(url, timeout=15, headers={"User-Agent": "BioNomen/2.0"})
        resp.raise_for_status()
        return int(resp.json().get("count", 0) or 0)
    except Exception:
        logger.warning("BioNomen: count specie fallito per key=%s", class_key, exc_info=True)
        return 0


# --------------------------------------------------------------------------
# Sharding adattivo — aggira il tetto di paginazione di GBIF
# --------------------------------------------------------------------------
# GBIF species/search rifiuta offset+limit > 100.000 (index.max_result_window
# di Elasticsearch): a 100.000 risponde, a 100.001 dà HTTP 500. Non è aggirabile
# con retry o pazienza. Insecta (1.105.104 specie) e Plantae (446.842) stanno
# sopra il tetto: paginandole dall'alto se ne raggiungeva solo il 9% e il 22%.
#
# La chiave è che il tetto vale PER QUERY, non in assoluto: se si spezza il taxon
# in sotto-alberi abbastanza piccoli, ogni sotto-albero è interamente paginabile.
# Misurato: Coleoptera (373.306) sfonda il tetto, ma nessuna delle sue 341
# famiglie lo raggiunge (la maggiore, Curculionidae, ha 76.814 specie).
#
# Per enumerare i figli si usa /species/{key}/children e NON species/search con
# rank=ORDER/FAMILY: children restituisce i figli diretti a QUALSIASI rank, quindi
# include anche i taxa "orfani" appesi direttamente al padre senza passare per i
# ranghi standard. Sotto Plantae sono 3.081 generi + 110 famiglie appesi al regno:
# uno sharding per soli ranghi canonici li perderebbe (misurato: 4.327 specie).
_FACET_LIMIT   = 200_000   # tetto richiesto al facet speciesKey (max reale: US insecta 96.763)
_GBIF_PAGE_CAP = 100_000   # offset+limit massimo accettato da GBIF
_SHARD_TARGET  = 90_000    # soglia di split: sotto questa un ramo si pagina intero
_SHARD_MAX_DEPTH = 6       # regno→phylum→classe→ordine→famiglia→genere: mai infinito


def _fetch_single_vernacular_by_key(args):
    """Come _fetch_single_vernacular, ma parte da una chiave senza nome noto.

    Il facet occurrence restituisce solo speciesKey: il nome scientifico va
    chiesto a /species/{key}. Serve anche a scartare le chiavi che non sono
    specie ACCEPTED (occurrence può riferirsi a sinonimi o a ranghi diversi).
    Ritorna (sci_name|None, vernacular|None, lang_code).
    """
    import requests  # non è importato a livello di modulo
    usage_key, lang_code, language = args
    try:
        surl = f"https://api.gbif.org/v1/species/{usage_key}"
        resp = requests.get(surl, timeout=8, headers={"User-Agent": "BioNomen/2.0"})
        resp.raise_for_status()
        sp = resp.json()
        if sp.get("rank") != "SPECIES" or sp.get("taxonomicStatus") != "ACCEPTED":
            return (None, None, lang_code)
        sci_name = sp.get("canonicalName") or sp.get("scientificName")
        if not sci_name:
            return (None, None, lang_code)
    except Exception:
        # Mai silenzioso: in un pool di thread un errore muto sparisce e il DB
        # risulta semplicemente "povero" senza che nessuno sappia perché.
        logger.warning("BioNomen: lookup specie %s fallito", usage_key, exc_info=True)
        return (None, None, lang_code)
    _, vname, lc = _fetch_single_vernacular((usage_key, sci_name, lang_code, language))
    return (sci_name, vname, lc)


def _gbif_species_keys_by_country(
    class_key: int, countries: List[str], stop_event=None
) -> List[int]:
    """Chiavi delle specie sotto class_key effettivamente osservate nei paesi dati.

    Perché occurrence e non species/search: il backbone tassonomico non ha
    nazionalità — `species/search?country=IT` esiste ma è ignorato (verificato:
    ritorna gli stessi 1.105.104 insetti del mondo intero). L'informazione
    "questa specie sta in Italia" vive solo negli avvistamenti (occurrence).

    Il facet speciesKey restituisce l'elenco completo in una sola chiamata, e
    GBIF deduplica da sé quando i paesi sono più d'uno (IT 24.698 + FR 35.844 →
    IT+FR 41.913, non la somma). Misurato 2026-07-17: insecta IT = 24.698 specie
    contro 1.105.104 mondiali, cioè il 2,2%.
    """
    import urllib.parse
    if not countries:
        return []
    params = [
        ("taxonKey", class_key),
        ("limit", 0),
        ("facet", "speciesKey"),
        ("facetLimit", _FACET_LIMIT),
    ]
    params += [("country", c) for c in countries]
    url = "https://api.gbif.org/v1/occurrence/search?" + urllib.parse.urlencode(params)
    try:
        data = _gbif_get_json(url)
    except Exception:
        logger.warning("BioNomen: facet speciesKey fallito per key=%s paesi=%s",
                       class_key, countries, exc_info=True)
        raise
    facets = data.get("facets") or []
    if not facets:
        return []
    counts = facets[0].get("counts", [])
    # Il facet ha comunque un tetto: se lo tocchiamo l'elenco è troncato e non
    # va spacciato per completo (è lo stesso difetto del tetto di paginazione).
    if len(counts) >= _FACET_LIMIT:
        raise _GbifPageCapError(
            f"facet speciesKey troncato a {_FACET_LIMIT} per paesi={countries}"
        )
    keys = []
    for c in counts:
        try:
            keys.append(int(c["name"]))
        except (KeyError, ValueError):
            continue
    return keys


# Validità della mappa degli shard su disco. La tassonomia GBIF si muove di poco
# in un mese; oltre, meglio ricalcolare che portarsi dietro rami spariti.
_SHARD_CACHE_DAYS = 30


def _shard_cache_path(taxon: str) -> Path:
    return get_data_dir() / f"shards_{taxon}.json"


def _shard_cache_signature(taxon: str) -> str:
    """Firma delle chiavi del taxon: se cambiano in TAXA, la mappa non vale più."""
    return ",".join(str(k) for k in TAXA.get(taxon, {}).get("class_keys", []))


def _load_shard_cache(taxon: str) -> Optional[List[tuple]]:
    """Mappa degli shard salvata da un download precedente, se ancora valida.

    Serve soprattutto a rendere riprendibile il download mondiale: pianificare
    insecta costa ~40 min di chiamate di count, e senza cache un download
    interrotto (utente, riavvio, rete) li ripagherebbe tutti a barra ferma prima
    di riprendere il lavoro vero. Il ramo per paese non passa di qui: prende le
    chiavi dal facet occurrence in una chiamata sola.
    """
    path = _shard_cache_path(taxon)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        saved_at = datetime.fromisoformat(data["saved_at"])
        if (datetime.now() - saved_at).days > _SHARD_CACHE_DAYS:
            logger.info("BioNomen: mappa shard di %s scaduta, la ricalcolo", taxon)
            return None
        if data.get("signature") != _shard_cache_signature(taxon):
            logger.info("BioNomen: chiavi di %s cambiate, ricalcolo la mappa shard", taxon)
            return None
        shards = [(int(k), str(n), int(c)) for k, n, c in data["shards"]]
        if not shards:
            return None
        logger.info("BioNomen: riuso la mappa shard di %s (%s shard, del %s)",
                    taxon, len(shards), saved_at.strftime("%d/%m/%y"))
        return shards
    except Exception:
        logger.warning("BioNomen: mappa shard di %s illeggibile, la ricalcolo",
                       taxon, exc_info=True)
        return None


def _save_shard_cache(taxon: str, shards: List[tuple]) -> None:
    """Salva la mappa degli shard. Se fallisce non è grave: si ripianifica."""
    if not shards:
        return
    try:
        path = _shard_cache_path(taxon)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"saved_at": datetime.now().isoformat(),
                        "signature": _shard_cache_signature(taxon),
                        "shards": [[k, n, c] for k, n, c in shards]}),
            encoding="utf-8",
        )
    except Exception:
        logger.warning("BioNomen: salvataggio mappa shard di %s fallito",
                       taxon, exc_info=True)


def _gbif_children(key: int, stop_event=None) -> List[dict]:
    """Figli diretti di un taxon GBIF, a qualsiasi rango.

    Usa /species/{key}/children, che non ha il tetto di paginazione di
    species/search e non filtra per rango: è l'unico modo di enumerare anche i
    taxa appesi direttamente al padre fuori dai ranghi canonici.
    """
    out: List[dict] = []
    offset = 0
    while True:
        if stop_event and stop_event.is_set():
            break
        url = f"https://api.gbif.org/v1/species/{key}/children?limit=100&offset={offset}"
        try:
            data = _gbif_get_json(url)
        except Exception:
            logger.warning("BioNomen: children falliti per key=%s offset=%s",
                           key, offset, exc_info=True)
            break
        results = data.get("results", [])
        out.extend(results)
        if data.get("endOfRecords", True) or not results:
            break
        offset += len(results)
    return out


def _plan_shards(class_key: int, label: str, stop_event=None,
                 status_callback: Optional[Callable[[str], None]] = None,
                 _depth: int = 0) -> List[tuple]:
    """Spezza un taxon in sotto-alberi interamente paginabili sotto il tetto GBIF.

    Ritorna una lista di (key, nome, count). Scende ricorsivamente solo nei rami
    che superano la soglia: per aves/mammalia/reptilia/amphibia non scende affatto
    (una sola chiamata di count) e il comportamento resta identico a prima.
    """
    count = _gbif_species_count(class_key)
    if count <= 0:
        return []
    if count <= _SHARD_TARGET:
        return [(class_key, label, count)]
    if _depth >= _SHARD_MAX_DEPTH:
        # Ramo irriducibile: lo si scarica comunque, ma paginabile solo fino al
        # tetto. Va detto, non nascosto.
        logger.warning(
            "BioNomen: %s ha %s specie e non è ulteriormente divisibile: "
            "verranno scaricate le prime %s",
            label, count, _GBIF_PAGE_CAP,
        )
        return [(class_key, label, count)]

    children = _gbif_children(class_key, stop_event=stop_event)
    if not children:
        logger.warning("BioNomen: %s (%s specie) supera il tetto ma non ha figli "
                       "enumerabili — troncato a %s", label, count, _GBIF_PAGE_CAP)
        return [(class_key, label, count)]

    logger.info("BioNomen: %s (%s specie) supera %s → split in %s sotto-taxa",
                label, count, _SHARD_TARGET, len(children))
    if status_callback:
        status_callback(f"Analisi struttura {label} ({len(children)} sotto-taxa)...")

    # I count dei figli in parallelo: sono centinaia (Insecta ne ha 453 al primo
    # livello) e in serie costerebbero minuti di attesa a barra ferma.
    from concurrent.futures import ThreadPoolExecutor

    kids = []
    for child in children:
        ckey = child.get("key")
        if not ckey:
            continue
        cname = child.get("scientificName") or child.get("canonicalName") or str(ckey)
        kids.append((ckey, cname))

    with ThreadPoolExecutor(max_workers=8) as ex:
        counts = list(ex.map(lambda kv: _gbif_species_count(kv[0]), kids))

    shards: List[tuple] = []
    for (ckey, cname), ccount in zip(kids, counts):
        if stop_event and stop_event.is_set():
            break
        if ccount <= 0:
            continue
        if ccount <= _SHARD_TARGET:
            # Caso normale: già paginabile, nessuna ricorsione e nessun costo.
            shards.append((ckey, cname, ccount))
        else:
            shards.extend(_plan_shards(ckey, cname, stop_event=stop_event,
                                       status_callback=status_callback,
                                       _depth=_depth + 1))
    return shards


def _fetch_gbif_vernacular_bulk(
    class_key: int,
    language: str,
    conn: sqlite3.Connection,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    count_callback: Optional[Callable[[int], None]] = None,
    stop_event=None,
    processed_base: int = 0,
    total_override: int = 0,
) -> tuple:
    """
    Scarica in bulk i nomi vernacolari da GBIF per una classe tassonomica.

    Strategia:
    - Pagina l'elenco specie via species/search?highertaxonKey=X (1000 per pagina)
    - Parallelizza le chiamate /vernacularNames con ThreadPoolExecutor
    - Commit ogni 200 inserimenti per ridurre I/O SQLite
    - Emette progress per ogni specie processata (non per pagina)

    Args:
        processed_base: specie già elaborate da chiavi precedenti dello stesso taxon
            (per i taxa multi-chiave come Reptilia), così il progress resta continuo.
        total_override: denominatore da usare per il progress. Se >0 sostituisce il
            count della singola chiave: per i taxa multi-chiave il totale è la somma
            di tutte le chiavi, non quello della chiave corrente.

    Ritorna (record_salvati, specie_interrogate, troncato).
    `record_salvati` conta SOLO le specie che un nome comune ce l'hanno davvero:
    è normale che sia molto minore di `specie_interrogate` (per Insecta ~25%,
    la maggior parte degli insetti non ha nome volgare). I due numeri vanno
    riportati distinti, altrimenti il log sembra denunciare una perdita di dati
    che non c'è.
    `troncato` è True se il download si è interrotto per un errore o per il
    tetto GBIF invece che per fine dei dati: il chiamante deve usarlo per NON
    dichiarare completo un DB che non lo è.
    """
    import urllib.request
    import urllib.parse
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    _WORKERS    = 3     # Chiamate HTTP in parallelo verso GBIF (ridotto per evitare throttling Defender)
    _BATCH_SIZE = 200   # Commit ogni N inserimenti
    _PAGE_SIZE  = 1000  # Specie per pagina dell'elenco
    _UI_EVERY   = 50    # Aggiorna UI ogni N record (throttling segnali Qt)

    lang_code      = _LANG_MAP.get(language, language)
    saved          = 0
    processed      = 0  # Specie completamente elaborate (con o senza nome)
    # Specie realmente chieste a GBIF in questa esecuzione: esclude quelle
    # saltate perché già in cache. È questo il numero da confrontare con
    # `saved` nel log — `processed` include le saltate e farebbe sembrare una
    # perdita di dati una ripresa che invece non aveva nulla da fare.
    queried        = 0
    total_estimate = total_override  # 0 = da determinare dalla prima pagina
    offset         = 0
    _last_ui       = 0  # Ultimo valore inviato alla UI
    truncated      = False  # True se interrotto da errore/tetto, non da fine dati

    def _emit_progress(current, total):
        """Emette progress solo ogni _UI_EVERY record per non inondare Qt."""
        nonlocal _last_ui
        if current - _last_ui >= _UI_EVERY or current >= total:
            if progress_callback:
                progress_callback(min(current, total), max(total, 1))
            _last_ui = current

    # Raccolta lock per SQLite (non thread-safe su più thread)
    db_lock = threading.Lock()

    while True:
        if stop_event and stop_event.is_set():
            break

        # Guardia sul tetto: inutile emettere una richiesta che GBIF rifiuterà.
        # Con lo sharding non dovrebbe mai scattare; se scatta, è un ramo
        # irriducibile e il troncamento va dichiarato, non subito in silenzio.
        if offset + _PAGE_SIZE > _GBIF_PAGE_CAP:
            logger.warning(
                "LOG:warning:BioNomen: key=%s raggiunge il tetto GBIF di %s record — "
                "il resto del ramo non è raggiungibile via API",
                class_key, _GBIF_PAGE_CAP,
            )
            truncated = True
            break

        # --- Recupera pagina elenco specie ---
        # Usa species/search (non species) perché:
        # - supporta il campo "count" nel JSON di risposta
        # - filtra solo specie ACCEPTED del backbone (esclude sinonimi e duplicati)
        # - Aves: ~14.600 ACCEPTED vs ~90.500 totali con sinonimi
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
            data = _gbif_get_json(url)
        except _GbifPageCapError:
            # Tetto di paginazione: il ramo andava spezzato più a fondo. Non è
            # "fine dei dati" — va segnalato come troncamento, non ignorato.
            logger.warning(
                "LOG:warning:BioNomen: tetto GBIF raggiunto su key=%s a offset=%s — "
                "il ramo resta incompleto", class_key, offset,
            )
            truncated = True
            break
        except Exception as e:
            # Rete o server: dopo i retry di _gbif_get_json non è transitorio.
            # NON è fine dei dati: il taxon va marcato incompleto, mai spacciato
            # per completo (era il difetto che rendeva i troncamenti invisibili).
            logger.warning(
                "LOG:warning:BioNomen: errore fetch key=%s offset=%s: %s — "
                "download troncato", class_key, offset, e,
            )
            truncated = True
            break

        results = data.get("results", [])

        # NIENTE fallback su "classKey" quando count=0: era la causa del denominatore
        # assurdo (19.563.307 invece di ~226.000). Per Reptilia highertaxonKey=358
        # restituisce 0 perché 358 è PROPARTE_SYNONYM, e il fallback ripartiva con
        # classKey=358, che GBIF interpreta in modo lasco e fa matchare quasi tutto
        # il backbone. La soluzione corretta non è ripiegare su una query più larga,
        # ma usare le chiavi giuste: vedi class_keys in TAXA.
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
            # Già interrogata → salta la chiamata HTTP. Si guardano DUE tabelle:
            # vernacular_names ha solo le specie che un nome comune ce l'hanno,
            # e per insecta sono ~l'1%. Senza vernacular_keys, riprendere un
            # download interrotto ri-interrogherebbe il 99% del già fatto.
            with db_lock:
                already_cached = conn.execute(
                    "SELECT 1 FROM vernacular_names WHERE scientific_name=? AND language=?",
                    (sci_name, lang_code),
                ).fetchone() is not None
                if not already_cached:
                    already_cached = conn.execute(
                        "SELECT 1 FROM vernacular_keys WHERE taxon_key=? AND language=?",
                        (usage_key, lang_code),
                    ).fetchone() is not None
            if already_cached:
                processed += 1
                _emit_progress(processed_base + processed, total_estimate)
                continue
            tasks.append((usage_key, sci_name, lang_code, language))

        # --- Esegui in parallelo ---
        queried += len(tasks)
        pending_rows = []
        executor = ThreadPoolExecutor(max_workers=_WORKERS)
        futures = {executor.submit(_fetch_single_vernacular, t): t for t in tasks}
        try:
            # NIENTE timeout su as_completed: vale per l'INTERO batch (1000 specie
            # con 3 worker = minuti), non per la singola richiesta. Con timeout=20
            # ogni pagina veniva troncata dopo 20s e le specie non ancora completate
            # andavano perse — è la causa dei DB gravemente incompleti.
            # La protezione contro il blocco SSL/Defender sta già dove serve, cioè
            # nella singola richiesta: _fetch_single_vernacular usa requests.get(
            # timeout=8), che a differenza di urllib rispetta il timeout su HTTPS,
            # e assorbe l'eccezione ritornando (sci_name, None, lang_code).
            # Qui i future arrivano quindi sempre già risolti: niente timeout.
            for future in as_completed(futures):
                if stop_event and stop_event.is_set():
                    for f in futures:
                        f.cancel()
                    break
                try:
                    sci_name, vname, lc = future.result()
                except Exception:
                    # Difesa residua: il worker cattura già tutto al suo interno
                    logger.warning("BioNomen: worker fallito", exc_info=True)
                    processed += 1
                    _emit_progress(processed_base + processed, total_estimate)
                    continue
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

                _emit_progress(processed_base + processed, total_estimate)
        finally:
            executor.shutdown(wait=False)

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

        # Segna la pagina come interrogata, incluse le specie senza nome comune.
        # DOPO il commit dei nomi, mai prima: al contrario, un crash tra le due
        # scritture marcherebbe come fatte delle specie i cui nomi sono andati
        # persi, e la ripresa le salterebbe per sempre.
        # Si fa a pagina conclusa perché la pagina è già l'unità di commit: se il
        # download si interrompe a metà, si rifà quella pagina, non tutto il taxon.
        if tasks and not (stop_event and stop_event.is_set()):
            with db_lock:
                conn.executemany(
                    "INSERT OR REPLACE INTO vernacular_keys (taxon_key, language) VALUES (?, ?)",
                    [(t[0], lang_code) for t in tasks],
                )
                conn.commit()

        offset += len(results)
        if data.get("endOfRecords", True):
            break

        time.sleep(0.05)  # Pausa cortesia verso GBIF

    return saved, queried, truncated


def _fetch_vernacular_by_keys(
    keys: List[int],
    language: str,
    conn: sqlite3.Connection,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    stop_event=None,
    processed_base: int = 0,
    total_override: int = 0,
) -> tuple:
    """Scarica i nomi comuni per una lista esplicita di chiavi GBIF.

    È il ramo "solo alcuni paesi": le chiavi arrivano dal facet occurrence, non
    dalla paginazione del backbone, quindi il tetto di paginazione non si applica
    proprio (non si pagina nulla).

    Ritorna (record_salvati, specie_interrogate, interrotto), coerente con
    _fetch_gbif_vernacular_bulk: `specie_interrogate` esclude quelle già presenti
    in cache da un download precedente, quindi vale 0 quando non c'era più nulla
    da fare — che è un successo, non un fallimento.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    _WORKERS    = 3
    _BATCH_SIZE = 200
    _UI_EVERY   = 50

    lang_code = _LANG_MAP.get(language, language)
    saved = 0
    processed = 0
    _last_ui = 0
    total = total_override or len(keys)
    db_lock = threading.Lock()

    def _emit(current):
        nonlocal _last_ui
        if current - _last_ui >= _UI_EVERY or current >= total:
            if progress_callback:
                progress_callback(min(current, total), max(total, 1))
            _last_ui = current

    # Le chiavi già in cache non vanno richieste: è ciò che rende l'append di un
    # nuovo paese economico (l'overlap con i paesi già scaricati è gratis).
    todo = []
    for k in keys:
        with db_lock:
            cached = conn.execute(
                "SELECT 1 FROM vernacular_keys WHERE taxon_key=? AND language=?",
                (k, lang_code),
            ).fetchone() is not None
        if cached:
            processed += 1
            _emit(processed_base + processed)
        else:
            todo.append((k, lang_code, language))

    pending_rows = []
    executor = ThreadPoolExecutor(max_workers=_WORKERS)
    futures = [executor.submit(_fetch_single_vernacular_by_key, t) for t in todo]
    try:
        for fut in as_completed(futures):
            if stop_event and stop_event.is_set():
                for f in futures:
                    f.cancel()
                break
            try:
                sci_name, vname, lc = fut.result()
            except Exception:
                logger.warning("BioNomen: worker per-chiave fallito", exc_info=True)
                processed += 1
                _emit(processed_base + processed)
                continue
            processed += 1
            if sci_name and vname:
                pending_rows.append((sci_name, vname, lc))
                saved += 1
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
            _emit(processed_base + processed)
    finally:
        executor.shutdown(wait=False)

    if pending_rows:
        with db_lock:
            conn.executemany(
                """INSERT OR REPLACE INTO vernacular_names
                   (scientific_name, vernacular_name, language, source, confidence)
                   VALUES (?, ?, ?, 'gbif_bulk', 1)""",
                pending_rows,
            )
            conn.commit()

    # Registra le chiavi interrogate (anche quelle senza nome comune): senza
    # questo, riscaricare un paese già fatto ripeterebbe tutte le chiamate HTTP
    # per le specie che un nome comune non ce l'hanno — cioè la maggioranza.
    interrupted = bool(stop_event and stop_event.is_set())
    if not interrupted:
        with db_lock:
            conn.executemany(
                "INSERT OR REPLACE INTO vernacular_keys (taxon_key, language) VALUES (?, ?)",
                [(k, lang_code) for k, _, _ in todo],
            )
            conn.commit()
    # len(todo) e non `processed`: le chiavi già in cache non sono state chieste
    # a GBIF, contarle renderebbe il log indistinguibile da una perdita di dati.
    return saved, len(todo), interrupted


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

    class_keys  = TAXA[taxon]["class_keys"]
    taxon_label = TAXA[taxon]["label"]
    conn        = _init_taxon_db(taxon, language)

    logger.info(
        f"BioNomen: download bulk {taxon} lingua={language} class_keys={class_keys}"
    )
    if status_callback:
        status_callback(f"Download {taxon_label}...")

    # --- Ramo "solo alcuni paesi" ---------------------------------------
    # Attivo solo se la config elenca dei paesi per questo taxon. È pensato per
    # insecta e plantae, gli unici sopra il tetto: insecta ha 1.105.104 specie nel
    # mondo ma 24.698 osservate in Italia (2,2%), plantae 446.842 contro 16.020.
    # I nomi finiscono nello stesso DB del download mondiale: aggiungere un paese
    # è un append, e le specie in comune coi paesi già scaricati sono gratis
    # (vernacular_keys). Nessuna traccia di "quale paese" nei nomi: non serve.
    countries = get_taxon_countries(taxon)
    if countries:
        if status_callback:
            status_callback(f"{taxon_label}: elenco specie di {', '.join(countries)}...")
        all_keys: List[int] = []
        seen = set()
        truncated_any = False
        for ck in class_keys:
            if stop_event and stop_event.is_set():
                break
            try:
                for k in _gbif_species_keys_by_country(ck, countries, stop_event=stop_event):
                    if k not in seen:
                        seen.add(k)
                        all_keys.append(k)
            except _GbifPageCapError as e:
                logger.warning(
                    "LOG:warning:BioNomen: %s — elenco specie troncato: %s. "
                    "Selezionare meno paesi per volta.", taxon, e,
                )
                truncated_any = True
            except Exception as e:
                logger.warning(
                    "LOG:warning:BioNomen: %s — elenco specie per paese fallito: %s",
                    taxon, e,
                )
                truncated_any = True

        logger.info("BioNomen: %s in %s = %s specie (mondo: %s)",
                    taxon, countries, len(all_keys), _SPECIES_TOTAL_GBIF.get(taxon, "?"))
        if count_callback and all_keys:
            count_callback(len(all_keys))
        if status_callback:
            status_callback(f"{taxon_label}: {len(all_keys):,} specie da {', '.join(countries)}"
                            .replace(",", "."))

        saved, queried, interrupted = _fetch_vernacular_by_keys(
            keys=all_keys,
            language=language,
            conn=conn,
            progress_callback=progress_callback,
            stop_event=stop_event,
            total_override=len(all_keys),
        )
        complete = not truncated_any and not interrupted
        now = datetime.now().strftime("%d/%m/%y %H:%M")
        if complete:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)",
                (now,),
            )
            conn.execute("DELETE FROM metadata WHERE key='incomplete'")
            # Traccia i paesi già scaricati, così la UI può dirlo e l'utente sa
            # cosa ha in casa prima di aggiungerne altri.
            done = set(get_downloaded_countries(taxon, language)) | set(countries)
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('countries', ?)",
                (",".join(sorted(done)),),
            )
        else:
            reason = "interrotto dall'utente" if interrupted else "download troncato"
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('incomplete', ?)",
                (f"{reason} il {now}",),
            )
        conn.commit()
        conn.close()
        if status_callback:
            suffix = "" if complete else " (incompleto)"
            status_callback(f"{taxon_label}: {saved:,} nomi salvati{suffix}".replace(",", "."))
        # Interrogate e salvate sono due numeri diversi e vanno detti entrambi:
        # "0 record" da solo sembra un fallimento, mentre di norma significa che
        # quelle specie erano già state interrogate da un download precedente.
        logger.info(
            "BioNomen: %s/%s paesi=%s %s — %s specie interrogate, "
            "%s con nome comune%s",
            taxon, language, countries,
            "completato" if complete else "TRONCATO", queried, saved,
            " (già tutte interrogate in precedenza)" if queried == 0 else "",
        )
        return saved

    # Pianifica gli shard: ogni chiave del taxon viene spezzata ricorsivamente
    # finché ogni pezzo non sta sotto il tetto di paginazione GBIF. Per i taxa
    # piccoli (aves, mammalia, reptilia, amphibia) non si spezza nulla: la lista
    # coincide con class_keys e il costo è una sola chiamata di count per chiave.
    # La mappa degli shard di un download precedente, se c'è, evita di ripagare
    # la pianificazione (per insecta ~40 min di sole chiamate di count): è ciò
    # che rende riprendibile un download mondiale interrotto a metà.
    shards: List[tuple] = _load_shard_cache(taxon) or []
    if not shards:
        if status_callback:
            status_callback(f"Analisi struttura {taxon_label}...")
        for ck in class_keys:
            if stop_event and stop_event.is_set():
                break
            shards.extend(_plan_shards(ck, taxon_label, stop_event=stop_event,
                                       status_callback=status_callback))
        # Non salvare una mappa monca: al prossimo giro sembrerebbe completa.
        if shards and not (stop_event and stop_event.is_set()):
            _save_shard_cache(taxon, shards)

    taxon_total = sum(c for _, _, c in shards)
    if taxon_total > 0 and count_callback:
        count_callback(taxon_total)
    logger.info(
        "BioNomen: %s = %s specie in %s shard (tetto GBIF %s per query)",
        taxon, taxon_total, len(shards), _GBIF_PAGE_CAP,
    )

    saved          = 0
    queried        = 0  # Specie interrogate: il denominatore di `saved` nel log
    processed_base = 0
    truncated_any  = False
    for idx, (skey, sname, scount) in enumerate(shards, 1):
        if stop_event and stop_event.is_set():
            break
        if len(shards) > 1 and status_callback:
            status_callback(f"{taxon_label}: {sname} ({idx}/{len(shards)})")
        s_saved, s_queried, s_trunc = _fetch_gbif_vernacular_bulk(
            class_key=skey,
            language=language,
            conn=conn,
            progress_callback=progress_callback,
            # Il count globale del taxon è già stato comunicato: i singoli shard
            # non devono sovrascriverlo col proprio.
            count_callback=None,
            stop_event=stop_event,
            processed_base=processed_base,
            total_override=taxon_total,
        )
        saved += s_saved
        queried += s_queried
        truncated_any = truncated_any or s_trunc
        processed_base += scount

    interrupted = bool(stop_event and stop_event.is_set())
    complete    = not truncated_any and not interrupted

    # `last_updated` è la prova che il DB è completo: scriverlo su un download
    # troncato o interrotto è ciò che rendeva invisibili i DB monchi. Se non è
    # completo si registra lo stato, così la UI può dirlo all'utente.
    now = datetime.now().strftime("%d/%m/%y %H:%M")
    if complete:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)",
            (now,),
        )
        conn.execute("DELETE FROM metadata WHERE key='incomplete'")
    else:
        reason = "interrotto dall'utente" if interrupted else "download troncato"
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('incomplete', ?)",
            (f"{reason} il {now}",),
        )
        logger.warning(
            "LOG:warning:BioNomen: %s/%s NON completo (%s) — %s nomi salvati, "
            "rilanciare il download per completarlo",
            taxon, language, reason, saved,
        )
    conn.commit()
    conn.close()

    # Vedi il ramo per-paesi: interrogate e con-nome sono numeri diversi, e uno
    # scarto ampio è fisiologico (moltissime specie non hanno nome volgare).
    logger.info(
        "BioNomen: %s/%s %s — %s specie interrogate, %s con nome comune%s",
        taxon, language, "completato" if complete else "TRONCATO", queried, saved,
        " (già tutte interrogate in precedenza)" if queried == 0 else "",
    )
    if status_callback:
        suffix = "" if complete else " (incompleto)"
        status_callback(
            f"{taxon_label}: {saved:,} nomi salvati{suffix}".replace(",", ".")
        )
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
        # "language" è una chiave morta (la config ha "language_mode"): senza
        # resolve_language un download lanciato senza lingua esplicita finiva
        # sempre in italiano, ignorando il selettore del plugin.
        language = resolve_language(plugin_cfg=cfg)
    taxa_enabled = cfg.get("taxa_enabled", ["aves"])

    # Stime specie ACCEPTED nel backbone GBIF — usate SOLO come denominatore
    # provvisorio finché non arriva il count reale (che ora arriva subito, prima
    # della prima pagina, da _gbif_species_count).
    # Valori misurati contro l'API GBIF il 2026-07-17.
    _SPECIES_ESTIMATE = {
        "aves":       14641,
        "mammalia":   21100,
        "reptilia":   14158,   # Squamata 12.784 + Testudines 1.136 + Crocodylia 238
        "amphibia":    9815,
        "insecta":  1105104,   # quasi tutte senza nome comune, ma vanno comunque interrogate
        "plantae":   446842,
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

        taxon_label = TAXA.get(taxon, {}).get("label", taxon)
        logger.info(f"BioNomen: download [{idx+1}/{total_taxa}] {taxon}")

        # Specie già completate dai taxa precedenti. Non usare le stime come base:
        # global_done viene incrementato solo con i count reali (vedi in fondo al ciclo).
        taxon_start = global_done

        def _count_cb(real_count, _taxon=taxon):
            # Count reale del taxon: ora arriva PRIMA di iniziare a scaricare
            real_counts[_taxon] = real_count
            logger.info(f"BioNomen: {_taxon} count reale GBIF = {real_count}")

        def _cb(current, total, _taxon_start=taxon_start, _taxon=taxon):
            # `current` è già il progresso assoluto dentro il taxon (0..count_taxon)
            if total > 0:
                real_counts[_taxon] = total
            g_total = _total_global()
            # Lascia sempre 1 unità di margine: il 100% del taxon si raggiunge solo
            # quando è davvero finito, non mentre le ultime HTTP sono in volo.
            g_current = _taxon_start + min(current, max(real_counts[_taxon] - 1, 0))
            if progress_callback:
                progress_callback(min(g_current, g_total), g_total)

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
