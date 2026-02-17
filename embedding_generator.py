"""
Embedding Generator - Generazione embedding per ricerca semantica e similarita
Modelli: CLIP (semantica), DINOv2 (visiva), Aesthetic, BRISQUE, BioCLIP (natura)
LLM: Qwen2-VL via Ollama per descrizioni e tag AI

"""

import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import warnings
import os

from utils.paths import get_app_dir

warnings.filterwarnings('ignore')
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'

logger = logging.getLogger(__name__)

class EmbeddingGenerator:
    """Generatore embedding multipli con supporto LLM Vision e BioCLIP"""

    def __init__(self, config, initialization_mode='full'):
        self.config = config
        self.embedding_config = config.get('embedding', {})
        self.enabled = self.embedding_config.get('enabled', False)

        # Modelli - inizializza tutti a None
        self.clip_model = None
        self.clip_processor = None
        self.dinov2_model = None
        self.dinov2_processor = None
        self.aesthetic_model = None
        self.aesthetic_head = None
        self.aesthetic_processor = None
        self.brisque_available = False
        self.brisque_model_path = None
        self.brisque_range_path = None
        self.bioclip_classifier = None

        # Cache immagine LLM: evita estrazione/base64 ripetute per la stessa immagine
        self._llm_image_cache = {'source': None, 'base64': None, 'temp_path': None}

        # Device
        self.device = self._get_device()

        # CARICAMENTO PROFILI OTTIMIZZAZIONE DA CONFIG
        self.optimization_profiles = self._load_optimization_profiles()

        # Traduttore
        self.translator = None
        if self.embedding_config.get('translation', {}).get('enabled', True):
            self._init_translator()

        # Inizializzazione selettiva
        if self.enabled:
            if initialization_mode == 'llm_only':
                self._init_llm_only()
            elif initialization_mode == 'bioclip_only':
                self._init_bioclip_only()
            else:  # 'full' - processing batch
                self._initialize_models()

    def _init_llm_only(self):
        """Inizializza solo componenti LLM"""
        # LLM Vision non ha inizializzazione di modelli pesanti
        # Usa direttamente Ollama API
        logger.info("Modalità LLM only - nessun modello AI caricato")

    def _init_bioclip_only(self):
        """Inizializza solo BioCLIP"""
        models_config = self.embedding_config.get('models', {})
        if models_config.get('bioclip', {}).get('enabled', False):
            self._init_bioclip()
            self.bioclip_enabled = hasattr(self, 'bioclip_classifier') and self.bioclip_classifier is not   None
    
    def warmup_ollama(self):
        """Pre-carica il modello LLM in VRAM di Ollama (metodo ufficiale preload)."""
        try:
            import requests
            llm_config = self.embedding_config.get('models', {}).get('llm_vision', {})
            if not llm_config.get('enabled', False):
                return
            endpoint = llm_config.get('endpoint', 'http://localhost:11434')
            model = llm_config.get('model', 'qwen3-vl:4b-instruct')
            generation = llm_config.get('generation', {})
            keep_alive = generation.get('keep_alive', -1)
            # Metodo ufficiale Ollama: invia solo il nome modello per forzare il preload
            payload = {
                "model": model,
                "keep_alive": keep_alive,
            }
            logger.info(f"Warmup Ollama: preload {model} in VRAM...")
            response = requests.post(
                f"{endpoint}/api/generate",
                json=payload,
                timeout=120
            )
            if response.status_code == 200:
                logger.info(f"✅ Ollama warmup completato: {model} pronto in VRAM (keep_alive={keep_alive})")
            else:
                logger.warning(f"⚠️ Ollama warmup fallito: HTTP {response.status_code} - {response.text[:200]}")
        except requests.exceptions.ConnectionError:
            logger.warning("⚠️ Ollama non raggiungibile - warmup saltato (Ollama è avviato?)")
        except Exception as e:
            logger.warning(f"⚠️ Ollama warmup errore: {e}")

    def _get_device(self):
        """Determina device"""
        try:
            import torch
            if torch.cuda.is_available():
                return 'cuda'
            return 'cpu'
        except ImportError:
            return 'cpu'

    def _load_optimization_profiles(self) -> Dict:
        """
        Carica profili di ottimizzazione da config.
        Ogni profilo definisce: target_size, method, resampling, quality
        """
        from PIL import Image

        config_profiles = self.config.get('image_optimization', {}).get('profiles', {})

        # Profili di default (fallback)
        default_profiles = {
            'clip_embedding': {'target_size': 224, 'resampling': Image.Resampling.LANCZOS},  # ViT-B/32 input 224x224
            'dinov2_embedding': {'target_size': 518, 'resampling': Image.Resampling.LANCZOS},  # DINOv2 input 518x518 (14x37)
            'bioclip_classification': {'target_size': 224, 'resampling': Image.Resampling.LANCZOS},  # ViT-B/16 input 224x224
            'aesthetic_score': {'target_size': 224, 'resampling': Image.Resampling.BILINEAR},  # CLIP-based input 224x224
            'technical_score': {'target_size': 512, 'resampling': Image.Resampling.LANCZOS},  # BRISQUE/MUSIQ
            'llm_vision': {'target_size': 512, 'resampling': Image.Resampling.LANCZOS},  # Qwen3-VL 448-512px
            'default': {'target_size': 512, 'resampling': Image.Resampling.LANCZOS}
        }

        # Mapping nomi resampling -> costanti PIL
        resampling_map = {
            'LANCZOS': Image.Resampling.LANCZOS,
            'BILINEAR': Image.Resampling.BILINEAR,
            'BICUBIC': Image.Resampling.BICUBIC,
            'NEAREST': Image.Resampling.NEAREST
        }

        # Merge config con default
        final_profiles = {}
        for name, default_profile in default_profiles.items():
            cfg_profile = config_profiles.get(name, {})
            final_profiles[name] = {
                'target_size': cfg_profile.get('target_size', default_profile['target_size']),
                'resampling': resampling_map.get(
                    cfg_profile.get('resampling', 'LANCZOS').upper(),
                    default_profile['resampling']
                )
            }

        return final_profiles

    def _prepare_image_for_model(self, image_input, profile_name: str):
        """
        Prepara immagine per un modello specifico usando il profilo configurato.
        Ridimensiona alla target_size del profilo con il resampling corretto.

        Args:
            image_input: PIL Image, Path, o stringa path
            profile_name: nome profilo (es. 'clip_embedding', 'dinov2_embedding')

        Returns:
            PIL Image ridimensionata secondo il profilo
        """
        from PIL import Image

        profile = self.optimization_profiles.get(profile_name, self.optimization_profiles['default'])
        target_size = profile['target_size']
        resampling = profile['resampling']

        # Carica immagine se necessario
        if isinstance(image_input, Image.Image):
            image = image_input.copy()
        elif isinstance(image_input, (str, Path)):
            image = Image.open(image_input)
        else:
            logger.warning(f"Tipo input non supportato per prepare_image_for_model: {type(image_input)}")
            return image_input

        # Converti in RGB se necessario
        if image.mode not in ['RGB', 'L']:
            image = image.convert('RGB')

        # Ridimensiona se necessario (mantiene aspect ratio)
        w, h = image.size
        max_side = max(w, h)

        if max_side > target_size:
            scale = target_size / max_side
            new_size = (int(w * scale), int(h * scale))
            image = image.resize(new_size, resampling)
            logger.debug(f"🎯 {profile_name}: {w}x{h} → {image.size[0]}x{image.size[1]} ({resampling})")

        return image

    def _init_translator(self):
        """Inizializza traduttore Argos IT->EN dal repo congelato o server ufficiale"""
        try:
            import argostranslate.package
            import argostranslate.translate

            # Verifica se pacchetto IT->EN già installato
            installed = argostranslate.package.get_installed_packages()
            it_en_installed = any(pkg.from_code == 'it' and pkg.to_code == 'en' for pkg in installed)

            if not it_en_installed:
                logger.info("Argos IT->EN: installazione...")

                frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')
                models_mapping = self.config.get('models_repository', {}).get('models', {})
                argos_subfolder = models_mapping.get('argos_it_en', 'argos-it-en')

                downloaded = False

                # Prova repo congelato
                if frozen_repo:
                    try:
                        from huggingface_hub import hf_hub_download
                        import tempfile
                        import shutil


                        # Scarica metadata per verificare presenza
                        metadata_path = hf_hub_download(
                            repo_id=frozen_repo,
                            filename=f"{argos_subfolder}/metadata.json",
                            repo_type="model"
                        )

                        # Se arriviamo qui, il pacchetto esiste nel repo
                        # Scarica tutti i file necessari in temp dir
                        temp_dir = Path(tempfile.mkdtemp())
                        package_dir = temp_dir / argos_subfolder

                        from huggingface_hub import snapshot_download
                        snapshot_download(
                            repo_id=frozen_repo,
                            allow_patterns=f"{argos_subfolder}/**",
                            local_dir=str(temp_dir),
                            repo_type="model"
                        )

                        # Crea file .argosmodel (è uno zip)
                        import zipfile
                        argosmodel_path = temp_dir / "translate-it_en.argosmodel"
                        with zipfile.ZipFile(argosmodel_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                            for file_path in package_dir.rglob('*'):
                                if file_path.is_file():
                                    arcname = file_path.relative_to(package_dir)
                                    zf.write(file_path, arcname)

                        # Installa pacchetto
                        argostranslate.package.install_from_path(str(argosmodel_path))
                        downloaded = True
                        logger.info("[OK] Argos IT->EN installato")

                        # Pulizia
                        shutil.rmtree(temp_dir, ignore_errors=True)

                    except Exception as e:
                        logger.warning(f"Argos: repo congelato non disponibile ({e}), uso fallback...")

                # Fallback: server Argos ufficiale
                if not downloaded:
                    try:
                        argostranslate.package.update_package_index()
                        available = argostranslate.package.get_available_packages()

                        pkg_to_install = None
                        for pkg in available:
                            if pkg.from_code == 'it' and pkg.to_code == 'en':
                                pkg_to_install = pkg
                                break

                        if pkg_to_install:
                            download_path = pkg_to_install.download()
                            argostranslate.package.install_from_path(download_path)
                            logger.info("[OK] Argos IT->EN installato (fallback)")
                        else:
                            logger.warning("Argos: pacchetto IT->EN non trovato nel server")

                    except Exception as e:
                        logger.warning(f"Argos fallback: {e}")

            self.translator = argostranslate.translate
            logger.info("[OK] Traduttore inizializzato")

        except ImportError:
            logger.warning("Argostranslate non disponibile - traduzioni disabilitate")
            self.translator = None
    
    def _initialize_models(self):
        """Inizializza modelli abilitati"""
        models_config = self.embedding_config.get('models', {})
        if models_config.get('clip', {}).get('enabled', False): 
            self._init_clip()
        if models_config.get('dinov2', {}).get('enabled', False): 
            self._init_dinov2()
        if models_config.get('aesthetic', {}).get('enabled', False):
            self._init_aesthetic()
        # BRISQUE/Technical: controlla sia models.technical che brisque_enabled
        brisque_enabled = models_config.get('technical', {}).get('enabled', False) or \
                          self.embedding_config.get('brisque_enabled', False)
        if brisque_enabled:
            self._init_brisque()
        if models_config.get('bioclip', {}).get('enabled', False):
            self._init_bioclip()
            self.bioclip_enabled = hasattr(self, 'bioclip_classifier') and self.bioclip_classifier is not None

    def _init_clip(self):
        """Inizializza CLIP dal repo congelato HEGOM/OffGallery-models"""
        try:
            from transformers import CLIPProcessor, CLIPModel

            # Repo congelato (priorità) e fallback ufficiale
            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')
            fallback_model = self.embedding_config.get('models', {}).get('clip', {}).get('model_name', 'laion/CLIP-ViT-B-32-laion2B-s34B-b79K')

            loaded = False

            # Prova repo congelato
            if frozen_repo:
                try:
                    self.clip_model = CLIPModel.from_pretrained(frozen_repo, subfolder='clip').to(self.device)
                    self.clip_processor = CLIPProcessor.from_pretrained(frozen_repo, subfolder='clip')
                    loaded = True
                    logger.info("[OK] CLIP caricato")
                except Exception as e:
                    logger.warning(f"CLIP: repo congelato non disponibile ({e}), uso fallback...")

            # Fallback repo ufficiale
            if not loaded:
                self.clip_model = CLIPModel.from_pretrained(fallback_model).to(self.device)
                self.clip_processor = CLIPProcessor.from_pretrained(fallback_model)
                logger.info(f"[OK] CLIP caricato (fallback: {fallback_model})")

            self.clip_model.eval()
            self.clip_enabled = True
        except Exception as e:
            logger.error(f"CLIP: {e}")
            self.clip_enabled = False

    def _init_dinov2(self):
        """Inizializza DINOv2 dal repo congelato HEGOM/OffGallery-models"""
        try:
            from transformers import AutoImageProcessor, AutoModel

            # Repo congelato (priorità) e fallback ufficiale
            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')
            fallback_model = self.embedding_config.get('models', {}).get('dinov2', {}).get('model_name', 'facebook/dinov2-base')

            loaded = False

            # Prova repo congelato
            if frozen_repo:
                try:
                    self.dinov2_model = AutoModel.from_pretrained(frozen_repo, subfolder='dinov2').to(self.device)
                    self.dinov2_processor = AutoImageProcessor.from_pretrained(frozen_repo, subfolder='dinov2')
                    loaded = True
                    logger.info("[OK] DINOv2 caricato")
                except Exception as e:
                    logger.warning(f"DINOv2: repo congelato non disponibile ({e}), uso fallback...")

            # Fallback repo ufficiale
            if not loaded:
                self.dinov2_model = AutoModel.from_pretrained(fallback_model).to(self.device)
                self.dinov2_processor = AutoImageProcessor.from_pretrained(fallback_model)
                logger.info(f"[OK] DINOv2 caricato (fallback: {fallback_model})")

            self.dinov2_model.eval()
            self.dinov2_enabled = True
        except Exception as e:
            logger.error(f"DINOv2: {e}")
            self.dinov2_enabled = False

    def _init_aesthetic(self):
        """Inizializza Aesthetic Score dal repo congelato HEGOM/OffGallery-models"""
        try:
            from transformers import CLIPProcessor, CLIPModel
            import torch
            import torch.nn as nn

            app_dir = get_app_dir()
            aesthetic_dir = app_dir / 'aesthetic'

            # Repo congelato e fallback
            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')
            fallback_model = 'openai/clip-vit-large-patch14'

            # Verifica se già presente in locale
            model_files = ['config.json', 'pytorch_model.bin', 'preprocessor_config.json', 'tokenizer_config.json']
            # Accetta anche model.safetensors al posto di pytorch_model.bin
            local_exists = aesthetic_dir.exists() and (
                (aesthetic_dir / 'pytorch_model.bin').exists() or
                (aesthetic_dir / 'model.safetensors').exists()
            )

            clip_model = None

            # 1. Prova a caricare da directory locale (già scaricato)
            if local_exists:
                try:
                    clip_model = CLIPModel.from_pretrained(str(aesthetic_dir)).to(self.device)
                    self.aesthetic_processor = CLIPProcessor.from_pretrained(str(aesthetic_dir))
                    logger.info("[OK] Aesthetic caricato")
                except Exception as e:
                    logger.warning(f"Aesthetic: cache locale non valida ({e})")
                    clip_model = None

            # 2. Prova repo congelato
            if clip_model is None and frozen_repo:
                try:
                    clip_model = CLIPModel.from_pretrained(frozen_repo, subfolder='aesthetic').to(self.device)
                    self.aesthetic_processor = CLIPProcessor.from_pretrained(frozen_repo, subfolder='aesthetic')
                    aesthetic_dir.mkdir(exist_ok=True)
                    clip_model.save_pretrained(str(aesthetic_dir))
                    self.aesthetic_processor.save_pretrained(str(aesthetic_dir))
                    logger.info("[OK] Aesthetic caricato")
                except Exception as e:
                    logger.warning(f"Aesthetic: repo congelato non disponibile ({e}), uso fallback...")
                    clip_model = None

            # 3. Fallback repo ufficiale
            if clip_model is None:
                clip_model = CLIPModel.from_pretrained(fallback_model).to(self.device)
                self.aesthetic_processor = CLIPProcessor.from_pretrained(fallback_model)
                aesthetic_dir.mkdir(exist_ok=True)
                clip_model.save_pretrained(str(aesthetic_dir))
                self.aesthetic_processor.save_pretrained(str(aesthetic_dir))
                logger.info(f"[OK] Aesthetic caricato (fallback: {fallback_model})")

            # Head per score estetico
            pooler_dim = clip_model.vision_model.config.hidden_size
            self.aesthetic_head = nn.Linear(pooler_dim, 1).to(self.device)
            torch.nn.init.xavier_normal_(self.aesthetic_head.weight)
            torch.nn.init.constant_(self.aesthetic_head.bias, 0.0)

            self.aesthetic_model = clip_model.vision_model
            self.aesthetic_model.eval()
            self.aesthetic_head.eval()
            self.aesthetic_enabled = True

        except Exception as e:
            logger.error(f"Aesthetic: {e}")
            self.aesthetic_enabled = False

    def _init_brisque(self):
        """Inizializza BRISQUE per valutazione qualità tecnica"""
        try:
            import cv2
            app_dir = get_app_dir()

            self.brisque_model_path = app_dir / 'brisque_models' / 'brisque_model_live.yml'
            self.brisque_range_path = app_dir / 'brisque_models' / 'brisque_range_live.yml'

            if self.brisque_model_path.exists() and self.brisque_range_path.exists():
                try:
                    cv2.quality.QualityBRISQUE_create(str(self.brisque_model_path), str(self.brisque_range_path))
                    self.brisque_available = True
                except Exception as e:
                    logger.warning(f"BRISQUE: errore caricamento modelli locali ({e})")
                    self.brisque_available = False
            else:
                try:
                    _ = cv2.quality.QualityBRISQUE_create()
                    self.brisque_available = True
                    self.brisque_model_path = None
                    self.brisque_range_path = None
                except Exception as e:
                    logger.warning(f"BRISQUE: modelli non disponibili ({e})")
                    self.brisque_available = False

            logger.info(f"[OK] BRISQUE: {'disponibile' if self.brisque_available else 'non disponibile'}")

        except Exception as e:
            logger.error(f"BRISQUE: {e}")
            self.brisque_available = False

    def _init_bioclip(self):
        """
        Inizializza BioCLIP TreeOfLife classifier.
        Priorità: cartella locale bioclip/ -> download da HuggingFace -> fallback repo ufficiale
        """
        if self.bioclip_classifier is not None:
            return True

        try:
            from bioclip import TreeOfLifeClassifier
            from bioclip.predict import BaseClassifier
            import open_clip
            import torch
            import numpy as np
            import json

            app_dir = get_app_dir()
            bioclip_dir = app_dir / 'bioclip'
            treeoflife_dir = app_dir / 'treeoflife'

            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')
            models_mapping = self.config.get('models_repository', {}).get('models', {})

            # File necessari per BioCLIP
            bioclip_files = ['open_clip_config.json', 'open_clip_model.safetensors']
            treeoflife_files = ['txt_emb_species.npy', 'txt_emb_species.json']

            # Verifica se i file locali esistono
            bioclip_local_ok = bioclip_dir.exists() and all(
                (bioclip_dir / f).exists() for f in bioclip_files
            )
            treeoflife_local_ok = treeoflife_dir.exists() and all(
                (treeoflife_dir / f).exists() for f in treeoflife_files
            )


            # Se mancano file locali, scarica da HuggingFace
            if not bioclip_local_ok or not treeoflife_local_ok:
                if frozen_repo:
                    try:
                        from huggingface_hub import hf_hub_download

                        bioclip_subfolder = models_mapping.get('bioclip', 'bioclip')
                        treeoflife_subfolder = models_mapping.get('treeoflife', 'treeoflife')

                        # Scarica BioCLIP model
                        if not bioclip_local_ok:
                            logger.info("BioCLIP: download modelli...")
                            bioclip_dir.mkdir(exist_ok=True)

                            for filename in bioclip_files:
                                try:
                                    downloaded = hf_hub_download(
                                        repo_id=frozen_repo,
                                        filename=f"{bioclip_subfolder}/{filename}",
                                        repo_type="model"
                                    )
                                    # Copia nella cartella locale
                                    import shutil
                                    shutil.copy2(downloaded, bioclip_dir / filename)
                                except Exception as e:
                                    logger.warning(f"BioCLIP: errore download {filename}: {e}")

                            bioclip_local_ok = all((bioclip_dir / f).exists() for f in bioclip_files)

                        # Scarica TreeOfLife embeddings (sono in treeoflife/embeddings/)
                        if not treeoflife_local_ok:
                            logger.info("TreeOfLife: download embeddings...")
                            treeoflife_dir.mkdir(exist_ok=True)

                            for filename in treeoflife_files:
                                try:
                                    downloaded = hf_hub_download(
                                        repo_id=frozen_repo,
                                        filename=f"{treeoflife_subfolder}/embeddings/{filename}",
                                        repo_type="model"
                                    )
                                    import shutil
                                    shutil.copy2(downloaded, treeoflife_dir / filename)
                                except Exception as e:
                                    logger.warning(f"TreeOfLife: errore download {filename}: {e}")

                            treeoflife_local_ok = all((treeoflife_dir / f).exists() for f in treeoflife_files)

                    except Exception as e:
                        logger.warning(f"BioCLIP: download da repo congelato fallito ({e})")

            # Carica da cartella locale se disponibile
            if bioclip_local_ok and treeoflife_local_ok:
                try:
                    # Carica modello con open_clip usando architettura ViT-L-14 e pesi locali
                    model, _, preprocess = open_clip.create_model_and_transforms(
                        model_name='ViT-L-14',  # Architettura BioCLIP (ViT-L/14)
                        pretrained=str(bioclip_dir / 'open_clip_model.safetensors'),
                        device=self.device
                    )

                    # Carica TreeOfLife embeddings
                    txt_emb = torch.from_numpy(
                        np.load(treeoflife_dir / 'txt_emb_species.npy')
                    ).to(self.device)

                    # Normalizza shape: il file può essere (dim, N_specie) o (N_specie, dim)
                    # Deve essere (N_specie, dim) per matmul con image_features (1, dim)
                    if txt_emb.ndim == 2 and txt_emb.shape[0] < txt_emb.shape[1]:
                        txt_emb = txt_emb.T
                        logger.info(f"TreeOfLife: embeddings trasposti → {txt_emb.shape}")

                    with open(treeoflife_dir / 'txt_emb_species.json', 'r') as f:
                        txt_names = json.load(f)

                    # Crea classifier wrapper compatibile con TreeOfLifeClassifier
                    class LocalTreeOfLifeClassifier:
                        """TreeOfLifeClassifier con modello locale, interfaccia compatibile"""
                        def __init__(self, model, preprocess, txt_emb, txt_names, device):
                            self.model = model
                            self.preprocess = preprocess
                            self.txt_embeddings = txt_emb
                            self.txt_names = txt_names
                            self.device = device

                        def predict(self, images, rank=None, k=5, min_prob=0.0):
                            """
                            Predice le top-k specie per una lista di immagini.
                            Interfaccia compatibile con TreeOfLifeClassifier.

                            Args:
                                images: Lista di PIL Images
                                rank: Ignorato (per compatibilità)
                                k: Numero di predizioni top
                                min_prob: Probabilità minima per includere risultato

                            Returns:
                                Lista di dict con species, genus, family, common_name, score
                            """
                            from PIL import Image

                            if not images:
                                return []

                            # Prendi la prima immagine (batch di 1)
                            image = images[0]
                            if isinstance(image, (str, Path)):
                                image = Image.open(image).convert('RGB')
                            elif hasattr(image, 'convert'):
                                image = image.convert('RGB')

                            # Preprocess e inference
                            image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)

                            with torch.no_grad():
                                image_features = self.model.encode_image(image_tensor)
                                image_features = image_features / image_features.norm(dim=-1, keepdim=True)

                                # Similarità con tutti gli embeddings (softmax per probabilità)
                                similarities = (image_features @ self.txt_embeddings.T).squeeze(0)
                                probs = torch.softmax(similarities * 100, dim=0)  # Temperature scaling

                                # Top-k
                                top_probs, top_indices = probs.topk(k)

                                results = []
                                for prob, idx in zip(top_probs, top_indices):
                                    prob_val = prob.item()
                                    if prob_val < min_prob:
                                        continue

                                    # Parsing tassonomico completo da TreeOfLife (7 livelli)
                                    entry = self.txt_names[idx.item()]

                                    # Formato lista: [[kingdom,phylum,class,order,family,genus,species], common_name]
                                    if isinstance(entry, list) and len(entry) >= 2:
                                        taxon = entry[0] if isinstance(entry[0], list) else []
                                        common_name = entry[1] if isinstance(entry[1], str) else ''
                                        kingdom = taxon[0] if len(taxon) > 0 else ''
                                        phylum = taxon[1] if len(taxon) > 1 else ''
                                        tax_class = taxon[2] if len(taxon) > 2 else ''
                                        order = taxon[3] if len(taxon) > 3 else ''
                                        family = taxon[4] if len(taxon) > 4 else 'Unknown'
                                        genus = taxon[5] if len(taxon) > 5 else 'Unknown'
                                        species_epithet = taxon[6] if len(taxon) > 6 else ''
                                        species = f"{genus} {species_epithet}".strip() if species_epithet else genus
                                    elif isinstance(entry, str):
                                        # Formato stringa semplice (vecchio formato)
                                        parts = entry.replace('_', ' ').split()
                                        genus = parts[0] if parts else 'Unknown'
                                        species = ' '.join(parts[:2]) if len(parts) >= 2 else entry
                                        family = 'Unknown'
                                        common_name = ''
                                        kingdom = phylum = tax_class = order = ''
                                        species_epithet = parts[1] if len(parts) >= 2 else ''
                                    else:
                                        continue

                                    results.append({
                                        'species': species,
                                        'genus': genus,
                                        'family': family,
                                        'common_name': common_name,
                                        'score': prob_val,
                                        'taxonomy': [kingdom, phylum, tax_class, order, family, genus, species_epithet]
                                    })

                                return results

                    self.bioclip_classifier = LocalTreeOfLifeClassifier(
                        model, preprocess, txt_emb, txt_names, self.device
                    )
                    logger.info("[OK] BioCLIP caricato")
                    return True

                except Exception as e:
                    logger.warning(f"BioCLIP: caricamento locale fallito ({e}), uso fallback...")

            # Fallback: TreeOfLifeClassifier standard (scarica da repo ufficiale)
            self.bioclip_classifier = TreeOfLifeClassifier(device=self.device)
            logger.info("[OK] BioCLIP caricato (fallback)")
            return True

        except Exception as e:
            logger.error(f"BioCLIP: {e}")
            return False

    def test_models(self):
        """Testa disponibilità modelli"""
        return {
            'clip': getattr(self, 'clip_enabled', False),
            'dinov2': getattr(self, 'dinov2_enabled', False),
            'aesthetic': getattr(self, 'aesthetic_enabled', False),
            'brisque': self.brisque_available,
            'bioclip': self.bioclip_classifier is not None
        }

    def generate_embeddings(self, input_data, original_path=None):
        """
        Genera embedding distinguendo tra File (Immagine) e Stringa (Testo).
        Supporta tutti i formati immagine (JPG, RAW, ecc.) tramite os.path.exists.

        Args:
            input_data: PIL Image, path string, o testo per query
            original_path: Path originale del file (opzionale, usato per BRISQUE)
                          BRISQUE richiede il file originale, non un thumbnail
        """
        import os
        import torch
        import numpy as np

        # 1. LOGICA TESTO (Ricerca Semantica)
        # Se l'input è una stringa e NON esiste come file fisico, è testo per la ricerca
        if isinstance(input_data, str) and not os.path.exists(input_data):
            try:
                if self.clip_model is None or self.clip_processor is None:
                    logger.error(" Modello CLIP o Processor non inizializzati.")
                    return None
                
                # Tokenizzazione e generazione embedding con la libreria Transformers
                inputs = self.clip_processor(text=[input_data], return_tensors="pt", padding=True).to(self.device)
                
                with torch.no_grad():
                    # Il metodo corretto per CLIPModel di HuggingFace è get_text_features
                    text_features = self.clip_model.get_text_features(**inputs)
                
                # Convertiamo in array numpy per la similarità
                text_emb = text_features.cpu().numpy().flatten()
                
                return {'text_embedding': text_emb}
                
            except Exception as e:
                logger.error(f"Errore CLIP testo (transformers): {e}")
                return None

        # 2. LOGICA IMMAGINE (Qualsiasi formato supportato)
        else:
            try:
                result = {}

                # CLIP embedding
                img_emb = self._generate_clip_embedding(input_data, 'path')
                result['clip_embedding'] = img_emb

                # DINOv2 embedding (se abilitato)
                if getattr(self, 'dinov2_enabled', False):
                    dinov2_emb = self._generate_dinov2_embedding(input_data, 'path')
                    result['dinov2_embedding'] = dinov2_emb
                    if dinov2_emb is not None:
                        logger.debug(f"DINOv2 embedding generato: shape={dinov2_emb.shape}")

                # Aesthetic score (se abilitato)
                if getattr(self, 'aesthetic_enabled', False):
                    aesthetic = self._generate_aesthetic_score(input_data, 'path')
                    result['aesthetic_score'] = aesthetic
                    logger.debug(f"Aesthetic score generato: {aesthetic}")

                # Technical score / BRISQUE (se abilitato)
                # NOTA: BRISQUE richiede il PATH originale di un file NON-RAW
                # Per file RAW: original_path sarà None → skip BRISQUE
                if getattr(self, 'brisque_available', False) and original_path is not None:
                    technical = self._generate_brisque_score(original_path)
                    result['technical_score'] = technical
                    if technical is not None:
                        logger.debug(f"Technical score generato: {technical}")
                elif getattr(self, 'brisque_available', False):
                    # RAW file - BRISQUE non applicabile
                    result['technical_score'] = None

                # BioCLIP tags + tassonomia completa (se abilitato)
                if getattr(self, 'bioclip_enabled', False):
                    bioclip_tags, bioclip_taxonomy = self.generate_bioclip_tags(input_data)
                    result['bioclip_tags'] = bioclip_tags
                    result['bioclip_taxonomy'] = bioclip_taxonomy
                    if bioclip_tags:
                        logger.info(f"BioCLIP tags generati: {bioclip_tags}")
                    if bioclip_taxonomy:
                        logger.info(f"BioCLIP taxonomy: {bioclip_taxonomy}")

                return result
            except Exception as e:
                logger.error(f"Errore CLIP immagine: {e}")
                return None

    def _predict_bioclip(self, image_input, input_type):
        """Esegue predizione BioCLIP usando configurazione da config.yaml.
        OTTIMIZZATO: Usa profilo 'bioclip_classification' per resize alla dimensione ottimale."""
        if self.bioclip_classifier is None:
            return []

        try:
            from bioclip.predict import Rank
            from PIL import Image

            # ─────────────────────────────────────
            # Config BioCLIP
            # ─────────────────────────────────────
            bioclip_cfg = (
               self.embedding_config
                .get('models', {})
                .get('bioclip', {})
            )

            max_tags = int(bioclip_cfg.get('max_tags', 5))
            threshold = float(bioclip_cfg.get('threshold', 0.1))

            # Ottieni target_size dal profilo config
            bioclip_profile = self.optimization_profiles.get('bioclip_classification', {})
            target_size = bioclip_profile.get('target_size', 384)

            # ─────────────────────────────────────
            # Normalizzazione input con profilo ottimizzazione
            # ─────────────────────────────────────
            if input_type == 'path':
                # Usa RAWProcessor con profilo esplicito
                try:
                    from raw_processor import RAWProcessor
                    raw_processor = RAWProcessor(self.config)

                    # Estrai immagine ottimizzata per BioCLIP usando profilo config
                    image = raw_processor.extract_thumbnail(
                        Path(image_input),
                        target_size=target_size,
                        profile_name='bioclip_classification'
                    )
                    if image is None:
                        # Fallback se RAW processor fallisce
                        logger.warning("RAW processor fallito, uso Image.open direttamente")
                        image = Image.open(image_input).convert('RGB')
                        image = self._prepare_image_for_model(image, 'bioclip_classification')
                    else:
                        logger.info(f"BioCLIP: immagine ottimizzata via RAW processor ({image.size})")

                except ImportError:
                    logger.warning("RAW processor non disponibile, uso Image.open")
                    image = Image.open(image_input).convert('RGB')
                    image = self._prepare_image_for_model(image, 'bioclip_classification')
                except Exception as e:
                    logger.warning(f"Errore RAW processor ({e}), uso Image.open")
                    image = Image.open(image_input).convert('RGB')
                    image = self._prepare_image_for_model(image, 'bioclip_classification')

            elif input_type == 'pil':
                # Prepara PIL image con profilo ottimizzazione
                image = self._prepare_image_for_model(image_input, 'bioclip_classification')
            else:
                return []

            # ─────────────────────────────────────
            # Predizione BioCLIP
            # ─────────────────────────────────────
            predictions = self.bioclip_classifier.predict(
                images=[image],
                rank=Rank.SPECIES,
                k=max_tags,
                min_prob=threshold
            )

            if not predictions:
                logger.info(f"BioCLIP: nessuna specie trovata sopra soglia {threshold}")
                return []

            logger.info(
                f"BioCLIP: {len(predictions)} predizioni "
                f"(k={max_tags}, threshold={threshold})"
            )

            return predictions

        except Exception as e:
            logger.error(f"Errore predizione BioCLIP: {e}")
            return []

    def _generate_clip_embedding(self, image_input, input_type):
        """Genera embedding CLIP per ricerca semantica.
        OTTIMIZZATO: Usa profilo 'clip_embedding' per resize alla dimensione ottimale."""
        try:
            import torch
            # Carica immagine
            image = self._load_image_from_input(image_input, input_type)
            # Prepara con profilo ottimizzazione (target_size e resampling da config)
            image = self._prepare_image_for_model(image, 'clip_embedding')
            inputs = self.clip_processor(images=image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                features = self.clip_model.get_image_features(**inputs)
            embedding = features.cpu().numpy()[0]
            return (embedding / np.linalg.norm(embedding)).astype(np.float32)
        except Exception as e:
            logger.error(f"CLIP embedding: {e}")
            return None

    def _generate_dinov2_embedding(self, image_input, input_type):
        """Genera embedding DINOv2 per similarita visiva.
        OTTIMIZZATO: Usa profilo 'dinov2_embedding' per resize alla dimensione ottimale."""
        try:
            import torch
            # Carica immagine
            image = self._load_image_from_input(image_input, input_type)
            # Prepara con profilo ottimizzazione (target_size e resampling da config)
            image = self._prepare_image_for_model(image, 'dinov2_embedding')
            inputs = self.dinov2_processor(images=image, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.dinov2_model(**inputs)
                features = outputs.last_hidden_state[:, 0, :]  # CLS token
            embedding = features.cpu().numpy()[0]
            return (embedding / np.linalg.norm(embedding)).astype(np.float32)
        except Exception as e:
            logger.error(f"DINOv2 embedding: {e}")
            return None

    def _generate_aesthetic_score(self, image_input, input_type):
        """Genera score estetico con normalizzazione 0-10 dinamica.
        OTTIMIZZATO: Usa profilo 'aesthetic_score' per resize alla dimensione ottimale."""
        try:
            import torch
            # Carica immagine
            image = self._load_image_from_input(image_input, input_type)
            # Prepara con profilo ottimizzazione (target_size e resampling da config)
            image = self._prepare_image_for_model(image, 'aesthetic_score')
            inputs = self.aesthetic_processor(images=image, return_tensors="pt").to(self.device)
            
            with torch.no_grad():
                vision_outputs = self.aesthetic_model(**inputs)
                image_embeds = vision_outputs.pooler_output
                raw_score = self.aesthetic_head(image_embeds).item()
                
                # Normalizzazione Sigmoide per mappare lo score in 0.0 - 10.0
                # Impedisce al valore di restare bloccato a 10
                score = 10 / (1 + np.exp(-raw_score))
            
            return round(score, 2)
        except Exception as e:
            logger.error(f"Errore aesthetic score: {e}")
            return None

    def _generate_brisque_score(self, image_path) -> Optional[float]:
        """
        Genera BRISQUE score SOLO da file path non-RAW.

        Configurazione in config_new.yaml → image_optimization.profiles.technical_score:
        - mode: 'optimized' (riduce a max_size) o 'original' (file intero)
        - max_size: dimensione max per mode optimized (default 1024)

        Args:
            image_path: Path del file immagine (DEVE essere path, non PIL Image)

        Returns:
            float: score 0-100 (100 = qualità perfetta) o None se non applicabile
        """
        try:
            import cv2
            from PIL import Image

            # BRISQUE richiede il PATH del file originale
            if isinstance(image_path, Image.Image):
                logger.warning("BRISQUE: ricevuto PIL Image invece di path - skip")
                return None

            image_path_obj = Path(image_path) if not isinstance(image_path, Path) else image_path
            if not image_path_obj.exists():
                logger.warning(f"BRISQUE: file non trovato {image_path}")
                return None

            # Carica immagine
            img = cv2.imread(str(image_path_obj))
            if img is None:
                logger.warning(f"BRISQUE: impossibile caricare {image_path}")
                return None

            # Leggi configurazione mode/max_size dal config
            brisque_cfg = self.config.get('image_optimization', {}).get('profiles', {}).get('technical_score', {})
            mode = brisque_cfg.get('mode', 'optimized')
            max_size = brisque_cfg.get('max_size', 1024)

            # Applica ridimensionamento se mode=optimized
            h, w = img.shape[:2]
            if mode == 'optimized' and max(h, w) > max_size:
                scale = max_size / max(h, w)
                new_size = (int(w * scale), int(h * scale))
                img = cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)
                logger.debug(f"BRISQUE: {w}x{h} → {new_size[0]}x{new_size[1]}")

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

            if self.brisque_model_path:
                brisque = cv2.quality.QualityBRISQUE_create(str(self.brisque_model_path), str(self.brisque_range_path))
            else:
                brisque = cv2.quality.QualityBRISQUE_create()

            score = brisque.compute(gray)[0]
            # Inversione: BRISQUE 0 è perfetto, 100 è pessimo
            return round(max(0.0, min(100.0, 100.0 - score)), 2)
        except Exception as e:
            logger.error(f"Errore BRISQUE: {e}")
            return None

    def generate_text_embedding(self, text_query: str):
        """Genera embedding CLIP per testo (ricerca semantica)"""
        try:
            import torch
            if not getattr(self, 'clip_enabled', False): 
                return None
            translated = self._translate_to_english(text_query) if self.translator else text_query
            inputs = self.clip_processor(text=[translated], return_tensors="pt", padding=True).to(self.device)
            with torch.no_grad():
                text_features = self.clip_model.get_text_features(**inputs)
            embedding = text_features.cpu().numpy()[0]
            return (embedding / np.linalg.norm(embedding)).astype(np.float32)
        except Exception as e:
            logger.error(f"Text embedding: {e}")
            return None

    def _translate_to_english(self, text):
        try:
            # Forziamo il ricaricamento dei pacchetti se non sembrano pronti
            import argostranslate.translate
            import argostranslate.package
            import logging
            # Disabilita i log verbosi di argostranslate
            logging.getLogger('argostranslate.utils').setLevel(logging.WARNING)
        
            # Se il testo è già inglese o troppo corto, usciamo
            if all(ord(c) < 128 for c in text) and len(text) < 5:
                return text
            
            # Eseguiamo la traduzione
            translated = argostranslate.translate.translate(text, "it", "en")
        
            # Debug interno
            if translated.lower() == text.lower():
                # Tentativo estremo: ricarica i pacchetti installati
                installed_packages = argostranslate.package.get_installed_packages()
                logger.debug(f"Pacchetti Argos installati rilevati: {len(installed_packages)}")
            
            return translated
        except Exception as e:
            logger.error(f"Errore durante la traduzione: {e}")
            return text

    def _detect_input_type(self, image_input):
        """Rileva tipo di input immagine"""
        try:
            from PIL import Image
            if isinstance(image_input, Image.Image):
                return 'pil'
            elif isinstance(image_input, (str, Path)):
                return 'path'
            elif hasattr(image_input, 'read'):
                return 'bytes'
            elif isinstance(image_input, np.ndarray):
                return 'numpy'
            else:
                return 'unknown'
        except ImportError:
            if isinstance(image_input, (str, Path)):
                return 'path'
            return 'unknown'

    def _load_image_from_input(self, image_input, input_type):
        """Carica immagine da diversi tipi di input - FIX PER OGGETTI GIÀ CARICATI"""
        try:
            from PIL import Image
            import io
        
            # Se è già un oggetto PIL Image, lo usiamo direttamente
            if isinstance(image_input, Image.Image):
                return image_input.convert('RGB')
            
            if input_type == 'pil':
                return image_input.convert('RGB')
            elif input_type == 'path':
                return Image.open(image_input).convert('RGB')
            elif input_type == 'bytes':
                # Verifica se image_input ha il metodo read, altrimenti è già un oggetto
                if hasattr(image_input, 'read'):
                    return Image.open(io.BytesIO(image_input.read())).convert('RGB')
                else:
                    return Image.open(io.BytesIO(image_input)).convert('RGB')
            elif input_type == 'numpy':
                return Image.fromarray(image_input).convert('RGB')
            else:
                # Se arriviamo qui e l'oggetto sembra un'immagine, proviamo il recupero estremo
                if hasattr(image_input, 'convert'):
                    return image_input.convert('RGB')
                raise ValueError(f"Tipo input non supportato: {input_type}")
        except Exception as e:
            logger.error(f"Errore caricamento immagine: {e}")
            raise

    # ===== BIOCLIP ON-DEMAND METHODS =====
    def generate_bioclip_tags(self, input_data):
        """
        Genera tag BioCLIP con tassonomia completa.
        Args:
            input_data: Path/str (filepath), PIL.Image, o lista di predizioni BioCLIP
        Returns:
            tuple: (flat_tags, taxonomy_array) dove:
                - flat_tags: lista tag display ["Specie: X", "Genere: Y", ...]
                - taxonomy_array: lista 7 livelli [kingdom, phylum, class, order, family, genus, species_epithet] o None
        """
        from PIL import Image

        # Inizializza BioCLIP se necessario
        if self.bioclip_classifier is None:
            if not self._init_bioclip():
                logger.error("BioCLIP non disponibile")
                return [], None

        predictions = None

        # Se è un filepath (string o Path), esegui pipeline completa
        if isinstance(input_data, (str, Path)):
            try:
                predictions = self._predict_bioclip(input_data, 'path')
            except Exception as e:
                logger.error(f"Errore BioCLIP da filepath: {e}")
                return [], None

        # Se è una PIL Image, usa direttamente
        elif isinstance(input_data, Image.Image):
            try:
                predictions = self._predict_bioclip(input_data, 'pil')
            except Exception as e:
                logger.error(f"Errore BioCLIP da PIL Image: {e}")
                return [], None

        # Se è una lista di predizioni, usa direttamente
        elif isinstance(input_data, list):
            predictions = input_data

        else:
            logger.error(f"Input non supportato per BioCLIP: {type(input_data)}")
            return [], None

        flat_tags = self._format_bioclip_tags(predictions)
        taxonomy = self._extract_best_taxonomy(predictions)
        return flat_tags, taxonomy
    
    def _format_bioclip_tags(self, predictions_list):
        """Formatta predizioni BioCLIP in tag (metodo originale)"""
        if not predictions_list or not isinstance(predictions_list, list):
            return []
    
        try:
            # Prendi la predizione con score più alto
            best_prediction = max(predictions_list, key=lambda x: x.get('score', 0))
        
            if best_prediction.get('score', 0) < 0.1:  # Soglia minima confidenza
                return []
        
            species = best_prediction.get('species', 'Unknown')
            genus = best_prediction.get('genus', 'Unknown')
            family = best_prediction.get('family', 'Unknown')
            common_name = best_prediction.get('common_name', '')
            score = best_prediction.get('score', 0)
        
            tags = [
                f"Specie: {species}",
                f"Genere: {genus}",
                f"Famiglia: {family}",
                f"Confidenza: {score:.2f}"
            ]
        
            if common_name:
                tags.append(f"Nome comune: {common_name}")
        
            return tags
        
        except Exception as e:
            logger.error(f"Errore parsing BioCLIP tags: {e}")
            return []

    def _extract_best_taxonomy(self, predictions_list):
        """Estrae tassonomia completa dalla migliore predizione BioCLIP"""
        if not predictions_list or not isinstance(predictions_list, list):
            return None
        try:
            best = max(predictions_list, key=lambda x: x.get('score', 0))
            if best.get('score', 0) < 0.1:
                return None
            return best.get('taxonomy')
        except Exception as e:
            logger.error(f"Errore estrazione taxonomy: {e}")
            return None

    @staticmethod
    def build_hierarchical_taxonomy(taxonomy_array, prefix="AI|Taxonomy"):
        """Costruisce stringa gerarchica da array tassonomico, saltando livelli vuoti.
        Es: ["Animalia","","Aves","","Passeridae","Passer","domesticus"]
          → "AI|Taxonomy|Animalia|Aves|Passeridae|Passer|domesticus"
        """
        if not taxonomy_array:
            return ""
        parts = [prefix]
        for level in taxonomy_array:
            if level and level.strip():
                parts.append(level.strip())
        return "|".join(parts) if len(parts) > 1 else ""

    @staticmethod
    def parse_hierarchical_taxonomy(hierarchical_str, prefix="AI|Taxonomy"):
        """Parsing inverso: da stringa gerarchica a lista livelli (senza prefix)."""
        if not hierarchical_str or not hierarchical_str.startswith(prefix + "|"):
            return None
        parts = hierarchical_str[len(prefix) + 1:].split("|")
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def extract_bioclip_context(bioclip_tags):
        """Estrae contesto compatto da tag BioCLIP per iniezione in prompt LLM.

        Input: ["Specie: Passer domesticus", "Confidenza: 0.85", "Nome comune: House Sparrow", ...]
        Output: "Passer domesticus (House Sparrow), conf:0.85" oppure None
        Soglia: confidenza < 0.15 → None (troppo incerto per il modello 4B)
        """
        if not bioclip_tags:
            return None

        species = None
        common_name = None
        confidence = None

        for tag in bioclip_tags:
            t = tag.strip()
            if t.startswith("Specie: ") or t.startswith("Species: "):
                species = t.split(": ", 1)[1].strip()
            elif t.startswith("Nome comune: ") or t.startswith("Common name: "):
                common_name = t.split(": ", 1)[1].strip()
            elif t.startswith("Confidenza: ") or t.startswith("Confidence: "):
                try:
                    confidence = float(t.split(": ", 1)[1].strip())
                except ValueError:
                    pass

        if not species or species == 'Unknown':
            return None
        if confidence is not None and confidence < 0.15:
            return None

        result = species
        if common_name:
            result = f"{species} ({common_name})"
        if confidence is not None:
            result = f"{result}, conf:{confidence:.2f}"
        return result

    # Mappa classe tassonomica BioCLIP → hint italiano per il prompt LLM
    TAXONOMY_CLASS_HINTS = {
        # Animali - Vertebrati
        'Aves': 'uccello',
        'Mammalia': 'mammifero',
        'Reptilia': 'rettile',
        'Amphibia': 'anfibio',
        'Actinopterygii': 'pesce',
        'Chondrichthyes': 'pesce cartilagineo',
        'Agnatha': 'pesce primitivo',
        # Animali - Invertebrati
        'Insecta': 'insetto',
        'Arachnida': 'aracnide',
        'Malacostraca': 'crostaceo',
        'Gastropoda': 'lumaca o chiocciola',
        'Bivalvia': 'mollusco bivalve',
        'Cephalopoda': 'cefalopode',
        # Piante
        'Magnoliopsida': 'pianta',
        'Liliopsida': 'pianta monocotiledone',
        'Pinopsida': 'conifera',
        'Polypodiopsida': 'felce',
        # Funghi
        'Agaricomycetes': 'fungo',
        'Lecanoromycetes': 'lichene',
    }

    @staticmethod
    def extract_category_hint(taxonomy):
        """Estrae hint di categoria italiana dalla tassonomia BioCLIP.

        Input: lista 7 livelli [kingdom, phylum, class, order, family, genus, species_epithet]
        Output: stringa italiana (es. "uccello", "mammifero") oppure None
        """
        if not taxonomy or not isinstance(taxonomy, list) or len(taxonomy) < 3:
            return None

        taxon_class = taxonomy[2]  # indice 2 = class
        if not taxon_class:
            return None

        return EmbeddingGenerator.TAXONOMY_CLASS_HINTS.get(taxon_class)

    # ===== LLM VISION METHODS =====

    def _prepare_llm_image(self, image_input) -> Optional[str]:
        """Prepara immagine per LLM: estrae thumbnail, converte in base64.
        Usa cache interna per evitare elaborazioni ripetute sulla stessa immagine."""
        import base64

        input_type = self._detect_input_type(image_input)

        # Chiave cache: path stringa o id oggetto PIL
        if input_type == 'path':
            cache_key = str(image_input)
        elif input_type == 'pil':
            cache_key = id(image_input)
        else:
            logger.error("LLM Vision: tipo input non supportato")
            return None

        # Se già in cache, ritorna base64 cachato
        if self._llm_image_cache['source'] == cache_key:
            return self._llm_image_cache['base64']

        # Pulisci cache precedente
        self._cleanup_llm_image_cache()

        temp_path = None
        try:
            if input_type == 'path':
                from raw_processor import RAWProcessor
                raw_processor = RAWProcessor(self.config)
                # Leggi target_size dal profilo llm_vision
                llm_profile = self.optimization_profiles.get('llm_vision', {})
                llm_target_size = llm_profile.get('target_size', 512)
                thumbnail = raw_processor.extract_thumbnail(Path(image_input), target_size=llm_target_size)
                if thumbnail:
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                        thumbnail.save(tmp.name, format='JPEG', quality=90)
                        temp_path = tmp.name
                else:
                    temp_path = str(image_input)
            elif input_type == 'pil':
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    image_input.save(tmp.name, format='JPEG', quality=85)
                    temp_path = tmp.name

            # Leggi e converti in base64
            with open(temp_path, 'rb') as f:
                image_b64 = base64.b64encode(f.read()).decode('utf-8')

            # Salva in cache
            self._llm_image_cache = {
                'source': cache_key,
                'base64': image_b64,
                'temp_path': temp_path if temp_path != str(image_input) else None
            }
            return image_b64

        except Exception as e:
            logger.error(f"Errore preparazione immagine LLM: {e}")
            if temp_path and temp_path != str(image_input):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            return None

    def _cleanup_llm_image_cache(self):
        """Pulisce il file temporaneo della cache immagine LLM."""
        if self._llm_image_cache['temp_path']:
            try:
                os.unlink(self._llm_image_cache['temp_path'])
            except OSError:
                pass
        self._llm_image_cache = {'source': None, 'base64': None, 'temp_path': None}

    def generate_llm_description(self, image_input, max_description_words: int = 100, bioclip_context: Optional[str] = None, category_hint: Optional[str] = None):
        """Genera descrizione LLM Vision.
        Usa category_hint nel prompt per guidare il modello, prepende nome latino da BioCLIP.
        """
        try:
            image_b64 = self._prepare_llm_image(image_input)
            if not image_b64:
                return None

            # Genera in IT con hint di categoria nel prompt
            response = self._call_ollama_vision_api(image_b64, mode='description', max_description_words=max_description_words, category_hint=category_hint)

            # Prependi nome latino da BioCLIP
            if bioclip_context and response:
                latin_name = bioclip_context.split('(')[0].split(',')[0].strip()
                if latin_name:
                    response = f"{latin_name}: {response}"

            return response

        except Exception as e:
            logger.error(f"Errore LLM description: {e}")
            return None

    def generate_llm_tags(self, image_input, max_tags: int = 10, bioclip_context: Optional[str] = None, category_hint: Optional[str] = None) -> List[str]:
        """Genera tag LLM Vision.
        Usa category_hint nel prompt per guidare il modello, aggiunge nome latino da BioCLIP.
        """
        try:
            image_b64 = self._prepare_llm_image(image_input)
            if not image_b64:
                return []

            # Genera in IT con hint di categoria nel prompt
            response = self._call_ollama_vision_api(image_b64, mode='tags', max_tags=max_tags, category_hint=category_hint)
            if response:
                tags = self._parse_llm_tags_response(response, max_tags)

                # Aggiungi nome latino da BioCLIP come primo tag
                if bioclip_context:
                    latin_name = bioclip_context.split('(')[0].split(',')[0].strip()
                    if latin_name:
                        tags = [latin_name] + [t for t in tags if t.lower() != latin_name.lower()]

                return tags[:max_tags]
            return []

        except Exception as e:
            logger.error(f"Errore LLM tags: {e}")
            return []

    def generate_llm_title(self, image_input, max_title_words: int = 5, bioclip_context: Optional[str] = None, category_hint: Optional[str] = None) -> Optional[str]:
        """Genera titolo LLM Vision.
        Usa category_hint nel prompt per guidare il modello, prepende nome latino da BioCLIP.
        """
        try:
            image_b64 = self._prepare_llm_image(image_input)
            if not image_b64:
                return None

            # Genera in IT con hint di categoria nel prompt
            response = self._call_ollama_vision_api(image_b64, mode='title', max_title_words=max_title_words, category_hint=category_hint)
            if response:
                title = response.strip().strip('"').strip("'").rstrip('.').rstrip(',').strip()

                # Prependi nome latino da BioCLIP
                if bioclip_context and title:
                    latin_name = bioclip_context.split('(')[0].split(',')[0].strip()
                    if latin_name:
                        title = f"{latin_name} - {title}"

                return title
            return None

        except Exception as e:
            logger.error(f"Errore LLM title: {e}")
            return None

    def generate_llm_content(self, image_input, mode='description', max_tags: int = 10, max_description_words: int = 100, max_title_words: int = 5, bioclip_context: Optional[str] = None, category_hint: Optional[str] = None):
        """Metodo unificato per contenuti LLM con parametri completi.

        Modes supportati:
        - 'description': solo descrizione
        - 'tags': solo tag
        - 'title': solo titolo
        - 'tags_and_description': tag + descrizione
        - 'all': tag + descrizione + titolo

        category_hint: hint italiano dalla classe tassonomica BioCLIP (es. "uccello")
        bioclip_context: nome latino per prepend programmatico
        """
        import logging
        logger = logging.getLogger(__name__)
        result = {}

        try:
            if mode in ['description', 'tags_and_description', 'all']:
                description = self.generate_llm_description(image_input, max_description_words, bioclip_context=bioclip_context, category_hint=category_hint)
                if description:
                    result['description'] = description

            if mode in ['tags', 'tags_and_description', 'all']:
                tags = self.generate_llm_tags(image_input, max_tags, bioclip_context=bioclip_context, category_hint=category_hint)
                if tags:
                    result['tags'] = tags

            if mode in ['title', 'all']:
                title = self.generate_llm_title(image_input, max_title_words, bioclip_context=bioclip_context, category_hint=category_hint)
                if title:
                    result['title'] = title

            return result if result else None

        except Exception as e:
            logger.error(f"Errore LLM content generation: {e}")
            return None

    def _call_ollama_vision_api(self, image_data_b64: str, mode: str, max_tags: int = 10, max_description_words: int = 100, max_title_words: int = 5, category_hint: Optional[str] = None) -> Optional[str]:
        """Chiama API Ollama Vision (Qwen3-VL) e ritorna SOLO il contenuto finale.

        Args:
            image_data_b64: immagine già codificata in base64
            mode: 'title', 'tags', 'description'
        Genera sempre in ITALIANO con termini generici.
        """
        try:
            import requests

            llm_config = self.embedding_config.get('models', {}).get('llm_vision', {})

            endpoint = llm_config.get('endpoint', 'http://localhost:11434')
            model = llm_config.get('model', 'qwen3-vl:4b-instruct')
            timeout = llm_config.get('timeout', 180)
            # Calcolo num_predict: ~3 token/tag, ~1.3 token/parola + margine
            if mode == "description":
                max_tokens = int(max_description_words * 1.5) + 20
            elif mode == "tags":
                # ~3 token per tag (parola + virgola + spazio)
                max_tokens = (max_tags * 3) + 10
            elif mode == "title":
                max_tokens = int(max_title_words * 2) + 10
            else:
                max_tokens = int(max_description_words * 1.3) + (max_tags * 2) + 20

            generation = llm_config.get('generation', {})
            temperature = generation.get('temperature', 0.7)
            top_p = generation.get('top_p', 0.8)
            top_k = generation.get('top_k', 20)
            min_p = generation.get('min_p', 0.0)
            num_ctx = generation.get('num_ctx', 2048)
            num_batch = generation.get('num_batch', 1024)

            # Genera sempre in italiano, identifica specie solo se sicuro
            # Se abbiamo un hint di categoria da BioCLIP, lo usiamo per guidare il modello
            category_line = ""
            if category_hint:
                category_line = f"- IMPORTANT: The main subject is a type of: {category_hint}. Use this as context.\n"

            italian_rules = (
                "LANGUAGE: ALL output MUST be in ITALIAN. NEVER use English words.\n"
                "ANIMAL/PLANT IDENTIFICATION:\n"
                f"{category_line}"
                "- If you clearly recognize the species, use its common Italian name (e.g. cervo, delfino, girasole)\n"
                "- If you are NOT sure, use a generic Italian term (uccello, animale, fiore, albero, pesce)\n"
                "- NEVER guess a species name. A generic term is ALWAYS better than a wrong name\n"
                "- Do NOT use scientific/Latin names\n"
            )

            if mode == "description":
                prompt = (
                    "You are a professional photography captioning system.\n"
                    "Task: describe the image.\n\n"
                    f"{italian_rules}"
                    "\nSTRICT RULES:\n"
                    "- Output ONLY the description text, nothing else\n"
                    "- Include: subject, environment, colors, composition, atmosphere\n"
                    f"- Concise, informative, max {max_description_words} words\n"
                )
            elif mode == "tags":
                prompt = (
                    "You are a professional photographic tagging system.\n"
                    "Task: observe the scene and generate photo tags, in format \"tag1,tag2,tag3\".\n"
                    "Priority: 1) subjects, 2) scene, 3) actions, 4) objects, 5) weather, 6) mood, 7) colors\n\n"
                    f"{italian_rules}"
                    "\nSTRICT RULES:\n"
                    f"- Maximum {max_tags} tags\n"
                    "- lowercase, singular form\n"
                    "- Only tag what you clearly see in the image\n"
                )
            elif mode == "title":
                prompt = (
                    "You are a professional photo archiving system.\n"
                    "Task: generate a factual, descriptive title for this photo.\n\n"
                    f"{italian_rules}"
                    "\nSTRICT RULES:\n"
                    "- Output ONLY the title text, nothing else\n"
                    "- NO quotes, NO punctuation at the end\n"
                    f"- Maximum {max_title_words} words\n"
                    "- Be DESCRIPTIVE, not poetic or creative\n"
                    "- Focus on: main subject, location type, action (if any)\n"
                    "- For animals/plants: prefer generic terms if unsure (e.g. 'Uccello bianco' not a wrong species)\n"
                )
            else:
                logger.error(f"Modalità non supportata: {mode}")
                return None

            # Soft switch Qwen3: disabilita thinking a livello di chat template
            # (complementare a "think": False nel payload API)
            prompt = "/no_think\n" + prompt

            # --- Payload Ollama ---
            keep_alive = generation.get('keep_alive', -1)
            payload = {
                "model": model,
                "prompt": prompt,
                "images": [image_data_b64],
                "stream": False,
                "think": False,
                "keep_alive": keep_alive,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "min_p": min_p,
                    "num_ctx": num_ctx,
                    "num_batch": num_batch,
                }
            }

            response = requests.post(
                f"{endpoint}/api/generate",
                json=payload,
                timeout=timeout
            )

            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                return None

            result = response.json()
            final_response = result.get("response", "").strip()

            # Rimuovi blocchi <think>...</think> da modelli qwen3
            final_response = self._strip_think_blocks(final_response)

            return final_response

        except Exception as e:
            logger.error(f"Errore chiamata Ollama Vision: {e}")
            return None

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        """Rimuovi blocchi <think>...</think> dalla risposta LLM (qwen3)."""
        import re
        if '<think>' in text:
            cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            if cleaned:
                return cleaned
            # Se dopo la rimozione non resta nulla, potrebbe essere un blocco non chiuso
            if '</think>' not in text:
                # Blocco <think> non chiuso: prendi tutto dopo <think>
                # (il modello ha usato tutti i token per il thinking)
                return ''
        return text


    def _parse_llm_tags_response(self, response: str, max_tags: int = 10) -> List[str]:
        """Parse risposta LLM per estrarre tag puliti"""
        try:
            # Pulisci e splitta
            tags = []
            
            # Rimuovi caratteri comuni
            response = response.replace('\n', ' ').replace('-', ' ').strip()
            
            # Splitta per virgole o punti e virgola
            raw_tags = [t.strip() for t in response.replace(';', ',').split(',')]
            
            for tag in raw_tags:
                # Pulisci tag singolo
                clean_tag = tag.strip().strip('"').strip("'").strip()
                
                # Filtra tag validi
                if (clean_tag and 
                    len(clean_tag) > 2 and 
                    len(clean_tag) < 50 and
                    not clean_tag.startswith(('http', 'www'))):
                    tags.append(clean_tag)
            
            return tags[:max_tags]
            
        except Exception as e:
            logger.error(f"Errore parse LLM tags: {e}")
            return []

    # ===== PROCESSING BATCH COMPLETO =====

    def process_image_complete(self, image_input, processing_config: Dict) -> Dict:
        """Processing completo immagine con tutti i modelli richiesti"""
        result = {
            'embedding_generated': False,
            'llm_generated': False,
            'bioclip_generated': False,
            'clip_embedding': None,
            'dinov2_embedding': None,
            'aesthetic_score': None,
            'technical_score': None,
            'bioclip_tags': [],
            'llm_description': None,
            'llm_tags': []
        }
        
        try:
            # Embedding standard (sempre se abilitati)
            embeddings = self.generate_embeddings(image_input)
            result.update(embeddings)
            result['embedding_generated'] = any([
                embeddings.get('clip_embedding') is not None,
                embeddings.get('dinov2_embedding') is not None
            ])
            
            # BioCLIP on-demand
            if processing_config.get('bioclip_enabled', False):
                bioclip_tags, bioclip_taxonomy = self.generate_bioclip_tags(image_input)
                result['bioclip_tags'] = bioclip_tags
                result['bioclip_taxonomy'] = bioclip_taxonomy
                result['bioclip_generated'] = len(bioclip_tags) > 0
            
            # LLM Vision on-demand
            llm_config = processing_config.get('llm_vision', {})
            if llm_config.get('enabled', False):
                mode = llm_config.get('mode', 'description')
                
                if mode in ['description', 'both']:
                    llm_description = self.generate_llm_description(image_input)
                    result['llm_description'] = llm_description
                    
                if mode in ['tags', 'both']:
                    llm_tags = self.generate_llm_tags(image_input)
                    result['llm_tags'] = llm_tags
                
                result['llm_generated'] = bool(result.get('llm_description') or result.get('llm_tags'))
            
            return result
            
        except Exception as e:
            logger.error(f"Errore processing completo: {e}")
            return result