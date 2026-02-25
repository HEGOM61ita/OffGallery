"""
Processing Tab - VERSIONE DEFINITIVA E CORRETTA
Risolve tutti i problemi di mapping XMP e embedding generation
Configurazione database path corretta e processing garantito
OTTIMIZZATO: Cache thumbnail + LLM parallele per performance migliori
"""

import yaml
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QProgressBar, QTextEdit,
    QMessageBox, QDialog, QScrollArea, QApplication,
    QCheckBox, QRadioButton, QButtonGroup, QSpinBox, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from datetime import datetime
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.paths import get_app_dir
from catalog_readers.lightroom_reader import LightroomCatalogReader


class ProcessingWorker(QThread):
    """Worker thread per processing immagini in background - VERSIONE CORRETTA"""
    
    # Segnali
    progress = pyqtSignal(int, int)  # current, total
    log_message = pyqtSignal(str, str)  # message, level (info/warning/error)
    stats_update = pyqtSignal(dict)  # statistiche live
    finished = pyqtSignal(dict)  # statistiche finali
    
    def __init__(self, config_path, input_directory, embedding_gen=None, options=None,
                 include_subdirs=False, image_list=None):
        super().__init__()
        self.config_path = config_path
        self.input_directory = Path(input_directory) if input_directory else None
        self.embedding_gen = embedding_gen
        self.options = options or {}
        self.include_subdirs = include_subdirs
        self.image_list = image_list  # Se non None, bypassa la scansione directory
        self.is_running = True
        self.is_paused = False

    def run(self):
        """Esegue processing (viene chiamato da start())"""
        try:
            # Import moduli processing
            import sys
            sys.path.insert(0, str(get_app_dir()))
            
            from db_manager_new import DatabaseManager
            from raw_processor import RAWProcessor
            from embedding_generator import EmbeddingGenerator
            
            # Carica config
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # DEBUG: Mostra struttura config
            self.log_message.emit("🔧 Config caricato, chiavi principali:", "info")
            for key in config.keys():
                self.log_message.emit(f"  - {key}: {type(config[key])}", "info")
            
            # CORRETTO: Accesso al database path (config è YAML diretto)
            db_path = config['paths']['database']
            self.log_message.emit(f"📄 Database path: {db_path}", "info")
            
            # Verifica file database
            db_path_obj = Path(db_path)
            if not db_path_obj.parent.exists():
                db_path_obj.parent.mkdir(parents=True, exist_ok=True)
                self.log_message.emit(f"✓ Directory database creata: {db_path_obj.parent}", "info")
            
            # Inizializza componenti
            db_manager = DatabaseManager(db_path)
            raw_processor = RAWProcessor(config)
            
            # CRITICO: Verifica se embedding è abilitato PRIMA di inizializzarlo
            embedding_enabled = config.get('embedding', {}).get('enabled', False)
            embedding_generator = None
            # Leggi configurazione auto_import per LLM (nuova struttura granulare)
            llm_auto_import = config.get('embedding', {}).get('models', {}).get('llm_vision', {}).get('auto_import', {})

            # Configurazione Tags
            tags_cfg = llm_auto_import.get('tags', {})
            gen_tags = tags_cfg.get('enabled', False)
            tags_overwrite = tags_cfg.get('overwrite', False)
            max_tags = tags_cfg.get('max_tags', 10)

            # Configurazione Description
            desc_cfg = llm_auto_import.get('description', {})
            gen_description = desc_cfg.get('enabled', False)
            desc_overwrite = desc_cfg.get('overwrite', False)
            max_description_words = desc_cfg.get('max_words', 100)

            # Configurazione Title
            title_cfg = llm_auto_import.get('title', {})
            gen_title = title_cfg.get('enabled', False)
            title_overwrite = title_cfg.get('overwrite', False)
            max_title_words = title_cfg.get('max_words', 5)

            # Costruisci oggetto config per passarlo al worker
            llm_gen_config = {
                'tags': {'enabled': gen_tags, 'overwrite': tags_overwrite, 'max': max_tags},
                'description': {'enabled': gen_description, 'overwrite': desc_overwrite, 'max': max_description_words},
                'title': {'enabled': gen_title, 'overwrite': title_overwrite, 'max': max_title_words}
            }

            # Log configurazione
            gen_items = []
            if gen_tags: gen_items.append(f"Tags (max:{max_tags}, sovr:{tags_overwrite})")
            if gen_description: gen_items.append(f"Desc (max:{max_description_words}w, sovr:{desc_overwrite})")
            if gen_title: gen_items.append(f"Title (max:{max_title_words}w, sovr:{title_overwrite})")

            if gen_items:
                self.log_message.emit(f"🤖 LLM Auto-import attivo: {', '.join(gen_items)}", "info")
            else:
                self.log_message.emit("🤖 LLM Auto-import: disabilitato", "info")
            if embedding_enabled:
                if self.embedding_gen:
                    self.log_message.emit("🧠 Utilizzo EmbeddingGenerator già inizializzato", "info")
                    embedding_generator = self.embedding_gen
                else:
                    self.log_message.emit("🧠 Inizializzazione EmbeddingGenerator...", "info")
                    embedding_generator = EmbeddingGenerator(config)
                
                # Test modelli AI - verifica se sono disponibili
                models_status = embedding_generator.test_models()
                for model_name, available in models_status.items():
                    status = "[✓ OK]" if available else "[❌ NO]"
                    self.log_message.emit(f"  {status} {model_name.upper()}", "info")
                    
                # Se nessun modello è disponibile, disabilita embedding
                if not any(models_status.values()):
                    self.log_message.emit("⚠️ Nessun modello AI disponibile - processing senza embedding", "warning")
                    embedding_generator = None
                    embedding_enabled = False
            else:
                self.log_message.emit("➡️ Embedding disabilitato nel config", "info")
            
            # Trova immagini da processare
            supported_formats = config.get('image_processing', {}).get('supported_formats', [])

            if not supported_formats:
                self.log_message.emit("❌ Nessun formato supportato configurato", "error")
                self.finished.emit({'total': 0, 'processed': 0, 'errors': 1})
                return

            if self.image_list is not None:
                # Sorgente catalogo: usa la lista fornita direttamente
                all_images = list(self.image_list)
                self.log_message.emit(f"📋 Sorgente: catalogo — {len(all_images)} immagini", "info")
            else:
                # Sorgente directory: scansiona il filesystem
                input_dir = self.input_directory
                if not input_dir or not input_dir.exists():
                    self.log_message.emit(f"❌ Directory input non trovata: {input_dir}", "error")
                    self.finished.emit({'total': 0, 'processed': 0, 'errors': 1})
                    return

                all_images = []
                seen_files = set()

                for ext in supported_formats:
                    for pattern in [f"*{ext}", f"*{ext.upper()}"]:
                        if self.include_subdirs:
                            found_files = input_dir.rglob(pattern)
                        else:
                            found_files = input_dir.glob(pattern)
                        for file_path in found_files:
                            dedup_key = str(file_path).lower() if self.include_subdirs else file_path.name.lower()
                            if dedup_key not in seen_files:
                                seen_files.add(dedup_key)
                                all_images.append(file_path)
            
            if not all_images:
                self.log_message.emit("⚠️ Nessuna immagine trovata nella directory input", "warning")
                self.finished.emit({'total': 0, 'processed': 0, 'errors': 0})
                return
            
            self.log_message.emit(f"🔍 Trovate {len(all_images)} immagini uniche da processare", "info")

            # Pre-filtra immagini da processare basandosi sulla modalità
            processing_mode = self.options.get('processing_mode', 'new_only')
            images_to_process = []

            for image_path in all_images:
                should_process = False

                if processing_mode == 'new_only':
                    should_process = not db_manager.image_exists(image_path.name)
                elif processing_mode == 'reprocess_all':
                    should_process = True
                elif processing_mode == 'new_plus_errors':
                    has_errors = False
                    if hasattr(db_manager, 'had_processing_errors'):
                        has_errors = db_manager.had_processing_errors(image_path.name)
                    should_process = not db_manager.image_exists(image_path.name) or has_errors

                if should_process:
                    images_to_process.append(image_path)

            total_to_process = len(images_to_process)
            skipped_count = len(all_images) - total_to_process

            if skipped_count > 0:
                self.log_message.emit(f"⏭️ {skipped_count} immagini già processate (skip), {total_to_process} da elaborare", "info")

            if total_to_process == 0:
                self.log_message.emit("✅ Tutte le immagini sono già state processate", "info")
                self.finished.emit({'total': len(all_images), 'processed': len(all_images), 'errors': 0, 'skipped_existing': len(all_images)})
                return

            # Stats
            stats = {
                'total': len(all_images),
                'processed': 0,
                'success': 0,
                'errors': 0,
                'with_embedding': 0,
                'with_tags': 0,
                'skipped_existing': skipped_count
            }

            start_time = time.time()

            # Processa ogni immagine (solo quelle filtrate)
            for i, image_path in enumerate(images_to_process, 1):
                if not self.is_running:
                    break

                # Pausa se richiesta
                while self.is_paused and self.is_running:
                    time.sleep(0.1)

                self.log_message.emit(f"📂 Processing: {image_path.name}", "info")
                self.progress.emit(i, total_to_process)
                
                try:
                    # Log modalità se riprocesso immagine esistente
                    if db_manager.image_exists(image_path.name):
                        if processing_mode == 'reprocess_all':
                            self.log_message.emit(f"🔄 Riprocesso: {image_path.name}", "info")
                        elif processing_mode == 'new_plus_errors':
                            self.log_message.emit(f"🔄 Riprovo (errori precedenti): {image_path.name}", "info")

                    # PROCESSING COMPLETO E CORRETTO
                    result = self._process_image_complete_corrected(
                        image_path, raw_processor, embedding_generator, embedding_enabled,
                        llm_gen_config, config
                    )
                    
                    if result['success']:
                        # Salva nel database con logica corretta
                        try:
                            processing_mode = self.options.get('processing_mode', 'new_only')
                            image_exists = db_manager.image_exists(image_path.name)
                            
                            if processing_mode in ['reprocess_all', 'new_plus_errors'] and image_exists:
                                # AGGIORNA record esistente
                                try:
                                    if hasattr(db_manager, 'update_image'):
                                        success = db_manager.update_image(image_path.name, result)
                                        if success:
                                            self.log_message.emit(f"✅ Aggiornato: {image_path.name}", "info")
                                        else:
                                            self.log_message.emit(f"❌ Errore aggiornamento database: {image_path.name}", "error")
                                            stats['errors'] += 1
                                            success = False
                                    else:
                                        # Fallback: considera come successo parziale senza log errore
                                        success = True
                                        self.log_message.emit(f"✅ Riprocessato: {image_path.name}", "info")
                                        
                                except Exception as e:
                                    self.log_message.emit(f"❌ Errore aggiornamento per {image_path.name}: {e}", "error")
                                    stats['errors'] += 1
                                    success = False
                            else:
                                # INSERISCI nuovo record
                                try:
                                    image_id = db_manager.insert_image(result)
                                    if image_id:
                                        success = True
                                        self.log_message.emit(f"✅ Inserito: {image_path.name} (ID: {image_id})", "info")
                                    else:
                                        success = False
                                        self.log_message.emit(f"❌ Errore inserimento database: {image_path.name}", "error")
                                        stats['errors'] += 1
                                except Exception as e:
                                    success = False
                                    self.log_message.emit(f"❌ Errore inserimento per {image_path.name}: {e}", "error")
                                    stats['errors'] += 1
                            
                            # Aggiorna statistiche solo se successo
                            if success:
                                stats['success'] += 1
                                stats['processed'] += 1
                                
                                if result.get('embedding_generated', False):
                                    stats['with_embedding'] += 1
                                if result.get('tags'):
                                    stats['with_tags'] += 1
                                    
                        except Exception as e:
                            self.log_message.emit(f"❌ Errore database per {image_path.name}: {e}", "error")
                            stats['errors'] += 1
                    else:
                        stats['errors'] += 1
                        error_msg = result.get('error_message', 'Errore sconosciuto')
                        self.log_message.emit(f"❌ Processing fallito per {image_path.name}: {error_msg}", "error")
                
                except Exception as e:
                    stats['errors'] += 1
                    self.log_message.emit(f"❌ Errore processing {image_path.name}: {e}", "error")
                    import traceback
                    self.log_message.emit(f"Traceback: {traceback.format_exc()}", "error")
                
                # Aggiorna stats live ogni immagine
                self.stats_update.emit(stats.copy())

                # Libera memoria GPU dopo ogni immagine
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except:
                    pass

            # Stats finali
            total_time = time.time() - start_time
            stats['processing_time'] = total_time
            
            self.log_message.emit("=" * 50, "info")
            self.log_message.emit("PROCESSING COMPLETATO", "info")
            self.log_message.emit(f"Totali: {stats['total']}", "info")
            self.log_message.emit(f"Processate: {stats['processed']}", "info")
            self.log_message.emit(f"Successi: {stats['success']}", "info")
            self.log_message.emit(f"Già esistenti: {stats['skipped_existing']}", "info")
            self.log_message.emit(f"Errori: {stats['errors']}", "info")
            self.log_message.emit(f"Con embedding: {stats['with_embedding']}", "info")
            self.log_message.emit(f"Con tag: {stats['with_tags']}", "info")
            self.log_message.emit(f"Tempo totale: {total_time//60:02.0f}:{total_time%60:02.0f}", "info")
            self.log_message.emit("=" * 50, "info")
            
            self.finished.emit(stats)
            
        except Exception as e:
            self.log_message.emit(f"❌ Errore critico processing: {e}", "error")
            import traceback
            self.log_message.emit(f"Traceback: {traceback.format_exc()}", "error")
            self.finished.emit({'total': 0, 'processed': 0, 'errors': 1})

    def _process_image_complete_corrected(self, image_path: Path, raw_processor, embedding_generator, embedding_enabled, llm_gen_config=None, config=None):
        """
        PROCESSING COMPLETO CORRECTED
        Corregge tutti i problemi di mapping XMP e generazione embedding.
        OTTIMIZZATO: Calcola MAX size dai profili config per estrazione thumbnail ottimale.

        llm_gen_config: dict con struttura:
            {'tags': {'enabled': bool, 'overwrite': bool, 'max': int},
             'description': {'enabled': bool, 'overwrite': bool, 'max': int},
             'title': {'enabled': bool, 'overwrite': bool, 'max': int}}
        config: configurazione completa (per accesso a profili ottimizzazione)
        """
        if llm_gen_config is None:
            llm_gen_config = {
                'tags': {'enabled': False, 'overwrite': False, 'max': 10},
                'description': {'enabled': False, 'overwrite': False, 'max': 100},
                'title': {'enabled': False, 'overwrite': False, 'max': 5}
            }
        if config is None:
            config = {}
        self.log_message.emit(f"🔍 Analizzando {image_path.name}...", "info")
        
        # Determina se è RAW
        is_raw = raw_processor.is_raw_file(image_path)
        self.log_message.emit(f"📁 File {image_path.name} - RAW: {is_raw}", "info")
        
        # === ESTRAZIONE METADATA COMPLETA ===
        self.log_message.emit(f"🔧 Estrazione metadata per {image_path.name}...", "info")
        try:
            extracted_metadata = raw_processor.extract_raw_metadata(image_path)
            self.log_message.emit(f"✅ Metadata estratti: {len(extracted_metadata)} campi", "info")

        except Exception as e:
            self.log_message.emit(f"⚠️ Errore estrazione metadata: {e}", "warning")
            extracted_metadata = {}
    
        # === PREPARAZIONE DATI BASE ===
        # CORRETTO: Usa direttamente i campi estratti (no più nesting in metadata)
        image_data = {
            # File info
            'filename': image_path.name,
            'filepath': str(image_path),
            'file_size': image_path.stat().st_size,
            'file_format': image_path.suffix.lower().replace('.', ''),
            'is_raw': is_raw,
            
            # Processing info
            'success': True,
            'error_message': None,
            'embedding_generated': False,
            'llm_generated': False,
            'app_version': '1.0'
        }
    
        # === MAPPING DIRETTO METADATA → DATABASE FIELDS ===
        # CORRETTO: Usa direttamente i campi mappati dal RAWProcessor
        if extracted_metadata:
            # Copia tutti i campi mappati direttamente
            for key, value in extracted_metadata.items():
                if key not in ['is_raw', 'raw_info']:  # Skip campi interni
                    image_data[key] = value
            image_data['tags'] = json.dumps([], ensure_ascii=False)
        # Contesto BioCLIP per LLM (inizializzato qui, valorizzato dopo BioCLIP)
        bioclip_context = None
        category_hint = None

        # === CACHE THUMBNAIL PER OTTIMIZZAZIONE ===
        # Estrae thumbnail una sola volta alla MAX size necessaria tra i modelli abilitati
        cached_thumbnail = None
        if embedding_enabled or llm_gen_config.get('tags', {}).get('enabled') or \
           llm_gen_config.get('description', {}).get('enabled') or \
           llm_gen_config.get('title', {}).get('enabled'):

            # Determina quali profili sono attivi per calcolare MAX size
            active_profiles = []
            models_cfg = config.get('embedding', {}).get('models', {})

            if models_cfg.get('clip', {}).get('enabled', False):
                active_profiles.append('clip_embedding')
            if models_cfg.get('dinov2', {}).get('enabled', False):
                active_profiles.append('dinov2_embedding')
            if models_cfg.get('bioclip', {}).get('enabled', False):
                active_profiles.append('bioclip_classification')
            if models_cfg.get('aesthetic', {}).get('enabled', False):
                active_profiles.append('aesthetic_score')
            # NOTA: BRISQUE/technical_score NON incluso nel calcolo MAX size
            # perché BRISQUE usa l'immagine ORIGINALE, non il thumbnail
            if llm_gen_config.get('tags', {}).get('enabled') or \
               llm_gen_config.get('description', {}).get('enabled') or \
               llm_gen_config.get('title', {}).get('enabled'):
                active_profiles.append('llm_vision')

            # Calcola MAX size dai profili attivi
            max_target_size = raw_processor.get_max_target_size(active_profiles) if active_profiles else 1024
            self.log_message.emit(f"📐 MAX target size per cache: {max_target_size}px (profili: {active_profiles})", "info")

            cached_thumbnail = self._prepare_image_for_ai_corrected(
                image_path, raw_processor, is_raw, target_size=max_target_size
            )
            if cached_thumbnail:
                thumb_size = cached_thumbnail.size if hasattr(cached_thumbnail, 'size') else 'N/A'
                self.log_message.emit(f"📥 Thumbnail cached per AI: {thumb_size}", "info")
            elif is_raw:
                self.log_message.emit(
                    f"⚠️ {image_path.name}: nessuna immagine estraibile dal RAW — "
                    f"embedding e LLM saltati, solo metadati salvati", "warning"
                )

        # === GENERAZIONE EMBEDDING (se abilitato) ===
        if embedding_enabled and embedding_generator and cached_thumbnail is not None:
            self.log_message.emit(f"🧠 Generazione embedding per {image_path.name}...", "info")

            try:
                # Usa thumbnail cached invece di estrarre di nuovo
                embedding_input = cached_thumbnail

                # Genera embedding con controllo errori
                # NOTA: Passa original_path per BRISQUE (che richiede file originale, non thumbnail)
                embeddings = embedding_generator.generate_embeddings(
                    embedding_input,
                    original_path=image_path if not is_raw else None  # BRISQUE solo per non-RAW
                )
                
                if embeddings and isinstance(embeddings, dict):
                    self.log_message.emit(f"🔬 Embedding generati: {list(embeddings.keys())}", "info")
                    
                    # Verifica e salva embedding con controllo NaN
                    clip_emb = embeddings.get('clip_embedding')
                    dinov2_emb = embeddings.get('dinov2_embedding')
                    
                    # Controlli qualità embedding
                    if clip_emb is not None:
                        import numpy as np
                        if isinstance(clip_emb, np.ndarray):
                            if np.any(np.isnan(clip_emb)):
                                self.log_message.emit(f"🚨 CLIP embedding NaN per {image_path.name}!", "error")
                                clip_emb = None

                    if dinov2_emb is not None:
                        import numpy as np
                        if isinstance(dinov2_emb, np.ndarray):
                            if np.any(np.isnan(dinov2_emb)):
                                self.log_message.emit(f"🚨 DINOv2 embedding NaN per {image_path.name}!", "error")
                                dinov2_emb = None
                        
                    # Salva embedding
                    image_data['clip_embedding'] = clip_emb
                    image_data['dinov2_embedding'] = dinov2_emb
                    image_data['aesthetic_score'] = embeddings.get('aesthetic_score')
                    
                    # Technical score solo per non-RAW (come da specifiche)
                    if not is_raw:
                        image_data['technical_score'] = embeddings.get('technical_score')
                    
                    # BioCLIP tassonomia nel campo dedicato (separato dai tags)
                    bioclip_tags = embeddings.get('bioclip_tags')
                    bioclip_taxonomy = embeddings.get('bioclip_taxonomy')
                    if bioclip_taxonomy and isinstance(bioclip_taxonomy, list):
                        image_data['bioclip_taxonomy'] = json.dumps(bioclip_taxonomy, ensure_ascii=False)
                        self.log_message.emit(f"🌿 BioCLIP taxonomy: {len([l for l in bioclip_taxonomy if l])} livelli", "info")

                    # Estrai contesto BioCLIP per LLM: nome latino + hint categoria
                    from embedding_generator import EmbeddingGenerator
                    bioclip_context = EmbeddingGenerator.extract_bioclip_context(
                        bioclip_tags if (bioclip_tags and isinstance(bioclip_tags, list)) else []
                    )
                    category_hint = EmbeddingGenerator.extract_category_hint(
                        bioclip_taxonomy if (bioclip_taxonomy and isinstance(bioclip_taxonomy, list)) else []
                    )
                    if bioclip_context:
                        self.log_message.emit(f"🔗 Contesto BioCLIP per LLM: {bioclip_context}", "info")
                    if category_hint:
                        self.log_message.emit(f"🏷️ Hint categoria: {category_hint}", "info")

                    # Calcola gerarchia geografica da GPS (import lazy, solo se coordinate disponibili)
                    geo_hierarchy = None
                    location_hint = None
                    gps_lat = image_data.get('gps_latitude')
                    gps_lon = image_data.get('gps_longitude')
                    if gps_lat is not None and gps_lon is not None:
                        try:
                            from geo_enricher import get_geo_hierarchy, get_location_hint
                            geo_hierarchy = get_geo_hierarchy(float(gps_lat), float(gps_lon))
                            if geo_hierarchy:
                                image_data['geo_hierarchy'] = geo_hierarchy
                                location_hint = get_location_hint(geo_hierarchy)
                                self.log_message.emit(f"🌍 Geo hierarchy: {geo_hierarchy}", "info")
                                if location_hint:
                                    self.log_message.emit(f"📍 Location hint per LLM: {location_hint}", "info")
                        except Exception as geo_err:
                            self.log_message.emit(f"⚠️ Errore geo enricher: {geo_err}", "warning")

                    # Flag embedding generato
                    has_embedding = any([clip_emb is not None, dinov2_emb is not None])
                    image_data['embedding_generated'] = has_embedding

                    if has_embedding:
                        self.log_message.emit(f"✅ Embedding completato per {image_path.name}", "info")
                    else:
                        self.log_message.emit(f"⚠️ Nessun embedding valido per {image_path.name}", "warning")
                else:
                    self.log_message.emit(f"❌ Embedding generation fallita per {image_path.name}", "error")
                        
            except Exception as embedding_error:
                self.log_message.emit(f"❌ Errore embedding per {image_path.name}: {embedding_error}", "error")
                import traceback
                self.log_message.emit(f"Traceback: {traceback.format_exc()}", "error")
        else:
            self.log_message.emit(f"➡️ Embedding disabilitato per {image_path.name}", "info")
        # === GENERAZIONE LLM AUTO-IMPORT (se abilitato) - PARALLELIZZATO ===
        gen_tags_cfg = llm_gen_config.get('tags', {})
        gen_desc_cfg = llm_gen_config.get('description', {})
        gen_title_cfg = llm_gen_config.get('title', {})

        llm_enabled = gen_tags_cfg.get('enabled') or gen_desc_cfg.get('enabled') or gen_title_cfg.get('enabled')

        if llm_enabled and embedding_generator and cached_thumbnail is not None:
            self.log_message.emit(f"🤖 Generazione LLM auto-import per {image_path.name}...", "info")

            try:
                # Usa thumbnail cached invece di estrarre di nuovo
                llm_input = cached_thumbnail

                # Prepara task paralleli per LLM (I/O bound - chiamate HTTP a Ollama)
                llm_futures = {}
                llm_results = {'tags': None, 'description': None, 'title': None}

                # Determina quali generazioni eseguire
                existing_tags = []
                if 'tags' in image_data and image_data['tags']:
                    try:
                        existing_tags = json.loads(image_data['tags'])
                    except:
                        existing_tags = []

                existing_desc = image_data.get('description', '') or ''
                existing_title = image_data.get('title', '') or ''

                should_gen_tags = gen_tags_cfg.get('enabled', False)
                should_gen_desc = gen_desc_cfg.get('enabled') and (gen_desc_cfg.get('overwrite') or not existing_desc.strip())
                should_gen_title = gen_title_cfg.get('enabled') and (gen_title_cfg.get('overwrite') or not existing_title.strip())

                # Conta operazioni da eseguire per log
                ops_count = sum([should_gen_tags, should_gen_desc, should_gen_title])
                if ops_count > 1:
                    self.log_message.emit(f"⚡ Esecuzione parallela di {ops_count} operazioni LLM...", "info")

                # Esegui chiamate LLM in parallelo (max 3 thread per evitare sovraccarico Ollama)
                with ThreadPoolExecutor(max_workers=3) as executor:
                    if should_gen_tags:
                        llm_futures['tags'] = executor.submit(
                            embedding_generator.generate_llm_tags,
                            llm_input,
                            gen_tags_cfg.get('max', 10),
                            bioclip_context,
                            category_hint,
                            location_hint
                        )

                    if should_gen_desc:
                        llm_futures['description'] = executor.submit(
                            embedding_generator.generate_llm_description,
                            llm_input,
                            gen_desc_cfg.get('max', 100),
                            bioclip_context,
                            category_hint,
                            location_hint
                        )

                    if should_gen_title:
                        llm_futures['title'] = executor.submit(
                            embedding_generator.generate_llm_title,
                            llm_input,
                            gen_title_cfg.get('max', 5),
                            bioclip_context,
                            category_hint,
                            location_hint
                        )

                    # Raccogli risultati
                    for key, future in llm_futures.items():
                        try:
                            llm_results[key] = future.result(timeout=200)  # timeout generoso per LLM
                        except Exception as e:
                            self.log_message.emit(f"⚠️ LLM {key} timeout/errore: {e}", "warning")

                # Pulisci cache immagine LLM (libera memoria e file temp)
                embedding_generator._cleanup_llm_image_cache()

                # === APPLICA RISULTATI TAGS (solo LLM + user, NO BioCLIP) ===
                if llm_results['tags']:
                    llm_tags = llm_results['tags']

                    if gen_tags_cfg.get('overwrite'):
                        # Sovrascrivi tutti i tag con i nuovi LLM
                        image_data['tags'] = json.dumps(llm_tags, ensure_ascii=False)
                        self.log_message.emit(f"🏷️ LLM tags (sovrascritti): {len(llm_tags)} tag", "info")
                    else:
                        existing_lower = {t.lower() for t in existing_tags}
                        new_llm_tags = [t for t in llm_tags if t.lower() not in existing_lower]
                        unified_tags = existing_tags + new_llm_tags
                        image_data['tags'] = json.dumps(unified_tags, ensure_ascii=False)
                        self.log_message.emit(f"🏷️ LLM tags aggiunti: {len(new_llm_tags)} nuovi tag", "info")

                # Aggiungi città geo come tag se non già presente (come BioCLIP aggiunge il nome latino)
                if geo_hierarchy:
                    try:
                        from geo_enricher import get_geo_leaf
                        city_tag = get_geo_leaf(geo_hierarchy)
                        if city_tag:
                            current_tags_str = image_data.get('tags', '[]')
                            current_tags = json.loads(current_tags_str) if current_tags_str else []
                            if city_tag.lower() not in {t.lower() for t in current_tags}:
                                current_tags.append(city_tag)
                                image_data['tags'] = json.dumps(current_tags, ensure_ascii=False)
                                self.log_message.emit(f"📍 Tag città aggiunto: {city_tag}", "info")
                    except Exception as geo_tag_err:
                        self.log_message.emit(f"⚠️ Errore aggiunta tag città: {geo_tag_err}", "warning")

                # === APPLICA RISULTATI DESCRIZIONE ===
                if llm_results['description']:
                    image_data['description'] = llm_results['description']
                    self.log_message.emit(f"📝 LLM descrizione generata: {len(llm_results['description'])} caratteri", "info")
                elif should_gen_desc and not llm_results['description']:
                    pass  # Silenzioso se fallisce
                elif gen_desc_cfg.get('enabled') and not should_gen_desc:
                    self.log_message.emit(f"⏭️ Descrizione esistente preservata (overwrite=False)", "info")

                # === APPLICA RISULTATI TITOLO ===
                if llm_results['title']:
                    image_data['title'] = llm_results['title']
                    self.log_message.emit(f"📌 LLM titolo generato: {llm_results['title']}", "info")
                elif gen_title_cfg.get('enabled') and not should_gen_title:
                    self.log_message.emit(f"⏭️ Titolo esistente preservato (overwrite=False)", "info")

                image_data['llm_generated'] = True

            except Exception as llm_error:
                self.log_message.emit(f"❌ Errore LLM auto-import per {image_path.name}: {llm_error}", "error")

        elif llm_enabled:
            self.log_message.emit(f"⚠️ LLM auto-import richiesto ma embedding_generator non disponibile", "warning")

        # Calcola hash file per deduplicazione
        try:
            import hashlib
            md5 = hashlib.md5()
            with open(image_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5.update(chunk)
            image_data['file_hash'] = md5.hexdigest()
        except Exception as e:
            self.log_message.emit(f"⚠️ Errore calcolo hash per {image_path.name}: {e}", "warning")

        return image_data

    def _prepare_image_for_ai_corrected(self, image_path, raw_processor, is_raw, target_size=1024):
        """
        Prepara input per AI con dimensioni ottimali.
        OTTIMIZZATO: Estrae a risoluzione massima (1024) per cache, i processor
        dei singoli modelli ridimensionano poi secondo le loro esigenze.

        Args:
            image_path: Path dell'immagine
            raw_processor: RAWProcessor instance
            is_raw: True se file RAW
            target_size: Dimensione target (default 1024 per cache ottimale)
        """
        try:
            # Se è RAW, usa RAWProcessor per estrarre thumbnail ottimizzato
            if is_raw:
                self.log_message.emit(f"🔄 Preparazione RAW per AI: {image_path.name}", "info")

                # Usa extract_thumbnail con dimensione massima per cache
                pil_image = raw_processor.extract_thumbnail(image_path, target_size=target_size)

                if pil_image:
                    dimensions = f"{pil_image.size[0]}x{pil_image.size[1]}"
                    self.log_message.emit(f"✅ RAW convertito per AI: {image_path.name} - {dimensions}", "info")
                    return pil_image
                else:
                    self.log_message.emit(f"❌ Conversione RAW fallita: {image_path.name}", "error")
                    return None

            # File standard: ottimizza per cache se troppo grandi
            else:
                try:
                    from PIL import Image
                    with Image.open(image_path) as img:
                        max_size = max(img.size)
                        # Se molto grande, riduci a target_size per cache
                        if max_size > target_size:
                            # Crea copia e riduci mantenendo qualità
                            pil_image = img.copy()
                            if pil_image.mode not in ['RGB', 'L']:
                                pil_image = pil_image.convert('RGB')

                            # Ridimensiona mantenendo aspect ratio
                            pil_image.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
                            dimensions = f"{pil_image.size[0]}x{pil_image.size[1]}"
                            self.log_message.emit(f"✅ Immagine ottimizzata per AI: {image_path.name} - {dimensions}", "info")
                            return pil_image

                        # Se già dimensioni OK, carica come PIL per cache
                        pil_image = img.copy()
                        if pil_image.mode not in ['RGB', 'L']:
                            pil_image = pil_image.convert('RGB')
                        self.log_message.emit(f"➡️ File dimensioni OK per AI: {image_path.name}", "info")
                        return pil_image

                except Exception as e:
                    self.log_message.emit(f"❌ Errore ottimizzazione immagine {image_path.name}: {e}", "error")
                    return image_path

        except Exception as e:
            filename = str(image_path.name if hasattr(image_path, 'name') else image_path)
            self.log_message.emit(f"❌ Errore prepare_image_for_ai {filename}: {e}", "error")
            return image_path

    def stop(self):
        """Ferma processing"""
        self.is_running = False

    def pause(self):
        """Pausa processing"""
        self.is_paused = True

    def resume(self):
        """Riprendi processing"""
        self.is_paused = False


class ProcessingTab(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)

        self.main_window = main_window
        self.config_path = main_window.config_path

        # Riutilizza EmbeddingGenerator centralizzato da MainWindow
        # (evita doppio caricamento modelli e doppio consumo VRAM)
        if hasattr(main_window, 'ai_models') and main_window.ai_models.get('initialized'):
            self.embedding_gen = main_window.ai_models.get('embedding_generator')
        else:
            self.embedding_gen = None

        self.worker = None
        self.images_to_process_count = 0
        self.processing_log_file = None  # File handle per log processing su disco
        self.catalog_path = None          # Path catalogo selezionato
        self.catalog_files = []           # Lista file dal catalogo
        self.init_ui()
    
    def _get_config_path(self):
        """Determina il path del file di configurazione"""
        app_dir = get_app_dir()

        possible_configs = [
            app_dir / 'config_new.yaml',                      # Directory app
            Path.cwd() / 'config_new.yaml',                   # Directory corrente
            Path.home() / '.offgallery' / 'config_new.yaml',  # Home utente
        ]

        # Cerca primo config esistente
        for config_path in possible_configs:
            if config_path.exists():
                return str(config_path)

        # Se nessun config trovato, usa default
        return str(app_dir / 'config_new.yaml')
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 5)  # Margine inferiore ridotto
        layout.setSpacing(6)  # Spacing ancora più ridotto
        
        # Selezione Directory Input
        input_group = QGroupBox("📂 Directory Input")
        input_layout = QHBoxLayout()
        
        self.input_dir_label = QLabel("Nessuna directory selezionata")
        self.input_dir_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                padding: 8px 12px;
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                font-size: 11px;
                font-weight: normal;
                min-height: 16px;
            }
        """)
        input_layout.addWidget(self.input_dir_label)
        
        self.browse_btn = QPushButton("📁 Seleziona Directory")
        self.browse_btn.clicked.connect(self.select_input_directory)
        self.browse_btn.setMinimumWidth(150)
        input_layout.addWidget(self.browse_btn)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh_scan)
        self.refresh_btn.setMinimumWidth(80)
        self.refresh_btn.setToolTip("Aggiorna scansione directory e stato database")
        input_layout.addWidget(self.refresh_btn)

        self.include_subdirs_cb = QCheckBox("Includi sotto-cartelle")
        self.include_subdirs_cb.setToolTip("Scansiona ricorsivamente anche le sotto-cartelle della directory selezionata")
        self.include_subdirs_cb.stateChanged.connect(self._on_subdirs_changed)
        input_layout.addWidget(self.include_subdirs_cb)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # ===== SORGENTE (radio: Directory / Catalogo) =====
        source_group = QGroupBox("📥 Sorgente Immagini")
        source_layout = QHBoxLayout()

        self.source_btn_group = QButtonGroup()

        self.source_dir_radio = QRadioButton("Directory")
        self.source_dir_radio.setChecked(True)
        self.source_dir_radio.setToolTip("Leggi immagini dalla directory selezionata sopra")
        self.source_btn_group.addButton(self.source_dir_radio, 0)
        source_layout.addWidget(self.source_dir_radio)

        self.source_catalog_radio = QRadioButton("Catalogo Lightroom (.lrcat)")
        self.source_catalog_radio.setToolTip("Leggi l'elenco delle immagini dal catalogo Lightroom")
        self.source_btn_group.addButton(self.source_catalog_radio, 1)
        source_layout.addWidget(self.source_catalog_radio)

        source_layout.addStretch()
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        self.source_btn_group.idClicked.connect(self._on_source_changed)

        # ===== CATALOGO LIGHTROOM =====
        self.catalog_group = QGroupBox("📋 Catalogo Lightroom")
        catalog_layout = QHBoxLayout()

        self.catalog_path_label = QLabel("Nessun catalogo selezionato")
        self.catalog_path_label.setStyleSheet("""
            QLabel {
                color: #2c3e50; padding: 8px 12px;
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 4px; font-size: 11px;
                min-height: 16px;
            }
        """)
        catalog_layout.addWidget(self.catalog_path_label)

        self.catalog_browse_btn = QPushButton("📁 Seleziona .lrcat")
        self.catalog_browse_btn.setMinimumWidth(150)
        self.catalog_browse_btn.clicked.connect(self.select_catalog)
        catalog_layout.addWidget(self.catalog_browse_btn)

        self.catalog_group.setLayout(catalog_layout)
        self.catalog_group.setEnabled(False)  # Disabilitato finché non si seleziona "Catalogo"
        layout.addWidget(self.catalog_group)

        self.catalog_info_label = QLabel("")
        self.catalog_info_label.setStyleSheet("color: #27ae60; font-size: 11px; padding: 2px 4px;")
        self.catalog_info_label.setVisible(False)
        layout.addWidget(self.catalog_info_label)

        # ===== STATUS (solo, senza statistiche) =====
        status_group = QGroupBox("📊 Status")
        status_layout = QVBoxLayout()
        
        self.db_label = QLabel("Database: ...")
        self.scan_label = QLabel("Seleziona una directory per iniziare")
        
        status_layout.addWidget(self.db_label)
        status_layout.addWidget(self.scan_label)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # ===== OPZIONI PROCESSING (3 modalità radio) =====
        options_group = QGroupBox("⚙️ Modalità Processing")
        options_layout = QVBoxLayout()
        
        self.processing_mode_group = QButtonGroup()
        
        mode_layout = QHBoxLayout()
        
        self.mode_new_only = QRadioButton("Solo nuove immagini")
        self.mode_new_only.setChecked(True)
        self.mode_new_only.setToolTip("Processa solo immagini non ancora nel database")
        self.processing_mode_group.addButton(self.mode_new_only, 0)
        mode_layout.addWidget(self.mode_new_only)
        
        self.mode_new_plus_errors = QRadioButton("Nuove + errori precedenti")
        self.mode_new_plus_errors.setToolTip("Processa nuove immagini e riprova quelle che avevano dato errore")
        # Bianco (nessuno stile speciale)
        self.processing_mode_group.addButton(self.mode_new_plus_errors, 1)
        mode_layout.addWidget(self.mode_new_plus_errors)
        
        self.mode_reprocess_all = QRadioButton("Riprocessa tutte")
        self.mode_reprocess_all.setToolTip("Riprocessa tutte le immagini, anche quelle già elaborate")
        self.mode_reprocess_all.setStyleSheet("color: #f57500; font-weight: bold;")  # Giallo/Arancione
        self.processing_mode_group.addButton(self.mode_reprocess_all, 2)
        mode_layout.addWidget(self.mode_reprocess_all)
        
        mode_layout.addStretch()
        options_layout.addLayout(mode_layout)
        
        # Connetti cambio modalità all'aggiornamento pulsante
        self.processing_mode_group.idClicked.connect(self.update_start_button_state)

        # Checkbox per salvataggio log completo su file
        log_layout = QHBoxLayout()
        self.enable_file_log_cb = QCheckBox("Salva log completo su file")
        self.enable_file_log_cb.setToolTip("Scrive tutti i messaggi su file nella directory log configurata (Impostazioni → Dir Log)")
        self.enable_file_log_cb.setChecked(False)
        log_layout.addWidget(self.enable_file_log_cb)
        log_layout.addStretch()
        options_layout.addLayout(log_layout)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # ===== GENERAZIONE AI (Tags / Descrizione / Titolo) =====
        gen_ai_group = QGroupBox("🤖 Generazione AI (Tags / Descrizione / Titolo)")
        gen_ai_layout = QVBoxLayout()

        from PyQt6.QtWidgets import QGridLayout
        gen_grid = QGridLayout()

        # Header
        lbl_genera = QLabel("Genera")
        lbl_genera.setStyleSheet("font-weight: bold;")
        gen_grid.addWidget(lbl_genera, 0, 0)

        lbl_sovr = QLabel("Sovrascrivi esistente")
        lbl_sovr.setStyleSheet("font-weight: bold;")
        gen_grid.addWidget(lbl_sovr, 0, 1)

        lbl_params = QLabel("Parametri")
        lbl_params.setStyleSheet("font-weight: bold;")
        gen_grid.addWidget(lbl_params, 0, 2, 1, 2)

        # Tags
        self.pt_gen_tags_check = QCheckBox("Tags")
        self.pt_gen_tags_check.setToolTip("Genera tag automaticamente durante il processing")
        self.pt_gen_tags_check.stateChanged.connect(self._toggle_pt_tags)
        gen_grid.addWidget(self.pt_gen_tags_check, 1, 0)

        self.pt_gen_tags_overwrite = QCheckBox()
        self.pt_gen_tags_overwrite.setToolTip("Sovrascrive i tag già presenti in XMP/Embedded")
        self.pt_gen_tags_overwrite.setEnabled(False)
        gen_grid.addWidget(self.pt_gen_tags_overwrite, 1, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        gen_grid.addWidget(QLabel("Max Tags:"), 1, 2)
        self.pt_llm_max_tags = QSpinBox()
        self.pt_llm_max_tags.setRange(1, 20)
        self.pt_llm_max_tags.setValue(10)
        self.pt_llm_max_tags.setEnabled(False)
        gen_grid.addWidget(self.pt_llm_max_tags, 1, 3)

        # Descrizione
        self.pt_gen_desc_check = QCheckBox("Descrizione")
        self.pt_gen_desc_check.setToolTip("Genera descrizione automaticamente durante il processing")
        self.pt_gen_desc_check.stateChanged.connect(self._toggle_pt_desc)
        gen_grid.addWidget(self.pt_gen_desc_check, 2, 0)

        self.pt_gen_desc_overwrite = QCheckBox()
        self.pt_gen_desc_overwrite.setToolTip("Sovrascrive la descrizione già presente in XMP/Embedded")
        self.pt_gen_desc_overwrite.setEnabled(False)
        gen_grid.addWidget(self.pt_gen_desc_overwrite, 2, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        gen_grid.addWidget(QLabel("Max Parole:"), 2, 2)
        self.pt_llm_max_words = QSpinBox()
        self.pt_llm_max_words.setRange(20, 300)
        self.pt_llm_max_words.setValue(100)
        self.pt_llm_max_words.setEnabled(False)
        gen_grid.addWidget(self.pt_llm_max_words, 2, 3)

        # Titolo
        self.pt_gen_title_check = QCheckBox("Titolo")
        self.pt_gen_title_check.setToolTip("Genera titolo automaticamente durante il processing")
        self.pt_gen_title_check.stateChanged.connect(self._toggle_pt_title)
        gen_grid.addWidget(self.pt_gen_title_check, 3, 0)

        self.pt_gen_title_overwrite = QCheckBox()
        self.pt_gen_title_overwrite.setToolTip("Sovrascrive il titolo già presente in XMP/Embedded")
        self.pt_gen_title_overwrite.setEnabled(False)
        gen_grid.addWidget(self.pt_gen_title_overwrite, 3, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        gen_grid.addWidget(QLabel("Max Parole:"), 3, 2)
        self.pt_llm_max_title = QSpinBox()
        self.pt_llm_max_title.setRange(1, 10)
        self.pt_llm_max_title.setValue(5)
        self.pt_llm_max_title.setEnabled(False)
        gen_grid.addWidget(self.pt_llm_max_title, 3, 3)

        gen_ai_layout.addLayout(gen_grid)

        info_lbl = QLabel("ℹ️ Quando 'Sovrascrivi' è disattivo, i dati esistenti vengono preservati")
        info_lbl.setStyleSheet("color: #7f8c8d; font-size: 10px; font-style: italic;")
        gen_ai_layout.addWidget(info_lbl)

        gen_ai_group.setLayout(gen_ai_layout)
        layout.addWidget(gen_ai_group)

        # Controlli principali
        controls_group = QGroupBox("🎮 Controlli")
        controls_layout = QHBoxLayout()
        
        # Start
        self.start_btn = QPushButton("▶️ AVVIA")
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setStyleSheet("font-weight: bold; background-color: #2e7d32; min-width: 100px;")
        controls_layout.addWidget(self.start_btn)
        
        # Pausa
        self.pause_btn = QPushButton("⏸️ PAUSA")
        self.pause_btn.clicked.connect(self.pause_processing)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setStyleSheet("min-width: 100px;")
        controls_layout.addWidget(self.pause_btn)
        
        # Stop
        self.stop_btn = QPushButton("⏹️ STOP")
        self.stop_btn.clicked.connect(self.stop_processing)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("min-width: 100px;")
        controls_layout.addWidget(self.stop_btn)
        
        # Save Log
        self.log_btn = QPushButton("💾 SALVA LOG")
        self.log_btn.clicked.connect(self.save_log)
        self.log_btn.setStyleSheet("min-width: 100px;")
        controls_layout.addWidget(self.log_btn)
        
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)
        
        # ===== PROGRESSO (SOLO LABEL DINAMICA) =====
        progress_group = QGroupBox("📊 Progresso")
        progress_layout = QVBoxLayout()

        # Progress bar grafica (stile splash screen)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3A3A3A;
                background-color: #1E1E1E;
                border-radius: 6px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #C88B2E, stop:1 #E0A84A);
                border-radius: 5px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)

        # Label progress testuale
        self.progress_label = QLabel("In attesa di avvio processing...")
        self.progress_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: white;
                padding: 10px;
                background-color: #616161;
                border-radius: 4px;
                border: 1px solid #424242;
                font-family: 'Consolas', 'Courier New', monospace;
                font-weight: bold;
                min-height: 20px;
            }
        """)
        # Word wrap per testi lunghi
        self.progress_label.setWordWrap(True)
        progress_layout.addWidget(self.progress_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # ===== LOG TERMINALE (NUOVO) =====
        terminal_group = QGroupBox("💻 Terminal Log")
        terminal_layout = QVBoxLayout()
        terminal_layout.setContentsMargins(5, 5, 5, 5)
        
        self.log_display = QTextEdit()
        
        # Dimensioni ottimali per terminale
        self.log_display.setFixedHeight(140)
        
        # Font monospaziato per terminale
        self.log_display.setFont(QFont("Courier New", 10))
        
        # Scrollbar sempre visibile
        from PyQt6.QtCore import Qt
        self.log_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.log_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Stile terminale classico: nero con verde
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #00ff00;
                border: 2px solid #333333;
                border-radius: 8px;
                padding: 8px;
                font-family: 'Courier New', 'Monaco', monospace;
                font-size: 10px;
                line-height: 1.2;
            }
            QScrollBar:vertical {
                background-color: #1a1a1a;
                width: 16px;
                border: 1px solid #333333;
                border-radius: 8px;
            }
            QScrollBar::handle:vertical {
                background-color: #00ff00;
                border-radius: 7px;
                min-height: 20px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #00cc00;
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #00aa00;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background-color: #1a1a1a;
                height: 16px;
                border: 1px solid #333333;
                border-radius: 8px;
            }
            QScrollBar::handle:horizontal {
                background-color: #00ff00;
                border-radius: 7px;
                min-width: 20px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #00cc00;
            }
        """)
        
        # Proprietà di sola lettura ma mantiene scrolling
        self.log_display.setReadOnly(True)
        
        # Auto-scroll alle ultime righe
        self.log_display.textChanged.connect(self._auto_scroll_terminal)
        
        terminal_layout.addWidget(self.log_display)
        
        terminal_group.setLayout(terminal_layout)
        layout.addWidget(terminal_group)
        
        # Carica directory salvata se presente
        self.load_saved_input_directory()
        
        # Inizializza terminale con messaggio di benvenuto
        self._init_terminal_welcome()
    
    def _auto_scroll_terminal(self):
        """Auto-scroll del terminale alle ultime righe"""
        try:
            scrollbar = self.log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            print(f"Errore auto-scroll: {e}")
    
    def _init_terminal_welcome(self):
        """Inizializza il terminale con messaggio di benvenuto"""
        try:
            self.log_display.clear()
            welcome_msg = """<span style="color: #00ff00; font-weight: bold;">
