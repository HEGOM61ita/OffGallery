#!/usr/bin/env python3
"""
Launcher GUI - OffGallery
Download automatico modelli al primo avvio, poi modalità offline.
"""

import os
import sys
from pathlib import Path


def get_app_dir() -> Path:
    """Directory root app - funziona come script e come EXE PyInstaller"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent


# Aggiungi directory root al path
app_dir = get_app_dir()
sys.path.insert(0, str(app_dir))


def check_models_cached() -> bool:
    """
    Verifica se i modelli AI sono già in cache.
    Controlla: aesthetic locale + bioclip locale + modelli HuggingFace in cache.
    """
    # 1. Verifica aesthetic locale (obbligatorio)
    aesthetic_dir = app_dir / 'aesthetic'
    if not aesthetic_dir.exists():
        return False
    aesthetic_ok = (
        (aesthetic_dir / 'model.safetensors').exists() or
        (aesthetic_dir / 'pytorch_model.bin').exists()
    )
    if not aesthetic_ok:
        return False

    # 2. Verifica bioclip locale (obbligatorio)
    bioclip_dir = app_dir / 'bioclip'
    treeoflife_dir = app_dir / 'treeoflife'
    bioclip_ok = (
        bioclip_dir.exists() and
        (bioclip_dir / 'open_clip_model.safetensors').exists() and
        treeoflife_dir.exists() and
        (treeoflife_dir / 'txt_emb_species.npy').exists()
    )
    if not bioclip_ok:
        return False

    # 3. Verifica cache HuggingFace per CLIP/DINOv2
    hf_cache = Path.home() / '.cache' / 'huggingface' / 'hub'

    try:
        import yaml
        config_path = app_dir / 'config_new.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            repo_id = config.get('models_repository', {}).get('huggingface_repo', '')
            if repo_id:
                cache_folder = hf_cache / f"models--{repo_id.replace('/', '--')}"
                if not cache_folder.exists():
                    return False
                snapshots_dir = cache_folder / 'snapshots'
                if not snapshots_dir.exists() or not any(snapshots_dir.iterdir()):
                    return False
    except Exception:
        return False

    return True


def main():
    # Gestione argomento --download-models (download manuale forzato)
    if '--download-models' in sys.argv:
        print("Modalità download modelli...")
        from model_downloader import run_download
        success = run_download(force='--force' in sys.argv)
        sys.exit(0 if success else 1)

    # === VERIFICA PRIMO AVVIO ===
    # Se i modelli non sono in cache, permetti download automatico
    models_ready = check_models_cached()

    if not models_ready:
        print("=" * 60)
        print("  PRIMO AVVIO - Download modelli AI in corso...")
        print("  Questo richiede una connessione internet.")
        print("  I download successivi non saranno necessari.")
        print("=" * 60)
        print()

        # NON settare offline per permettere download
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"

        # I modelli verranno scaricati automaticamente da from_pretrained()
        # quando EmbeddingGenerator li inizializza
    else:
        # Modelli già in cache: modalità offline
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"

    # Avvio GUI
    from gui.splash_screen import run_with_splash
    run_with_splash()


if __name__ == '__main__':
    main()
