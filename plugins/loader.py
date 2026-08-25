# Copyright (C) 2026  OffGallery / HEGOM
# Licensed under the GNU Affero General Public License v3 — see LICENSE in project root.
# Covered by the Plugin Interface Exception — see plugins/PLUGIN_LICENSE_EXCEPTION.md.

"""
Loader e auto-detection dei plugin di OffGallery.

Funzioni esportate:
  load_plugin(config)               → Optional[LLMVisionPlugin]
  load_prompt_context_plugin(config)→ Optional[PromptContextPlugin]
  detect_available_backends()       → dict

Questo file è coperto dalla Plugin Interface Exception dichiarata in base.py:
i plugin caricati tramite questo loader possono avere licenze diverse dall'AGPLv3,
a condizione che interagiscano con OffGallery esclusivamente tramite le interfacce
(LLMVisionPlugin, GeoEnricherPlugin, PromptContextPlugin) definite in base.py.
Vedere plugins/PLUGIN_LICENSE_EXCEPTION.md.
"""

import logging
import subprocess
import time
from typing import Optional

from .base import LLMVisionPlugin, PromptContextPlugin

logger = logging.getLogger(__name__)


def load_plugin(config: dict) -> Optional[LLMVisionPlugin]:
    """Carica il plugin LLM attivo in base alla configurazione.

    Legge config['embedding']['models']['llm_vision']['backend']:
        'ollama'    → carica OllamaPlugin (errore se non raggiungibile)
        'lmstudio'  → carica LMStudioPlugin
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
            llm_config['last_detected_backend'] = 'ollama'
            return plugin
        logger.warning("Ollama selezionato in config ma non raggiungibile — LLM disabilitato")
        return None

    if backend == 'lmstudio':
        plugin = _try_load_lmstudio(llm_config)
        if plugin:
            logger.info("Plugin LLM attivo: LM Studio")
            llm_config['last_detected_backend'] = 'lmstudio'
            return plugin
        logger.warning("LM Studio selezionato in config ma non raggiungibile — LLM disabilitato")
        return None

    # auto: prova prima il backend usato l'ultima volta (hint), poi l'altro
    # Riduce le chiamate inutili al backend sbagliato
    last_backend = llm_config.get('last_detected_backend', '')
    if last_backend == 'lmstudio':
        order = [('lmstudio', _try_load_lmstudio), ('ollama', _try_load_ollama)]
    else:
        order = [('ollama', _try_load_ollama), ('lmstudio', _try_load_lmstudio)]

    for name, loader_fn in order:
        plugin = loader_fn(llm_config)
        if plugin:
            logger.info(f"Auto-detected: {name} attivo")
            llm_config['last_detected_backend'] = name
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


def load_prompt_context_plugin(config: dict) -> Optional[PromptContextPlugin]:
    """Carica il plugin PromptContext se presente e abilitato.

    Cerca plugins/prompt_context/ e lo istanzia se disponibile.
    In assenza del plugin (directory mancante, dipendenze non installate,
    plugin disabilitato in config) ritorna None senza errori — il sistema
    funziona normalmente senza blocco CONTEXT nel prompt.

    Args:
        config: configurazione applicazione (stessa passata a load_plugin)

    Returns:
        Istanza PromptContextPlugin pronta all'uso, oppure None.
    """
    prompt_ctx_config = config.get('prompt_context', {})
    if not prompt_ctx_config.get('enabled', True):
        return None

    try:
        from .prompt_context.plugin import PromptContextPluginImpl
        plugin = PromptContextPluginImpl(prompt_ctx_config)
        if plugin.is_available():
            logger.info(f"Plugin PromptContext attivo: preset '{plugin.get_preset_name()}'")
        else:
            logger.debug("PromptContextPlugin caricato, preset verrà impostato dalla UI")
        return plugin
    except ImportError:
        logger.debug("plugins/prompt_context non installato — blocco CONTEXT disabilitato")
    except Exception as e:
        logger.warning(f"PromptContextPlugin non caricabile: {e}", exc_info=True)

    return None


# --- helpers privati ---

def _try_load_ollama(llm_config: dict) -> Optional[LLMVisionPlugin]:
    try:
        from .llm_ollama.plugin import OllamaPlugin
        plugin = OllamaPlugin(llm_config)
        if plugin.is_available():
            return plugin

        # Server non risponde — prova ad avviarlo automaticamente
        ollama_exe = _find_ollama_exe()
        if ollama_exe:
            logger.info(f"Avvio automatico Ollama: {ollama_exe}")
            import subprocess, time
            subprocess.Popen(
                [ollama_exe, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            for _ in range(15):
                time.sleep(1)
                if plugin.is_available():
                    logger.info("Ollama avviato correttamente.")
                    return plugin
            logger.warning("Ollama avviato ma non risponde dopo 15 secondi.")
        else:
            logger.debug("Ollama non trovato nel sistema — avvio automatico non possibile.")
    except Exception as e:
        logger.debug(f"Ollama plugin non caricabile: {e}")
    return None


def _find_ollama_exe() -> Optional[str]:
    import shutil, os, platform
    found = shutil.which("ollama")
    if found:
        return found
    candidates = [
        os.path.expanduser("~/.local/bin/ollama"),
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
    ]
    if platform.system() == "Windows":
        candidates += [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
        ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def _find_lms_exe() -> Optional[str]:
    """Cerca 'lms', lo strumento a riga di comando di LM Studio.

    Viene installato insieme al programma ma non sempre finisce nel PATH:
    di qui la ricerca nei percorsi noti. Il file .lmstudio-home-pointer, se
    presente, indica dove LM Studio tiene i propri dati.
    """
    import shutil, os, platform

    found = shutil.which("lms")
    if found:
        return found

    candidates = []

    # LM Studio annota la propria cartella dati in questo file
    try:
        pointer = os.path.expanduser("~/.lmstudio-home-pointer")
        if os.path.isfile(pointer):
            with open(pointer, encoding='utf-8') as f:
                home = f.read().strip()
            if home:
                candidates.append(os.path.join(home, "bin", "lms.exe"))
                candidates.append(os.path.join(home, "bin", "lms"))
    except Exception as e:
        logger.debug(f"Lettura .lmstudio-home-pointer fallita: {e}")

    candidates += [
        os.path.expanduser("~/.lmstudio/bin/lms"),
        os.path.expanduser("~/.cache/lm-studio/bin/lms"),
        "/usr/local/bin/lms",
    ]
    if platform.system() == "Windows":
        candidates += [
            os.path.expanduser(r"~\.lmstudio\bin\lms.exe"),
            os.path.expanduser(r"~\.cache\lm-studio\bin\lms.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "LM-Studio", "lms.exe"),
        ]

    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def _try_load_lmstudio(llm_config: dict) -> Optional[LLMVisionPlugin]:
    try:
        from .llm_lmstudio.plugin import LMStudioPlugin
        plugin = LMStudioPlugin(llm_config)
        if plugin.is_available():
            return plugin

        # Non risponde: prova ad accendere il server, come si fa con Ollama.
        # Si usa 'lms server start' e non l'avvio del programma: accendere il
        # server e' cio' che serve, e non apre finestre sullo schermo.
        lms_exe = _find_lms_exe()
        if not lms_exe:
            logger.info(
                "LM Studio non risponde e lo strumento 'lms' non e' stato trovato: "
                "avvio automatico non possibile. Se LM Studio e' installato, "
                "abilita 'lms' dal programma (Developer > Install CLI), oppure "
                "accendi il server a mano."
            )
            return None

        logger.info(f"LM Studio non risponde — avvio del server: {lms_exe} server start")
        try:
            from utils.subprocess_utils import subprocess_creation_kwargs
            _kwargs = subprocess_creation_kwargs()
        except Exception:
            _kwargs = {}
        result = subprocess.run(
            [lms_exe, "server", "start"],
            capture_output=True, text=True, timeout=30, **_kwargs
        )
        if result.returncode != 0:
            logger.warning(
                f"Avvio del server LM Studio non riuscito "
                f"(codice {result.returncode}): {(result.stderr or '').strip()[:200]}"
            )
            return None

        # Il server impiega qualche istante ad accettare richieste
        for _ in range(15):
            time.sleep(1)
            if plugin.is_available():
                logger.info("Server LM Studio avviato correttamente.")
                return plugin
        logger.warning("Server LM Studio avviato ma non risponde dopo 15 secondi.")

    except FileNotFoundError:
        logger.info("Strumento 'lms' non eseguibile — avvio automatico non possibile.")
    except subprocess.TimeoutExpired:
        logger.warning("Avvio del server LM Studio: nessuna risposta entro 30 secondi.")
    except Exception as e:
        logger.debug(f"LM Studio plugin non caricabile: {e}", exc_info=True)
    return None
