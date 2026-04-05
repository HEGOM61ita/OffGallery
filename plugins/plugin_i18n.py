"""
Micro-sistema i18n per i plugin standalone di OffGallery.

Uso:
    from plugins.plugin_i18n import pt   # "plugin translate"
    pt("mode.unprocessed")               # → "Solo foto non ancora processate" / "Unprocessed photos only"

La lingua viene letta da config_new.yaml (ui.language).
Se non trovata, default: 'it'.
"""

from pathlib import Path
import json

_STRINGS = {
    # ── Modalità elaborazione (comuni a tutti i plugin) ──────────────────────
    "mode.title":        {"it": "Modalità elaborazione",         "en": "Processing mode"},
    "mode.unprocessed":  {"it": "Solo foto non ancora processate  (consigliato)",
                          "en": "Unprocessed photos only  (recommended)"},
    "mode.all":          {"it": "Tutto il database  (rielabora anche le foto già processate)",
                          "en": "Entire database  (reprocesses already processed photos)"},
    "mode.ids":          {"it": "Foto selezionate in Gallery",   "en": "Photos selected in Gallery"},
    "mode.ids_count":    {"it": "Foto selezionate in Gallery  ({n} foto)",
                          "en": "Photos selected in Gallery  ({n} photos)"},

    # ── Bottoni e azioni comuni ───────────────────────────────────────────────
    "btn.browse":        {"it": "Sfoglia…",   "en": "Browse…"},
    "btn.build_db":      {"it": "⚙  Costruisci database ora",
                          "en": "⚙  Build database now"},
    "btn.build_db_wdpa": {"it": "⚙  Costruisci database WDPA ora",
                          "en": "⚙  Build WDPA database now"},

    # ── Messaggi di stato ─────────────────────────────────────────────────────
    "status.building":   {"it": "Costruzione in corso...",  "en": "Building…"},
    "status.build_ok":   {"it": "✅ Database costruito con successo",
                          "en": "✅ Database built successfully"},
    "status.build_err":  {"it": "❌ Errore: {e}",           "en": "❌ Error: {e}"},

    # ── NaturArea ─────────────────────────────────────────────────────────────
    "na.title":       {"it": "NaturArea — Configurazione",
                       "en": "NaturArea — Configuration"},
    "na.info":        {
        "it": (
            "Identifica l'area protetta e il tipo di habitat per ogni foto con coordinate GPS.<br><br>"
            "I dati sulle aree protette vengono recuperati in tempo reale dall'API pubblica "
            "<b>UNEP-WCMC</b> (protectedplanet.net) — <b>non serve scaricare nulla</b>.<br>"
            "I risultati vengono salvati in cache locale: le rielaborazioni successive "
            "non richiedono connessione internet.<br><br>"
            "Il tipo di habitat (bosco, prato, acqua…) viene ricavato dalle mappe satellitari "
            "<b>ESA WorldCover</b>, scaricate automaticamente per zona geografica."
        ),
        "en": (
            "Identifies the protected area and habitat type for each photo with GPS coordinates.<br><br>"
            "Protected area data is fetched in real time from the public <b>UNEP-WCMC</b> API "
            "(protectedplanet.net) — <b>no download required</b>.<br>"
            "Results are cached locally: subsequent runs require no internet connection.<br><br>"
            "Habitat type (forest, grassland, water…) is derived from <b>ESA WorldCover</b> "
            "satellite maps, downloaded automatically per geographic zone."
        ),
    },
    "na.esa.title":   {"it": "<b>Cache tile habitat (ESA WorldCover)</b>",
                       "en": "<b>Habitat tile cache (ESA WorldCover)</b>"},
    "na.esa.note":    {
        "it": (
            "Le mappe satellitari vengono scaricate automaticamente la prima volta che elabori\n"
            "foto per una certa area geografica (~50–100 MB per zona).\n"
            "Scegli qui dove tenerle in cache."
        ),
        "en": (
            "Satellite maps are downloaded automatically the first time you process\n"
            "photos in a given area (~50–100 MB per zone).\n"
            "Choose where to cache them here."
        ),
    },
    "na.gps.title":   {"it": "<b>Tolleranza GPS</b>",    "en": "<b>GPS tolerance</b>"},
    "na.gps.unit":    {"it": "metri",                     "en": "metres"},
    "na.timeout.title": {"it": "<b>Timeout API</b>",     "en": "<b>API timeout</b>"},
    "na.timeout.unit":  {"it": "secondi",                 "en": "seconds"},

    # ── Weather Context ───────────────────────────────────────────────────────
    "wc.title":          {"it": "Meteo — Configurazione",       "en": "Weather — Configuration"},
    "wc.cache.title":    {"it": "<b>Cache meteo (SQLite)</b>",  "en": "<b>Weather cache (SQLite)</b>"},
    "wc.cache.note":     {
        "it": "La cache evita query duplicate all'API Open-Meteo per le stesse coordinate e data.",
        "en": "The cache avoids duplicate queries to the Open-Meteo API for the same coordinates and date.",
    },
    "wc.timeout.title":  {"it": "<b>Timeout richieste (secondi)</b>",
                          "en": "<b>Request timeout (seconds)</b>"},
    "wc.timeout.hint":   {"it": "(default: 10 s)",  "en": "(default: 10 s)"},
    "wc.dlg.browse":     {"it": "Percorso cache meteo",         "en": "Weather cache path"},

    # ── Bottoni comuni aggiuntivi ─────────────────────────────────────────────
    "btn.close":         {"it": "Chiudi",  "en": "Close"},

    # ── GeoSpecies ────────────────────────────────────────────────────────────
    "gs.config_title":   {"it": "GeoSpecies — Configurazione",
                          "en": "GeoSpecies — Configuration"},

    # Tab etichette
    "gs.tab_taxon":      {"it": "Taxon",      "en": "Taxa"},
    "gs.tab_sources":    {"it": "Fonti dati", "en": "Data sources"},
    "gs.tab_cache":      {"it": "Cache",      "en": "Cache"},
    "gs.tab_params":     {"it": "Parametri",  "en": "Parameters"},

    # Tab Taxon
    "gs.taxon_info": {
        "it": "Seleziona i gruppi di specie da usare per affinare BioCLIP.",
        "en": "Select the species groups to use to refine BioCLIP.",
    },
    "gs.taxon_group_a": {
        "it": "Specie mobili — lista per paese (Strategy A)",
        "en": "Mobile species — country checklist (Strategy A)",
    },
    "gs.taxon_group_b": {
        "it": "Specie sessili — lista per area geografica (Strategy B)",
        "en": "Sessile species — geographic area checklist (Strategy B)",
    },

    # Tab Fonti dati
    "gs.gbif_info": {
        "it": (
            "GBIF (Global Biodiversity Information Facility) è la fonte principale per tutte le checklist. "
            "Richiede connessione internet solo durante il download della cache; "
            "l'elaborazione delle foto avviene offline."
        ),
        "en": (
            "GBIF (Global Biodiversity Information Facility) is the main source for all checklists. "
            "Internet connection is required only during cache download; "
            "photo processing runs offline."
        ),
    },
    "gs.ebird_enable":   {"it": "Usa eBird per gli uccelli (Aves)",
                          "en": "Use eBird for birds (Aves)"},
    "gs.ebird_key":      {"it": "API Key eBird:",  "en": "eBird API Key:"},
    "gs.ebird_note": {
        "it": "API Key eBird gratuita disponibile su ebird.org/api/keygen",
        "en": "Free eBird API key available at ebird.org/api/keygen",
    },

    # Tab Cache
    "gs.cache_dir_title":         {"it": "Directory cache", "en": "Cache directory"},
    "gs.cache_dir_browse":        {"it": "Seleziona directory cache GeoSpecies",
                                   "en": "Select GeoSpecies cache directory"},
    "gs.cache_days":              {"it": "Durata cache:", "en": "Cache duration:"},
    "gs.days_unit":               {"it": "giorni",        "en": "days"},
    "gs.cache_list_title":        {"it": "Checklist in cache", "en": "Cached checklists"},
    "gs.cache_col_taxon":         {"it": "Taxon",    "en": "Taxon"},
    "gs.cache_col_area":          {"it": "Area",     "en": "Area"},
    "gs.cache_col_species":       {"it": "Specie",   "en": "Species"},
    "gs.cache_col_date":          {"it": "Data",     "en": "Date"},
    "gs.cache_refresh":           {"it": "Aggiorna", "en": "Refresh"},
    "gs.cache_delete_selected":   {"it": "Elimina selezionati", "en": "Delete selected"},
    "gs.cache_clear_all":         {"it": "Svuota tutto", "en": "Clear all"},
    "gs.cache_clear_confirm_title": {"it": "Conferma svuotamento",
                                     "en": "Confirm clear"},
    "gs.cache_clear_confirm_body":  {
        "it": "Eliminare tutte le checklist in cache? Dovranno essere riscaricate.",
        "en": "Delete all cached checklists? They will need to be re-downloaded.",
    },
    "gs.cache_cleared":           {"it": "{n} file rimossi.", "en": "{n} files removed."},

    # Tab Parametri
    "gs.radius_label": {"it": "Raggio ricerca specie sessili (Strategy B):",
                        "en": "Search radius for sessile species (Strategy B):"},
    "gs.radius_note": {
        "it": "Distanza in km dal punto GPS entro cui cercare le specie in GBIF.",
        "en": "Distance in km from the GPS point within which to search for species in GBIF.",
    },
    "gs.max_species_label": {"it": "Max specie per taxon:",
                              "en": "Max species per taxon:"},
    "gs.timeout_label":     {"it": "Timeout richieste GBIF:", "en": "GBIF request timeout:"},
    "gs.timeout_unit":      {"it": "secondi", "en": "seconds"},

    # Pulsante download
    "gs.btn_download":      {"it": "⬇  Scarica checklist...",
                             "en": "⬇  Download checklists..."},

    # DownloadDialog
    "gs.download_title":    {"it": "GeoSpecies — Scarica checklist",
                             "en": "GeoSpecies — Download checklists"},
    "gs.download_info": {
        "it": (
            "Scarica in anticipo le checklist di specie per i paesi di tuo interesse.<br>"
            "Questo consente di classificare le foto offline, senza connessione internet.<br>"
            "<b>Strategy A</b> (uccelli, mammiferi, rettili): lista per paese.<br>"
            "<b>Strategy B</b> (piante, funghi, insetti…): generata automaticamente "
            "su richiesta in base alle coordinate GPS."
        ),
        "en": (
            "Pre-download species checklists for countries of interest.<br>"
            "This allows classifying photos offline, without internet connection.<br>"
            "<b>Strategy A</b> (birds, mammals, reptiles): country checklist.<br>"
            "<b>Strategy B</b> (plants, fungi, insects…): generated automatically "
            "on demand based on GPS coordinates."
        ),
    },
    "gs.download_countries":  {"it": "Paesi",    "en": "Countries"},
    "gs.download_taxa":       {"it": "Taxon da scaricare", "en": "Taxa to download"},
    "gs.download_note_b": {
        "it": "Strategy B (piante, funghi, insetti, anfibi, aracnidi) non è scaricabile per paese — viene generata on-demand dalle coordinate GPS della foto.",
        "en": "Strategy B (plants, fungi, insects, amphibians, arachnids) cannot be downloaded by country — it is generated on demand from the photo's GPS coordinates.",
    },
    "gs.btn_load_countries":  {"it": "Carica",   "en": "Load"},
    "gs.btn_select_all":      {"it": "Tutti",     "en": "All"},
    "gs.btn_select_none":     {"it": "Nessuno",   "en": "None"},
    "gs.btn_start_download":  {"it": "Scarica",   "en": "Download"},
    "gs.loading_countries":   {"it": "Caricamento lista paesi...", "en": "Loading country list..."},
    "gs.countries_loaded":    {"it": "{n} paesi disponibili.", "en": "{n} countries available."},
    "gs.countries_load_error": {"it": "Errore: impossibile caricare i paesi (verifica la connessione).",
                                "en": "Error: could not load countries (check your connection)."},
    "gs.download_no_countries": {"it": "Seleziona almeno un paese.", "en": "Select at least one country."},
    "gs.download_no_taxa":    {"it": "Seleziona almeno un taxon.", "en": "Select at least one taxon."},
    "gs.download_complete":   {"it": "✅ Download completato.", "en": "✅ Download complete."},

    # Continenti
    "gs.continent_europe":    {"it": "Europa",          "en": "Europe"},
    "gs.continent_africa":    {"it": "Africa",           "en": "Africa"},
    "gs.continent_asia":      {"it": "Asia",             "en": "Asia"},
    "gs.continent_namerica":  {"it": "Nord America",     "en": "North America"},
    "gs.continent_samerica":  {"it": "Sud America",      "en": "South America"},
    "gs.continent_oceania":   {"it": "Oceania",          "en": "Oceania"},
    "gs.continent_antarctica": {"it": "Antartide",       "en": "Antarctica"},
}


def _read_lang() -> str:
    """Legge la lingua corrente da config_new.yaml. Fallback: 'it'."""
    for candidate in (
        Path(__file__).parent.parent / 'config_new.yaml',
        Path(__file__).parent.parent.parent / 'config_new.yaml',
    ):
        if candidate.exists():
            try:
                import yaml  # type: ignore
                cfg = yaml.safe_load(candidate.read_text(encoding='utf-8')) or {}
                lang = cfg.get('ui', {}).get('language', 'it')
                return lang if lang in ('it', 'en') else 'it'
            except Exception:
                pass
    return 'it'


def pt(key: str, **kwargs) -> str:
    """Plugin Translate: ritorna la stringa nella lingua corrente.
    kwargs vengono interpolati con str.format(**kwargs)."""
    lang = _read_lang()
    entry = _STRINGS.get(key, {})
    text = entry.get(lang) or entry.get('it') or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text
