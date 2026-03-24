"""
device_allocator.py — Rilevamento hardware e allocazione device per-modello.

Modulo standalone senza dipendenze PyQt. Usato da:
- gui/config_tab.py (UI auto-ottimizzazione)
- embedding_generator.py (risoluzione device per ogni modello)
"""

import logging
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Prefetch DxDiag (Windows AMD/Intel) ─────────────────────────────────────
# Avviato in background subito dopo la splash screen; il risultato è pronto
# quando EmbeddingGenerator chiama detect_hardware() → _detect_directml_vram().
_dxdiag_result: Optional[float] = None
_dxdiag_event = threading.Event()
_dxdiag_started = False


def prefetch_dxdiag_vram() -> None:
    """Avvia il rilevamento VRAM via DxDiag in un thread background.

    Da chiamare subito dopo splash.show() — solo su Windows senza NVIDIA.
    Su altri sistemi (macOS, Linux, NVIDIA/CUDA) è un no-op immediato.
    """
    global _dxdiag_started
    import platform
    import shutil

    # Non serve su macOS/Linux
    if platform.system() != 'Windows':
        _dxdiag_event.set()
        return

    # Non serve se c'è una GPU NVIDIA (userà CUDA, non DirectML)
    if shutil.which('nvidia-smi') is not None:
        _dxdiag_event.set()
        return

    if _dxdiag_started:
        return
    _dxdiag_started = True

    def _worker():
        global _dxdiag_result
        _dxdiag_result = _run_dxdiag()
        _dxdiag_event.set()

    t = threading.Thread(target=_worker, name='dxdiag-prefetch', daemon=True)
    t.start()
    logger.debug("DxDiag VRAM prefetch avviato in background")

# Stima VRAM per modello in inference (fp32, GB)
MODEL_VRAM_ESTIMATES: Dict[str, float] = {
    'clip':      1.7,   # CLIP ViT-L/14
    'dinov2':    0.7,   # DINOv2 base
    'aesthetic': 1.7,   # CLIP backbone + linear head
    'bioclip':   2.0,   # BioCLIP ViT-L-14 + TreeOfLife embeddings
    'technical': 0.3,   # MUSIQ (pyiqa)
}

# Fattore di accelerazione GPU stimato per ogni modello (rispetto a CPU).
# Usato per calcolare il ROI dell'allocazione GPU: speedup / vram_cost.
# Nessun modello è hardcoded su CPU — il greedy decide in base allo spazio.
MODEL_GPU_SPEEDUP: Dict[str, float] = {
    'bioclip':   8.0,   # ~8x più veloce su GPU (inferenza su ~450k specie)
    'clip':      4.0,   # ~4x più veloce su GPU (embedding per ricerca semantica)
    'aesthetic': 3.0,   # ~3x più veloce su GPU (backbone CLIP)
    'technical': 3.5,   # ~3.5x più veloce su GPU (ma già rapido in assoluto)
    'dinov2':    2.5,   # ~2.5x più veloce su GPU (leggero, parallelizza bene su CPU)
}

# Ordine allocazione GPU calcolato per ROI decrescente (speedup / vram_cost):
#   technical: 3.5/0.3 = 11.7  ← miglior ROI per VRAM spesa
#   dinov2:    2.5/0.7 =  3.6
#   bioclip:   8.0/2.0 =  4.0
#   clip:      4.0/1.7 =  2.4
#   aesthetic: 3.0/1.7 =  1.8  ← peggior ROI
# (calcolato dinamicamente in auto_allocate — questa lista è solo documentazione)
MODEL_GPU_PRIORITY: List[str] = sorted(
    MODEL_GPU_SPEEDUP.keys(),
    key=lambda m: MODEL_GPU_SPEEDUP[m] / MODEL_VRAM_ESTIMATES.get(m, 1.0),
    reverse=True
)

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
    headroom: float = 0.90,
    llm_vram_gb: float = 0.0
) -> Dict[str, str]:
    """Calcola allocazione ottimale GPU/CPU per ogni modello abilitato.

    Strategia greedy per ROI: ordina i modelli per (speedup_GPU / VRAM_costo)
    decrescente, poi li alloca su GPU finché c'è spazio. Nessun modello è
    hardcoded su CPU — se c'è VRAM, anche i modelli leggeri ci vanno.

    Il LLM (Ollama/LM Studio) occupa VRAM propria già dedotta dal budget.
    L'headroom è 90% perché il LLM è già contabilizzato separatamente.

    Args:
        hardware: output di detect_hardware()
        enabled_models: modelli da considerare (None = tutti). Modelli non
                        presenti restano su CPU (non vengono caricati).
        headroom: frazione VRAM utilizzabile (default 0.90)
        llm_vram_gb: VRAM già occupata dal LLM

    Returns:
        dict model_key -> 'gpu' | 'cpu'  (solo per i modelli in ALL_MODELS)
    """
    if enabled_models is None:
        enabled_models = ALL_MODELS

    allocation: Dict[str, str] = {}
    backend = hardware.get('backend', 'cpu')

    # Caso 1: nessuna GPU → tutto su CPU
    if backend == 'cpu':
        for model in ALL_MODELS:
            allocation[model] = 'cpu'
        return allocation

    # Caso 2: Apple Silicon MPS — memoria unificata, no limite VRAM discreto.
    # Alloca su GPU tutti i modelli abilitati (Metal acceleration).
    if backend == 'mps':
        for model in ALL_MODELS:
            allocation[model] = 'gpu' if model in enabled_models else 'cpu'
        return allocation

    # Caso 3: CUDA o DirectML — budget VRAM limitato.
    vram_total = hardware.get('vram_total_gb') or 4.0
    remaining = vram_total * headroom - llm_vram_gb

    # Ordina i modelli abilitati per ROI GPU decrescente:
    # ROI = speedup_GPU / vram_cost → chi guadagna di più per GB speso va prima.
    candidates = sorted(
        [m for m in enabled_models if m in ALL_MODELS],
        key=lambda m: MODEL_GPU_SPEEDUP.get(m, 1.0) / MODEL_VRAM_ESTIMATES.get(m, 1.0),
        reverse=True
    )

    for model in candidates:
        vram_needed = MODEL_VRAM_ESTIMATES.get(model, 0)
        if remaining >= vram_needed:
            allocation[model] = 'gpu'
            remaining -= vram_needed
        else:
            allocation[model] = 'cpu'

    # Modelli non abilitati → CPU (non vengono caricati, ma il dict li include)
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


