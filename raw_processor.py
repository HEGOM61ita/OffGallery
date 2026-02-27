"""
RAW Processor - Estrazione completa EXIF + XMP + Thumbnail ottimizzato
Sistema ottimizzato con ExifTool per tutto (metadati + thumbnail)
VERSIONE RISTRUTTURATA con OTTIMIZZAZIONE AUTOMATICA PER MODELLI AI
"""

import logging
import subprocess
import json
import tempfile
import inspect
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)


class CallerOptimizer:
    """Sistema di rilevamento automatico del chiamante per ottimizzazione"""

    @staticmethod
    def detect_caller_purpose():
        """
        Rileva il contesto del chiamante per ottimizzare l'estrazione.
        NON restituisce size hardcoded - le size vengono dai profili config.

        Returns: (purpose, None, quality_level)
            - purpose: nome del profilo da usare (es. 'clip_embedding', 'llm_vision')
            - None: la size viene determinata dal profilo config
            - quality_level: hint per il livello di qualità
        """
        try:
            # Analizza lo stack delle chiamate
            stack = inspect.stack()
            for frame_info in stack[2:6]:  # Salta i primi 2 frame (questo metodo + extract_thumbnail)
                filename = Path(frame_info.filename).name
                function_name = frame_info.function
                logger.debug(f"🔍 CALLER DEBUG: filename={filename}, function={function_name}")

                # EMBEDDING GENERATOR - Modelli AI
                if 'embedding_generator' in filename:
                    if 'llm' in function_name.lower():
                        logger.debug(f"🔍 DETECTED PURPOSE: llm_vision")
                        return 'llm_vision', None, 'high'
                    elif 'clip' in function_name.lower():
                        return 'clip_embedding', None, 'high'
                    elif 'dinov2' in function_name.lower():
                        return 'dinov2_embedding', None, 'high'
                    elif 'aesthetic' in function_name.lower():
                        return 'aesthetic_score', None, 'standard'
                    elif 'bioclip' in function_name.lower():
                        return 'bioclip_classification', None, 'high'
                    else:
                        return 'ai_processing', None, 'standard'

                # PROCESSING TAB - Batch processing
                elif 'processing_tab' in filename:
                    if 'ai' in function_name.lower():
                        return 'ai_processing', None, 'standard'
                    else:
                        return 'metadata_extraction', None, 'fast'

                # GALLERY - Visualizzazione veloce
                elif 'gallery' in filename:
                    return 'gallery_display', None, 'fast'

                # LLM WORKER
                elif 'llm_worker' in filename:
                    return 'llm_vision', None, 'high'

        except Exception as e:
            logger.debug(f"Caller detection failed: {e}")

        # Fallback default
        return 'default', None, 'standard'


