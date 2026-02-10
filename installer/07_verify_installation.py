#!/usr/bin/env python3
"""
OffGallery Installer - Step 7: Verifica Installazione
Controlla che tutti i componenti siano installati correttamente.
"""

import sys
import os

# Disabilita warning
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
import warnings
warnings.filterwarnings('ignore')

def print_header():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     OFFGALLERY INSTALLER - STEP 7: VERIFICA FINALE          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

def check_python():
    """Verifica versione Python"""
    version = sys.version_info
    ok = version.major == 3 and version.minor >= 11
    return ok, f"Python {version.major}.{version.minor}.{version.micro}"

def check_torch():
    """Verifica PyTorch e CUDA"""
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            return True, f"PyTorch {torch.__version__} + GPU ({gpu_name})"
        else:
            return True, f"PyTorch {torch.__version__} (solo CPU)"
    except ImportError:
        return False, "PyTorch NON installato"

def check_transformers():
    """Verifica Transformers"""
    try:
        import transformers
        return True, f"Transformers {transformers.__version__}"
    except ImportError:
        return False, "Transformers NON installato"

def check_pyqt6():
    """Verifica PyQt6"""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QT_VERSION_STR
        return True, f"PyQt6 {QT_VERSION_STR}"
    except ImportError:
        return False, "PyQt6 NON installato"

def check_clip_model():
    """Verifica modello CLIP in cache"""
    try:
        from transformers import CLIPModel
        # Prova a caricare in modalità offline
        os.environ["HF_HUB_OFFLINE"] = "1"
        model = CLIPModel.from_pretrained("laion/CLIP-ViT-B-32-laion2B-s34B-b79K")
        del model
        return True, "CLIP (laion) in cache"
    except:
        return False, "CLIP NON in cache (esegui 04_download_models.py)"
    finally:
        os.environ.pop("HF_HUB_OFFLINE", None)

def check_dinov2_model():
    """Verifica modello DINOv2 in cache"""
    try:
        from transformers import AutoModel
        os.environ["HF_HUB_OFFLINE"] = "1"
        model = AutoModel.from_pretrained("facebook/dinov2-base")
        del model
        return True, "DINOv2 in cache"
    except:
        return False, "DINOv2 NON in cache (esegui 04_download_models.py)"
    finally:
        os.environ.pop("HF_HUB_OFFLINE", None)

def check_aesthetic_model():
    """Verifica modello Aesthetic in cache"""
    try:
        from transformers import CLIPModel
        os.environ["HF_HUB_OFFLINE"] = "1"
        model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14")
        del model
        return True, "CLIP Aesthetic in cache"
    except:
        return False, "CLIP Aesthetic NON in cache (esegui 04_download_models.py)"
    finally:
        os.environ.pop("HF_HUB_OFFLINE", None)

def check_bioclip():
    """Verifica BioCLIP"""
    try:
        from bioclip import TreeOfLifeClassifier
        return True, "BioCLIP disponibile"
    except ImportError:
        return False, "BioCLIP NON installato"

def check_argos():
    """Verifica Argos Translate IT->EN"""
    try:
        import argostranslate.package
        import argostranslate.translate

        installed = argostranslate.package.get_installed_packages()
        for pkg in installed:
            if pkg.from_code == 'it' and pkg.to_code == 'en':
                # Test traduzione
                result = argostranslate.translate.translate("gatto", "it", "en")
                if result.lower() != "gatto":
                    return True, "Argos IT->EN funzionante"
                else:
                    return False, "Argos installato ma traduzione non funziona"

        return False, "Argos: pacchetto IT->EN mancante (esegui 05_setup_argos.py)"
    except ImportError:
        return False, "Argos NON installato"

def check_ollama():
    """Verifica Ollama e modello"""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            for m in models:
                if 'qwen3-vl:4b-instruct' in m.get('name', ''):
                    return True, "Ollama + qwen3-vl:4b-instruct"

            return True, "Ollama attivo (ma modello qwen3-vl non trovato)"
        return False, "Ollama non risponde"
    except:
        return False, "Ollama NON raggiungibile (avvialo o esegui 06_setup_ollama.bat)"

def check_opencv():
    """Verifica OpenCV con BRISQUE"""
    try:
        import cv2
        # Verifica modulo quality
        _ = cv2.quality.QualityBRISQUE_create
        return True, f"OpenCV {cv2.__version__} + BRISQUE"
    except ImportError:
        return False, "OpenCV NON installato"
    except AttributeError:
        return True, f"OpenCV {cv2.__version__} (senza BRISQUE)"

def main():
    print_header()

    print("Verifica componenti installazione OffGallery...")
    print()

    checks = [
        ("Python", check_python),
        ("PyTorch", check_torch),
        ("Transformers", check_transformers),
        ("PyQt6 (UI)", check_pyqt6),
        ("OpenCV", check_opencv),
        ("CLIP Model", check_clip_model),
        ("DINOv2 Model", check_dinov2_model),
        ("Aesthetic Model", check_aesthetic_model),
        ("BioCLIP", check_bioclip),
        ("Argos Translate", check_argos),
        ("Ollama LLM", check_ollama),
    ]

    results = []
    all_ok = True
    critical_ok = True

    print("─" * 60)

    for name, check_func in checks:
        try:
            ok, detail = check_func()
        except Exception as e:
            ok, detail = False, f"Errore: {e}"

        status = "[OK]" if ok else "[!!]"
        print(f"  {status} {name}: {detail}")

        results.append((name, ok, detail))
        if not ok:
            all_ok = False
            # Componenti critici
            if name in ["Python", "PyTorch", "Transformers", "PyQt6 (UI)"]:
                critical_ok = False

    print("─" * 60)
    print()

    # Riepilogo
    print("═" * 60)
    if all_ok:
        print("[OK] INSTALLAZIONE COMPLETA!")
        print()
        print("Puoi avviare OffGallery con:")
        print("  conda activate OffGallery")
        print("  python gui_launcher.py")
    elif critical_ok:
        print("[OK] INSTALLAZIONE BASE COMPLETATA")
        print()
        print("Alcuni componenti opzionali mancano, ma l'app funzionerà.")
        print("Puoi avviare OffGallery con:")
        print("  conda activate OffGallery")
        print("  python gui_launcher.py")
    else:
        print("[!!] INSTALLAZIONE INCOMPLETA")
        print()
        print("Componenti critici mancanti. Rivedi gli step precedenti.")
    print("═" * 60)

    print()
    input("Premi INVIO per chiudere...")

if __name__ == "__main__":
    main()
