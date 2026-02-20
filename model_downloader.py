#!/usr/bin/env python3
"""
OffGallery - Model Downloader
Scarica i modelli AI dal repository HuggingFace congelato.
Tutti i modelli sono hostati su un repo controllato per garantire stabilità.
"""

import sys
import os
from pathlib import Path

# Determina directory app
def get_app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent


APP_DIR = get_app_dir()


def load_config():
    """Carica configurazione da config_new.yaml"""
    import yaml
    config_path = APP_DIR / 'config_new.yaml'

    if not config_path.exists():
        print(f"[ERRORE] Config non trovato: {config_path}")
        return None

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def print_header():
    print()
    print("=" * 60)
    print("       OFFGALLERY - DOWNLOAD MODELLI AI")
    print("=" * 60)
    print()


def print_ok(msg):
    print(f"[OK] {msg}")


def print_error(msg):
    print(f"[ERRORE] {msg}")


def print_info(msg):
    print(f"[...] {msg}")


def get_models_dir(config=None) -> Path:
    """Restituisce il percorso assoluto della directory modelli."""
    if config is None:
        config = load_config() or {}
    rel = config.get('models_repository', {}).get('models_dir', 'Models')
    p = Path(rel)
    return p if p.is_absolute() else APP_DIR / p


def check_models_exist(config=None):
    """Verifica se i modelli sono già presenti nella models_dir."""
    models_dir = get_models_dir(config)
    aesthetic_dir = models_dir / 'aesthetic'
    clip_dir = models_dir / 'clip'
    dinov2_dir = models_dir / 'dinov2'

    if not (aesthetic_dir.exists() and (
        (aesthetic_dir / 'model.safetensors').exists() or
        (aesthetic_dir / 'pytorch_model.bin').exists()
    )):
        return False
    if not (clip_dir.exists() and (clip_dir / 'config.json').exists()):
        return False
    if not (dinov2_dir.exists() and (dinov2_dir / 'config.json').exists()):
        return False
    return True


def download_from_hf_repo(repo_id: str, subfolder: str, local_dir: Path, description: str):
    """
    Scarica un modello/sottocartella dal repo HuggingFace congelato.

    Args:
        repo_id: ID del repo (es. "username/OffGallery-models")
        subfolder: Sottocartella nel repo (es. "clip", "dinov2")
        local_dir: Directory locale dove salvare
        description: Descrizione per il log
    """
    try:
        from huggingface_hub import snapshot_download

        print()
        print("-" * 60)
        print_info(f"Download {description}")
        print_info(f"Da: {repo_id}/{subfolder}")
        print_info(f"A: {local_dir}")

        # Scarica la sottocartella specifica
        snapshot_download(
            repo_id=repo_id,
            allow_patterns=f"{subfolder}/*",
            local_dir=local_dir,
            local_dir_use_symlinks=False,
        )

        print_ok(f"{description} scaricato")
        return True

    except Exception as e:
        print_error(f"{description}: {e}")
        return False


