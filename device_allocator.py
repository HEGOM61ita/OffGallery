"""
device_allocator.py — Rilevamento hardware e allocazione device per-modello.

Modulo standalone senza dipendenze PyQt. Usato da:
- gui/config_tab.py (UI auto-ottimizzazione)
- embedding_generator.py (risoluzione device per ogni modello)
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Stima VRAM per modello in inference (fp32, GB)
MODEL_VRAM_ESTIMATES: Dict[str, float] = {
    'clip':      1.7,   # CLIP ViT-L/14
    'dinov2':    0.7,   # DINOv2 base
    'aesthetic': 1.7,   # CLIP backbone + linear head
    'bioclip':   2.0,   # BioCLIP ViT-L-14 + TreeOfLife embeddings
    'technical': 0.3,   # MUSIQ (pyiqa)
}

# Modelli che beneficiano davvero della GPU (pesanti, lenti su CPU).
# Gli altri sono veloci su CPU e parallelizzano meglio lì.
MODELS_PREFER_GPU: List[str] = [
    'bioclip',    # Il più pesante (~2 GB), lentissimo su CPU
    'clip',       # Core per ricerca semantica, pesante (~1.7 GB)
]

# Modelli veloci su CPU che parallelizzano bene — meglio lasciarli su CPU
# così la GPU non serializza thread inutilmente
MODELS_PREFER_CPU: List[str] = [
    'dinov2',     # Leggero (~0.7 GB), veloce su CPU
    'technical',  # MUSIQ — già veloce su CPU (0.28s/foto)
]

# Aesthetic: via di mezzo — su GPU se c'è VRAM, altrimenti CPU va bene
MODELS_GPU_IF_ROOM: List[str] = [
    'aesthetic',  # Pesante (~1.7 GB), ma accettabile su CPU
]

# Ordine allocazione GPU: prima i must-have, poi i nice-to-have
MODEL_GPU_PRIORITY: List[str] = MODELS_PREFER_GPU + MODELS_GPU_IF_ROOM

# Tutti i modelli gestiti da questo allocatore
ALL_MODELS: List[str] = list(MODEL_VRAM_ESTIMATES.keys())


def detect_hardware() -> dict:
    """Rileva hardware GPU disponibile.

    Returns:
        dict con chiavi:
            backend: 'cuda' | 'mps' | 'directml' | 'cpu'
            gpu_name: str | None
            vram_total_gb: float | None  (None per MPS/unified memory)
            is_unified_memory: bool      (True per Apple Silicon)
            cpu_cores: int
            ram_total_gb: float
    """
    import os
    import psutil

    result = {
        'backend': 'cpu',
        'gpu_name': None,
        'vram_total_gb': None,
        'is_unified_memory': False,
        'cpu_cores': os.cpu_count() or 1,
        'ram_total_gb': round(psutil.virtual_memory().total / (1024**3), 1),
    }

    try:
        import torch
    except ImportError:
        logger.warning("PyTorch non installato — solo CPU disponibile")
        return result

    # CUDA (NVIDIA)
    if torch.cuda.is_available():
        result['backend'] = 'cuda'
        result['gpu_name'] = torch.cuda.get_device_name(0)
        vram_bytes = torch.cuda.get_device_properties(0).total_memory
        result['vram_total_gb'] = round(vram_bytes / (1024**3), 1)
        return result

    # MPS (Apple Silicon)
    if torch.backends.mps.is_available():
        result['backend'] = 'mps'
        result['gpu_name'] = _detect_apple_gpu_name()
        result['is_unified_memory'] = True
        # Su Apple Silicon la VRAM è la RAM di sistema (unified)
        result['vram_total_gb'] = None
        return result

    # DirectML (AMD/Intel su Windows)
    try:
        import torch_directml
        dml_device = torch_directml.device()
        if dml_device is not None:
            result['backend'] = 'directml'
            result['gpu_name'] = _detect_directml_gpu_name()
            result['vram_total_gb'] = _detect_directml_vram()
            return result
    except (ImportError, Exception):
        pass

    return result


def auto_allocate(
    hardware: dict,
    enabled_models: Optional[List[str]] = None,
    headroom: float = 0.80,
    llm_vram_gb: float = 0.0
) -> Dict[str, str]:
    """Calcola allocazione ottimale GPU/CPU per ogni modello.

    Strategia: i modelli pesanti e lenti vanno su GPU, quelli leggeri e veloci
    restano su CPU dove parallelizzano meglio (i thread GPU si serializzano).
    La VRAM già occupata dal LLM (Ollama/LM Studio) viene sottratta dal budget.

    Args:
        hardware: output di detect_hardware()
        enabled_models: lista modelli abilitati (None = tutti)
        headroom: percentuale VRAM utilizzabile (0.80 = 80%)
        llm_vram_gb: VRAM già occupata dal LLM

    Returns:
        dict model_key -> 'gpu' | 'cpu'
    """
    if enabled_models is None:
        enabled_models = ALL_MODELS

    allocation = {}
    backend = hardware.get('backend', 'cpu')

    # Caso 1: nessuna GPU → tutto su CPU
    if backend == 'cpu':
        for model in ALL_MODELS:
            allocation[model] = 'cpu'
        return allocation

    # Caso 2: Apple Silicon (MPS) — memoria unificata, no costo copia GPU↔CPU.
    # Modelli pesanti su GPU (accelerazione Metal), leggeri su CPU (parallelismo)
    if backend == 'mps':
        for model in ALL_MODELS:
            if model not in enabled_models:
                allocation[model] = 'cpu'
            elif model in MODELS_PREFER_CPU:
                allocation[model] = 'cpu'
            else:
                allocation[model] = 'gpu'
        return allocation

    # Caso 3: CUDA o DirectML — budget VRAM limitato
    vram_total = hardware.get('vram_total_gb')
    if vram_total is None:
        vram_total = 4.0

    budget = vram_total * headroom
    # Sottrae VRAM già occupata dal LLM (Ollama/LM Studio)
    remaining = budget - llm_vram_gb

    # Modelli che preferiscono CPU → sempre CPU (parallelismo)
    for model in MODELS_PREFER_CPU:
        allocation[model] = 'cpu'

    # Modelli che devono stare su GPU → allocali se c'è spazio
    for model in MODEL_GPU_PRIORITY:
        if model not in enabled_models:
            allocation[model] = 'cpu'
            continue
        if model in allocation:
            continue  # già assegnato
        vram_needed = MODEL_VRAM_ESTIMATES.get(model, 0)
        if remaining >= vram_needed:
            allocation[model] = 'gpu'
            remaining -= vram_needed
        else:
            allocation[model] = 'cpu'

    # Modelli non ancora assegnati (safety)
    for model in ALL_MODELS:
        if model not in allocation:
            allocation[model] = 'cpu'

    return allocation


def resolve_device(model_key: str, config: dict, hardware_backend: str) -> str:
    """Risolve il device effettivo (stringa torch) per un modello.

    Legge config['embedding']['models'][model_key]['device'] (gpu/cpu).
    Se assente, default GPU (usa backend rilevato).

    Args:
        model_key: chiave modello (clip, dinov2, aesthetic, bioclip, technical)
        config: dizionario config completo
        hardware_backend: backend rilevato ('cuda', 'mps', 'directml', 'cpu')

    Returns:
        Stringa device per torch: 'cuda', 'mps', 'cpu', o oggetto DirectML
    """
    model_cfg = config.get('embedding', {}).get('models', {}).get(model_key, {})
    model_device = model_cfg.get('device', 'gpu')

    if model_device == 'cpu':
        return 'cpu'

    # 'gpu' → converti nel backend reale
    return _backend_to_torch_device(hardware_backend)


def detect_llm_vram(config: dict) -> dict:
    """Rileva VRAM usata dal modello LLM (Ollama o LM Studio).

    Returns:
        dict con: vram_gb (float), source ('ollama_api'/'lmstudio_estimate'/'estimate'/'none'),
                  model_name (str)
    """
    llm_cfg = config.get('embedding', {}).get('models', {}).get('llm_vision', {})
    backend = llm_cfg.get('backend', 'ollama')
    endpoint = llm_cfg.get('endpoint', '')
    model_name = llm_cfg.get('model', '')
    enabled = llm_cfg.get('enabled', False)

    result = {'vram_gb': 0.0, 'source': 'none', 'model_name': model_name}

    if not enabled or not endpoint or not model_name:
        return result

    # Ollama: /api/ps restituisce size_vram reale
    if backend == 'ollama':
        try:
            import requests
            r = requests.get(f"{endpoint}/api/ps", timeout=3)
            if r.status_code == 200:
                for m in r.json().get('models', []):
                    if model_name in m.get('name', ''):
                        vram_bytes = m.get('size_vram', 0)
                        if vram_bytes > 0:
                            result['vram_gb'] = round(vram_bytes / (1024**3), 1)
                            result['source'] = 'ollama_api'
                            return result
                # Modello non caricato in VRAM ma Ollama raggiungibile → stima
        except Exception:
            pass

    # LM Studio: prova /v1/models per ottenere info sul modello caricato
    if backend == 'lmstudio':
        try:
            import requests
            r = requests.get(f"{endpoint}/v1/models", timeout=3)
            if r.status_code == 200:
                # LM Studio restituisce i modelli caricati — il nome può contenere Xb
                for m in r.json().get('data', []):
                    mid = m.get('id', '')
                    if model_name in mid or mid in model_name:
                        # Prova a stimare dal nome del modello restituito (più completo)
                        est = _estimate_llm_vram_from_name(mid)
                        if est > 0:
                            result['vram_gb'] = est
                            result['source'] = 'lmstudio_estimate'
                            return result
        except Exception:
            pass

    # Fallback: stima dal nome modello in config
    est = _estimate_llm_vram_from_name(model_name)
    if est > 0:
        result['vram_gb'] = est
        result['source'] = 'estimate'
    return result


def _estimate_llm_vram_from_name(model_name: str) -> float:
    """Stima VRAM da nome modello (es. 'qwen2.5:4b-q4_K_M' → ~3.0 GB)."""
    import re
    name_lower = model_name.lower()

    # Cerca pattern come '4b', '7b', '8b', '13b', '14b', '32b', '70b'
    match = re.search(r'(\d+)b', name_lower)
    if match:
        params_b = int(match.group(1))
    else:
        return 3.0  # default conservativo

    # Cerca quantizzazione: q4, q5, q8, fp16
    is_q4 = 'q4' in name_lower or 'q3' in name_lower
    is_q5 = 'q5' in name_lower or 'q6' in name_lower
    is_q8 = 'q8' in name_lower
    is_fp16 = 'fp16' in name_lower or 'f16' in name_lower

    # Stima: parametri * bytes_per_param + overhead (~0.5 GB)
    if is_q4:
        bytes_per_param = 0.5  # ~4 bit
    elif is_q5:
        bytes_per_param = 0.65
    elif is_q8:
        bytes_per_param = 1.0
    elif is_fp16:
        bytes_per_param = 2.0
    else:
        bytes_per_param = 0.5  # default Q4

    vram_gb = (params_b * bytes_per_param) + 0.5  # overhead KV cache base
    return round(vram_gb, 1)


def get_vram_budget_info(
    allocation: Dict[str, str],
    vram_total_gb: Optional[float],
    llm_vram_gb: float = 0.0
) -> dict:
    """Calcola info budget VRAM per la UI.

    Args:
        allocation: dict model_key -> 'gpu'/'cpu'
        vram_total_gb: VRAM totale GPU (None per MPS)
        llm_vram_gb: VRAM usata dal LLM (Ollama/LM Studio)

    Returns:
        dict con: used_gb, total_gb, percentage, status, llm_vram_gb
    """
    used_models = sum(
        MODEL_VRAM_ESTIMATES.get(m, 0)
        for m, dev in allocation.items()
        if dev == 'gpu'
    )
    used = used_models + llm_vram_gb

    if vram_total_gb is None or vram_total_gb <= 0:
        return {
            'used_gb': round(used, 1),
            'used_models_gb': round(used_models, 1),
            'llm_vram_gb': round(llm_vram_gb, 1),
            'total_gb': 0,
            'percentage': 0,
            'status': 'unknown',
        }

    pct = (used / vram_total_gb) * 100
    if pct <= 80:
        status = 'ok'
    elif pct <= 95:
        status = 'warning'
    else:
        status = 'over'

    return {
        'used_gb': round(used, 1),
        'used_models_gb': round(used_models, 1),
        'llm_vram_gb': round(llm_vram_gb, 1),
        'total_gb': round(vram_total_gb, 1),
        'percentage': round(pct),
        'status': status,
    }


# --- Utility interne ---

def _backend_to_torch_device(backend: str):
    """Converte backend in device torch, con verifica disponibilità."""
    if backend == 'cuda':
        try:
            import torch
            if torch.cuda.is_available():
                return 'cuda'
        except ImportError:
            pass
        return 'cpu'

    if backend == 'mps':
        try:
            import torch
            if torch.backends.mps.is_available():
                return 'mps'
        except ImportError:
            pass
        return 'cpu'

    if backend == 'directml':
        try:
            import torch_directml
            return torch_directml.device()
        except (ImportError, Exception):
            return 'cpu'

    return 'cpu'


def _detect_apple_gpu_name() -> str:
    """Rileva nome GPU Apple Silicon."""
    try:
        import platform
        proc = platform.processor()
        if proc:
            return f"Apple {proc}"
        # Fallback: legge chip da sysctl su macOS
        import subprocess
        result = subprocess.run(
            ['sysctl', '-n', 'machdep.cpu.brand_string'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "Apple Silicon GPU"


def _detect_directml_gpu_name() -> Optional[str]:
    """Rileva nome GPU per DirectML (AMD/Intel su Windows)."""
    try:
        # Tenta WMI su Windows
        import subprocess
        result = subprocess.run(
            ['wmic', 'path', 'win32_VideoController', 'get', 'name', '/value'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.startswith('Name='):
                    name = line.split('=', 1)[1].strip()
                    if name:
                        return name
    except Exception:
        pass
    return "DirectML GPU"


def _detect_directml_vram() -> Optional[float]:
    """Rileva VRAM per GPU DirectML (AMD/Intel su Windows)."""
    try:
        import subprocess
        result = subprocess.run(
            ['wmic', 'path', 'win32_VideoController', 'get', 'AdapterRAM', '/value'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.startswith('AdapterRAM='):
                    ram_str = line.split('=', 1)[1].strip()
                    if ram_str and ram_str.isdigit():
                        vram_bytes = int(ram_str)
                        if vram_bytes > 0:
                            return round(vram_bytes / (1024**3), 1)
    except Exception:
        pass
    # Fallback conservativo
    return 4.0
