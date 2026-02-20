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
    Verifica se i modelli AI sono già presenti in models_dir.
    Controlla: aesthetic, bioclip, treeoflife, clip, dinov2.
    """
    try:
        import yaml
        config_path = app_dir / 'config_new.yaml'
        if not config_path.exists():
            return False
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception:
        return False

    repo_config = config.get('models_repository', {})
    models_config = repo_config.get('models', {})
    rel = repo_config.get('models_dir', 'Models')
    p = Path(rel)
    models_dir = p if p.is_absolute() else app_dir / p

    aesthetic_subfolder = models_config.get('aesthetic', 'aesthetic')
    aesthetic_dir = models_dir / aesthetic_subfolder
    if not (aesthetic_dir.exists() and (
        (aesthetic_dir / 'model.safetensors').exists() or
        (aesthetic_dir / 'pytorch_model.bin').exists()
    )):
        return False

    bioclip_subfolder = models_config.get('bioclip', 'bioclip')
    treeoflife_subfolder = models_config.get('treeoflife', 'treeoflife')
    bioclip_dir = models_dir / bioclip_subfolder
    treeoflife_dir = models_dir / treeoflife_subfolder
    if not (
        bioclip_dir.exists() and (bioclip_dir / 'open_clip_model.safetensors').exists() and
        treeoflife_dir.exists() and (treeoflife_dir / 'txt_emb_species.npy').exists()
    ):
        return False

    clip_subfolder = models_config.get('clip', 'clip')
    dinov2_subfolder = models_config.get('dinov2', 'dinov2')
    clip_dir = models_dir / clip_subfolder
    dinov2_dir = models_dir / dinov2_subfolder
    if not (clip_dir.exists() and (clip_dir / 'config.json').exists()):
        return False
    if not (dinov2_dir.exists() and (dinov2_dir / 'config.json').exists()):
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