def download_all_models(repo_id: str, models_config: dict, models_dir: Path):
    """
    Scarica tutti i modelli dal repository HuggingFace congelato in models_dir.

    Il repo deve avere questa struttura:
    repo_id/
    ├── clip/           (modello CLIP completo)
    ├── dinov2/         (modello DINOv2 completo)
    ├── aesthetic/      (modello CLIP per aesthetic)
    ├── bioclip/        (modello BioCLIP v2)
    ├── treeoflife/     (dataset TreeOfLife per BioCLIP)
    └── argos-it-en/    (pacchetto traduzione Argos)
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print_error("huggingface_hub non installato")
        return False

    models_dir.mkdir(parents=True, exist_ok=True)
    success = True

    print(f"Repository congelato: {repo_id}")
    print(f"Destinazione modelli: {models_dir}")
    print()

    # --- CLIP ---
    print()
    print("-" * 60)
    print_info("Download CLIP (ricerca semantica) - ~580 MB")
    try:
        clip_subfolder = models_config.get('clip', 'clip')
        clip_dir = models_dir / clip_subfolder
        if clip_dir.exists() and (clip_dir / 'config.json').exists():
            print_ok("CLIP già presente")
        else:
            snapshot_download(
                repo_id=repo_id,
                allow_patterns=f"{clip_subfolder}/**",
                local_dir=str(models_dir),
                local_dir_use_symlinks=False,
            )
            print_ok("CLIP scaricato")
    except Exception as e:
        print_error(f"CLIP: {e}")
        success = False

    # --- DINOv2 ---
    print()
    print("-" * 60)
    print_info("Download DINOv2 (similarità visiva) - ~330 MB")
    try:
        dinov2_subfolder = models_config.get('dinov2', 'dinov2')
        dinov2_dir = models_dir / dinov2_subfolder
        if dinov2_dir.exists() and (dinov2_dir / 'config.json').exists():
            print_ok("DINOv2 già presente")
        else:
            snapshot_download(
                repo_id=repo_id,
                allow_patterns=f"{dinov2_subfolder}/**",
                local_dir=str(models_dir),
                local_dir_use_symlinks=False,
            )
            print_ok("DINOv2 scaricato")
    except Exception as e:
        print_error(f"DINOv2: {e}")
        success = False

    # --- Aesthetic ---
    print()
    print("-" * 60)
    print_info("Download Aesthetic (score estetico) - ~1.6 GB")
    try:
        aesthetic_subfolder = models_config.get('aesthetic', 'aesthetic')
        aesthetic_dir = models_dir / aesthetic_subfolder
        if aesthetic_dir.exists() and (
            (aesthetic_dir / 'model.safetensors').exists() or
            (aesthetic_dir / 'pytorch_model.bin').exists()
        ):
            print_ok("Aesthetic già presente")
        else:
            aesthetic_dir.mkdir(exist_ok=True)
            snapshot_download(
                repo_id=repo_id,
                allow_patterns=f"{aesthetic_subfolder}/**",
                local_dir=str(models_dir),
                local_dir_use_symlinks=False,
            )
            print_ok("Aesthetic scaricato")
    except Exception as e:
        print_error(f"Aesthetic: {e}")
        success = False

    # --- BioCLIP v2 + TreeOfLife ---
    print()
    print("-" * 60)
    print_info("Download BioCLIP v2 + TreeOfLife (classificazione natura) - ~4.2 GB")
    try:
        bioclip_subfolder = models_config.get('bioclip', 'bioclip')
        treeoflife_subfolder = models_config.get('treeoflife', 'treeoflife')
        bioclip_dir = models_dir / bioclip_subfolder
        treeoflife_dir = models_dir / treeoflife_subfolder

        if bioclip_dir.exists() and (bioclip_dir / 'open_clip_model.safetensors').exists():
            print_ok("BioCLIP v2 già presente")
        else:
            snapshot_download(
                repo_id=repo_id,
                allow_patterns=f"{bioclip_subfolder}/**",
                local_dir=str(models_dir),
                local_dir_use_symlinks=False,
            )
            print_ok("BioCLIP v2 scaricato")

        if treeoflife_dir.exists() and (treeoflife_dir / 'txt_emb_species.npy').exists():
            print_ok("TreeOfLife già presente")
        else:
            snapshot_download(
                repo_id=repo_id,
                allow_patterns=f"{treeoflife_subfolder}/**",
                local_dir=str(models_dir),
                local_dir_use_symlinks=False,
            )
            print_ok("TreeOfLife scaricato")

    except Exception as e:
        print_error(f"BioCLIP: {e}")
        success = False

    return success


def download_argos_from_hf(repo_id: str, models_config: dict):
    """
    Scarica il pacchetto Argos Translate IT->EN dal repo HuggingFace.
    Il pacchetto è un file .argosmodel che viene installato localmente.
    """
    print()
    print("-" * 60)
    print_info("Download Argos Translate IT->EN - ~92 MB")

    try:
        import argostranslate.package

        # Verifica se già installato
        installed = argostranslate.package.get_installed_packages()
        for pkg in installed:
            if pkg.from_code == 'it' and pkg.to_code == 'en':
                print_ok("Argos IT->EN già installato")
                return True

        # Scarica da HuggingFace
        from huggingface_hub import hf_hub_download

        argos_subfolder = models_config.get('argos_it_en', 'argos-it-en')

        # Cerca il file .argosmodel nel repo
        print_info("Download pacchetto da HuggingFace...")

        # Il file dovrebbe essere qualcosa come argos-it-en/translate-it_en.argosmodel
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=f"{argos_subfolder}/translate-it_en.argosmodel",
            local_dir=str(APP_DIR / 'temp_argos'),
        )

        # Installa il pacchetto
        print_info("Installazione pacchetto...")
        argostranslate.package.install_from_path(local_path)

        # Pulizia
        import shutil
        temp_dir = APP_DIR / 'temp_argos'
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        print_ok("Argos IT->EN installato da HuggingFace")
        return True

    except Exception as e:
        print_error(f"Argos da HF: {e}")

        # Fallback: prova dal server Argos originale
        print_info("Tentativo fallback da server Argos...")
        return download_argos_fallback()


def download_argos_fallback():
    """Fallback: scarica Argos dal server originale"""
    try:
        import argostranslate.package
        import argostranslate.translate

        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()

        pkg_to_install = None
        for pkg in available:
            if pkg.from_code == 'it' and pkg.to_code == 'en':
                pkg_to_install = pkg
                break

        if pkg_to_install is None:
            print_error("Pacchetto IT->EN non trovato")
            return False

        download_path = pkg_to_install.download()
        argostranslate.package.install_from_path(download_path)
        print_ok("Argos IT->EN installato (fallback)")
        return True

    except Exception as e:
        print_error(f"Argos fallback: {e}")
        return False


def run_download(force=False):
    """Esegue il download dei modelli"""
    print_header()

    # Carica config
    config = load_config()
    if config is None:
        return False

    repo_config = config.get('models_repository', {})
    repo_id = repo_config.get('huggingface_repo', '')
    auto_download = repo_config.get('auto_download', True)
    models_config = repo_config.get('models', {})
    models_dir = get_models_dir(config)

    if not repo_id:
        print_error("huggingface_repo non configurato in config_new.yaml")
        print_info("Imposta models_repository.huggingface_repo nel config")
        return False

    if not auto_download and not force:
        print_info("Auto-download disabilitato in config")
        return True

    # Verifica se già scaricati
    if not force and check_models_exist(config):
        print_ok("Modelli già presenti, skip download")
        print_info("Usa --force per forzare il re-download")
        return True

    print(f"Repository congelato: {repo_id}")
    print(f"Destinazione modelli: {models_dir}")
    print()
    print("NOTA: I modelli sono congelati sul tuo repository HuggingFace")
    print("      per garantire compatibilità futura.")
    print()

    # Download
    hf_ok = download_all_models(repo_id, models_config, models_dir)
    argos_ok = download_argos_from_hf(repo_id, models_config)

    # Riepilogo
    print()
    print("=" * 60)
    if hf_ok and argos_ok:
        print_ok("Tutti i modelli scaricati con successo!")
        print()
        print("Ora puoi avviare OffGallery.exe")
    else:
        print("[!!] Alcuni modelli non sono stati scaricati")
        print("     Riprova eseguendo: python model_downloader.py --force")
    print("=" * 60)

    return hf_ok and argos_ok


def main():
    """Entry point per esecuzione standalone"""
    import argparse
    parser = argparse.ArgumentParser(description='OffGallery Model Downloader')
    parser.add_argument('--force', action='store_true', help='Forza re-download')
    args = parser.parse_args()

    success = run_download(force=args.force)

    if not getattr(sys, 'frozen', False):
        input("\nPremi INVIO per chiudere...")

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
