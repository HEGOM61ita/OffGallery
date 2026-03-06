"""
Modulo i18n — internazionalizzazione OffGallery.
Carica le stringhe UI dal file JSON della lingua selezionata.

Utilizzo:
    from i18n import t, load_language
    load_language("en")
    label = t("gallery.btn.search")
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Dizionario stringhe attivo
_strings: dict = {}

# Lingua attualmente caricata
_current_language: str = "it"

# Directory dei file JSON (relativa alla root dell'app)
_I18N_DIR = Path(__file__).parent / "i18n"

# Lingue supportate: codice ISO → nome visualizzato + emoji bandiera
SUPPORTED_LANGUAGES = {
    "it": ("Italiano", "🇮🇹"),
    "en": ("English", "🇬🇧"),
}


def load_language(language: str) -> bool:
    """
    Carica il file JSON per la lingua specificata.
    Ritorna True se caricato con successo, False altrimenti.
    Se la lingua non esiste, mantiene quella precedente.
    """
    global _strings, _current_language

    lang_file = _I18N_DIR / f"{language}.json"

    if not lang_file.exists():
        logger.warning(f"File lingua non trovato: {lang_file} — mantengo '{_current_language}'")
        return False

    try:
        with open(lang_file, encoding="utf-8") as f:
            data = json.load(f)
        # Rimuove il campo commento se presente
        data.pop("_comment", None)
        _strings = data
        _current_language = language
        logger.info(f"Lingua caricata: {language} ({len(_strings)} stringhe)")
        return True
    except Exception as e:
        logger.error(f"Errore caricamento lingua '{language}': {e}")
        return False


def t(key: str, **kwargs) -> str:
    """
    Restituisce la stringa localizzata per la chiave data.
    Se la chiave non esiste, restituisce la chiave stessa (mai crash, mai stringa vuota).
    Supporta interpolazione: t("gallery.progress.similar_analysis", n=42)
    """
    value = _strings.get(key, key)
    if kwargs:
        try:
            value = value.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return value


def current_language() -> str:
    """Ritorna il codice della lingua attualmente caricata."""
    return _current_language


def available_languages() -> list[tuple[str, str, str]]:
    """
    Ritorna la lista delle lingue disponibili come (codice, nome, bandiera).
    Include solo le lingue per cui esiste il file JSON.
    """
    result = []
    for code, (name, flag) in SUPPORTED_LANGUAGES.items():
        if (_I18N_DIR / f"{code}.json").exists():
            result.append((code, name, flag))
    return result
