"""
BioNomen — Logica core per lookup nomi comuni biologici.

Strategie di lookup (priorità decrescente):
  1. Cache locale SQLite (bionomen.db)
  2. GBIF vernacular names API
  3. iNaturalist API (con filtro anti-geografico)
  4. Wikidata SPARQL

Questo modulo e' completamente standalone: non importa nulla da OffGallery.
Comunicazione con OffGallery tramite stdout: righe PROGRESS:n:total
"""

import sqlite3
import json
import time
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Directory del plugin (stessa cartella di questo file)
_PLUGIN_DIR = Path(__file__).parent

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

# Etichette lingua per Wikidata SPARQL
_WIKIDATA_LANG = {
    "it": "it",
    "en": "en",
    "de": "de",
    "fr": "fr",
    "es": "es",
    "pt": "pt",
}


def get_db_path() -> Path:
    """Ritorna il path del database locale bionomen.db."""
    return _PLUGIN_DIR / "bionomen.db"


def is_database_present() -> bool:
    """Verifica se il database locale esiste e contiene la tabella principale."""
    db = get_db_path()
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


def get_database_date() -> Optional[str]:
    """Ritorna la data dell'ultimo aggiornamento del DB, o None se assente."""
    db = get_db_path()
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.execute(
            "SELECT value FROM metadata WHERE key='last_updated' LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _init_local_db() -> sqlite3.Connection:
    """Inizializza il database locale con lo schema completo."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vernacular_names (
            scientific_name  TEXT NOT NULL,
            vernacular_name  TEXT NOT NULL,
            language         TEXT NOT NULL,
            source           TEXT,
            confidence       INTEGER,
            PRIMARY KEY (scientific_name, source)
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
    """Cerca il nome vernacolare su GBIF via API REST."""
    try:
        import urllib.request
        import urllib.parse

        # Passo 1: match del nome scientifico per ottenere l'usageKey GBIF
        match_url = (
            "https://api.gbif.org/v1/species/match?"
            + urllib.parse.urlencode({"name": scientific_name, "verbose": "false"})
        )
        req = urllib.request.Request(match_url, headers={"User-Agent": "BioNomen/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        usage_key = data.get("usageKey") or data.get("speciesKey")
        if not usage_key:
            return None

        # Passo 2: recupera i nomi vernacolari per l'usageKey
        vern_url = f"https://api.gbif.org/v1/species/{usage_key}/vernacularNames?limit=100"
        req2 = urllib.request.Request(vern_url, headers={"User-Agent": "BioNomen/1.0"})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            vdata = json.loads(resp2.read().decode())

        results = vdata.get("results", [])
        lang_code = _LANG_MAP.get(language, language)

        # Cerca prima corrispondenza esatta di lingua
        for entry in results:
            entry_lang = entry.get("language", "")
            if entry_lang == lang_code and entry.get("vernacularName"):
                return entry["vernacularName"]

        # Fallback: cerca anche per codice breve (es. "it")
        for entry in results:
            entry_lang = entry.get("language", "")
            if entry_lang == language and entry.get("vernacularName"):
                return entry["vernacularName"]

        return None

    except Exception as e:
        logger.debug(f"GBIF lookup fallito per '{scientific_name}': {e}")
        return None


def _contains_geo_term(name: str) -> bool:
    """Verifica se il nome contiene termini geografici da filtrare."""
    name_lower = name.lower()
    for term in _GEO_FILTER_TERMS:
        if term in name_lower:
            return True
    return False


def _lookup_inaturalist(scientific_name: str, language: str) -> Optional[str]:
    """Cerca il nome vernacolare su iNaturalist con filtro anti-geografico."""
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("results", [])
        if not results:
            return None

        taxon = results[0]
        # preferred_common_name e' gia' nella lingua richiesta tramite locale
        common = taxon.get("preferred_common_name", "")
        if common and not _contains_geo_term(common):
            return common

        # Fallback: cerca in taxon_names
        for entry in taxon.get("taxon_names", []):
            if entry.get("lexicon", "").lower() == language and entry.get("name"):
                candidate = entry["name"]
                if not _contains_geo_term(candidate):
                    return candidate

        return None

    except Exception as e:
        logger.debug(f"iNaturalist lookup fallito per '{scientific_name}': {e}")
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
        with urllib.request.urlopen(req, timeout=15) as resp:
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
        return None


def lookup_vernacular_name(scientific_name: str, language: str = "it") -> Optional[str]:
    """
    Cerca il nome vernacolare per un nome scientifico.

    Strategia (priorita' decrescente):
      1. Cache locale (bionomen.db)
      2. GBIF API
      3. iNaturalist API (con filtro anti-geografico)
      4. Wikidata SPARQL (scarta se == nome scientifico)

    Args:
        scientific_name: Nome scientifico (es. "Columba palumbus")
        language: Codice lingua ISO 639-1 (default "it")

    Returns:
        Nome vernacolare trovato, o None se non trovato.
    """
    if not scientific_name or not scientific_name.strip():
        return None

    scientific_name = scientific_name.strip()

    # Inizializza (o apre) il DB locale
    conn = _init_local_db()

    try:
        # 1. Cache locale
        cached = _lookup_in_cache(conn, scientific_name, language)
        if cached is not None:
            return cached if cached != "" else None

        # 2. GBIF
        result = _lookup_gbif(scientific_name, language)
        if result:
            _save_to_cache(conn, scientific_name, result, language, "gbif", 1)
            return result

        # 3. iNaturalist
        result = _lookup_inaturalist(scientific_name, language)
        if result:
            _save_to_cache(conn, scientific_name, result, language, "inaturalist", 2)
            return result

        # 4. Wikidata
        result = _lookup_wikidata(scientific_name, language)
        if result:
            _save_to_cache(conn, scientific_name, result, language, "wikidata", 3)
            return result

        # Nessun risultato: salva stringa vuota in cache per evitare lookup ripetuti
        _save_to_cache(conn, scientific_name, "", language, "none", 9)
        return None

    finally:
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
    Il nome scientifico e' di solito all'ultimo livello non vuoto.
    """
    if not bioclip_taxonomy_json:
        return None
    try:
        taxonomy = json.loads(bioclip_taxonomy_json)
        if not isinstance(taxonomy, list):
            return None
        # Cerca dall'ultimo livello verso il primo: il nome scientifico e'
        # tipicamente "Genus species" (due parole) negli ultimi livelli
        for level in reversed(taxonomy):
            if isinstance(level, str) and level.strip():
                parts = level.strip().split()
                if len(parts) >= 2:
                    return level.strip()
        # Fallback: ultimo livello non vuoto
        for level in reversed(taxonomy):
            if isinstance(level, str) and level.strip():
                return level.strip()
        return None
    except Exception:
        return None


def _update_tags_with_vernacular(
    existing_tags_json: Optional[str],
    scientific_name: Optional[str],
    vernacular_name: str,
) -> str:
    """
    Inserisce il nome vernacolare in seconda posizione nei tags.

    - Il nome scientifico (da BioCLIP) deve essere il primo tag.
    - Il nome vernacolare va in seconda posizione.
    - Deduplicazione case-insensitive.
    - Se il nome vernacolare e' gia' presente, non viene aggiunto di nuovo.
    - Se in posizione 2 c'e' un nome diverso, emette warning nel log e aggiunge comunque.

    Returns:
        JSON string dell'array tags aggiornato.
    """
    try:
        tags = json.loads(existing_tags_json) if existing_tags_json else []
        if not isinstance(tags, list):
            tags = []
    except Exception:
        tags = []

    # Normalizzazione: deduplicazione case-insensitive mantenendo ordine
    seen_lower = set()
    deduped = []
    for tag in tags:
        if isinstance(tag, str) and tag.lower() not in seen_lower:
            seen_lower.add(tag.lower())
            deduped.append(tag)
    tags = deduped

    # Controlla se il nome vernacolare e' gia' presente (case-insensitive)
    vern_lower = vernacular_name.lower()
    if vern_lower in seen_lower:
        # Gia' presente: non aggiungere
        return json.dumps(tags, ensure_ascii=False)

    # Determina la posizione di inserimento: seconda (dopo nome scientifico)
    insert_pos = 1  # default: seconda posizione

    # Verifica che il primo tag sia il nome scientifico
    if tags and scientific_name:
        if tags[0].lower() != scientific_name.lower():
            # Il primo tag non e' il nome scientifico: inserisci all'inizio
            insert_pos = 0

    # Controlla se gia' c'e' qualcosa in posizione insert_pos
    if len(tags) > insert_pos:
        existing_at_pos = tags[insert_pos]
        if existing_at_pos.lower() != vern_lower:
            logger.warning(
                f"Tag in posizione {insert_pos+1} ('{existing_at_pos}') "
                f"diverso dal nome vernacolare ('{vernacular_name}'). "
                f"Aggiunta comunque."
            )

    # Inserisci il nome vernacolare nella posizione corretta
    tags.insert(insert_pos, vernacular_name)

    return json.dumps(tags, ensure_ascii=False)


def process_images(
    offgallery_db_path: str,
    mode: str = "unprocessed",
    language: str = "it",
    progress_callback: Optional[Callable[[int, int], None]] = None,
):
    """
    Itera sulle foto nel DB OffGallery e aggiorna tags e vernacular_name.

    Args:
        offgallery_db_path: Path assoluto al database OffGallery
        mode: "unprocessed" (solo foto con vernacular_name IS NULL)
              "all"          (tutto il database)
        language: Codice lingua ISO 639-1 (default "it")
        progress_callback: Funzione chiamata con (current, total) ad ogni immagine
    """
    conn = sqlite3.connect(offgallery_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Aggiunge colonna vernacular_name se non esiste
    _ensure_vernacular_column(conn)

    # Seleziona le foto da elaborare
    if mode == "all":
        cur = conn.execute(
            "SELECT id, tags, bioclip_taxonomy FROM images WHERE bioclip_taxonomy IS NOT NULL"
        )
    else:
        # Solo non processate: vernacular_name IS NULL e bioclip_taxonomy presente
        cur = conn.execute(
            """SELECT id, tags, bioclip_taxonomy FROM images
               WHERE bioclip_taxonomy IS NOT NULL AND vernacular_name IS NULL"""
        )

    rows = cur.fetchall()
    total = len(rows)

    logger.info(f"BioNomen: {total} immagini da elaborare (mode={mode}, lang={language})")

    for idx, row in enumerate(rows, start=1):
        image_id = row["id"]
        tags_json = row["tags"]
        bioclip_json = row["bioclip_taxonomy"]

        # Progresso
        if progress_callback:
            progress_callback(idx, total)
        # Stampa su stdout per comunicazione con OffGallery
        print(f"PROGRESS:{idx}:{total}", flush=True)

        # Estrai nome scientifico dalla tassonomia BioCLIP
        scientific_name = _extract_scientific_name(bioclip_json)
        if not scientific_name:
            # Segna come processata (senza nome trovato) per non riprocessare
            conn.execute(
                "UPDATE images SET vernacular_name=? WHERE id=?",
                ("", image_id),
            )
            conn.commit()
            continue

        # Lookup nome vernacolare
        vernacular = lookup_vernacular_name(scientific_name, language)

        # Aggiorna il record
        if vernacular:
            new_tags_json = _update_tags_with_vernacular(tags_json, scientific_name, vernacular)
            conn.execute(
                "UPDATE images SET tags=?, vernacular_name=? WHERE id=?",
                (new_tags_json, vernacular, image_id),
            )
        else:
            # Nome non trovato: segna stringa vuota per non riprocessare
            conn.execute(
                "UPDATE images SET vernacular_name=? WHERE id=?",
                ("", image_id),
            )

        conn.commit()

        # Pausa minima per non sovraccaricare le API esterne
        time.sleep(0.1)

    conn.close()
    logger.info("BioNomen: elaborazione completata")


def download_and_build_database(
    progress_callback: Optional[Callable[[int, int], None]] = None,
):
    """
    Inizializza il database locale bionomen.db.
    In questa versione, il DB viene popolato on-demand durante process_images.
    Questo metodo crea solo la struttura vuota e aggiorna la data.

    Args:
        progress_callback: Funzione chiamata con (current, total)
    """
    conn = _init_local_db()

    # Salva la data di creazione/aggiornamento
    now = datetime.now().strftime("%d/%m/%y")
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)",
        (now,),
    )
    conn.commit()
    conn.close()

    if progress_callback:
        progress_callback(1, 1)
    print("PROGRESS:1:1", flush=True)

    logger.info(f"BioNomen: database inizializzato ({now})")