class RAWProcessor:
    """Processore unificato RAW con ExifTool per tutto + ottimizzazione automatica"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.raw_config = config.get('image_processing', {}).get('raw_processing', {})
        
        # CARICAMENTO PROFILI DA CONFIG YAML
        self.optimization_enabled = config.get('image_optimization', {}).get('enabled', True)
        config_profiles = config.get('image_optimization', {}).get('profiles', {})
        
        # PROFILI OTTIMIZZATI (fallback hardcoded + override da config)
        self.optimization_profiles = self._load_optimization_profiles(config_profiles)
        
        # Dimensioni ottimali per CLIP - CRITICO per embedding validi (DEPRECATO)
        self.ai_target_size = 512  # Mantenuto per compatibilità
        
    def _load_optimization_profiles(self, config_profiles: Dict) -> Dict:
        """Carica profili ottimizzazione da config con fallback hardcoded"""
        
        # PROFILI HARDCODED OTTIMIZZATI (fallback di sicurezza)
        hardcoded_profiles = {
            'llm_vision': {
                'target_size': 1024,
                'quality': 95,
                'method': 'rawpy_full',
                'resampling': 'LANCZOS',
                'upscale': False
            },
            'clip_embedding': {
                'target_size': 512,
                'quality': 90,
                'method': 'high_quality',
                'resampling': 'LANCZOS',
                'upscale': False
            },
            'dinov2_embedding': {
                'target_size': 518,
                'quality': 90,
                'method': 'high_quality',
                'resampling': 'LANCZOS',
                'upscale': False
            },
            'aesthetic_score': {
                'target_size': 336,
                'quality': 85,
                'method': 'preview_optimized',
                'resampling': 'BILINEAR',
                'upscale': False
            },
            'technical_score': {
                'target_size': 512,
                'quality': 90,
                'method': 'preview_optimized',
                'resampling': 'LANCZOS',
                'upscale': False
            },
            'bioclip_classification': {
                'target_size': 384,
                'quality': 90,
                'method': 'high_quality',
                'resampling': 'LANCZOS',
                'upscale': False
            },
            'ai_processing': {
                'target_size': 512,
                'quality': 85,
                'method': 'preview_optimized',
                'resampling': 'LANCZOS',
                'upscale': False
            },
            'gallery_display': {
                'target_size': 256,
                'quality': 75,
                'method': 'fast_thumbnail',
                'resampling': 'BILINEAR',
                'upscale': False
            },
            'metadata_extraction': {
                'target_size': 256,
                'quality': 75,
                'method': 'fast_thumbnail',
                'resampling': 'BILINEAR',
                'upscale': False
            },
            'default': {
                'target_size': 512,
                'quality': 85,
                'method': 'preview_optimized',
                'resampling': 'LANCZOS',
                'upscale': False
            }
        }
        
        # Merge config con hardcoded (config ha priorità)
        final_profiles = {}
        for profile_name, hardcoded_profile in hardcoded_profiles.items():
            config_profile = config_profiles.get(profile_name, {})
            
            # Merge con priorità al config
            merged_profile = hardcoded_profile.copy()
            merged_profile.update(config_profile)
            
            # Converti resampling string in PIL constant
            merged_profile['resampling'] = self._get_resampling_method(merged_profile.get('resampling', 'LANCZOS'))
            
            final_profiles[profile_name] = merged_profile
        
        logger.info(f"✓ Loaded optimization profiles: {len(final_profiles)} profiles")
        if config_profiles:
            logger.info(f"✓ Config overrides: {list(config_profiles.keys())}")
            
        return final_profiles
    
    def _get_resampling_method(self, resampling_name: str):
        """Converte nome resampling in costante PIL"""
        resampling_map = {
            'LANCZOS': Image.Resampling.LANCZOS,
            'BILINEAR': Image.Resampling.BILINEAR,
            'BICUBIC': Image.Resampling.BICUBIC,
            'NEAREST': Image.Resampling.NEAREST
        }
        return resampling_map.get(resampling_name.upper(), Image.Resampling.LANCZOS)

    def get_max_target_size(self, profile_names: List[str] = None) -> int:
        """
        Calcola la MAX target_size tra i profili specificati.
        Utile per estrarre thumbnail una volta alla dimensione massima necessaria.

        Args:
            profile_names: lista di nomi profilo (es. ['clip_embedding', 'dinov2_embedding'])
                          Se None, usa tutti i profili AI-related

        Returns:
            int: la dimensione massima tra i profili
        """
        if profile_names is None:
            # Default: tutti i profili AI (esclusi gallery/metadata)
            profile_names = [
                'clip_embedding', 'dinov2_embedding', 'bioclip_classification',
                'aesthetic_score', 'llm_vision', 'ai_processing'
            ]

        max_size = self.ai_target_size  # fallback default

        for name in profile_names:
            profile = self.optimization_profiles.get(name)
            if profile:
                size = profile.get('target_size', 0)
                if size > max_size:
                    max_size = size
                    logger.debug(f"Max size updated: {name} → {size}px")

        logger.info(f"📐 Max target size calculated: {max_size}px from profiles: {profile_names}")
        return max_size

    def get_profile(self, profile_name: str) -> dict:
        """
        Ottiene un profilo di ottimizzazione per nome.

        Args:
            profile_name: nome del profilo (es. 'clip_embedding')

        Returns:
            dict con target_size, method, resampling, quality, upscale
        """
        return self.optimization_profiles.get(profile_name, self.optimization_profiles['default'])
        
    def extract_raw_metadata(self, raw_path: Path) -> Dict[str, Any]:
        """
        Estrazione unificata EXIF + XMP completi per tutti i formati
        
        Strategia:
        - RAW (ORF, CR2, etc.): EXIF embedded + XMP sidecar (.xmp)
        - JPEG/TIFF: EXIF + XMP embedded  
        - DNG: EXIF + XMP embedded + XMP sidecar merge
        
        Returns:
            Dict con metadati completi estratti
        """
        metadata = {
            'is_raw': self.is_raw_file(raw_path),
            'raw_format': raw_path.suffix.lower()[1:] if raw_path.suffix else None,  # → 'orf'
            'raw_info': self.get_raw_info(raw_path)
        }
        
        try:
            # ===== ESTRAZIONE EXIF + XMP EMBEDDED =====
            exif_data = self._extract_with_exiftool(raw_path)
            
            # ===== ESTRAZIONE XMP SIDECAR (solo per RAW) =====
            xmp_sidecar_data = {}
            if self.is_raw_file(raw_path):
                xmp_sidecar_data = self._extract_xmp_sidecar(raw_path)
            
            # ===== MERGE INTELLIGENTE =====
            # Priorità: Sidecar > Embedded > Default
            final_data = self._merge_xmp_data(exif_data, xmp_sidecar_data)
            
            # ===== MAPPING CAMPI STANDARDIZZATO =====
            metadata.update(self._map_all_fields(final_data))
            
            # ===== ANALISI BIANCO/NERO (ottimizzata) =====
            try:
                # Estrazione veloce dedicata per analisi B/N
                bw_image = self._extract_for_bw_analysis(raw_path)
                if bw_image:
                    is_mono = self._is_monochrome_image(bw_image)
                    metadata['is_monochrome'] = 1 if is_mono else 0
                    logger.info(f"🎨 Analisi B/N per {raw_path.name}: {is_mono}")
                    # Chiudi l'immagine per liberare memoria
                    try:
                        bw_image.close()
                    except:
                        pass
                else:
                    metadata['is_monochrome'] = 0
                    logger.warning(f"❌ Immagine non estratta per analisi B/N: {raw_path.name}")
            except Exception as e:
                logger.error(f"Errore analisi B/N per {raw_path.name}: {e}")
                metadata['is_monochrome'] = 0
            
            logger.debug(f"Estrazione completata per {raw_path.name}: {len(metadata)} campi")
            
        except Exception as e:
            logger.error(f"Errore estrazione metadata per {raw_path.name}: {e}")
            
        return metadata
    
    def extract_thumbnail(self, raw_path: Path, target_size: int = None, profile_name: str = None) -> Optional[Image.Image]:
        """
        Estrai thumbnail da qualsiasi file con OTTIMIZZAZIONE AUTOMATICA
        Il metodo di estrazione si adatta automaticamente al chiamante.

        PRIORITÀ SIZE:
        1. target_size esplicito (se passato)
        2. profile_name esplicito → size dal profilo config
        3. CallerOptimizer detection → size dal profilo config
        4. Fallback default (512px)

        Args:
            raw_path: Path del file (RAW, JPEG, etc.)
            target_size: dimensione target esplicita (opzionale)
            profile_name: nome profilo da usare (opzionale, es. 'clip_embedding')

        Returns:
            PIL Image ottimizzata per il contesto d'uso
        """
        try:
            # RILEVAMENTO AUTOMATICO DEL CHIAMANTE (solo se ottimizzazione abilitata)
            if self.optimization_enabled:
                # Determina il profilo da usare
                if profile_name:
                    # Profilo esplicito specificato
                    purpose = profile_name
                else:
                    # Rilevamento automatico dal chiamante
                    purpose, _, quality_level = CallerOptimizer.detect_caller_purpose()

                # Ottieni profilo di ottimizzazione
                profile = self.optimization_profiles.get(purpose, self.optimization_profiles['default'])

                # PRIORITÀ SIZE: esplicito > profilo config > fallback
                if target_size is None:
                    target_size = profile.get('target_size', self.ai_target_size)

                logger.info(f"🎯 Profile: {purpose} | Size: {target_size}px | Method: {profile['method']}")

                # ESTRAZIONE OTTIMIZZATA IN BASE AL PROFILO
                if profile['method'] == 'rawpy_full':
                    thumbnail = self._extract_rawpy_full_quality(raw_path, target_size, profile)
                elif profile['method'] == 'high_quality':
                    thumbnail = self._extract_high_quality(raw_path, target_size, profile)
                elif profile['method'] == 'preview_optimized':
                    thumbnail = self._extract_preview_optimized(raw_path, target_size, profile)
                elif profile['method'] == 'fast_thumbnail':
                    thumbnail = self._extract_fast_thumbnail(raw_path, target_size, profile)
                else:
                    # Fallback al metodo originale
                    thumbnail = self._extract_original_method(raw_path, target_size)

                if thumbnail:
                    logger.debug(f"✓ Extracted for {purpose}: {raw_path.name} → {thumbnail.size}")
                    return thumbnail
                else:
                    logger.warning(f"❌ Failed extraction for {purpose}: {raw_path.name}")
                    # Fallback al metodo originale
                    return self._extract_original_method(raw_path, target_size or self.ai_target_size)
            else:
                # Ottimizzazione disabilitata - usa metodo originale
                logger.debug("⚠️ Optimization disabled - using original method")
                return self._extract_original_method(raw_path, target_size or self.ai_target_size)

        except Exception as e:
            logger.error(f"Errore extract_thumbnail per {raw_path.name}: {e}")
            # Fallback di emergenza
            return self._extract_original_method(raw_path, target_size or self.ai_target_size)
    
    # ===== METODI DI ESTRAZIONE OTTIMIZZATI =====
    
    def _extract_rawpy_full_quality(self, raw_path: Path, target_size: int, profile: dict) -> Optional[Image.Image]:
        """Estrazione RAW massima qualità per LLM Vision (usa rawpy direttamente)"""
        if not self.is_raw_file(raw_path):
            return self._extract_high_quality(raw_path, target_size, profile)
        
        try:
            import rawpy
            with rawpy.imread(str(raw_path)) as raw:
                # Postprocessing completo per massima qualità
                rgb = raw.postprocess(
                    use_camera_wb=True,
                    no_auto_bright=False,
                    output_bps=16  # 16-bit per massima qualità
                )
                image = Image.fromarray(rgb)
                
                # Resize mantenendo proporzioni
                w, h = image.size
                max_side = max(w, h)
                if max_side > target_size:
                    scale = target_size / max_side
                    new_size = (int(w * scale), int(h * scale))
                    image = image.resize(new_size, profile['resampling'])
                
                return image.convert('RGB')
                
        except ImportError:
            logger.warning("rawpy non disponibile - fallback a metodo alternativo")
            return self._extract_high_quality(raw_path, target_size, profile)
        except Exception as e:
            logger.debug(f"rawpy extraction failed: {e}")
            return self._extract_high_quality(raw_path, target_size, profile)
    
    def _extract_high_quality(self, raw_path: Path, target_size: int, profile: dict) -> Optional[Image.Image]:
        """Estrazione alta qualità per modelli AI critici (BioCLIP, etc.)"""
        try:
            # STRATEGIA 1: Preview Image se grande
            thumbnail = self._extract_preview_image(raw_path)
            if thumbnail and max(thumbnail.size) >= 400:
                thumbnail = self._resize_with_quality(thumbnail, target_size, profile)
                return thumbnail
            
            # STRATEGIA 2: JPEG from RAW
            if self.is_raw_file(raw_path):
                thumbnail = self._extract_jpeg_from_raw(raw_path, target_size)
                if thumbnail:
                    return thumbnail
            
            # STRATEGIA 3: Full image resized
            thumbnail = self._extract_full_image_resized(raw_path, target_size)
            if thumbnail:
                return self._resize_with_quality(thumbnail, target_size, profile)
            
            return None
            
        except Exception as e:
            logger.debug(f"High quality extraction failed: {e}")
            return None
    
    def _extract_preview_optimized(self, raw_path: Path, target_size: int, profile: dict) -> Optional[Image.Image]:
        """Estrazione bilanciata qualità/velocità per CLIP, DINOv2, Aesthetic"""
        try:
            # STRATEGIA 1: Preview Image
            thumbnail = self._extract_preview_image(raw_path)
            if thumbnail and max(thumbnail.size) >= 250:
                return self._resize_with_quality(thumbnail, target_size, profile)
            
            # STRATEGIA 2: Thumbnail embedded ridimensionato
            thumbnail = self._extract_thumbnail_embedded(raw_path)
            if thumbnail:
                return self._resize_with_quality(thumbnail, target_size, profile)
            
            # STRATEGIA 3: Full image per non-RAW
            if not self.is_raw_file(raw_path):
                thumbnail = self._extract_full_image_resized(raw_path, target_size)
                if thumbnail:
                    return self._resize_with_quality(thumbnail, target_size, profile)
            
            return None
            
        except Exception as e:
            logger.debug(f"Preview optimized extraction failed: {e}")
            return None
    
    def _extract_fast_thumbnail(self, raw_path: Path, target_size: int, profile: dict) -> Optional[Image.Image]:
        """Estrazione veloce per gallery e preview"""
        try:
            # STRATEGIA 1: Thumbnail embedded (più veloce)
            thumbnail = self._extract_thumbnail_embedded(raw_path)
            if thumbnail:
                return self._resize_with_quality(thumbnail, target_size, profile)
            
            # STRATEGIA 2: Preview se necessario
            thumbnail = self._extract_preview_image(raw_path)
            if thumbnail:
                return self._resize_with_quality(thumbnail, target_size, profile)
            
            return None
            
        except Exception as e:
            logger.debug(f"Fast thumbnail extraction failed: {e}")
            return None
    
    def _extract_original_method(self, raw_path: Path, target_size: int) -> Optional[Image.Image]:
        """Metodo di estrazione originale (fallback)"""
        try:
            # Replica il metodo originale per compatibilità
            thumbnail = self._extract_preview_image(raw_path)

            if thumbnail and max(thumbnail.size) >= 300:
                thumbnail.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
                return thumbnail

            if self.is_raw_file(raw_path):
                thumbnail = self._extract_jpeg_from_raw(raw_path, target_size)
                if thumbnail:
                    return thumbnail

            thumbnail = self._extract_thumbnail_embedded(raw_path)
            if thumbnail:
                thumbnail = thumbnail.resize((target_size, target_size), Image.Resampling.LANCZOS)
                return thumbnail

            if not self.is_raw_file(raw_path):
                thumbnail = self._extract_full_image_resized(raw_path, target_size)
                if thumbnail:
                    return thumbnail

            # Ultimo tentativo: prova tag ExifTool alternativi (es. Nikon High-Efficiency)
            if self.is_raw_file(raw_path):
                thumbnail = self._extract_exiftool_any_preview(raw_path, target_size)
                if thumbnail:
                    return thumbnail

            return None

        except Exception as e:
            logger.debug(f"Original method failed: {e}")
            return None

    def _extract_exiftool_any_preview(self, file_path: Path, target_size: int) -> Optional[Image.Image]:
        """Ultimo tentativo per formati RAW insoliti: prova tag ExifTool alternativi in sequenza.
        Utile per Nikon High-Efficiency NEF, fotocamere recenti non ancora supportate da rawpy."""
        tags_to_try = [
            '-LargePreview',
            '-SubIFD:PreviewImage',
            '-OriginalRawImage',
            '-PreviewTIFF',
            '-RawThumbnailImage',
        ]
        for tag in tags_to_try:
            try:
                result = subprocess.run(
                    ['exiftool', '-b', tag, str(file_path)],
                    capture_output=True, timeout=15
                )
                if result.returncode == 0 and result.stdout and len(result.stdout) > 1000:
                    try:
                        thumbnail = Image.open(BytesIO(result.stdout)).convert('RGB')
                        if max(thumbnail.size) > target_size:
                            thumbnail.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
                        logger.info(f"✅ ExifTool fallback ({tag}): {file_path.name} → {thumbnail.size}")
                        return thumbnail
                    except Exception:
                        pass
            except Exception:
                pass
        return None
    
    def _resize_with_quality(self, image: Image.Image, target_size: int, profile: dict) -> Image.Image:
        """Ridimensiona immagine con parametri di qualità del profilo"""
        w, h = image.size
        
        # Ridimensiona mantenendo proporzioni se necessario
        max_side = max(w, h)
        if max_side > target_size:
            scale = target_size / max_side
            new_size = (int(w * scale), int(h * scale))
            image = image.resize(new_size, profile['resampling'])
        elif max_side < target_size and profile.get('upscale', False):
            # Upscale solo se richiesto dal profilo
            scale = target_size / max_side
            new_size = (int(w * scale), int(h * scale))
            image = image.resize(new_size, profile['resampling'])
        
        return image.convert('RGB')
    
    # ===== METODI ORIGINALI (mantenuti per compatibilità) =====
    
    def _extract_thumbnail_embedded(self, file_path: Path) -> Optional[Image.Image]:
        """Estrai thumbnail embedded con ExifTool"""
        try:
            result = subprocess.run([
                'exiftool', '-ThumbnailImage', '-b', str(file_path)
            ], capture_output=True, timeout=15)
            
            if result.returncode == 0 and result.stdout and len(result.stdout) > 1000:
                # Converti bytes in PIL Image
                thumbnail = Image.open(BytesIO(result.stdout))
                logger.debug(f"ExifTool thumbnail: {file_path.name} → {thumbnail.size}")
                return thumbnail
                
        except Exception as e:
            logger.debug(f"ExifTool thumbnail failed for {file_path.name}: {e}")
            
        return None
    
    def _extract_preview_image(self, file_path: Path) -> Optional[Image.Image]:
        """Estrai preview image con ExifTool (spesso più grande del thumbnail)"""
        try:
            result = subprocess.run([
                'exiftool', '-PreviewImage', '-b', str(file_path)
            ], capture_output=True, timeout=15)
            
            if result.returncode == 0 and result.stdout and len(result.stdout) > 1000:
                thumbnail = Image.open(BytesIO(result.stdout))
                logger.debug(f"ExifTool preview: {file_path.name} → {thumbnail.size}")
                return thumbnail
                
        except Exception as e:
            logger.debug(f"ExifTool preview failed for {file_path.name}: {e}")
            
        return None
    
    def _extract_jpeg_from_raw(self, file_path: Path, target_size: int) -> Optional[Image.Image]:
        """Estrai JPEG completo da RAW usando ExifTool (legge stdout direttamente)."""
        for tag in ('-JpgFromRaw', '-OtherImage'):
            try:
                result = subprocess.run(
                    ['exiftool', '-b', tag, str(file_path)],
                    capture_output=True, timeout=30
                )
                if result.returncode == 0 and result.stdout and len(result.stdout) > 1000:
                    try:
                        thumbnail = Image.open(BytesIO(result.stdout)).convert('RGB')
                        if max(thumbnail.size) > target_size:
                            thumbnail.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
                        logger.debug(f"ExifTool {tag}: {file_path.name} → {thumbnail.size}")
                        return thumbnail
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"ExifTool {tag} error for {file_path.name}: {e}")

        logger.debug(f"ExifTool JPEG from RAW failed for {file_path.name}")
        return None
    
    def _extract_full_image_resized(self, file_path: Path, target_size: int) -> Optional[Image.Image]:
        """Estrai e ridimensiona immagine completa (per JPEG, TIFF, etc.)"""
        try:
            # Apri immagine direttamente con PIL
            with Image.open(file_path) as img:
                img = img.convert('RGB')
                w, h = img.size
                
                # Ridimensiona solo se necessario
                max_side = max(w, h)
                if max_side > target_size:
                    scale = target_size / max_side
                    new_size = (int(w * scale), int(h * scale))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                logger.debug(f"Full image resized: {file_path.name} → {img.size}")
                return img.copy()
                
        except Exception as e:
            logger.debug(f"Full image resize failed for {file_path.name}: {e}")
            return None

    # ===== RESTO DEI METODI ORIGINALI (invariati) =====
    
    def _extract_with_exiftool(self, file_path: Path) -> Dict[str, Any]:
        """Estrazione EXIF + XMP embedded con ExifTool JSON - VERSIONE RESILIENTE"""
        try:
            # Flag ottimizzati per mapping multi-brand:
            # -G = Include group names (formato standard EXIF:Make)
            # -a = Include tutti i tag duplicati  
            # -s = Nome tag abbreviato
            # -e = Includi anche tag vuoti/error
            result = subprocess.run([
                'exiftool', '-json', '-G', '-a', '-s', '-e', str(file_path)
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout:
                data_list = json.loads(result.stdout)
                if data_list:
                    return data_list[0]  # ExifTool ritorna sempre una lista
            
            logger.warning(f"ExifTool extraction failed for {file_path.name}")
            return {}
            
        except subprocess.TimeoutExpired:
            logger.error(f"ExifTool timeout for {file_path.name}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"ExifTool JSON parse error for {file_path.name}: {e}")
            return {}
        except Exception as e:
            logger.error(f"ExifTool error for {file_path.name}: {e}")
            return {}
    
    def _extract_xmp_sidecar(self, raw_path: Path) -> Dict[str, Any]:
        """Estrazione XMP sidecar per file RAW - VERSIONE RESILIENTE"""
        xmp_path = raw_path.with_suffix('.xmp')
        
        if not xmp_path.exists():
            # Prova con maiuscolo
            xmp_path = raw_path.with_suffix('.XMP')
            
        if xmp_path.exists():
            try:
                # Flag coerenti con _extract_with_exiftool
                result = subprocess.run([
                    'exiftool', '-json', '-G', '-a', '-s', '-e', str(xmp_path)
                ], capture_output=True, text=True, timeout=15)
                
                if result.returncode == 0 and result.stdout:
                    data_list = json.loads(result.stdout)
                    if data_list:
                        logger.debug(f"XMP sidecar estratto: {xmp_path.name}")
                        return data_list[0]
                        
            except Exception as e:
                logger.debug(f"Errore estrazione XMP sidecar {xmp_path.name}: {e}")
        
        return {}
    
    def _merge_xmp_data(self, exif_data: Dict, xmp_sidecar_data: Dict) -> Dict[str, Any]:
        """Merge intelligente dati XMP con priorità sidecar"""
        merged = exif_data.copy()
        
        # Sovrascrivi con dati sidecar (priorità alta)
        for key, value in xmp_sidecar_data.items():
            if value:  # Solo se non vuoto
                merged[key] = value
                
        return merged
    
    def _map_all_fields(self, xmp_data: Dict) -> Dict[str, Any]:
        """
        MAPPING UNIVERSALE con strategia GET_VAL a cascata
        Supporta tutte le marche: Olympus, Canon, Nikon, Sony, DJI, etc.
        """
        mapped = {}
        
        def get_val(keys: list):
            """Cerca la prima chiave disponibile con fallback multi-prefisso"""
            for k in keys:
                # Prova prefissi in ordine di priorità (incluso XMP-dc per Dublin Core)
                for prefix in ['XMP-dc:', 'XMP-lr:', 'XMP-xmp:', 'XMP-exif:', 'XMP:', 'EXIF:', 'IFD0:', 'Main:', 'Composite:', 'IPTC:', '']:
                    full_key = f"{prefix}{k}" if prefix else k
                    if full_key in xmp_data and xmp_data[full_key]:
                        return xmp_data[full_key]
            return None
        
        # ===== IDENTIFICAZIONE CAMERA & LENS (Multi-brand) =====
        mapped['camera_make'] = get_val(['Make', 'Manufacturer'])
        mapped['camera_model'] = get_val(['Model'])
        mapped['lens_model'] = get_val(['LensModel', 'LensType', 'LensID', 'Lens', 'LensInfo'])
        
        # ===== DIMENSIONI (Risolve problema campi vuoti) =====
        mapped['width'] = self._parse_int(get_val(['ExifImageWidth', 'ImageWidth', 'RelatedImageWidth']))
        mapped['height'] = self._parse_int(get_val(['ExifImageHeight', 'ImageHeight', 'RelatedImageHeight']))
        
        # Gestione speciale Composite:ImageSize formato "5184x3888"
        if not mapped['width'] or not mapped['height']:
            composite_size = get_val(['ImageSize'])
            if composite_size and 'x' in str(composite_size):
                try:
                    parts = str(composite_size).split('x')
                    if not mapped['width']:
                        mapped['width'] = self._parse_int(parts[0])
                    if not mapped['height']:
                        mapped['height'] = self._parse_int(parts[1])
                except:
                    pass
        
        # ===== PARAMETRI FOTOGRAFICI =====
        mapped['focal_length'] = self._parse_numeric(get_val(['FocalLength']))
        mapped['focal_length_35mm'] = self._parse_numeric(get_val(['FocalLengthIn35mmFormat', 'ScaleFactor35efl', 'FocalLengthIn35mmFilm']))
        mapped['aperture'] = self._parse_numeric(get_val(['FNumber', 'ApertureValue', 'Aperture']))
        mapped['iso'] = self._parse_int(get_val(['ISO', 'ISOSpeedRatings']))
        
        # Shutter speed con doppio formato
        raw_shutter = get_val(['ExposureTime', 'ShutterSpeed', 'ShutterSpeedValue'])
        mapped['shutter_speed'] = self._format_shutter_speed(raw_shutter)
        mapped['shutter_speed_decimal'] = self._parse_shutter_speed_decimal(raw_shutter)
        
        # ===== IMPOSTAZIONI ESPOSIZIONE =====
        mapped['exposure_mode'] = self._parse_exposure_mode(get_val(['ExposureMode']))
        mapped['exposure_bias'] = self._parse_numeric(get_val(['ExposureBias', 'ExposureCompensation']))
        mapped['metering_mode'] = get_val(['MeteringMode'])
        mapped['white_balance'] = get_val(['WhiteBalance'])
        mapped['flash_used'] = self._parse_flash_used(get_val(['Flash']))
        mapped['flash_mode'] = get_val(['FlashMode'])
        mapped['color_space'] = get_val(['ColorSpace'])
        mapped['orientation'] = self._parse_orientation(get_val(['Orientation']))
        
        # ===== DATE E ORA =====
        mapped['datetime_original'] = self._normalize_datetime(get_val(['DateTimeOriginal', 'CreateDate']))
        mapped['datetime_digitized'] = self._normalize_datetime(get_val(['DateTimeDigitized']))
        mapped['datetime_modified'] = self._normalize_datetime(get_val(['FileModifyDate']))
        
        # ===== GPS =====
        lat_ref = get_val(['GPSLatitudeRef'])
        lon_ref = get_val(['GPSLongitudeRef'])
        mapped['gps_latitude'] = self._parse_gps_coordinate(get_val(['GPSLatitude']), lat_ref)
        mapped['gps_longitude'] = self._parse_gps_coordinate(get_val(['GPSLongitude']), lon_ref)
        mapped['gps_altitude'] = self._parse_numeric(get_val(['GPSAltitude']))
        mapped['gps_direction'] = self._parse_numeric(get_val(['GPSDirection', 'GPSImgDirection']))
        
        # ===== GPS LOCATION =====
        mapped['gps_city'] = get_val(['City'])
        mapped['gps_state'] = get_val(['State', 'Province'])
        mapped['gps_country'] = get_val(['Country', 'Country-PrimaryLocationName'])
        mapped['gps_location'] = get_val(['Location', 'SubLocation', 'Sub-location'])
        
        # ===== CALCOLI DERIVATI =====
        if mapped.get('width') and mapped.get('height'):
            mapped['aspect_ratio'] = round(mapped['width'] / mapped['height'], 3)
            mapped['megapixels'] = round((mapped['width'] * mapped['height']) / 1000000, 2)
        
        # ===== FILE INFO =====
        mapped['file_size'] = self._parse_int(get_val(['FileSize']))
        mapped['file_format'] = self._extract_format(get_val(['FileType']))
        
        # ===== AUTHOR/COPYRIGHT =====
        mapped['artist'] = get_val(['Artist', 'Creator'])
        mapped['copyright'] = get_val(['Copyright', 'Rights'])
        mapped['software'] = get_val(['Software'])
        
        # ===== METADATA =====
        mapped['title'] = get_val(['Title', 'ObjectName'])
        mapped['description'] = get_val(['Description', 'Caption-Abstract'])
        
        # ===== LIGHTROOM/XMP =====
        # Rating con priorità Adobe-first: XMP-xmp > XMP-lr > EXIF > Microsoft > Altri
        mapped['lr_rating'] = self._extract_rating_with_priority(xmp_data)
        # Color Label con priorità Adobe-first
        mapped['color_label'] = self._extract_color_label_with_priority(xmp_data)
        mapped['lr_instructions'] = get_val(['Instructions'])
        
        # ===== KEYWORDS/TAGS =====
        keywords_raw = get_val(['Keywords', 'Subject'])
        mapped['tags'] = self._extract_keywords_as_json(keywords_raw)
        
        # ===== EXIF COMPLETO JSON =====
        mapped['exif_json'] = json.dumps(xmp_data, ensure_ascii=False)
        
        # Pulizia finale - rimuovi None/vuoti
        return {k: v for k, v in mapped.items() if v is not None and v != ''}
    
    def _extract_keywords_as_json(self, keywords_raw) -> Optional[str]:
        """
        Converte keywords XMP in formato JSON per database
        
        Supporta:
        - JSON: ["tag1", "tag2"]
        - CSV: "tag1, tag2, tag3"
        - Lista: [tag1, tag2]
        """
        if not keywords_raw:
            return None
            
        try:
            # Se è già lista Python
            if isinstance(keywords_raw, list):
                keywords_list = keywords_raw
            # Se è JSON string
            elif isinstance(keywords_raw, str) and keywords_raw.strip().startswith('['):
                keywords_list = json.loads(keywords_raw)
            # Se è CSV string
            else:
                keywords_list = [k.strip() for k in str(keywords_raw).split(',') if k.strip()]
            
            # Filtra e normalizza
            filtered = [str(k).strip() for k in keywords_list if str(k).strip()]
            
            if filtered:
                return json.dumps(filtered, ensure_ascii=False)
                
        except Exception as e:
            logger.debug(f"Keywords parsing failed: {e}")
            
        return None
    
    def _extract_format(self, file_type):
        """Estrae formato file pulito"""
        if not file_type:
            return None
        # Converte "JPEG" in "jpg", "TIFF" in "tif", etc.
        format_map = {
            'JPEG': 'jpg',
            'TIFF': 'tif', 
            'DNG': 'dng',
            'PNG': 'png',
            'ORF': 'orf',
            'CR2': 'cr2',
            'NEF': 'nef',
            'ARW': 'arw'
        }
        return format_map.get(file_type.upper(), file_type.lower())
    
    def _format_shutter_speed(self, value):
        """Formatta shutter speed come stringa leggibile"""
        if not value:
            return None
        try:
            # Se è già una stringa formattata (es. "1/250"), restituiscila
            if isinstance(value, str) and '/' in value:
                return value
            
            # Se è un decimale, convertilo in frazione
            decimal_value = float(value)
            if decimal_value >= 1:
                return f"{decimal_value:.1f}s"
            else:
                # Converti in frazione (es. 0.004 -> "1/250")
                denominator = round(1 / decimal_value)
                return f"1/{denominator}"
        except:
            return str(value)
    
    def _parse_exposure_mode(self, exposure_str) -> Optional[int]:
        """Converte exposure mode da stringa EXIF a numero standard"""
        if not exposure_str:
            return None
        
        exposure_str = str(exposure_str).lower()
        
        # Mapping EXIF standard
        exposure_map = {
            'auto': 0,
            'manual': 1,
            'aperture priority': 2,  
            'aperture-priority': 2,
            'shutter priority': 3,
            'shutter-priority': 3,
            'program': 4,
            'action': 5,
            'portrait': 6,
            'landscape': 7
        }
        
        return exposure_map.get(exposure_str)
    
    def _parse_orientation(self, orientation_str) -> Optional[int]:
        """Converte orientation da stringa EXIF a numero standard (1-8)"""
        if not orientation_str:
            return None

        # Prova parsing diretto prima (ExifTool con flag -# o valori numerici)
        try:
            val = int(float(str(orientation_str)))
            if 1 <= val <= 8:
                return val
        except (ValueError, TypeError):
            pass

        s = str(orientation_str).lower()

        # Controlla pattern specifici prima di quelli generici (ordine critico)
        if 'mirror horizontal and rotate 270' in s:
            return 5  # Specchio orizzontale + 270° CW
        elif 'mirror horizontal and rotate 90' in s:
            return 7  # Specchio orizzontale + 90° CW
        elif 'rotate 270' in s:
            return 8  # 270° CW (identico a 90° CCW per display)
        elif 'rotate 180' in s:
            return 3  # 180°
        elif 'rotate 90' in s:
            return 6  # 90° CW
        elif 'mirror horizontal' in s or 'flip horizontal' in s:
            return 2  # Specchio orizzontale
        elif 'mirror vertical' in s or 'flip vertical' in s:
            return 4  # Specchio verticale
        elif 'horizontal' in s and 'normal' in s:
            return 1  # Normale
        elif 'right' in s:
            return 6  # Compatibilità short-form ExifTool ("right-top")
        elif 'left' in s:
            return 8  # Compatibilità short-form ExifTool ("left-bottom")

        return 1  # Default: normale
    
    def _parse_numeric(self, value) -> Optional[float]:
        """Converte valore in float"""
        if not value:
            return None
        try:
            # Rimuovi unità di misura comuni
            if isinstance(value, str):
                value = value.replace('mm', '').replace(' ', '').replace('°', '')
            return float(value)
        except:
            return None
    
    def _parse_int(self, value) -> Optional[int]:
        """Converte valore in int con supporto per formati speciali"""
        if not value:
            return None
        try:
            # Se è già un numero
            return int(float(value))
        except:
            # Gestisce formato "5184x3888" di Composite:ImageSize
            if isinstance(value, str) and 'x' in value:
                # Per width prende il primo numero, per height il secondo
                # Questo viene gestito nel mapping specifico
                return None
            return None
    
    def _extract_for_bw_analysis(self, file_path: Path) -> Optional[Image.Image]:
        """
        Estrazione VELOCE e SICURA specificamente per analisi B/N.
        Usa thumbnail embedded per RAW (istantanea), fallback sicuro.
        Non passa per il sistema di profili - ottimizzata per velocità.
        """
        try:
            if self.is_raw_file(file_path):
                # === FILE RAW: thumbnail embedded (velocissima) ===
                try:
                    import rawpy
                    with rawpy.imread(str(file_path)) as raw:
                        try:
                            # Prova thumbnail embedded (JPEG preview nel RAW)
                            thumb = raw.extract_thumb()
                            if thumb.format == rawpy.ThumbFormat.JPEG:
                                from io import BytesIO
                                img = Image.open(BytesIO(thumb.data))
                                logger.debug(f"⚡ B/N analysis: thumbnail JPEG embedded per {file_path.name}")
                                return img
                            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                                img = Image.fromarray(thumb.data)
                                logger.debug(f"⚡ B/N analysis: thumbnail bitmap embedded per {file_path.name}")
                                return img
                        except rawpy.LibRawNoThumbnailError:
                            pass  # Fallback al postprocess veloce

                        # Fallback: postprocess veloce con half_size
                        rgb = raw.postprocess(
                            use_camera_wb=True,
                            half_size=True,  # 4x più veloce
                            output_bps=8
                        )
                        logger.debug(f"⚡ B/N analysis: rawpy half_size per {file_path.name}")
                        return Image.fromarray(rgb)

                except ImportError:
                    logger.warning("rawpy non disponibile per analisi B/N")
                    return None
                except Exception as e:
                    logger.debug(f"Errore rawpy per B/N: {e}")
                    return None
            else:
                # === FILE NON-RAW: PIL diretto ===
                img = Image.open(file_path)
                logger.debug(f"⚡ B/N analysis: PIL diretto per {file_path.name}")
                return img

        except Exception as e:
            logger.error(f"Errore estrazione per B/N analysis: {e}")
            return None

    def _is_monochrome_image(self, image: Image.Image) -> bool:
        """
        Rileva se un'immagine è in bianco e nero
        Analizza la varianza dei canali RGB per determinare se è monocromatica
        """
        try:
            # Converti in RGB se necessario
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Ridimensiona per velocità di analisi
            sample_img = image.resize((50, 50), Image.Resampling.LANCZOS)
            
            # Converti in array numpy per analisi
            import numpy as np
            arr = np.array(sample_img)
            
            # Estrai canali R, G, B
            r_channel = arr[:, :, 0].flatten()
            g_channel = arr[:, :, 1].flatten()
            b_channel = arr[:, :, 2].flatten()
            
            # Calcola differenze tra canali
            rg_diff = np.abs(r_channel.astype(float) - g_channel.astype(float))
            rb_diff = np.abs(r_channel.astype(float) - b_channel.astype(float))
            gb_diff = np.abs(g_channel.astype(float) - b_channel.astype(float))
            
            # Calcola varianza media tra i canali
            avg_variance = (np.mean(rg_diff) + np.mean(rb_diff) + np.mean(gb_diff)) / 3
            
            # Soglia empirica: se varianza < 3, probabilmente B/N
            is_bw = avg_variance < 3.0
            
            logger.info(f"🔬 Analisi B/N dettagliata - Varianza: {avg_variance:.2f}, B/N: {is_bw}")
            return is_bw
            
        except Exception as e:
            logger.debug(f"Errore analisi B/N: {e}")
            return False
    
    def _parse_shutter_speed_decimal(self, shutter_speed) -> Optional[float]:
        """Converte shutter speed in formato decimale"""
        if not shutter_speed:
            return None
        try:
            shutter_str = str(shutter_speed)
            
            # Format "1/250" 
            if '/' in shutter_str:
                num, den = shutter_str.split('/')
                return float(num) / float(den)
            
            # Format "1/250 s"
            if ' s' in shutter_str:
                shutter_str = shutter_str.replace(' s', '')
                
            # Format diretto "0.004"
            return float(shutter_str)
            
        except:
            return None
    
    def _parse_flash_used(self, flash_value) -> Optional[bool]:
        """Determina se flash è stato utilizzato"""
        if flash_value is None:
            return None
        
        try:
            # Se è un numero, usa il bit 0 per determinare se fired
            flash_int = int(flash_value)
            return bool(flash_int & 1)
        except:
            # Se è una stringa, analizza il contenuto
            flash_str = str(flash_value).lower()
            
            # Indicatori di flash NON utilizzato
            no_flash_indicators = [
                'no flash', 'off', 'did not fire', 'no flash function',
                'flash not fired', 'disabled', 'not used'
            ]
            
            # Indicatori di flash utilizzato  
            flash_indicators = [
                'fired', 'on', 'used', 'triggered', 'flash fired',
                'compulsory flash mode', 'auto flash mode'
            ]
            
            # Controlla indicatori negativi
            for indicator in no_flash_indicators:
                if indicator in flash_str:
                    return False
            
            # Controlla indicatori positivi
            for indicator in flash_indicators:
                if indicator in flash_str:
                    return True
            
            return None
    
    def _parse_gps_coordinate(self, gps_value, ref=None) -> Optional[float]:
        """Converte coordinata GPS in decimali (supporta decimale e DMS ExifTool).

        Gestisce il formato DMS di ExifTool: "41 deg 3' 14.70""
        e applica il segno corretto in base al riferimento (S/W → negativo).
        """
        if not gps_value:
            return None
        try:
            import re

            decimal = None

            # Se già in formato numerico
            if isinstance(gps_value, (int, float)):
                decimal = float(gps_value)

            elif isinstance(gps_value, str):
                gps_str = gps_value.strip()

                # Formato DMS ExifTool: "41 deg 3' 14.70""
                dms_match = re.match(
                    r'(\d+(?:\.\d+)?)\s+deg\s+(\d+(?:\.\d+)?)[\'′]\s*([\d.]+)[\"″]?',
                    gps_str
                )
                if dms_match:
                    d = float(dms_match.group(1))
                    m = float(dms_match.group(2))
                    s = float(dms_match.group(3))
                    decimal = d + m / 60.0 + s / 3600.0
                else:
                    # Prova come valore decimale diretto
                    decimal = float(gps_str)

            if decimal is None:
                return None

            # Applica segno in base al riferimento emisferiale (S o W → negativo)
            if ref and str(ref).strip().upper() in ('S', 'W'):
                decimal = -abs(decimal)

            return decimal

        except:
            pass
        return None
    
    def _normalize_datetime(self, dt_value) -> Optional[str]:
        """Normalizza formato datetime"""
        if not dt_value:
            return None
        
        try:
            # Normalizza formato per database (ISO format preferred)
            dt_str = str(dt_value)
            # Replace formato EXIF "YYYY:MM:DD HH:MM:SS" con ISO "YYYY-MM-DD HH:MM:SS"
            if ':' in dt_str and len(dt_str) >= 10:
                parts = dt_str.split(' ')
                if len(parts) >= 1:
                    date_part = parts[0].replace(':', '-')
                    if len(parts) > 1:
                        return f"{date_part} {parts[1]}"
                    return date_part
            return dt_str
        except:
            return str(dt_value)
    
    def _parse_rating(self, rating_raw) -> Optional[int]:
        """Converte rating in intero 1-5"""
        if not rating_raw:
            return None
        try:
            rating = int(float(rating_raw))
            return rating if 1 <= rating <= 5 else None
        except:
            return None

    def _extract_rating_with_priority(self, xmp_data: Dict) -> Optional[int]:
        """
        Estrae rating con priorità definita per gestire immagini processate da software diversi.

        Ordine di priorità (Adobe-first):
        1. XMP-xmp:Rating - Standard Adobe (Lightroom, Photoshop, Bridge)
        2. XMP-lr:Rating - Lightroom specifico
        3. EXIF:Rating - Embedded nella foto originale
        4. XMP-microsoft:Rating - Windows
        5. Qualsiasi altro campo Rating - Fallback generico
        """
        # Priorità 1: Adobe XMP standard
        rating = self._parse_rating(xmp_data.get('XMP-xmp:Rating'))
        if rating is not None:
            logger.debug(f"Rating trovato in XMP-xmp:Rating = {rating}")
            return rating

        # Priorità 2: Lightroom specifico
        rating = self._parse_rating(xmp_data.get('XMP-lr:Rating'))
        if rating is not None:
            logger.debug(f"Rating trovato in XMP-lr:Rating = {rating}")
            return rating

        # Priorità 3: EXIF embedded
        rating = self._parse_rating(xmp_data.get('EXIF:Rating'))
        if rating is not None:
            logger.debug(f"Rating trovato in EXIF:Rating = {rating}")
            return rating

        # Priorità 4: Microsoft/Windows
        rating = self._parse_rating(xmp_data.get('XMP-microsoft:Rating'))
        if rating is not None:
            logger.debug(f"Rating trovato in XMP-microsoft:Rating = {rating}")
            return rating

        # Priorità 5: Fallback - cerca qualsiasi campo che termina con :Rating
        for key, value in xmp_data.items():
            if key.endswith(':Rating') or key == 'Rating':
                rating = self._parse_rating(value)
                if rating is not None:
                    logger.debug(f"Rating trovato in {key} = {rating}")
                    return rating

        return None

    def _extract_color_label_with_priority(self, xmp_data: Dict) -> Optional[str]:
        """
        Estrae color label con priorità definita per gestire immagini processate da software diversi.

        Ordine di priorità (Adobe-first):
        1. XMP-xmp:Label - Standard Adobe (Lightroom, Photoshop, Bridge)
        2. XMP-lr:Label - Lightroom specifico
        3. XMP-photoshop:Urgency - Photoshop (a volte usato per colori)
        4. Qualsiasi altro campo Label/ColorLabel - Fallback generico
        """
        # Priorità 1: Adobe XMP standard
        label = xmp_data.get('XMP-xmp:Label')
        if label:
            logger.debug(f"Color Label trovato in XMP-xmp:Label = {label}")
            return str(label)

        # Priorità 2: Lightroom specifico
        label = xmp_data.get('XMP-lr:Label')
        if label:
            logger.debug(f"Color Label trovato in XMP-lr:Label = {label}")
            return str(label)

        # Priorità 3: Photoshop
        label = xmp_data.get('XMP-photoshop:Urgency')
        if label:
            logger.debug(f"Color Label trovato in XMP-photoshop:Urgency = {label}")
            return str(label)

        # Priorità 4: Fallback - cerca qualsiasi campo Label o ColorLabel
        for key, value in xmp_data.items():
            if key.endswith(':Label') or key.endswith(':ColorLabel') or key in ['Label', 'ColorLabel']:
                if value:
                    logger.debug(f"Color Label trovato in {key} = {value}")
                    return str(value)

        return None

    def is_raw_file(self, file_path: Path) -> bool:
        """Determina se il file è RAW"""
        raw_extensions = {
            '.cr2', '.cr3', '.crw',  # Canon
            '.nef', '.nrw',          # Nikon
            '.arw', '.srf', '.sr2',  # Sony
            '.orf',                  # Olympus
            '.raf',                  # Fujifilm
            '.rw2',                  # Panasonic
            '.pef', '.ptx',          # Pentax
            '.raw',                  # Generic
            '.dng',                  # Adobe Digital Negative
            '.3fr',                  # Hasselblad
            '.iiq',                  # Phase One
            '.rwl', '.x3f'          # Altri
        }
        return file_path.suffix.lower() in raw_extensions
    
    def get_raw_info(self, raw_path: Path) -> Dict[str, Any]:
        """Informazioni base sul formato RAW"""
        ext = raw_path.suffix.lower()
        
        raw_brands = {
            '.cr2': 'Canon', '.cr3': 'Canon', '.crw': 'Canon',
            '.nef': 'Nikon', '.nrw': 'Nikon',
            '.arw': 'Sony', '.srf': 'Sony', '.sr2': 'Sony',
            '.orf': 'Olympus',
            '.raf': 'Fujifilm',
            '.rw2': 'Panasonic',
            '.pef': 'Pentax', '.ptx': 'Pentax',
            '.dng': 'Adobe',
            '.3fr': 'Hasselblad',
            '.iiq': 'Phase One',
        }
        
        return {
            'brand': raw_brands.get(ext, 'Unknown'),
            'type': 'TIFF-based' if ext in ['.cr2', '.nef', '.orf'] else 'Proprietary',
            'embedded_thumb': True,  # Quasi tutti i RAW hanno thumbnail embedded
            'optimal_size': 512  # Size ottimale default
        }

# Compatibilità
RAW_PROCESSOR_AVAILABLE = True
