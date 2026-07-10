# Copyright (C) 2026  OffGallery / HEGOM — All rights reserved.
# Distributed under the OffGallery Plugins License v1.0.
# Proprietary — do NOT redistribute. See LEGAL_NOTICE.txt in this directory.

"""
Plugin PromptContext per OffGallery.

Gestisce un catalogo di preset YAML (built-in + utente) e fornisce
il blocco CONTEXT da iniettare nel prompt vision tramite l'interfaccia
PromptContextPlugin definita in plugins/base.py.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Percorso directory del plugin
_PLUGIN_DIR = Path(__file__).parent

# Directory preset: built-in (nel plugin) e utente (in APP_DIR/user_presets)
_BUILTIN_PRESETS_DIR = _PLUGIN_DIR / 'presets'


def _get_user_presets_dir() -> Path:
    """Ritorna la directory dei preset utente, creandola se necessario."""
    try:
        # Prova a usare APP_DIR da OffGallery
        _app_dir_module = None
        for _mod_name in ('utils.paths', 'paths'):
            try:
                import importlib
                _m = importlib.import_module(_mod_name)
                _app_dir_module = _m
                break
            except ImportError:
                continue
        if _app_dir_module and hasattr(_app_dir_module, 'get_app_dir'):
            user_dir = _app_dir_module.get_app_dir() / 'user_presets'
        else:
            user_dir = Path.home() / '.config' / 'offgallery' / 'prompt_presets'
    except Exception:
        user_dir = Path.home() / '.config' / 'offgallery' / 'prompt_presets'
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _load_yaml(path: Path) -> Optional[dict]:
    """Carica un file YAML ritornando il dict o None in caso di errore."""
    try:
        import yaml
        with open(path, encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Errore caricamento preset {path.name}: {e}")
        return None


def load_all_presets() -> list[dict]:
    """Carica tutti i preset disponibili (built-in + utente), ordinati per nome.

    Returns:
        Lista di dict con chiavi: id, name, description, icon, author,
        context_block, source ('builtin' o 'user'), path.
    """
    presets = []

    # Preset built-in
    if _BUILTIN_PRESETS_DIR.exists():
        for yaml_path in sorted(_BUILTIN_PRESETS_DIR.glob('*.yaml')):
            data = _load_yaml(yaml_path)
            if data and 'context_block' in data:
                data['source'] = 'builtin'
                data['path'] = str(yaml_path)
                presets.append(data)

    # Preset utente (possono sovrascrivere built-in con stesso id)
    builtin_ids = {p['id'] for p in presets}
    user_dir = _get_user_presets_dir()
    for yaml_path in sorted(user_dir.glob('*.yaml')):
        data = _load_yaml(yaml_path)
        if data and 'context_block' in data:
            data['source'] = 'user'
            data['path'] = str(yaml_path)
            # Preset utente con stesso id sostituisce il built-in
            presets = [p for p in presets if p.get('id') != data.get('id')]
            presets.append(data)

    return sorted(presets, key=lambda p: (p.get('source', 'z'), p.get('name', '')))


def save_user_preset(preset_data: dict) -> Path:
    """Salva un preset nella directory utente.

    Args:
        preset_data: dict con almeno id, name, context_block.

    Returns:
        Path del file salvato.
    """
    import yaml
    user_dir = _get_user_presets_dir()
    filename = preset_data.get('id', 'custom').replace(' ', '_') + '.yaml'
    out_path = user_dir / filename
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(preset_data, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False)
    logger.info(f"Preset utente salvato: {out_path}")
    return out_path


def delete_user_preset(preset_id: str) -> bool:
    """Elimina un preset utente per id.

    Returns:
        True se eliminato, False se non trovato o è built-in.
    """
    user_dir = _get_user_presets_dir()
    filename = preset_id.replace(' ', '_') + '.yaml'
    target = user_dir / filename
    if target.exists():
        target.unlink()
        logger.info(f"Preset utente eliminato: {target}")
        return True
    return False


def generate_preset_from_description(user_input: str, llm_endpoint: str = 'http://localhost:11434',
                                     model: str = '', timeout: int = 60) -> Optional[str]:
    """Genera un context_block da una descrizione in linguaggio libero via LLM locale.

    Chiama il modello LLM in modalità testo puro (nessuna immagine) con il meta-prompt
    ottimizzato dagli autori. Parametri di generazione calibrati per questo compito
    (più creatività rispetto al vision, output breve e strutturato).

    Args:
        user_input:    Descrizione dell'archivio fotografico scritta dall'utente.
        llm_endpoint:  URL base Ollama (default http://localhost:11434).
        model:         Nome modello da usare (default: modello configurato in OffGallery).
        timeout:       Timeout HTTP in secondi.

    Returns:
        Stringa del context_block generato (inizia con "CONTEXT:"), oppure None se errore.
    """
    meta_prompt_path = _PLUGIN_DIR / 'generator' / 'meta_prompt.txt'
    if not meta_prompt_path.exists():
        logger.error("meta_prompt.txt non trovato")
        return None

    try:
        meta_prompt_template = meta_prompt_path.read_text(encoding='utf-8')
    except Exception as e:
        logger.error(f"Errore lettura meta_prompt.txt: {e}")
        return None

    prompt = meta_prompt_template.replace('{user_input}', user_input.strip())

    # Parametri ottimizzati per generazione testo (non vision)
    # Temperatura più alta rispetto al vision (0.1): serve creatività controllata
    payload = {
        'model':  model,
        'prompt': prompt,
        'stream': False,
        'think':  False,
        'options': {
            'num_predict': 220,
            'temperature': 0.4,
            'top_p':       0.9,
            'top_k':       50,
            'num_ctx':     2048,
        }
    }

    try:
        import requests
        r = requests.post(f'{llm_endpoint}/api/generate', json=payload, timeout=timeout)
        r.raise_for_status()
        raw = r.json().get('response', '').strip()
    except Exception as e:
        logger.error(f"Errore chiamata LLM per generazione preset: {e}")
        return None

    if not raw:
        return None

    # Rimuovi eventuale blocco <think> (Qwen3)
    import re
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    if not raw:
        return None

    # Assicura che inizi con "CONTEXT:"
    if not raw.upper().startswith('CONTEXT:'):
        # Cerca la riga CONTEXT: nel testo
        for line in raw.split('\n'):
            if line.strip().upper().startswith('CONTEXT:'):
                idx = raw.find(line)
                raw = raw[idx:]
                break
        else:
            # Prefissa se il modello ha omesso l'intestazione
            raw = 'CONTEXT: ' + raw

    logger.info(f"Preset generato da LLM ({len(raw)} chars)")
    return raw


class PromptContextPluginImpl:
    """Implementazione concreta di PromptContextPlugin.

    Carica il preset attivo dalla configurazione e lo mantiene in memoria.
    Se nessun preset è attivo (active_preset vuoto o ''), get_context()
    ritorna None e il prompt viene costruito senza blocco CONTEXT.
    """

    def __init__(self, config: dict):
        """
        Args:
            config: sezione 'prompt_context' della configurazione app.
        """
        self._config = config
        self._active_preset: Optional[dict] = None
        self._active_preset_id: str = config.get('active_preset', '')
        self._load_active_preset()

    def _load_active_preset(self):
        """Carica il preset attivo dal catalogo."""
        if not self._active_preset_id:
            self._active_preset = None
            return
        all_presets = load_all_presets()
        for p in all_presets:
            if p.get('id') == self._active_preset_id:
                self._active_preset = p
                logger.debug(f"Preset attivo caricato: '{p.get('name', self._active_preset_id)}'")
                return
        logger.warning(f"Preset '{self._active_preset_id}' non trovato nel catalogo — CONTEXT disabilitato")
        self._active_preset = None

    def is_available(self) -> bool:
        """True se c'è un preset attivo con context_block valido."""
        return (
            self._active_preset is not None
            and bool(self._active_preset.get('context_block', '').strip())
        )

    def get_context(self, metadata: dict) -> Optional[str]:
        """Ritorna il context_block del preset attivo, o None se assente."""
        if not self.is_available():
            return None
        return self._active_preset['context_block'].strip()

    def get_preset_name(self) -> str:
        """Nome del preset attivo per i log."""
        if self._active_preset:
            return self._active_preset.get('name', self._active_preset_id)
        return '(nessuno)'

    def set_active_preset(self, preset_id: str):
        """Cambia il preset attivo a runtime (usato dalla UI senza riavvio)."""
        self._active_preset_id = preset_id
        self._config['active_preset'] = preset_id
        self._load_active_preset()

    def reload(self):
        """Ricarica il catalogo e il preset attivo dal disco."""
        self._load_active_preset()
