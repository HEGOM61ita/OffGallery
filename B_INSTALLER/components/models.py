"""
Download dei modelli AI da HuggingFace HEGOM/OffGallery-models.
Supporta resume, verifica hash e progresso per modello.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Callable

from utils.download import download_file, DownloadProgress, DownloadError


# ---------------------------------------------------------------------------
# Repository HuggingFace
# ---------------------------------------------------------------------------

HF_REPO    = "HEGOM/OffGallery-models"
HF_BASE    = f"https://huggingface.co/{HF_REPO}/resolve/main"

# Cartella locale dove vengono salvati i modelli
MODELS_SUBDIR = "Models"


# ---------------------------------------------------------------------------
# Manifest dei modelli
# ---------------------------------------------------------------------------

@dataclass
class ModelFile:
    """Un singolo file da scaricare per un modello."""
    remote_path: str          # percorso relativo nel repo HF
    local_name:  str          # nome file locale (dentro la sottocartella del modello)
    size_mb:     int          # dimensione approssimativa in MB (per stima)
    sha256:      Optional[str] = None  # hash atteso (None = skip verifica)


@dataclass
class ModelSpec:
    """Specifica completa di un modello."""
    key:         str           # chiave usata in state_manager ("clip", "dinov2", ...)
    label:       str           # nome leggibile per la UI
    subdir:      str           # sottocartella dentro Models/
    files:       list[ModelFile] = field(default_factory=list)
    optional:    bool = False  # se True, l'utente può saltarlo


# Manifest principale — aggiornare qui quando cambiano i file nel repo HF
# Struttura verificata il 2026-05-05 su HEGOM/OffGallery-models
MODELS: list[ModelSpec] = [
    ModelSpec(
        key="clip",
        label="CLIP ViT-L/14",
        subdir="clip",
        files=[
            ModelFile(remote_path="clip/config.json",              local_name="config.json",              size_mb=0),
            ModelFile(remote_path="clip/merges.txt",               local_name="merges.txt",               size_mb=1),
            ModelFile(remote_path="clip/model.safetensors",        local_name="model.safetensors",        size_mb=1631),
            ModelFile(remote_path="clip/preprocessor_config.json", local_name="preprocessor_config.json", size_mb=0),
            ModelFile(remote_path="clip/special_tokens_map.json",  local_name="special_tokens_map.json",  size_mb=0),
            ModelFile(remote_path="clip/tokenizer_config.json",    local_name="tokenizer_config.json",    size_mb=0),
            ModelFile(remote_path="clip/tokenizer.json",           local_name="tokenizer.json",           size_mb=4),
            ModelFile(remote_path="clip/vocab.json",               local_name="vocab.json",               size_mb=1),
        ],
    ),
    ModelSpec(
        key="dinov2",
        label="DINOv2",
        subdir="dinov2",
        files=[
            ModelFile(remote_path="dinov2/config.json",              local_name="config.json",              size_mb=0),
            ModelFile(remote_path="dinov2/model.safetensors",        local_name="model.safetensors",        size_mb=330),
            ModelFile(remote_path="dinov2/preprocessor_config.json", local_name="preprocessor_config.json", size_mb=0),
        ],
    ),
    ModelSpec(
        key="aesthetic",
        label="Aesthetic Scorer",
        subdir="aesthetic",
        files=[
            ModelFile(remote_path="aesthetic/config.json",              local_name="config.json",              size_mb=0),
            ModelFile(remote_path="aesthetic/merges.txt",               local_name="merges.txt",               size_mb=1),
            ModelFile(remote_path="aesthetic/model.safetensors",        local_name="model.safetensors",        size_mb=1631),
            ModelFile(remote_path="aesthetic/preprocessor_config.json", local_name="preprocessor_config.json", size_mb=0),
            ModelFile(remote_path="aesthetic/special_tokens_map.json",  local_name="special_tokens_map.json",  size_mb=0),
            ModelFile(remote_path="aesthetic/tokenizer_config.json",    local_name="tokenizer_config.json",    size_mb=0),
            ModelFile(remote_path="aesthetic/tokenizer.json",           local_name="tokenizer.json",           size_mb=2),
            ModelFile(remote_path="aesthetic/vocab.json",               local_name="vocab.json",               size_mb=1),
        ],
    ),
    ModelSpec(
        key="bioclip",
        label="BioCLIP v2",
        subdir="bioclip",
        files=[
            ModelFile(remote_path="bioclip/open_clip_config.json",        local_name="open_clip_config.json",        size_mb=0),
            ModelFile(remote_path="bioclip/open_clip_model.safetensors",  local_name="open_clip_model.safetensors",  size_mb=1631),
        ],
    ),
    ModelSpec(
        key="treeoflife",
        label="TreeOfLife Embeddings",
        subdir="treeoflife",
        files=[
            # local_name è flat (senza embeddings/) perché embedding_generator
            # si aspetta i file direttamente in Models/treeoflife/
            ModelFile(remote_path="treeoflife/embeddings/txt_emb_species.json", local_name="txt_emb_species.json", size_mb=87),
            ModelFile(remote_path="treeoflife/embeddings/txt_emb_species.npy",  local_name="txt_emb_species.npy",  size_mb=2541),
        ],
    ),
    ModelSpec(
        key="musiq",
        label="MUSIQ (qualità tecnica)",
        subdir="musiq",
        files=[
            ModelFile(remote_path="musiq/musiq_koniq_ckpt-e95806b9.pth", local_name="musiq_koniq_ckpt-e95806b9.pth", size_mb=104),
        ],
    ),
]
# Nota: Argos Translate non è qui — viene installato via argostranslate.package
# in components/argos_install.py (usa ~/.local/share/argos-translate/packages/)


# ---------------------------------------------------------------------------
# Callback di progresso composto
# ---------------------------------------------------------------------------

@dataclass
class ModelProgress:
    """Stato di avanzamento passato alla UI durante il download dei modelli."""
    model_key:        str
    model_label:      str
    file_name:        str
    file_index:       int          # file corrente nel modello (0-based)
    file_count:       int          # totale file nel modello
    model_index:      int          # modello corrente (0-based)
    model_count:      int          # totale modelli da scaricare
    bytes_done:       int
    bytes_total:      int
    speed_bps:        float
    eta_sec:          float


ModelProgressCallback = Callable[[ModelProgress], None]


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------

def download_models(
    models_dir:  str,
    keys:        Optional[list[str]] = None,
    progress_cb: Optional[ModelProgressCallback] = None,
    log_cb:      Optional[Callable] = None,
    force:       bool = False,
) -> dict[str, bool]:
    """
    Scarica i modelli specificati in `keys` (default: tutti).
    Salta i modelli già presenti e completi, a meno che `force=True`.

    Restituisce un dict {key: success} per ogni modello.
    """
    specs = _filter_models(keys)
    results: dict[str, bool] = {}

    for model_idx, spec in enumerate(specs):
        model_dir = os.path.join(models_dir, MODELS_SUBDIR, spec.subdir)
        os.makedirs(model_dir, exist_ok=True)

        # Se force=True elimina i file esistenti prima di riscaricàre
        if force and _model_complete(spec, model_dir):
            _log(log_cb, f"[{spec.label}] Rimozione file esistenti per riscarica...")
            for mf in spec.files:
                dest = os.path.join(model_dir, mf.local_name)
                if os.path.isfile(dest):
                    os.remove(dest)

        # Tutti i file già presenti?
        if not force and _model_complete(spec, model_dir):
            _log(log_cb, f"[{spec.label}] già presente, skip.")
            results[spec.key] = True
            continue

        _log(log_cb, f"[{spec.label}] Download ({_total_mb(spec)} MB)...")
        success = True

        for file_idx, mf in enumerate(spec.files):
            dest = os.path.join(model_dir, mf.local_name)

            def _cb(p: DownloadProgress, fi=file_idx, mi=model_idx, mf=mf, spec=spec):
                if progress_cb:
                    progress_cb(ModelProgress(
                        model_key=spec.key,
                        model_label=spec.label,
                        file_name=mf.local_name,
                        file_index=fi,
                        file_count=len(spec.files),
                        model_index=mi,
                        model_count=len(specs),
                        bytes_done=p.bytes_done,
                        bytes_total=p.bytes_total,
                        speed_bps=p.speed_bps,
                        eta_sec=p.eta_sec,
                    ))

            url = f"{HF_BASE}/{mf.remote_path}"
            try:
                download_file(
                    url=url,
                    dest_path=dest,
                    expected_sha256=mf.sha256,
                    progress_cb=_cb,
                )
                _log(log_cb, f"  ✓ {mf.local_name}")
            except DownloadError as exc:
                _log(log_cb, f"  ✗ {mf.local_name}: {exc}")
                success = False
                break

        results[spec.key] = success
        if success:
            _log(log_cb, f"[{spec.label}] completato.")
        else:
            _log(log_cb, f"[{spec.label}] fallito — riprova più tardi.")

    return results


def model_exists(models_dir: str, key: str) -> bool:
    """True se tutti i file del modello `key` sono presenti."""
    spec = _spec_by_key(key)
    if not spec:
        return False
    model_dir = os.path.join(models_dir, MODELS_SUBDIR, spec.subdir)
    return _model_complete(spec, model_dir)


def all_models_exist(models_dir: str, keys: Optional[list[str]] = None) -> bool:
    """True se tutti i modelli richiesti sono già scaricati."""
    specs = _filter_models(keys)
    return all(
        model_exists(models_dir, spec.key)
        for spec in specs
    )


def total_download_mb(keys: Optional[list[str]] = None) -> int:
    """Stima la dimensione totale in MB dei modelli da scaricare."""
    return sum(_total_mb(s) for s in _filter_models(keys))


def model_keys() -> list[str]:
    """Restituisce le chiavi di tutti i modelli nel manifest."""
    return [m.key for m in MODELS]


# ---------------------------------------------------------------------------
# Helper privati
# ---------------------------------------------------------------------------

def _filter_models(keys: Optional[list[str]]) -> list[ModelSpec]:
    if keys is None:
        return MODELS
    key_set = set(keys)
    found = [m for m in MODELS if m.key in key_set]
    missing = key_set - {m.key for m in found}
    if missing:
        raise ValueError(f"Modelli sconosciuti: {missing}. Disponibili: {model_keys()}")
    return found


def _spec_by_key(key: str) -> Optional[ModelSpec]:
    return next((m for m in MODELS if m.key == key), None)


def _model_complete(spec: ModelSpec, model_dir: str) -> bool:
    """True se tutti i file del modello esistono localmente (non controlla l'hash)."""
    return all(
        os.path.isfile(os.path.join(model_dir, mf.local_name))
        for mf in spec.files
    )


def _total_mb(spec: ModelSpec) -> int:
    return sum(mf.size_mb for mf in spec.files)


def _log(cb: Optional[Callable], msg: str):
    if cb:
        cb(msg)