def _run_dxdiag() -> Optional[float]:
    """Esegue DxDiag e legge la VRAM dal report testuale.

    DxDiag riporta 'Dedicated Memory: X MB' tramite DirectX, bypassando il
    limite 32-bit di wmic/Get-CimInstance che cappano sempre a 4 GB su Windows.
    """
    try:
        import subprocess
        import tempfile
        import time
        import re
        import os

        tmp = os.path.join(tempfile.gettempdir(), 'offgallery_dxdiag.txt')

        # Rimuovi eventuale file residuo da run precedenti
        try:
            os.remove(tmp)
        except OSError:
            pass

        subprocess.run(
            ['dxdiag', '/t', tmp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30
        )

        # dxdiag /t è sincrono ma su alcuni sistemi scrive in modo asincrono:
        # aspetta max 20s che il file raggiunga una dimensione minima plausibile
        deadline = time.time() + 20
        while time.time() < deadline:
            if os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
                break
            time.sleep(0.2)
        else:
            logger.warning("DxDiag: timeout attesa file report")
            return None

        with open(tmp, 'r', errors='ignore') as f:
            text = f.read()

        # Pulizia file temporaneo
        try:
            os.remove(tmp)
        except OSError:
            pass

        # "Dedicated Memory: 8192 MB" — prende il valore massimo tra più GPU
        matches = re.findall(r'Dedicated Memory:\s*(\d+)\s*MB', text)
        if matches:
            vram_mb = max(int(m) for m in matches)
            if vram_mb > 0:
                return round(vram_mb / 1024, 1)

    except Exception as e:
        logger.debug(f"DxDiag VRAM: {e}")

    return None


def _detect_directml_vram() -> Optional[float]:
    """Rileva VRAM per GPU DirectML (AMD/Intel su Windows).

    Usa il risultato del prefetch DxDiag se disponibile (avviato in background
    dalla splash screen). Fallback a wmic se DxDiag non funziona — wmic cappa
    a 4 GB per overflow 32-bit, ma è meglio del default conservativo.
    """
    # Risultato prefetch già pronto → ritorna subito
    if _dxdiag_event.is_set() and _dxdiag_result is not None:
        logger.debug(f"DxDiag VRAM (cache): {_dxdiag_result} GB")
        return _dxdiag_result

    # Prefetch in corso → aspetta (max 25s — avviene solo se detect_hardware
    # viene chiamato prima che il background thread finisca)
    if _dxdiag_started:
        logger.debug("DxDiag VRAM: attendo prefetch background...")
        _dxdiag_event.wait(timeout=25)
        if _dxdiag_result is not None:
            logger.debug(f"DxDiag VRAM (wait): {_dxdiag_result} GB")
            return _dxdiag_result

    # Prefetch non avviato (es. detect_hardware() chiamato direttamente
    # senza passare per la splash): esegui dxdiag inline
    if not _dxdiag_started:
        result = _run_dxdiag()
        if result is not None:
            return result

    # Fallback wmic (cappa a 4 GB, ma almeno non restituisce un default arbitrario)
    try:
        import subprocess
        r = subprocess.run(
            ['wmic', 'path', 'win32_VideoController', 'get', 'AdapterRAM', '/value'],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            for line in r.stdout.strip().split('\n'):
                if line.startswith('AdapterRAM='):
                    ram_str = line.split('=', 1)[1].strip()
                    if ram_str and ram_str.isdigit():
                        vram_bytes = int(ram_str)
                        if vram_bytes > 0:
                            return round(vram_bytes / (1024 ** 3), 1)
    except Exception:
        pass

    return 4.0