==================================================
    OFFGALLERY PROCESSING TERMINAL v1.0
==================================================</span>
<span style="color: #00cc00;">System initialized and ready for image processing...</span>
"""
            self.log_display.append(welcome_msg)
        except Exception as e:
            print(f"Errore init terminale: {e}")
    
    def select_input_directory(self):
        """Apre dialog per selezione directory input"""
        from PyQt6.QtWidgets import QFileDialog
        
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Seleziona Directory Immagini", 
            str(Path.home())
        )
        
        if directory:
            self.set_input_directory(directory)
    
    def set_input_directory(self, directory_path):
        """Imposta directory input e salva in config"""
        try:
            directory = Path(directory_path)
            if not directory.exists():
                QMessageBox.warning(self, "Errore", f"Directory non esistente: {directory}")
                return
            
            # Aggiorna UI
            self.input_dir_label.setText(str(directory))
            self.input_dir_label.setStyleSheet("""
                QLabel {
                    color: #2c3e50;
                    padding: 8px 12px;
                    background-color: #ecf0f1;
                    border: 1px solid #bdc3c7;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: normal;
                    min-height: 16px;
                }
            """)
            # Directory selezionata, abilita processing
            
            # Salva in config
            self.save_input_directory_to_config(str(directory))
            
            # Auto-scansiona
            self.scan_directory()
            
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore impostazione directory: {e}")
    
    def _save_llm_config_to_yaml(self, llm_gen_config: dict):
        """Salva impostazioni generazione AI nel YAML per la prossima sessione"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            llm = (config.setdefault('embedding', {})
                         .setdefault('models', {})
                         .setdefault('llm_vision', {}))
            ai = llm.setdefault('auto_import', {})

            ai['tags'] = {
                'enabled': llm_gen_config['tags']['enabled'],
                'overwrite': llm_gen_config['tags']['overwrite'],
                'max_tags': llm_gen_config['tags']['max'],
            }
            ai['description'] = {
                'enabled': llm_gen_config['description']['enabled'],
                'overwrite': llm_gen_config['description']['overwrite'],
                'max_words': llm_gen_config['description']['max'],
            }
            ai['title'] = {
                'enabled': llm_gen_config['title']['enabled'],
                'overwrite': llm_gen_config['title']['overwrite'],
                'max_words': llm_gen_config['title']['max'],
            }

            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Errore salvataggio config LLM: {e}")

    def save_input_directory_to_config(self, directory_path):
        """Salva directory input nel config YAML"""
        try:
            # Carica config esistente
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Assicurati che paths esista
            if 'paths' not in config:
                config['paths'] = {}
            
            # Aggiorna input_dir
            config['paths']['input_dir'] = directory_path
            
            # Salva config
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
                
        except Exception as e:
            print(f"Errore salvataggio directory in config: {e}")
    
    def load_saved_input_directory(self):
        """Carica directory input e impostazioni LLM dal config YAML"""
        try:
            if not Path(self.config_path).exists():
                return

            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # Carica directory salvata
            if 'paths' in config and 'input_dir' in config['paths']:
                input_dir = config['paths']['input_dir']
                if Path(input_dir).exists():
                    self.set_input_directory(input_dir)
                else:
                    self.input_dir_label.setText("Directory salvata non più disponibile")
                    self.input_dir_label.setStyleSheet("color: #cc3333;")

            # Carica impostazioni generazione AI (tags/desc/title)
            auto_import = (config.get('embedding', {})
                           .get('models', {})
                           .get('llm_vision', {})
                           .get('auto_import', {}))

            tags_cfg = auto_import.get('tags', {})
            self.pt_gen_tags_check.setChecked(tags_cfg.get('enabled', False))
            self.pt_gen_tags_overwrite.setChecked(tags_cfg.get('overwrite', False))
            self.pt_llm_max_tags.setValue(tags_cfg.get('max_tags', 10))
            self._toggle_pt_tags(self.pt_gen_tags_check.isChecked())

            desc_cfg = auto_import.get('description', {})
            self.pt_gen_desc_check.setChecked(desc_cfg.get('enabled', False))
            self.pt_gen_desc_overwrite.setChecked(desc_cfg.get('overwrite', False))
            self.pt_llm_max_words.setValue(desc_cfg.get('max_words', 100))
            self._toggle_pt_desc(self.pt_gen_desc_check.isChecked())

            title_cfg = auto_import.get('title', {})
            self.pt_gen_title_check.setChecked(title_cfg.get('enabled', False))
            self.pt_gen_title_overwrite.setChecked(title_cfg.get('overwrite', False))
            self.pt_llm_max_title.setValue(title_cfg.get('max_words', 5))
            self._toggle_pt_title(self.pt_gen_title_check.isChecked())

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Errore caricamento config in processing tab: {e}")

    def _on_subdirs_changed(self, state):
        """Ri-scansiona quando cambia il checkbox sotto-cartelle"""
        input_dir_text = self.input_dir_label.text()
        if input_dir_text not in ["Nessuna directory selezionata", "Directory salvata non più disponibile"]:
            self.scan_directory()

    def _on_source_changed(self, source_id):
        """Abilita/disabilita sezioni in base alla sorgente selezionata"""
        is_catalog = (source_id == 1)
        # Abilita/disabilita controlli directory
        self.browse_btn.setEnabled(not is_catalog)
        self.refresh_btn.setEnabled(not is_catalog)
        self.include_subdirs_cb.setEnabled(not is_catalog)
        # Abilita/disabilita sezione catalogo
        self.catalog_group.setEnabled(is_catalog)
        # Aggiorna stato pulsante avvia
        self.update_start_button_state()

    def _toggle_pt_tags(self, state):
        """Abilita/disabilita controlli tag in processing tab"""
        enabled = self.pt_gen_tags_check.isChecked()
        self.pt_gen_tags_overwrite.setEnabled(enabled)
        self.pt_llm_max_tags.setEnabled(enabled)

    def _toggle_pt_desc(self, state):
        """Abilita/disabilita controlli descrizione in processing tab"""
        enabled = self.pt_gen_desc_check.isChecked()
        self.pt_gen_desc_overwrite.setEnabled(enabled)
        self.pt_llm_max_words.setEnabled(enabled)

    def _toggle_pt_title(self, state):
        """Abilita/disabilita controlli titolo in processing tab"""
        enabled = self.pt_gen_title_check.isChecked()
        self.pt_gen_title_overwrite.setEnabled(enabled)
        self.pt_llm_max_title.setEnabled(enabled)

    def select_catalog(self):
        """Apre dialog per selezione catalogo Lightroom"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona Catalogo Lightroom",
            str(Path.home()),
            "Catalogo Lightroom (*.lrcat);;Tutti i file (*.*)"
        )
        if not path:
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            supported_formats = config.get('image_processing', {}).get('supported_formats', [])

            reader = LightroomCatalogReader()
            result = reader.read_catalog(Path(path), supported_formats)

            self.catalog_path = Path(path)
            self.catalog_files = result['files']
            stats = result['stats']

            self.catalog_path_label.setText(str(self.catalog_path))

            info_parts = [
                f"Catalogo: {stats['catalog_name']}",
                f"{stats['found_on_disk']} foto compatibili",
            ]
            if stats['missing_on_disk'] > 0:
                info_parts.append(f"⚠️ {stats['missing_on_disk']} non trovate su disco")
            self.catalog_info_label.setText("  |  ".join(info_parts))
            self.catalog_info_label.setVisible(True)

            # Aggiorna status
            self.scan_label.setText(
                f"Catalogo: {stats['found_on_disk']} immagini disponibili "
                f"({stats['total_in_catalog']} nel catalogo)"
            )
            self.images_to_process_count = stats['found_on_disk']
            self.update_start_button_state()

        except Exception as e:
            QMessageBox.warning(self, "Errore lettura catalogo", str(e))

    def refresh_scan(self):
        """Aggiorna scansione directory e stato database"""
        try:
            input_dir_text = self.input_dir_label.text()
            if input_dir_text in ["Nessuna directory selezionata", "Directory salvata non più disponibile"]:
                QMessageBox.warning(self, "Attenzione", "Seleziona prima una directory")
                return

            # Feedback visivo
            self.scan_label.setText("🔄 Aggiornamento in corso...")
            QApplication.processEvents()

            # Esegui scansione
            self.scan_directory()

            print("🔄 Refresh completato")

        except Exception as e:
            print(f"Errore refresh: {e}")
            self.scan_label.setText(f"❌ Errore refresh: {e}")

    def scan_directory(self):
        """Scansiona directory per contare immagini NON processate"""
        try:
            # Ottieni directory input dall'UI
            input_dir_text = self.input_dir_label.text()
            if input_dir_text in ["Nessuna directory selezionata", "Directory salvata non più disponibile"]:
                self.scan_label.setText("⚠️ Seleziona una directory per vedere le statistiche")
                return
            
            input_dir = Path(input_dir_text)
            if not input_dir.exists():
                self.scan_label.setText(f"❌ Directory non esistente: {input_dir}")
                return
            
            # Carica config per formati supportati e database
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            db_path = Path(config['paths']['database'])
            supported_formats = config.get('image_processing', {}).get('supported_formats', [])
            
            if not supported_formats:
                self.scan_label.setText("❌ Nessun formato supportato configurato")
                return
            
            self.db_label.setText(f"Database: {db_path}")
            
            # Conta immagini (CORRETTO: evita duplicati case-sensitive)
            all_images = []
            seen_files = set()
            include_subdirs = self.include_subdirs_cb.isChecked()

            for ext in supported_formats:
                # Cerca sia minuscole che maiuscole
                for pattern in [f"*{ext}", f"*{ext.upper()}"]:
                    if include_subdirs:
                        found_files = input_dir.rglob(pattern)
                    else:
                        found_files = input_dir.glob(pattern)
                    for file_path in found_files:
                        # Con sotto-cartelle usa path completo per dedup, altrimenti solo nome
                        dedup_key = str(file_path).lower() if include_subdirs else file_path.name.lower()
                        if dedup_key not in seen_files:
                            seen_files.add(dedup_key)
                            all_images.append(file_path)
            
            # Verifica quali sono già nel database
            images_to_process = all_images
            already_processed = 0
            
            if db_path.exists():
                try:
                    import sys
                    sys.path.insert(0, str(get_app_dir()))
                    from db_manager_new import DatabaseManager
                    
                    db_manager = DatabaseManager(str(db_path))
                    processed_files = db_manager.get_all_images()
                    if include_subdirs:
                        processed_paths = {Path(f['filepath']).resolve().as_posix().lower() for f in processed_files}
                        images_to_process = [img for img in all_images
                                           if img.resolve().as_posix().lower() not in processed_paths]
                    else:
                        processed_names = {Path(f['filepath']).name.lower() for f in processed_files}
                        images_to_process = [img for img in all_images
                                           if img.name.lower() not in processed_names]
                    already_processed = len(all_images) - len(images_to_process)
                    
                except Exception as e:
                    self.scan_label.setText(f"Errore verifica database: {e}")
                    return
            
            total_found = len(all_images)
            to_process = len(images_to_process)
            
            # Salva il numero di immagini da processare per la logica del pulsante
            self.images_to_process_count = to_process
            
            if to_process == 0:
                self.scan_label.setText(f"Trovate {total_found} immagini, tutte già processate ✅")
                # Aggiorna stato pulsante in base alle modalità
                self.update_start_button_state()
            else:
                self.scan_label.setText(
                    f"Trovate {total_found} immagini, {to_process} da processare "
                    f"({already_processed} già processate)"
                )
                # Abilita pulsante se ci sono immagini da processare
                self.start_btn.setEnabled(True)
            
        except Exception as e:
            self.scan_label.setText(f"Errore scansione: {e}")
    
    def update_start_button_state(self):
        """Aggiorna stato pulsante START in base a modalità e immagini disponibili"""
        try:
            # Controlla se ci sono immagini da processare
            images_available = getattr(self, 'images_to_process_count', 0)
            
            # Ottieni modalità selezionata
            mode_id = self.processing_mode_group.checkedId() if hasattr(self, 'processing_mode_group') else 0
            
            if mode_id == 0:  # Solo nuove immagini
                if images_available == 0:
                    self.start_btn.setEnabled(False)
                    self.start_btn.setToolTip("Nessuna nuova immagine da processare. Cambia modalità per riprocessare.")
                else:
                    self.start_btn.setEnabled(True)
                    self.start_btn.setToolTip("Avvia processing delle nuove immagini")
            else:  # Altre modalità
                self.start_btn.setEnabled(True)
                if mode_id == 1:  # new_plus_errors
                    self.start_btn.setToolTip("Avvia processing di nuove immagini + riprova errori")
                else:  # reprocess_all
                    self.start_btn.setToolTip("Avvia riprocessing di tutte le immagini")
                    
        except Exception as e:
            print(f"Errore update_start_button_state: {e}")
            # Fallback: abilita sempre
            self.start_btn.setEnabled(True)
    
    def start_processing(self):
        """Avvia processing"""
        if self.worker and self.worker.isRunning():
            return

        # Determina sorgente
        use_catalog = self.source_catalog_radio.isChecked()

        if use_catalog:
            # Verifica catalogo selezionato
            if not self.catalog_files:
                QMessageBox.warning(self, "Errore", "Seleziona prima un catalogo Lightroom (.lrcat)")
                return
        else:
            # Verifica directory selezionata
            input_dir_text = self.input_dir_label.text()
            if input_dir_text in ["Nessuna directory selezionata", "Directory salvata non più disponibile"]:
                QMessageBox.warning(self, "Errore", "Seleziona prima una directory input")
                return
            if not Path(input_dir_text).exists():
                QMessageBox.warning(self, "Errore", f"Directory non esistente: {input_dir_text}")
                return

        try:
            # Costruisce llm_gen_config dai widget locali
            llm_gen_config = {
                'tags': {
                    'enabled': self.pt_gen_tags_check.isChecked(),
                    'overwrite': self.pt_gen_tags_overwrite.isChecked(),
                    'max': self.pt_llm_max_tags.value(),
                },
                'description': {
                    'enabled': self.pt_gen_desc_check.isChecked(),
                    'overwrite': self.pt_gen_desc_overwrite.isChecked(),
                    'max': self.pt_llm_max_words.value(),
                },
                'title': {
                    'enabled': self.pt_gen_title_check.isChecked(),
                    'overwrite': self.pt_gen_title_overwrite.isChecked(),
                    'max': self.pt_llm_max_title.value(),
                },
            }

            # Salva valori LLM nel YAML per la prossima sessione
            self._save_llm_config_to_yaml(llm_gen_config)

            # Reset progress bar
            self.progress_bar.setValue(0)
            self.log_display.clear()

            # Apri file log se richiesto
            if self.enable_file_log_cb.isChecked():
                self._open_processing_log()

            self.log_display.append("[{}] Avvio processing...".format(
                datetime.now().strftime("%H:%M:%S")
            ))

            # Determina modalità processing
            mode_id = self.processing_mode_group.checkedId()
            if mode_id == 0:
                processing_mode = 'new_only'
                mode_text = 'Solo nuove immagini'
            elif mode_id == 1:
                processing_mode = 'new_plus_errors'
                mode_text = 'Nuove immagini + errori precedenti'
            else:  # mode_id == 2
                processing_mode = 'reprocess_all'
                mode_text = 'Riprocessa tutte le immagini'

            self.log_display.append(f"Modalità: {mode_text}")

            if self.processing_log_file:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.processing_log_file.write(f"[{timestamp}] [INFO] Avvio processing...\n")
                self.processing_log_file.write(f"[{timestamp}] [INFO] Modalità: {mode_text}\n")
                self.processing_log_file.flush()

            # Crea worker
            if use_catalog:
                input_dir_text = None
                image_list = self.catalog_files
            else:
                image_list = None

            self.worker = ProcessingWorker(
                self.config_path,
                input_dir_text,
                self.embedding_gen,
                {'processing_mode': processing_mode},
                include_subdirs=self.include_subdirs_cb.isChecked(),
                image_list=image_list
            )

            # Connetti segnali
            self.worker.progress.connect(self.update_progress)
            self.worker.log_message.connect(self.add_log_message)
            self.worker.stats_update.connect(self.update_stats)
            self.worker.finished.connect(self.processing_finished)

            self.worker.start()

            # UI state
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)

        except Exception as e:
            self.add_log_message(f"Errore avvio processing: {e}", "error")
    
    def _open_processing_log(self):
        """Apre file log processing nella directory log da config"""
        try:
            import yaml
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            log_dir = Path(config.get('paths', {}).get('log_dir', 'logs'))

            # Se path relativo, rendi relativo alla directory dell'app
            if not log_dir.is_absolute():
                log_dir = get_app_dir() / log_dir

            log_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = log_dir / f"processing_log_{timestamp}.txt"

            self.processing_log_file = open(log_path, 'w', encoding='utf-8')
            self.processing_log_file.write("=" * 70 + "\n")
            self.processing_log_file.write(f"LOG PROCESSING OFFGALLERY\n")
            self.processing_log_file.write(f"Sessione: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.processing_log_file.write("=" * 70 + "\n\n")
            self.processing_log_file.flush()

            self.add_log_message(f"Log file: {log_path}", "info")

        except Exception as e:
            self.processing_log_file = None
            self.add_log_message(f"Errore apertura log file: {e}", "warning")

    def _close_processing_log(self):
        """Chiude file log processing"""
        if self.processing_log_file:
            try:
                self.processing_log_file.write("\n" + "=" * 70 + "\n")
                self.processing_log_file.write("FINE LOG\n")
                self.processing_log_file.write("=" * 70 + "\n")
                self.processing_log_file.close()
            except Exception:
                pass
            finally:
                self.processing_log_file = None

    def pause_processing(self):
        """Pausa processing"""
        if self.worker:
            if self.worker.is_paused:
                self.worker.resume()
                self.pause_btn.setText("⏸️ PAUSA")
                self.add_log_message("Processing ripreso", "info")
            else:
                self.worker.pause()
                self.pause_btn.setText("▶️ RIPRENDI")
                self.add_log_message("Processing in pausa", "info")
    
    def stop_processing(self):
        """Ferma processing"""
        if self.worker:
            self.worker.stop()
            self.add_log_message("Arresto processing...", "info")
    
    def update_progress(self, current, total):
        """Aggiorna progresso con barra grafica e testuale"""
        if total > 0:
            percentage = int((current / total) * 100)

            # Aggiorna progress bar grafica
            self.progress_bar.setValue(percentage)

            # Testo semplice (la barra grafica mostra già il progresso)
            progress_text = f"📊 {current}/{total} ({percentage}%)"

            self.progress_label.setText(progress_text)
            
            # Stile sobrio uniforme senza colori dinamici
            self.progress_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #2c3e50;
                    padding: 10px;
                    background-color: #ecf0f1;
                    border-radius: 4px;
                    border: 1px solid #bdc3c7;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-weight: bold;
                    min-height: 20px;
                }
            """)
    
    def add_log_message(self, message, level):
        """Aggiunge messaggio al log terminale"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Colori terminale: diverse tonalità di verde per i diversi livelli
        color_map = {
            'info': '#00ff00',      # Verde brillante per info
            'warning': '#ffff00',   # Giallo per warning
            'error': '#ff6600',     # Arancione per errori
            'success': '#00ff88',   # Verde acqua per successi
            'debug': '#88ff88'      # Verde chiaro per debug
        }
        
        color = color_map.get(level, '#00ff00')
        
        # Formato terminale classico
        formatted = f'<span style="color: #00cc00;">[{timestamp}]</span> <span style="color: {color};">{message}</span>'
        
        self.log_display.append(formatted)

        # Scrivi su file log se attivo (log completo, senza cap)
        if self.processing_log_file:
            try:
                self.processing_log_file.write(f"[{timestamp}] [{level.upper()}] {message}\n")
                self.processing_log_file.flush()
            except Exception:
                pass

        # Limita buffer terminale a 500 righe per evitare degrado GUI
        max_lines = 500
        doc = self.log_display.document()
        if doc.blockCount() > max_lines:
            cursor = self.log_display.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor,
                                doc.blockCount() - max_lines)
            cursor.removeSelectedText()
            cursor.deleteChar()  # Rimuove newline residuo

        # Auto-scroll gestito dal signal textChanged
    
    def update_stats(self, stats):
        """Update stats - non più necessario dato che tutto è nella progress bar"""
        # Manteniamo il metodo per compatibilità con il worker ma non fa nulla
        # Tutte le statistiche sono ora nella progress bar tramite update_progress
        pass
    
    def processing_finished(self, stats):
        """Processing completato"""
        # Chiudi file log processing
        self._close_processing_log()

        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        
        # Calcola statistiche per il completamento
        total = stats.get('total', 0)
        success = stats.get('success', 0)
        errors = stats.get('errors', 0)
        processing_time = stats.get('processing_time', 0)
        
        if total > 0:
            success_rate = round((success / total) * 100, 1)
            time_per_image = round(processing_time / total, 1) if total > 0 else 0
            
            # Mostra statistiche di completamento
            completion_text = f"✅ Completato! {success}/{total} ({success_rate}%) - ⏱️ {time_per_image}s/img"
            if errors > 0:
                completion_text += f" - ⚠️ {errors} errori"
                
            self.progress_label.setText(completion_text)
            self.progress_bar.setValue(100)

            # Stile sobrio uniforme per completamento
            self.progress_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #2c3e50;
                    padding: 10px;
                    background-color: #ecf0f1;
                    border-radius: 4px;
                    border: 1px solid #bdc3c7;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-weight: bold;
                    min-height: 20px;
                }
            """)
        else:
            self.progress_label.setText("✅ Completato!")
        
        # Aggiorna scan per refresh statistiche
        self.scan_directory()
    
    def save_log(self):
        """Salva il contenuto del log live su file"""
        try:
            from PyQt6.QtWidgets import QFileDialog
            
            # Proponi nome file con timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suggested_name = f"processing_log_{timestamp}.txt"
            
            # Dialog salvataggio
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Salva Log Processing",
                suggested_name,
                "File di testo (*.txt);;Tutti i file (*.*)"
            )
            
            if file_path:
                # Estrai testo puro dal log HTML
                plain_text = self.log_display.toPlainText()
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("=" * 70 + "\n")
                    f.write(f"LOG PROCESSING OFFGALLERY\n")
                    f.write(f"Salvato: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 70 + "\n\n")
                    f.write(plain_text)
                
                QMessageBox.information(self, "Log Salvato", f"Log salvato in:\n{file_path}")
                
        except Exception as e:
            QMessageBox.warning(self, "Errore", f"Errore salvataggio log:\n{e}")
