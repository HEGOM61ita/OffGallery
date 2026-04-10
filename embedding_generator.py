"""
Embedding Generator - Generazione embedding per ricerca semantica e similarita
Modelli: CLIP (semantica), DINOv2 (visiva), Aesthetic, MUSIQ (qualità tecnica), BioCLIP (natura)
LLM: Qwen2-VL via Ollama per descrizioni e tag AI

"""

import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import warnings
import os

from utils.paths import get_app_dir
from utils.tag_utils import normalize_tags

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
        self.musiq_model = None
        self.musiq_available = False
        self.musiq_device = 'cpu'  # MUSIQ gira su CPU di default (leggero, 0.28s/foto)
        self.bioclip_classifier = None
        self.bioclip_on_cpu = False

        # Cache immagine LLM: evita estrazione/base64 ripetute per la stessa immagine
        self._llm_image_cache = {'source': None, 'base64': None, 'temp_path': None}

        # Contatore foto elaborate senza GPS (GeoSpecies non attivo)
        self.geospecies_skipped_no_gps = 0

        # Buffer messaggi di avvio — accumulati durante __init__ prima che la tab esista.
        # La tab li scarica nell'area log al momento della sua creazione.
        self.startup_log: list[tuple[str, str]] = []  # lista di (messaggio, livello)

        # Device per-modello (allocazione da config o auto-detect)
        from device_allocator import detect_hardware, resolve_device, MODEL_VRAM_ESTIMATES
        self._hardware = detect_hardware()
        self._hw_backend = self._hardware['backend']
        self._model_devices = {}  # cache device risolti per modello

        # Avviso VRAM: controlla se la somma dei modelli configurati su GPU
        # supera la VRAM disponibile (solo CUDA/DirectML — MPS è unified memory).
        if self._hw_backend in ('cuda', 'directml'):
            vram_total = self._hardware.get('vram_total_gb') or 0.0
            if vram_total > 0:
                models_cfg = self.embedding_config.get('models', {})
                gpu_vram_requested = sum(
                    MODEL_VRAM_ESTIMATES.get(key, 0)
                    for key, cfg in models_cfg.items()
                    if isinstance(cfg, dict) and cfg.get('device', 'gpu') == 'gpu'
                    and key in MODEL_VRAM_ESTIMATES
                )
                if gpu_vram_requested > vram_total * 0.90:
                    msg = (
                        f"⚠️ VRAM: i modelli configurati su GPU richiedono ~{gpu_vram_requested:.1f} GB "
                        f"ma la GPU ha {vram_total:.1f} GB (soglia 90% = {vram_total*0.90:.1f} GB). "
                        f"Alcuni modelli potrebbero fallire o scalare su CPU automaticamente."
                    )
                    logger.warning(msg)
                    self.startup_log.append((msg, 'warning'))

        # CARICAMENTO PROFILI OTTIMIZZAZIONE DA CONFIG
        self.optimization_profiles = self._load_optimization_profiles()

        # Traduttore query → EN (per CLIP)
        self.translator = None
        if self.embedding_config.get('translation', {}).get('enabled', True):
            self._init_translator()

        # Traduttore EN → lingua contenuti (per ricerca tag)
        self._tag_lang = self.config.get('ui', {}).get('llm_output_language', 'it')
        self._tag_translator_ready = False
        self._init_tag_translator()

        # Plugin LLM Vision (Ollama / LM Studio / altro)
        self.llm_plugin = None
        self._init_llm_plugin()

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
        # Il plugin viene già inizializzato in __init__ tramite _init_llm_plugin()
        logger.info("Modalità LLM only - nessun modello AI caricato")

    def _init_llm_plugin(self):
        """Carica il plugin LLM attivo dalla directory /plugins/.

        Delegato interamente al loader: nessuna logica backend-specifica qui.
        Se nessun backend è disponibile, self.llm_plugin rimane None e la
        generazione tag/descrizione/titolo viene saltata con warning.
        """
        try:
            import sys
            from utils.paths import get_app_dir
            _plugins_dir = str(get_app_dir() / 'plugins')
            if _plugins_dir not in sys.path:
                sys.path.insert(0, _plugins_dir)
            from plugins.loader import load_plugin
            self.llm_plugin = load_plugin(self.config)
            if self.llm_plugin:
                logger.debug(f"Plugin LLM caricato: {type(self.llm_plugin).__name__}")
        except Exception as e:
            logger.debug(f"Plugin LLM non disponibile: {e}")
            self.llm_plugin = None

    def _init_bioclip_only(self):
        """Inizializza solo BioCLIP"""
        models_config = self.embedding_config.get('models', {})
        if models_config.get('bioclip', {}).get('enabled', False):
            self._init_bioclip()
            self.bioclip_enabled = hasattr(self, 'bioclip_classifier') and self.bioclip_classifier is not   None
    
    def warmup_llm(self):
        """Pre-carica il modello LLM in VRAM tramite il plugin attivo."""
        if self.llm_plugin:
            self.llm_plugin.warmup()
        else:
            logger.warning("⚠️ Nessun plugin LLM disponibile — warmup saltato")


    def _device_for(self, model_key: str) -> str:
        """Restituisce device torch per un modello specifico (con cache)."""
        if model_key not in self._model_devices:
            from device_allocator import resolve_device
            device = resolve_device(model_key, self.config, self._hw_backend)
            self._model_devices[model_key] = device
            logger.info(f"📍 {model_key.upper()} → device: {device}")
        return self._model_devices[model_key]


    def _load_optimization_profiles(self) -> Dict:
        """
        Carica profili di ottimizzazione da config.
        Ogni profilo definisce: target_size, method, resampling, quality
        """
        from PIL import Image

        config_profiles = self.config.get('image_optimization', {}).get('profiles', {})

        # Profili di default (fallback)
        default_profiles = {
            'clip_embedding': {'target_size': 224, 'resampling': Image.Resampling.LANCZOS},  # ViT-L/14 input 224x224
            'dinov2_embedding': {'target_size': 518, 'resampling': Image.Resampling.LANCZOS},  # DINOv2 input 518x518 (14x37)
            'bioclip_classification': {'target_size': 224, 'resampling': Image.Resampling.LANCZOS},  # ViT-B/16 input 224x224
            'aesthetic_score': {'target_size': 224, 'resampling': Image.Resampling.BILINEAR},  # CLIP-based input 224x224
            'technical_score': {'target_size': 1024, 'resampling': Image.Resampling.LANCZOS},  # MUSIQ a 1024px
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
            # Cattura FileNotFoundError: argostranslate crasha se trova sottodirectory
            # prive di metadata.json (installazione parziale/corrotta)
            try:
                installed = argostranslate.package.get_installed_packages()
            except Exception as e:
                logger.warning(f"Argos: directory pacchetti corrotta ({e}) - pulizia in corso...")
                # Rimuovi sottodirectory senza metadata.json (installazioni incomplete)
                import shutil
                argos_pkg_dir = Path.home() / '.local' / 'share' / 'argos-translate' / 'packages'
                if argos_pkg_dir.exists():
                    for sub in argos_pkg_dir.iterdir():
                        if sub.is_dir() and not (sub / 'metadata.json').exists():
                            shutil.rmtree(str(sub), ignore_errors=True)
                            logger.info(f"Argos: rimossa directory corrotta: {sub.name}")
                try:
                    installed = argostranslate.package.get_installed_packages()
                except Exception:
                    installed = []
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

    def _init_tag_translator(self):
        """Verifica/installa pacchetto Argos EN→lingua_contenuti per ricerca tag.
        Chiamato a startup: stesso pattern di _init_translator, nessun side effect a runtime."""
        if self._tag_lang == 'en':
            # I tag sono in inglese: nessuna traduzione necessaria
            self._tag_translator_ready = True
            return

        try:
            import argostranslate.package
            import argostranslate.translate
            import logging
            logging.getLogger('argostranslate.utils').setLevel(logging.WARNING)

            # Verifica se il pacchetto EN→X è già installato
            try:
                installed = argostranslate.package.get_installed_packages()
            except Exception:
                installed = []

            has_pkg = any(
                p.from_code == 'en' and p.to_code == self._tag_lang
                for p in installed
            )

            if has_pkg:
                self._tag_translator_ready = True
                logger.info(f"[OK] Traduttore EN→{self._tag_lang} disponibile per ricerca tag")
                return

            # Pacchetto non installato: tenta download dall'indice ufficiale Argos
            logger.warning(
                f"⚠️ Pacchetto traduzione EN→{self._tag_lang} non installato. "
                f"Tentativo download in corso..."
            )
            try:
                argostranslate.package.update_package_index()
                available = argostranslate.package.get_available_packages()
                pkg = next(
                    (p for p in available
                     if p.from_code == 'en' and p.to_code == self._tag_lang),
                    None
                )
                if pkg:
                    download_path = pkg.download()
                    argostranslate.package.install_from_path(download_path)
                    self._tag_translator_ready = True
                    logger.info(f"[OK] Pacchetto EN→{self._tag_lang} installato — ricerca tag attiva")
                else:
                    logger.warning(
                        f"⚠️ Pacchetto EN→{self._tag_lang} non trovato nell'indice Argos. "
                        f"La ricerca tag userà la query in inglese (risultati parziali possibili)."
                    )
            except Exception as e:
                logger.warning(
                    f"⚠️ Download EN→{self._tag_lang} fallito ({e}). "
                    f"La ricerca tag userà la query in inglese (risultati parziali possibili)."
                )

        except ImportError:
            logger.warning("Argostranslate non disponibile — ricerca tag senza traduzione")

    def _translate_to_tag_language(self, text_en: str) -> str:
        """Traduce la query EN nella lingua dei contenuti per il matching tag.
        Ritorna il testo originale se la traduzione non è disponibile."""
        if self._tag_lang == 'en' or not self._tag_translator_ready:
            return text_en
        try:
            import argostranslate.translate
            result = argostranslate.translate.translate(text_en, 'en', self._tag_lang)
            logger.debug(f"Tag query: '{text_en}' → '{result}' ({self._tag_lang})")
            return result
        except Exception as e:
            logger.debug(f"Traduzione EN→{self._tag_lang} fallita: {e}")
            return text_en

    def _get_models_dir(self) -> Path:
        """Restituisce il percorso assoluto della directory modelli dal config."""
        rel = self.config.get('models_repository', {}).get('models_dir', 'Models')
        p = Path(rel)
        return p if p.is_absolute() else get_app_dir() / p

    def _initialize_models(self):
        """Inizializza modelli abilitati.
        Tutti i messaggi logger emessi durante l'init vengono anche accumulati
        in self.startup_log, così la tab li mostra all'apertura.
        """
        import logging as _logging

        class _StartupLogHandler(_logging.Handler):
            def __init__(self, buf):
                super().__init__()
                self._buf = buf
            def emit(self, record):
                level = 'warning' if record.levelno >= _logging.WARNING else 'info'
                self._buf.append((record.getMessage(), level))

        _handler = _StartupLogHandler(self.startup_log)
        _handler.setLevel(_logging.DEBUG)
        logger.addHandler(_handler)

        try:
            models_config = self.embedding_config.get('models', {})
            if models_config.get('clip', {}).get('enabled', False):
                self._init_clip()
            if models_config.get('dinov2', {}).get('enabled', False):
                self._init_dinov2()
            if models_config.get('aesthetic', {}).get('enabled', False):
                self._init_aesthetic()
            # MUSIQ/Technical: valutazione qualità tecnica
            if models_config.get('technical', {}).get('enabled', False):
                self._init_musiq()
            if models_config.get('bioclip', {}).get('enabled', False):
                self._init_bioclip()
                self.bioclip_enabled = hasattr(self, 'bioclip_classifier') and self.bioclip_classifier is not None
        finally:
            logger.removeHandler(_handler)

    def _init_clip(self):
        """Inizializza CLIP: prima da models_dir locale, poi repo congelato (hf_hub_download), poi fallback ufficiale (snapshot_download)"""
        try:
            from transformers import CLIPProcessor, CLIPModel

            models_dir = self._get_models_dir()
            clip_subfolder = self.config.get('models_repository', {}).get('models', {}).get('clip', 'clip')
            clip_local = models_dir / clip_subfolder
            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')
            fallback_model = self.embedding_config.get('models', {}).get('clip', {}).get('model_name', 'laion/CLIP-ViT-B-32-laion2B-s34B-b79K')

            loaded = False

            # 1. Cartella locale (models_dir/clip/)
            if clip_local.exists() and (clip_local / 'config.json').exists():
                try:
                    self.clip_model = CLIPModel.from_pretrained(str(clip_local)).to(self._device_for('clip'))
                    self.clip_processor = CLIPProcessor.from_pretrained(str(clip_local))
                    loaded = True
                    logger.info("[OK] CLIP caricato da locale")
                except Exception as e:
                    logger.warning(f"CLIP: cartella locale non valida ({e}), uso repo...")

            # 2. Repo congelato: copia file per file come BioCLIP (evita save_pretrained)
            if not loaded and frozen_repo:
                try:
                    from huggingface_hub import hf_hub_download
                    import shutil as _shutil

                    clip_local.mkdir(parents=True, exist_ok=True)
                    _clip_files = [
                        'config.json', 'model.safetensors', 'preprocessor_config.json',
                        'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json',
                        'vocab.json', 'merges.txt'
                    ]
                    for _fname in _clip_files:
                        try:
                            _dl = hf_hub_download(
                                repo_id=frozen_repo,
                                filename=f"{clip_subfolder}/{_fname}",
                                repo_type="model"
                            )
                            _shutil.copy2(_dl, clip_local / _fname)
                        except Exception:
                            pass  # file opzionale o non presente

                    if (clip_local / 'config.json').exists() and (clip_local / 'model.safetensors').exists():
                        self.clip_model = CLIPModel.from_pretrained(str(clip_local)).to(self._device_for('clip'))
                        self.clip_processor = CLIPProcessor.from_pretrained(str(clip_local))
                        loaded = True
                        logger.info("[OK] CLIP caricato da repo")
                    else:
                        logger.warning("CLIP: repo congelato incompleto, uso fallback...")
                except Exception as e:
                    logger.warning(f"CLIP: repo congelato non disponibile ({e}), uso fallback...")

            # 3. Fallback repo ufficiale: snapshot_download diretto in Models/clip/ (evita save_pretrained)
            if not loaded:
                try:
                    from huggingface_hub import snapshot_download
                    clip_local.mkdir(parents=True, exist_ok=True)
                    snapshot_download(
                        repo_id=fallback_model,
                        local_dir=str(clip_local),
                        local_dir_use_symlinks=False,
                        ignore_patterns=['*.msgpack', '*.h5', 'rust_model.ot', 'tf_model.h5', 'flax_model.msgpack']
                    )
                    self.clip_model = CLIPModel.from_pretrained(str(clip_local)).to(self._device_for('clip'))
                    self.clip_processor = CLIPProcessor.from_pretrained(str(clip_local))
                    logger.info(f"[OK] CLIP caricato e salvato (fallback: {fallback_model})")
                    loaded = True
                except Exception as fe:
                    logger.error(f"CLIP: snapshot_download fallito ({fe}), provo from_pretrained in memoria...")
                    self.clip_model = CLIPModel.from_pretrained(fallback_model).to(self._device_for('clip'))
                    self.clip_processor = CLIPProcessor.from_pretrained(fallback_model)
                    logger.info(f"[OK] CLIP caricato in memoria senza persistenza (fallback: {fallback_model})")
                    loaded = True

            self.clip_model.eval()
            self.clip_enabled = True
            # Log versione transformers per diagnostica compatibilità embedding
            try:
                import transformers as _tf
                logger.info(f"CLIP caricato con transformers=={_tf.__version__}")
            except Exception:
                pass
            # Log diagnostico: mostra architettura effettiva del modello caricato
            try:
                _vcfg = self.clip_model.vision_model.config
                _proj  = self.clip_model.visual_projection.weight.shape  # (projection_dim, hidden_size)
                logger.info(
                    f"CLIP architettura — hidden_size={_vcfg.hidden_size}, "
                    f"projection_dim={_proj[0]}, "
                    f"patch_size={getattr(_vcfg, 'patch_size', '?')}, "
                    f"num_hidden_layers={getattr(_vcfg, 'num_hidden_layers', '?')}"
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"CLIP: {e}")
            self.clip_enabled = False

    def _init_dinov2(self):
        """Inizializza DINOv2: prima da models_dir locale, poi repo congelato, poi fallback ufficiale"""
        try:
            from transformers import AutoImageProcessor, AutoModel

            models_dir = self._get_models_dir()
            dinov2_subfolder = self.config.get('models_repository', {}).get('models', {}).get('dinov2', 'dinov2')
            dinov2_local = models_dir / dinov2_subfolder
            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')
            fallback_model = self.embedding_config.get('models', {}).get('dinov2', {}).get('model_name', 'facebook/dinov2-base')

            loaded = False

            # 1. Cartella locale (models_dir/dinov2/)
            if dinov2_local.exists() and (dinov2_local / 'config.json').exists():
                try:
                    self.dinov2_model = AutoModel.from_pretrained(str(dinov2_local)).to(self._device_for('dinov2'))
                    self.dinov2_processor = AutoImageProcessor.from_pretrained(str(dinov2_local))
                    loaded = True
                    logger.info("[OK] DINOv2 caricato da locale")
                except Exception as e:
                    logger.warning(f"DINOv2: cartella locale non valida ({e}), uso repo...")

            # 2. Repo congelato: copia file per file (evita save_pretrained che fallisce su CUDA)
            if not loaded and frozen_repo:
                try:
                    from huggingface_hub import hf_hub_download
                    import shutil as _shutil

                    dinov2_local.mkdir(parents=True, exist_ok=True)
                    _dinov2_files = [
                        'config.json', 'model.safetensors', 'preprocessor_config.json'
                    ]
                    for _fname in _dinov2_files:
                        try:
                            _dl = hf_hub_download(
                                repo_id=frozen_repo,
                                filename=f"{dinov2_subfolder}/{_fname}",
                                repo_type="model"
                            )
                            _shutil.copy2(_dl, dinov2_local / _fname)
                        except Exception:
                            pass  # file opzionale o non presente

                    if (dinov2_local / 'config.json').exists() and (dinov2_local / 'model.safetensors').exists():
                        self.dinov2_model = AutoModel.from_pretrained(str(dinov2_local)).to(self._device_for('dinov2'))
                        self.dinov2_processor = AutoImageProcessor.from_pretrained(str(dinov2_local))
                        loaded = True
                        logger.info("[OK] DINOv2 caricato da repo")
                    else:
                        logger.warning("DINOv2: repo congelato incompleto, uso fallback...")
                except Exception as e:
                    logger.warning(f"DINOv2: repo congelato non disponibile ({e}), uso fallback...")

            # 3. Fallback repo ufficiale: snapshot_download diretto in Models/dinov2/
            if not loaded:
                try:
                    from huggingface_hub import snapshot_download
                    dinov2_local.mkdir(parents=True, exist_ok=True)
                    snapshot_download(
                        repo_id=fallback_model,
                        local_dir=str(dinov2_local),
                        local_dir_use_symlinks=False,
                        ignore_patterns=['*.msgpack', '*.h5', 'rust_model.ot', 'tf_model.h5', 'flax_model.msgpack']
                    )
                    self.dinov2_model = AutoModel.from_pretrained(str(dinov2_local)).to(self._device_for('dinov2'))
                    self.dinov2_processor = AutoImageProcessor.from_pretrained(str(dinov2_local))
                    logger.info(f"[OK] DINOv2 caricato e salvato (fallback: {fallback_model})")
                    loaded = True
                except Exception as fe:
                    logger.error(f"DINOv2: snapshot_download fallito ({fe}), provo from_pretrained in memoria...")
                    self.dinov2_model = AutoModel.from_pretrained(fallback_model).to(self._device_for('dinov2'))
                    self.dinov2_processor = AutoImageProcessor.from_pretrained(fallback_model)
                    logger.info(f"[OK] DINOv2 caricato in memoria senza persistenza (fallback: {fallback_model})")
                    loaded = True

            self.dinov2_model.eval()
            self.dinov2_enabled = True
        except Exception as e:
            logger.error(f"DINOv2: {e}")
            self.dinov2_enabled = False

    def _init_aesthetic(self):
        """Inizializza Aesthetic Score: prima da models_dir locale, poi repo congelato (hf_hub_download), poi fallback ufficiale (snapshot_download)"""
        try:
            from transformers import CLIPProcessor, CLIPModel
            import torch
            import torch.nn as nn

            models_dir = self._get_models_dir()
            aesthetic_subfolder = self.config.get('models_repository', {}).get('models', {}).get('aesthetic', 'aesthetic')
            aesthetic_dir = models_dir / aesthetic_subfolder

            # Repo congelato e fallback
            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')
            fallback_model = 'openai/clip-vit-large-patch14'

            # Verifica se già presente in locale (accetta sia pytorch_model.bin che model.safetensors)
            local_exists = aesthetic_dir.exists() and (
                (aesthetic_dir / 'pytorch_model.bin').exists() or
                (aesthetic_dir / 'model.safetensors').exists()
            )

            clip_model = None

            # 1. Prova a caricare da directory locale (già scaricato)
            if local_exists:
                try:
                    clip_model = CLIPModel.from_pretrained(str(aesthetic_dir)).to(self._device_for('aesthetic'))
                    self.aesthetic_processor = CLIPProcessor.from_pretrained(str(aesthetic_dir))
                    logger.info("[OK] Aesthetic caricato da locale")
                except Exception as e:
                    logger.warning(f"Aesthetic: cartella locale non valida ({e}), uso repo...")
                    clip_model = None

            # 2. Repo congelato: copia file per file come CLIP (evita save_pretrained)
            if clip_model is None and frozen_repo:
                try:
                    from huggingface_hub import hf_hub_download
                    import shutil as _shutil

                    aesthetic_dir.mkdir(parents=True, exist_ok=True)
                    _aesthetic_files = [
                        'config.json', 'model.safetensors', 'preprocessor_config.json',
                        'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json',
                        'vocab.json', 'merges.txt'
                    ]
                    for _fname in _aesthetic_files:
                        try:
                            _dl = hf_hub_download(
                                repo_id=frozen_repo,
                                filename=f"{aesthetic_subfolder}/{_fname}",
                                repo_type="model"
                            )
                            _shutil.copy2(_dl, aesthetic_dir / _fname)
                        except Exception:
                            pass  # file opzionale o non presente

                    if (aesthetic_dir / 'config.json').exists() and (aesthetic_dir / 'model.safetensors').exists():
                        clip_model = CLIPModel.from_pretrained(str(aesthetic_dir)).to(self._device_for('aesthetic'))
                        self.aesthetic_processor = CLIPProcessor.from_pretrained(str(aesthetic_dir))
                        logger.info("[OK] Aesthetic caricato da repo")
                    else:
                        logger.warning("Aesthetic: repo congelato incompleto, uso fallback...")
                except Exception as e:
                    logger.error(f"Aesthetic: repo congelato fallito ({e}), uso fallback...")
                    clip_model = None

            # 3. Fallback repo ufficiale: snapshot_download diretto in Models/aesthetic/ (evita save_pretrained)
            if clip_model is None:
                try:
                    from huggingface_hub import snapshot_download
                    aesthetic_dir.mkdir(parents=True, exist_ok=True)
                    snapshot_download(
                        repo_id=fallback_model,
                        local_dir=str(aesthetic_dir),
                        local_dir_use_symlinks=False,
                        ignore_patterns=['*.msgpack', '*.h5', 'rust_model.ot', 'tf_model.h5', 'flax_model.msgpack']
                    )
                    clip_model = CLIPModel.from_pretrained(str(aesthetic_dir)).to(self._device_for('aesthetic'))
                    self.aesthetic_processor = CLIPProcessor.from_pretrained(str(aesthetic_dir))
                    logger.info(f"[OK] Aesthetic caricato e salvato (fallback: {fallback_model})")
                except Exception as fe:
                    logger.error(f"Aesthetic: snapshot_download fallito ({fe}), provo from_pretrained in memoria...")
                    clip_model = CLIPModel.from_pretrained(fallback_model).to(self._device_for('aesthetic'))
                    self.aesthetic_processor = CLIPProcessor.from_pretrained(fallback_model)
                    logger.info(f"[OK] Aesthetic caricato in memoria senza persistenza (fallback: {fallback_model})")

            # Head per score estetico
            pooler_dim = clip_model.vision_model.config.hidden_size
            self.aesthetic_head = nn.Linear(pooler_dim, 1).to(self._device_for('aesthetic'))
            torch.nn.init.xavier_normal_(self.aesthetic_head.weight)
            torch.nn.init.constant_(self.aesthetic_head.bias, 0.0)

            self.aesthetic_model = clip_model.vision_model
            self.aesthetic_model.eval()
            self.aesthetic_head.eval()
            self.aesthetic_enabled = True

        except Exception as e:
            logger.error(f"Aesthetic: {e}")
            self.aesthetic_enabled = False

    def _init_musiq(self):
        """Inizializza MUSIQ per valutazione qualità tecnica.
        Priorità: locale Models/musiq/ → repo HF frozen → download pyiqa.
        Usa pyiqa per architettura, pesi dal repo congelato. Fallback CPU come BioCLIP."""
        try:
            import pyiqa
            import torch
            from pyiqa.archs.arch_util import load_pretrained_network

            _MUSIQ_WEIGHTS = 'musiq_koniq_ckpt-e95806b9.pth'
            models_dir = self._get_models_dir()
            musiq_local = models_dir / 'musiq'
            local_weights = musiq_local / _MUSIQ_WEIGHTS
            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')

            # 1. Scarica pesi se non presenti in locale
            if not local_weights.exists():
                # Prova repo HF frozen
                if frozen_repo:
                    try:
                        from huggingface_hub import hf_hub_download
                        import shutil as _shutil

                        musiq_local.mkdir(parents=True, exist_ok=True)
                        _dl = hf_hub_download(
                            repo_id=frozen_repo,
                            filename=f"musiq/{_MUSIQ_WEIGHTS}",
                            repo_type="model"
                        )
                        _shutil.copy2(_dl, local_weights)
                        logger.info(f"MUSIQ: pesi scaricati da repo frozen → {local_weights}")
                    except Exception as e:
                        logger.warning(f"MUSIQ: repo frozen non disponibile ({e})")

            # 2. Crea modello e carica pesi
            musiq_device = self._device_for('technical')

            def _create_and_load(device):
                if local_weights.exists():
                    # Crea architettura senza scaricare pesi, poi carica da locale
                    model = pyiqa.create_metric('musiq', device=device, pretrained=False)
                    load_pretrained_network(model.net, str(local_weights), strict=True)
                    model.net = model.net.to(device)
                    logger.info(f"[OK] MUSIQ: caricato da locale su {device}")
                else:
                    # Fallback: lascia che pyiqa scarichi i pesi (primo avvio senza HF)
                    model = pyiqa.create_metric('musiq', device=device)
                    # Salva pesi in locale per avvii successivi
                    try:
                        musiq_local.mkdir(parents=True, exist_ok=True)
                        torch.save(model.net.state_dict(), local_weights)
                        logger.info(f"MUSIQ: pesi salvati in {local_weights}")
                    except Exception:
                        pass
                    logger.info(f"[OK] MUSIQ: caricato da pyiqa su {device}")
                return model

            try:
                self.musiq_model = _create_and_load(musiq_device)
                self.musiq_device = musiq_device

            except Exception as vram_err:
                # Fallback CPU per qualsiasi errore su GPU: OOM, CUDA error, VRAM satura.
                # Il catch precedente (solo RuntimeError + "out of memory") non intercettava
                # errori CUDA diversi (es. allocazione fallita con VRAM piena ma messaggio
                # diverso), lasciando MUSIQ rosso senza tentare CPU.
                if musiq_device != 'cpu':
                    logger.warning(
                        f"MUSIQ: errore su {musiq_device} "
                        f"({type(vram_err).__name__}: {str(vram_err)[:120]}), "
                        f"fallback CPU...")
                    self.musiq_model = _create_and_load('cpu')
                    self.musiq_device = 'cpu'
                else:
                    raise

            self.musiq_available = True

        except ImportError:
            logger.warning("MUSIQ: pyiqa non installato (pip install pyiqa)")
            self.musiq_available = False
        except Exception as e:
            import traceback
            logger.error(f"MUSIQ: errore inizializzazione: {e}\n{traceback.format_exc()}")
            self.musiq_available = False

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

            models_dir = self._get_models_dir()
            models_mapping = self.config.get('models_repository', {}).get('models', {})
            bioclip_subfolder = models_mapping.get('bioclip', 'bioclip')
            treeoflife_subfolder = models_mapping.get('treeoflife', 'treeoflife')
            bioclip_dir = models_dir / bioclip_subfolder
            treeoflife_dir = models_dir / treeoflife_subfolder

            frozen_repo = self.config.get('models_repository', {}).get('huggingface_repo', '')

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
                    # Determina device per BioCLIP (fallback CPU se VRAM insufficiente)
                    bioclip_device = self._device_for('bioclip')
                    try:
                        model, _, preprocess = open_clip.create_model_and_transforms(
                            model_name='ViT-L-14',
                            pretrained=str(bioclip_dir / 'open_clip_model.safetensors'),
                            device=bioclip_device
                        )
                    except RuntimeError as vram_err:
                        if 'not enough' in str(vram_err).lower() or 'out of memory' in str(vram_err).lower():
                            logger.warning(f"BioCLIP: VRAM insufficiente, caricamento su CPU...")
                            bioclip_device = 'cpu'
                            model, _, preprocess = open_clip.create_model_and_transforms(
                                model_name='ViT-L-14',
                                pretrained=str(bioclip_dir / 'open_clip_model.safetensors'),
                                device=bioclip_device
                            )
                        else:
                            raise

                    # Carica TreeOfLife embeddings
                    txt_emb = torch.from_numpy(
                        np.load(treeoflife_dir / 'txt_emb_species.npy')
                    ).to(bioclip_device)

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
                        model, preprocess, txt_emb, txt_names, bioclip_device
                    )
                    self.bioclip_on_cpu = (bioclip_device == 'cpu')
                    if self.bioclip_on_cpu:
                        logger.info("[OK] BioCLIP caricato (CPU — VRAM insufficiente per GPU)")
                    else:
                        logger.info("[OK] BioCLIP caricato")
                    return True

                except Exception as e:
                    logger.warning(f"BioCLIP: caricamento locale fallito ({e}), uso fallback...")

            # Fallback: TreeOfLifeClassifier standard (scarica da repo ufficiale)
            try:
                self.bioclip_classifier = TreeOfLifeClassifier(device=self._device_for('bioclip'))
                self.bioclip_on_cpu = False
                logger.info("[OK] BioCLIP caricato (fallback)")
                return True
            except RuntimeError as vram_err:
                if 'not enough' in str(vram_err).lower() or 'out of memory' in str(vram_err).lower():
                    logger.warning("BioCLIP fallback: VRAM insufficiente, caricamento su CPU...")
                    self.bioclip_classifier = TreeOfLifeClassifier(device='cpu')
                    self.bioclip_on_cpu = True
                    logger.info("[OK] BioCLIP caricato (fallback, CPU)")
                    return True
                raise

        except Exception as e:
            logger.error(f"BioCLIP: {e}")
            return False

    def test_models(self):
        """Testa disponibilità modelli"""
        return {
            'clip': getattr(self, 'clip_enabled', False),
            'dinov2': getattr(self, 'dinov2_enabled', False),
            'aesthetic': getattr(self, 'aesthetic_enabled', False),
            'musiq': self.musiq_available,
            'bioclip': self.bioclip_classifier is not None
        }

    def generate_embeddings(self, input_data, original_path=None):
        """
        Genera embedding distinguendo tra File (Immagine) e Stringa (Testo).
        Supporta tutti i formati immagine (JPG, RAW, ecc.) tramite os.path.exists.

        Args:
            input_data: PIL Image, path string, o testo per query
            original_path: Path originale del file (opzionale, legacy)
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
                inputs = self.clip_processor(text=[input_data], return_tensors="pt", padding=True).to(self._device_for('clip'))
                
                with torch.no_grad():
                    # Path manuale deterministico: bypassa get_text_features() per
                    # consistenza con il path immagine. Entrambi manuali = zero dipendenza
                    # dal comportamento specifico della versione transformers installata.
                    text_out = self.clip_model.text_model(
                        input_ids=inputs['input_ids'],
                        attention_mask=inputs.get('attention_mask')
                    )
                    text_features = self.clip_model.text_projection(text_out.pooler_output)

                # Normalizziamo come per le immagini (consistenza)
                text_emb = text_features.cpu().numpy().flatten()
                text_emb = (text_emb / np.linalg.norm(text_emb)).astype(np.float32)
                logger.debug(f"CLIP text embedding: shape={text_emb.shape}, norm={np.linalg.norm(text_emb):.4f}")

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

                # Technical score / MUSIQ (se abilitato)
                # MUSIQ lavora su PIL Image (thumbnail), funziona sia per RAW che JPG
                if getattr(self, 'musiq_available', False):
                    technical = self._generate_musiq_score(input_data)
                    result['technical_score'] = technical
                    if technical is not None:
                        logger.debug(f"Technical score MUSIQ: {technical}")

                # BioCLIP tags + tassonomia completa (se abilitato)
                if getattr(self, 'bioclip_enabled', False):
                    bioclip_tags, bioclip_taxonomy = self.generate_bioclip_tags(input_data)
                    result['bioclip_tags'] = bioclip_tags
                    result['bioclip_taxonomy'] = bioclip_taxonomy
                    if bioclip_tags:
                        logger.info(f"BioCLIP tags generati: {bioclip_tags}")
                    if bioclip_taxonomy:
                        logger.info(f"BioCLIP taxonomy: {bioclip_taxonomy}")

                # Pulizia memoria GPU dopo ogni foto.
                # Su Apple Silicon (MPS): libera il pool MPS per evitare di ingolfare
                # la unified memory durante sessioni di elaborazione lunghe.
                # Su CUDA e CPU: gc.collect() è comunque utile, il ramo MPS non esegue.
                import gc
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()
                gc.collect()

                return result
            except Exception as e:
                logger.error(f"Errore CLIP immagine: {e}")
                return None

    def _predict_bioclip(self, image_input, input_type, geo_hierarchy=None):
        """Esegue predizione BioCLIP usando configurazione da config.yaml.
        OTTIMIZZATO: Usa profilo 'bioclip_classification' per resize alla dimensione ottimale.

        Args:
            image_input: path file, PIL Image, o bytes
            input_type: 'path', 'pil', 'bytes'
            geo_hierarchy: stringa GeOFF|Continent|Country|Region|City opzionale —
                           se fornita e GeoSpecies è attivo con cache per quel paese,
                           usa un sottoinsieme geografico di specie invece dei 450k globali.
                           Nessuna chiamata API — solo cache locale.
        """
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
            # GeoSpecies: subset geografico specie
            # ─────────────────────────────────────
            # Solo cache locale — nessuna chiamata API durante elaborazione.
            # Se la cache per il paese non esiste, fallback silenzioso a TreeOfLife.
            active_classifier = self.bioclip_classifier
            self._last_geospecies_meta = None

            if not geo_hierarchy:
                self.geospecies_skipped_no_gps += 1

            if geo_hierarchy:
                try:
                    from plugins.geospecies.geospecies import get_species_subset
                    species_subset = get_species_subset(
                        lat=0, lon=0,  # non usati — paese da geo_hierarchy
                        geo_hierarchy=geo_hierarchy
                    )
                    if species_subset and len(species_subset) >= 10:
                        try:
                            from bioclip import CustomLabelsClassifier
                            geo_classifier = CustomLabelsClassifier(cls_ary=species_subset)
                            active_classifier = geo_classifier
                            self._last_geospecies_meta = {"species_count": len(species_subset)}
                            logger.debug(
                                f"GeoSpecies: classificatore geografico attivo "
                                f"({len(species_subset)} specie)"
                            )
                        except Exception as e:
                            logger.debug(f"GeoSpecies: CustomLabelsClassifier non disponibile ({e}), uso TreeOfLife")
                    else:
                        logger.debug(f"GeoSpecies: cache assente per {geo_hierarchy}, uso TreeOfLife")
                except ImportError:
                    pass  # Plugin GeoSpecies non installato
                except Exception as e:
                    logger.debug(f"GeoSpecies: errore ({e}), uso TreeOfLife standard")

            # ─────────────────────────────────────
            # Predizione BioCLIP
            # ─────────────────────────────────────
            predictions = active_classifier.predict(
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
            inputs = self.clip_processor(images=image, return_tensors="pt").to(self._device_for('clip'))
            with torch.no_grad():
                # Path manuale deterministico: bypassa get_image_features() che cambia
                # comportamento tra versioni di transformers (causa principale di score
                # vicini a zero). Usiamo direttamente vision_model → CLS → layernorm → projection.
                vision_out = self.clip_model.vision_model(pixel_values=inputs['pixel_values'])
                cls_token = vision_out.last_hidden_state[:, 0, :]  # CLS token raw: (1, hidden_size)
                if hasattr(self.clip_model.vision_model, 'post_layernorm'):
                    cls_token = self.clip_model.vision_model.post_layernorm(cls_token)
                features = self.clip_model.visual_projection(cls_token)
            embedding = features.cpu().numpy()[0]
            normalized = (embedding / np.linalg.norm(embedding)).astype(np.float32)
            logger.debug(f"CLIP embedding generato: shape={normalized.shape}, norm={np.linalg.norm(normalized):.4f}")
            return normalized
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
            inputs = self.dinov2_processor(images=image, return_tensors="pt").to(self._device_for('dinov2'))
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
            inputs = self.aesthetic_processor(images=image, return_tensors="pt").to(self._device_for('aesthetic'))
            
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

    def _generate_musiq_score(self, input_data) -> Optional[float]:
        """
        Genera score qualità tecnica con MUSIQ via pyiqa.
        Accetta PIL Image o path. Normalizza a 1024px (lato lungo).
        Funziona su JPG e RAW (tramite thumbnail/preview).

        Returns:
            float: score MUSIQ (scala ~0-100, maggiore = migliore) o None
        """
        try:
            import torch
            from PIL import Image

            if self.musiq_model is None:
                return None

            # Ottieni PIL Image
            if isinstance(input_data, Image.Image):
                img = input_data.convert('RGB')
            elif isinstance(input_data, (str, Path)):
                img = Image.open(str(input_data)).convert('RGB')
            else:
                logger.warning(f"MUSIQ: tipo input non supportato: {type(input_data)}")
                return None

            # Normalizza a 1024px (lato lungo) per score comparabili
            max_side = max(img.size)
            if max_side > 1024:
                scale = 1024 / max_side
                img = img.resize(
                    (int(img.size[0] * scale), int(img.size[1] * scale)),
                    Image.Resampling.LANCZOS
                )

            with torch.no_grad():
                score = self.musiq_model(img).item()

            return round(score, 2)
        except Exception as e:
            logger.error(f"Errore MUSIQ: {e}")
            return None

    def generate_text_embedding(self, text_query: str):
        """Genera embedding CLIP per testo (ricerca semantica)"""
        try:
            import torch
            if not getattr(self, 'clip_enabled', False): 
                return None
            translated = self._translate_to_english(text_query) if self.translator else text_query
            inputs = self.clip_processor(text=[translated], return_tensors="pt", padding=True).to(self._device_for('clip'))
            with torch.no_grad():
                # Path manuale deterministico (come generate_embeddings)
                text_out = self.clip_model.text_model(
                    input_ids=inputs['input_ids'],
                    attention_mask=inputs.get('attention_mask')
                )
                text_features = self.clip_model.text_projection(text_out.pooler_output)
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
        
            # Tentiamo sempre la traduzione IT→EN: anche parole brevi come
            # "coro", "mare", "neve" devono diventare "choir", "sea", "snow"
            # per ottenere score CLIP significativi (CLIP è addestrato su EN)
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
    def generate_bioclip_tags(self, input_data, geo_hierarchy=None):
        """
        Genera tag BioCLIP con tassonomia completa.
        Args:
            input_data: Path/str (filepath), PIL.Image, o lista di predizioni BioCLIP
            geo_hierarchy: stringa GeOFF|Continent|Country|Region|City opzionale —
                           passata a GeoSpecies per subset geografico da cache locale
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
                predictions = self._predict_bioclip(input_data, 'path', geo_hierarchy=geo_hierarchy)
            except Exception as e:
                logger.error(f"Errore BioCLIP da filepath: {e}")
                return [], None

        # Se è una PIL Image, usa direttamente
        elif isinstance(input_data, Image.Image):
            try:
                predictions = self._predict_bioclip(input_data, 'pil', geo_hierarchy=geo_hierarchy)
            except Exception as e:
                logger.error(f"Errore BioCLIP da PIL Image: {e}")
                return [], None

        # Se è una lista di predizioni, usa direttamente
        elif isinstance(input_data, list):
            predictions = input_data

        else:
            logger.error(f"Input non supportato per BioCLIP: {type(input_data)}")
            return [], None

        # Scarta predizioni con regno non biologico (falsi positivi a threshold bassi)
        predictions = self._filter_by_known_kingdom(predictions)

        flat_tags = self._format_bioclip_tags(predictions)
        taxonomy = self._extract_best_taxonomy(predictions)
        return flat_tags, taxonomy
    
    def _filter_by_known_kingdom(self, predictions):
        """
        Filtra le predizioni BioCLIP mantenendo solo quelle con un regno biologico riconoscibile.
        Evita falsi positivi su oggetti non biologici (rocce, edifici, ecc.)
        che a threshold bassi possono ricevere score > 0 per qualche specie.
        Taxonomy[0] = kingdom nella struttura dati BioCLIP.
        """
        if not predictions:
            return []
        known = self.BIOCLIP_KNOWN_KINGDOMS
        filtered = [
            p for p in predictions
            if p.get('taxonomy') and len(p['taxonomy']) > 0 and p['taxonomy'][0] in known
        ]
        if len(filtered) < len(predictions):
            skipped = len(predictions) - len(filtered)
            kingdoms_found = {p.get('taxonomy', [None])[0] for p in predictions if p.get('taxonomy')}
            logger.debug(
                f"BioCLIP kingdom filter: {skipped} predizioni scartate "
                f"(regni non riconosciuti: {kingdoms_found - known})"
            )
        return filtered

    def _format_bioclip_tags(self, predictions_list):
        """Formatta predizioni BioCLIP in tag (metodo originale)"""
        if not predictions_list or not isinstance(predictions_list, list):
            return []

        try:
            # Prendi la predizione con score più alto
            best_prediction = max(predictions_list, key=lambda x: x.get('score', 0))

            # Usa soglia dal config (stessa usata in _predict_bioclip come min_prob)
            threshold = float(
                self.embedding_config.get('models', {}).get('bioclip', {}).get('threshold', 0.1)
            )
            if best_prediction.get('score', 0) < threshold:
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
            # Usa soglia dal config (stessa usata in _predict_bioclip come min_prob)
            threshold = float(
                self.embedding_config.get('models', {}).get('bioclip', {}).get('threshold', 0.1)
            )
            if best.get('score', 0) < threshold:
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

    # Regni biologici validi nel dataset TreeOfLife di BioCLIP.
    # Usato per scartare falsi positivi su oggetti non biologici (sassi, edifici, ecc.)
    # con threshold bassi (< 0.1).
    BIOCLIP_KNOWN_KINGDOMS = {
        'Animalia',   # animali
        'Plantae',    # piante
        'Fungi',      # funghi
        'Chromista',  # alghe brune, diatomee, ecc.
        'Protozoa',   # protozoi
        'Bacteria',   # batteri (raro in foto, ma presente nel dataset)
        'Archaea',    # archei (molto raro in foto)
    }

    # Mappa codice lingua → nome completo in inglese per istruzioni al prompt LLM
    LLM_OUTPUT_LANGUAGES = {
        'it': 'ITALIAN',
        'en': 'ENGLISH',
        'fr': 'FRENCH',
        'de': 'GERMAN',
        'es': 'SPANISH',
        'pt': 'PORTUGUESE',
    }

    # Esempi anchor-lingua per prompt tags singolo.
    # Parole neutre e generiche — non devono influenzare il contenuto generato,
    # servono solo ad ancorare il modello alla lingua corretta.
    LLM_TAGS_LANG_EXAMPLES = {
        'it': 'albero,montagna,tramonto,persone,strada',
        'en': 'tree,mountain,sunset,people,road',
        'fr': 'arbre,montagne,coucher de soleil,personnes,route',
        'de': 'Baum,Berg,Sonnenuntergang,Menschen,Straße',
        'es': 'árbol,montaña,atardecer,personas,camino',
        'pt': 'árvore,montanha,pôr do sol,pessoas,estrada',
    }

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
        """Prepara immagine per LLM: ridimensiona al profilo llm_vision e codifica in base64.

        Input PIL (batch pipeline): resize in memoria + encode diretto (no file temporaneo).
        Input path (gallery on-demand): estrae thumbnail via RAWProcessor.
        Usa cache interna per evitare elaborazioni ripetute sulla stessa immagine.
        """
        import base64
        import io
        from PIL import Image

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

        # Parametri dal profilo llm_vision
        llm_profile = self.optimization_profiles.get('llm_vision', {})
        llm_target_size = llm_profile.get('target_size', 512)
        llm_quality = llm_profile.get('quality', 85)
        llm_resampling = llm_profile.get('resampling', Image.Resampling.LANCZOS)

        try:
            import time as _t
            _t0 = _t.time()

            if input_type == 'path':
                from raw_processor import RAWProcessor
                raw_processor = RAWProcessor(self.config)
                thumbnail = raw_processor.extract_thumbnail(
                    Path(image_input), target_size=llm_target_size)
                if thumbnail is None:
                    # Fallback: leggi file grezzo come bytes per base64
                    with open(str(image_input), 'rb') as f:
                        image_b64 = base64.b64encode(f.read()).decode('utf-8')
                    self._llm_image_cache = {
                        'source': cache_key, 'base64': image_b64, 'temp_path': None}
                    return image_b64
                img = thumbnail
            else:
                img = image_input

            _t1 = _t.time()
            # Ridimensiona al target_size del profilo (il work thumb può essere più grande)
            resized = False
            if max(img.size) > llm_target_size:
                img = img.copy()
                img.thumbnail((llm_target_size, llm_target_size), llm_resampling)
                resized = True

            _t2 = _t.time()
            # Codifica JPEG direttamente in memoria (no file temporaneo su disco)
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=llm_quality)
            b64_bytes = buf.getvalue()
            image_b64 = base64.b64encode(b64_bytes).decode('utf-8')

            _t3 = _t.time()
            logger.debug(
                f"⏱ _prepare_llm_image: input={_t1-_t0:.3f}s resize={_t2-_t1:.3f}s "
                f"encode={_t3-_t2:.3f}s total={_t3-_t0:.3f}s "
                f"(size={img.size}, jpeg={len(b64_bytes)//1024}KB, resized={resized})")

            self._llm_image_cache = {
                'source': cache_key, 'base64': image_b64, 'temp_path': None}
            return image_b64

        except Exception as e:
            logger.error(f"Errore preparazione immagine LLM: {e}")
            return None

    def _cleanup_llm_image_cache(self):
        """Pulisce la cache immagine LLM."""
        # temp_path mantenuto per compatibilità, ma non più usato dal flusso in-memory
        tp = self._llm_image_cache.get('temp_path')
        if tp:
            try:
                os.unlink(tp)
            except OSError:
                pass
        self._llm_image_cache = {'source': None, 'base64': None, 'temp_path': None}

    def generate_llm_description(self, image_input, max_description_words: int = 100, bioclip_context: Optional[str] = None, category_hint: Optional[str] = None, location_hint: Optional[str] = None):
        """Genera descrizione LLM Vision tramite nucleo analitico unificato."""
        result = self.generate_llm_combined(
            image_input, modes=['description'],
            max_description_words=max_description_words,
            bioclip_context=bioclip_context,
            category_hint=category_hint, location_hint=location_hint
        )
        return result.get('description') if result else None

    def generate_llm_tags(self, image_input, max_tags: int = 10, bioclip_context: Optional[str] = None, category_hint: Optional[str] = None, location_hint: Optional[str] = None) -> List[str]:
        """Genera tag LLM Vision tramite nucleo analitico unificato."""
        result = self.generate_llm_combined(
            image_input, modes=['tags'],
            max_tags=max_tags,
            bioclip_context=bioclip_context,
            category_hint=category_hint, location_hint=location_hint
        )
        return result.get('tags', []) if result else []

    def generate_llm_title(self, image_input, max_title_words: int = 5, bioclip_context: Optional[str] = None, category_hint: Optional[str] = None, location_hint: Optional[str] = None) -> Optional[str]:
        """Genera titolo LLM Vision tramite nucleo analitico unificato."""
        result = self.generate_llm_combined(
            image_input, modes=['title'],
            max_title_words=max_title_words,
            bioclip_context=bioclip_context,
            category_hint=category_hint, location_hint=location_hint
        )
        return result.get('title') if result else None

    def generate_llm_combined(self, image_input, modes: list,
                              max_tags: int = 10, max_description_words: int = 100,
                              max_title_words: int = 5,
                              bioclip_context: Optional[str] = None,
                              category_hint: Optional[str] = None,
                              location_hint: Optional[str] = None) -> dict:
        """Genera tags/descrizione/titolo con UNA SOLA chiamata LLM.

        Tutti i modi (singoli o combinati) passano per _call_llm_vision_unified
        che usa sempre il nucleo analitico — garantisce qualità uniforme
        indipendentemente da cosa l'utente ha selezionato.

        Args:
            modes: lista con qualsiasi combinazione di 'tags', 'description', 'title'

        Returns:
            dict con le chiavi richieste (es. {'tags': [...], 'description': '...', 'title': '...'})
        """
        if not modes:
            return {}
        try:
            image_b64 = self._prepare_llm_image(image_input)
            if not image_b64:
                return {}

            # Ancora semantica: se manca 'tags', lo aggiungiamo silenziosamente
            # come primo campo — il modello identifica i soggetti prima di scrivere
            # titolo o descrizione, evitando pattern matching superficiale.
            # I tag aggiunti come ancora vengono poi rimossi dal risultato finale.
            anchor_added = False
            effective_modes = list(modes)
            if 'tags' not in effective_modes and len(effective_modes) < 3:
                effective_modes = ['tags'] + effective_modes
                anchor_added = True

            result = self._call_llm_vision_unified(
                image_b64, effective_modes, max_tags if not anchor_added else 5,
                max_description_words, max_title_words,
                category_hint=category_hint, location_hint=location_hint
            )

            # Rimuovi i tag ancora dal risultato se non erano richiesti
            if anchor_added:
                result.pop('tags', None)
            if not result:
                return {}

            # Post-processing BioCLIP: prepend nome latino, normalize_tags per dedup/ordine
            latin_name = None
            if bioclip_context:
                latin_name = bioclip_context.split('(')[0].split(',')[0].strip() or None
            if latin_name:
                if 'tags' in result:
                    result['tags'] = normalize_tags(result['tags'], scientific_name=latin_name)[:max_tags]
                if 'description' in result and result['description']:
                    result['description'] = f"{latin_name}: {result['description']}"
                if 'title' in result and result['title']:
                    result['title'] = f"{latin_name} - {result['title']}"
            elif 'tags' in result:
                result['tags'] = normalize_tags(result['tags'])[:max_tags]

            return result

        except Exception as e:
            logger.error(f"Errore generate_llm_combined: {e}")
            return {}

    def _parse_combined_response(self, text: str, modes: list, max_tags: int) -> dict:
        """Parsa la risposta strutturata TAGS/DESCRIPTION/TITLE dal modello.

        Gestisce sia risposte con label (TAGS:/DESCRIPTION:/TITLE:) sia risposte
        senza label, che alcuni modelli producono quando viene richiesto un solo modo.
        """
        result: dict = {}
        current_key: Optional[str] = None
        current_lines: list = []

        # Label riconosciute: usate per troncare contenuto spurio che il modello
        # a volte ripete dentro la descrizione o i tag
        known_labels = ('TAGS:', 'DESCRIPTION:', 'DESCRIZIONE:', 'TITLE:', 'TITOLO:')

        def _flush(key, lines):
            content = ' '.join(lines).strip()
            if not content:
                return
            if key == 'tags':
                # Tronca prima di eventuale testo spurio del prompt (es. "- TAGS: comma-separated")
                # che il modello può copiare dopo l'elenco vero
                for sep in (' - ', ' — ', '\n'):
                    if sep in content:
                        # Tieni solo la parte prima del separatore se dopo c'è testo non-tag
                        candidate = content.split(sep)[0]
                        # Valido solo se contiene virgole (= lista tag reale)
                        if ',' in candidate or len(candidate.split()) <= 3:
                            content = candidate
                            break
                raw = [t.strip().strip('"').strip("'").strip()
                       for t in content.replace(';', ',').split(',')]
                seen: set = set()
                tags = []
                for t in raw:
                    # Scarta token che sembrano istruzioni del prompt
                    if any(t.upper().startswith(lbl) for lbl in known_labels):
                        break
                    if (t and 2 < len(t) < 50
                            and not t.startswith(('http', 'www'))
                            and t.lower() not in seen):
                        seen.add(t.lower())
                        tags.append(t)
                result['tags'] = tags[:max_tags]
            elif key == 'description':
                # Tronca appena il modello ricomincia a scrivere label (TAGS:/TITLE:/ecc.)
                import re as _re
                label_pattern = _re.compile(
                    r'\b(TAGS|DESCRIPTION|DESCRIZIONE|TITLE|TITOLO)\s*:', _re.IGNORECASE)
                match = label_pattern.search(content)
                if match:
                    content = content[:match.start()].strip()
                result['description'] = content
            elif key == 'title':
                # Solo la prima riga: il modello può aggiungere testo extra su righe successive
                first = lines[0].strip() if lines else content
                result['title'] = first.strip('"').strip("'").rstrip('.').rstrip(',').strip()

        for line in text.strip().split('\n'):
            s = line.strip()
            upper = s.upper()
            matched_key = None

            if 'tags' in modes and upper.startswith('TAGS:'):
                matched_key = 'tags'
                content = s[5:].strip()
            elif 'description' in modes and (upper.startswith('DESCRIPTION:') or upper.startswith('DESCRIZIONE:')):
                matched_key = 'description'
                content = s.split(':', 1)[1].strip()
            elif 'title' in modes and (upper.startswith('TITLE:') or upper.startswith('TITOLO:')):
                matched_key = 'title'
                content = s.split(':', 1)[1].strip()
            else:
                content = None

            if matched_key:
                if current_key:
                    _flush(current_key, current_lines)
                current_key = matched_key
                current_lines = [content] if content else []
            elif current_key and s:
                current_lines.append(s)

        if current_key:
            _flush(current_key, current_lines)

        # Fallback: se nessuna label trovata e modo singolo, usa il testo diretto
        if not result and len(modes) == 1:
            single_mode = modes[0]
            clean = text.strip()
            if single_mode == 'tags':
                raw = [t.strip().strip('"').strip("'").strip()
                       for t in clean.replace(';', ',').split(',')]
                seen: set = set()
                tags = []
                for t in raw:
                    if (t and 2 < len(t) < 50
                            and not t.startswith(('http', 'www'))
                            and t.lower() not in seen):
                        seen.add(t.lower())
                        tags.append(t)
                if tags:
                    result['tags'] = tags[:max_tags]
            elif single_mode == 'description':
                if clean:
                    result['description'] = clean
            elif single_mode == 'title':
                first_line = clean.split('\n')[0].strip()
                result['title'] = first_line.strip('"').strip("'").rstrip('.').rstrip(',').strip()

        return result

    def generate_llm_content(self, image_input, mode='description', max_tags: int = 10, max_description_words: int = 100, max_title_words: int = 5, bioclip_context: Optional[str] = None, category_hint: Optional[str] = None, location_hint: Optional[str] = None):
        """Metodo unificato per contenuti LLM con parametri completi.

        Traduce la stringa mode in lista di modi e delega a generate_llm_combined
        — una sola chiamata LLM con nucleo analitico fisso per tutti i casi.

        Modes supportati:
        - 'description': solo descrizione
        - 'tags': solo tag
        - 'title': solo titolo
        - 'tags_and_description': tag + descrizione
        - 'all': tag + descrizione + titolo
        """
        # Mappa stringa mode → lista di modi per generate_llm_combined
        mode_map = {
            'description':       ['description'],
            'tags':              ['tags'],
            'title':             ['title'],
            'tags_and_description': ['tags', 'description'],
            'all':               ['tags', 'description', 'title'],
        }
        modes = mode_map.get(mode)
        if not modes:
            logger.error(f"Modalità LLM non supportata: {mode}")
            return None

        try:
            result = self.generate_llm_combined(
                image_input, modes=modes,
                max_tags=max_tags,
                max_description_words=max_description_words,
                max_title_words=max_title_words,
                bioclip_context=bioclip_context,
                category_hint=category_hint,
                location_hint=location_hint,
            )
            return result if result else None

        except Exception as e:
            logger.error(f"Errore LLM content generation: {e}")
            return None

    def _call_llm_vision_unified(self, image_data_b64: str, modes: list,
                                  max_tags: int = 10, max_description_words: int = 100,
                                  max_title_words: int = 5,
                                  category_hint: Optional[str] = None,
                                  location_hint: Optional[str] = None) -> dict:
        """Nucleo unificato per tutte le chiamate LLM Vision.

        Sostituisce _call_llm_vision (singolo) e _call_llm_vision_combined.
        Usa sempre un nucleo analitico fisso che forza il modello a ragionare
        sull'immagine prima di generare l'output, indipendentemente dai modi richiesti.
        Questo garantisce qualità uniforme per tag soli, descrizione sola, titolo solo
        o qualsiasi combinazione.

        Args:
            modes: lista con qualsiasi combinazione di 'tags', 'description', 'title'
        Returns:
            dict con le chiavi richieste (es. {'tags': [...], 'description': '...', 'title': '...'})
        """
        if not modes:
            return {}
        try:
            llm_config = self.embedding_config.get('models', {}).get('llm_vision', {})
            model    = llm_config.get('model', 'qwen3.5:4b-q4_K_M')
            timeout  = llm_config.get('timeout', 180)
            generation = llm_config.get('generation', {})
            temperature = generation.get('temperature', 0.7)
            top_p    = generation.get('top_p',    0.8)
            top_k    = generation.get('top_k',    20)
            min_p    = generation.get('min_p',    0.0)
            num_ctx  = generation.get('num_ctx',  2048)
            num_batch = generation.get('num_batch', 1024)

            lang_code = self.config.get('ui', {}).get('llm_output_language', 'it')
            lang_name = EmbeddingGenerator.LLM_OUTPUT_LANGUAGES.get(lang_code, 'ITALIAN')

            # --- Regole lingua e contesto (invarianti) ---
            # Traduce category_hint (italiano) in inglese per il prompt (sempre in EN)
            category_hint_en = category_hint
            if category_hint:
                try:
                    import argostranslate.translate as _at
                    category_hint_en = _at.translate(category_hint, 'it', 'en') or category_hint
                except Exception:
                    pass

            category_line = ""
            if category_hint_en:
                category_line = (
                    f"- The main subject is a {category_hint_en}. The species is already identified externally.\n"
                    "- DO NOT name the species. NEVER use species or scientific names.\n"
                    "- Focus ONLY on: visual attributes, behavior, environment, colors, composition.\n"
                )
                # Per il titolo: il LLM deve tradurre il termine generico, non usare nomi latini
                if modes == ['title']:
                    category_line = (
                        f"- The main subject is a {category_hint_en}. Use the correct {lang_name} translation of this term.\n"
                        "- DO NOT use species names or scientific Latin names.\n"
                    )

            if location_hint:
                if lang_code == 'en':
                    location_line = f"- LOCATION: This photo was taken in: {location_hint}. Use standard English place names. Mention the location naturally if relevant.\n"
                else:
                    location_line = f"- LOCATION: This photo was taken in: {location_hint}. Translate ALL place names to {lang_name}. Mention the location naturally if relevant.\n"
            else:
                location_line = "- LOCATION: No GPS data available. Do NOT mention, guess or infer any specific location, city, country or place name.\n"

            language_rules = (
                f"LANGUAGE: ALL output MUST be in {lang_name}. NEVER mix languages.\n"
                f"{category_line}"
                f"{location_line}"
                f"- If no species hint and you recognize an animal/plant, use a generic {lang_name} term.\n"
                "- NEVER guess a species name. A generic term is ALWAYS better than a wrong name.\n"
                "- NEVER use scientific/Latin names.\n"
            )

            # --- Nucleo analitico fisso ---
            # Forza il modello a costruire una rappresentazione interna completa
            # della scena prima di produrre qualsiasi output.
            # "do not output" = il testo di analisi non deve apparire nella risposta.
            analysis_kernel = (
                "STEP 1 — ANALYSIS (internal reasoning, do not output this):\n"
                "Carefully examine the image: main subject and its exact nature, secondary elements,\n"
                "actions or motion, environment and setting, colors and light, composition and perspective,\n"
                "atmosphere and mood. Build a complete mental description before generating any output.\n\n"
            )

            # --- Sezioni output dinamiche in base ai modi richiesti ---
            # L'ordine delle sezioni segue esattamente l'ordine di `modes`:
            # chi chiama decide quale campo funge da ancora semantica per i successivi.
            # Regola: il campo più "semplice" (tags) va prima dei campi che ne beneficiano
            # (title, description) — il modello legge nel contesto già generato.
            section_specs = {
                'title': (
                    f"TITLE: ...  "
                    f"(max {max_title_words} words, {lang_name}, factual/descriptive, no quotes, no ending punctuation)"
                ),
                'tags': (
                    f"TAGS: tag1,tag2,...  "
                    f"(max {max_tags}, {lang_name}, singular, comma-separated, only what you clearly see)"
                ),
                'description': (
                    f"DESCRIPTION: ...  "
                    f"(max {max_description_words} words, {lang_name}, single paragraph, "
                    f"subject/environment/colors/composition/atmosphere)"
                ),
            }
            format_lines = [section_specs[m] for m in modes if m in section_specs]
            format_spec = '\n'.join(format_lines)

            # --- Calcolo max_tokens: somma dei modi richiesti ---
            max_tokens = 15  # overhead label+newline
            if 'tags' in modes:
                max_tokens += max_tags * 3 + 10
            if 'description' in modes:
                max_tokens += int(max_description_words * 1.5) + 20
            if 'title' in modes:
                max_tokens += int(max_title_words * 2) + 10

            prompt = (
                "/no_think\n"
                "You are a professional photography cataloging system.\n\n"
                f"{language_rules}\n"
                f"{analysis_kernel}"
                "STEP 2 — OUTPUT:\n"
                "Write ONLY the lines below. Start each line with its label exactly as shown.\n"
                "Stop immediately after the last required line. Do not repeat labels.\n\n"
                f"{format_spec}\n"
            )

            params = {
                'model':      model,
                'timeout':    timeout,
                'keep_alive': generation.get('keep_alive', -1),
                'temperature': temperature,
                'top_p':      top_p,
                'top_k':      top_k,
                'min_p':      min_p,
                'num_ctx':    num_ctx,
                'num_batch':  num_batch,
            }

            if not self.llm_plugin:
                logger.warning("⚠️ Nessun plugin LLM disponibile — generazione testo saltata.")
                return {}

            logger.info(
                f"[LLM] modes={modes} | plugin={type(self.llm_plugin).__name__} | "
                f"model={model} | max_tokens={max_tokens} | "
                f"img_b64_len={len(image_data_b64)} (~{len(image_data_b64)*3//4//1024}KB) | "
                f"num_ctx={num_ctx} | temperature={temperature} | top_k={top_k}\n"
                f"[LLM] PROMPT:\n{prompt}"
            )

            response = self.llm_plugin.generate(image_data_b64, prompt, max_tokens, params)
            logger.info(f"[LLM] RISPOSTA RAW:\n{response}")

            if not response:
                return {}

            # Parsing: se un solo modo, la risposta può essere senza label (testo diretto)
            # oppure con label — _parse_combined_response gestisce entrambi i casi
            return self._parse_combined_response(response, modes, max_tags)

        except Exception as e:
            logger.error(f"Errore _call_llm_vision_unified: {e}")
            return {}

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
                
                # Filtra tag validi e deduplicati (case-insensitive)
                if (clean_tag and
                    len(clean_tag) > 2 and
                    len(clean_tag) < 50 and
                    not clean_tag.startswith(('http', 'www')) and
                    clean_tag.lower() not in {t.lower() for t in tags}):
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