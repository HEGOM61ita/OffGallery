"""
Loader e auto-detection dei plugin LLM Vision.

Usato da embedding_generator all'inizializzazione per caricare
il plugin corretto in base a config['embedding']['models']['llm_vision']['backend'].
Usato da main_window all'avvio per il check di disponibilità.
"""

import logging
from typing import Optional

from .base import LLMVisionPlugin

logger = logging.getLogger(__name__)


def load_plugin(config: dict) -> Optional[LLMVisionPlugin]:
    """Carica il plugin LLM attivo in base alla configurazione.

    Legge config['embedding']['models']['llm_vision']['backend']:
        'ollama'    → carica OllamaPlugin (errore se non raggiungibile)
        'lmstudio'  → carica LMStudioPlugin (non ancora implementato)
        'auto'      → prova Ollama, poi LM Studio, avvisa se nessuno trovato
        'none'      → nessun plugin, LLM disabilitato

    Returns:
        Istanza del plugin attivo, oppure None.
    """
    llm_config = config.get('embedding', {}).get('models', {}).get('llm_vision', {})
    if not llm_config.get('enabled', False):
        return None

    backend = llm_config.get('backend', 'auto')

    if backend == 'none':
        logger.info("LLM backend disabilitato da configurazione")
        return None

    if backend == 'ollama':
        plugin = _try_load_ollama(llm_config)
        if plugin:
            logger.info("Plugin LLM attivo: Ollama")
            return plugin
        logger.warning("Ollama selezionato in config ma non raggiungibile — LLM disabilitato")
        return None

    if backend == 'lmstudio':
        plugin = _try_load_lmstudio(llm_config)
        if plugin:
            logger.info("Plugin LLM attivo: LM Studio")
            return plugin
        logger.warning("LM Studio selezionato in config ma non raggiungibile — LLM disabilitato")
        return None

    # auto: prova Ollama, poi LM Studio
    plugin = _try_load_ollama(llm_config)
    if plugin:
        logger.info("Auto-detected: Ollama attivo")
        return plugin

    plugin = _try_load_lmstudio(llm_config)
    if plugin:
        logger.info("Auto-detected: LM Studio attivo")
        return plugin

    logger.warning(
        "Nessun backend LLM trovato (Ollama/LM Studio non raggiungibili) — "
        "generazione tag/descrizione/titolo disabilitata. "
        "Il programma funziona normalmente per tutte le altre funzioni."
    )
    return None


def detect_available_backends() -> dict:
    """Controlla quali backend LLM sono attivi. Chiamato all'avvio del programma.

    Usato da main_window per aggiornare la config e mostrare lo stato in UI.

    Returns:
        {'ollama': bool, 'lmstudio': bool}
    """
    import requests

    result = {'ollama': False, 'lmstudio': False}

    try:
        r = requests.get('http://localhost:11434/api/tags', timeout=5)
        result['ollama'] = (r.status_code == 200)
    except Exception:
        pass

    try:
        r = requests.get('http://localhost:1234/v1/models', timeout=5)
        result['lmstudio'] = (r.status_code == 200)
    except Exception:
        pass

    return result


# --- helpers privati ---

def _try_load_ollama(llm_config: dict) -> Optional[LLMVisionPlugin]:
    try:
        from .llm_ollama.plugin import OllamaPlugin
        plugin = OllamaPlugin(llm_config)
        if plugin.is_available():
            return plugin
    except Exception as e:
        logger.debug(f"Ollama plugin non caricabile: {e}")
    return None


def _try_load_lmstudio(llm_config: dict) -> Optional[LLMVisionPlugin]:
    try:
        from .llm_lmstudio.plugin import LMStudioPlugin
        plugin = LMStudioPlugin(llm_config)
        if plugin.is_available():
            return plugin
    except Exception as e:
        logger.debug(f"LM Studio plugin non caricabile: {e}")
    return None
