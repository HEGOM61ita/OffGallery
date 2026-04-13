"""
Processing Tab - VERSIONE DEFINITIVA E CORRETTA
Risolve tutti i problemi di mapping XMP e embedding generation
Configurazione database path corretta e processing garantito
OTTIMIZZATO: Cache thumbnail + LLM parallele per performance migliori
"""

import yaml
import sys
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QPushButton, QProgressBar, QTextEdit,
    QMessageBox, QDialog, QScrollArea, QApplication,
    QCheckBox, QRadioButton, QButtonGroup, QSpinBox, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from datetime import datetime
import time
import json
import threading
import queue

import logging

from utils.paths import get_app_dir
from utils.tag_utils import normalize_tags
from catalog_readers.lightroom_reader import LightroomCatalogReader
from i18n import t

logger = logging.getLogger(__name__)


class ProcessingWorker(QThread):
    """Worker thread per processing immagini — ARCHITETTURA MULTI-THREAD

    Flusso:
      Fase 0 (prep, sequenziale): EXIF + thumbnail + geo + hash → inserimento DB record base
      Fase 1 (parallela): 6 thread indipendenti (CLIP, DINOv2, BioCLIP, Aesthetic, MUSIQ, LLM)
      Ogni thread processa tutte le immagini col proprio modello e aggiorna il DB campo per campo.
      BioCLIP→LLM: coda (queue.Queue) per passare contesto tassonomico appena disponibile.

    Sincronizzazione:
      - db_lock: un solo Lock per serializzare scritture DB (SQLite non è thread-safe)
      - llm_queue: Queue per dipendenza BioCLIP→LLM (nessun lock necessario)
      - bioclip_results + bioclip_lock: contesto per LLM (lock separato, mai annidato)
      - is_running / is_paused: controllati da TUTTI i thread
    """

    # Segnali (emessi solo dal QThread principale o con Qt.QueuedConnection implicita)
    progress = pyqtSignal(int, int)  # current, total (fase prep)
    model_progress = pyqtSignal(str, int, int)  # model_key, current, total
    log_message = pyqtSignal(str, str)  # message, level
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
        self.image_list = image_list
        self.is_running = True
        self.is_paused = False
        # Sincronizzazione multi-thread
        self._db_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._gpu_lock = threading.Lock()  # serializza inferenza GPU tra thread
        self._model_threads = []  # riferimenti ai thread modello attivi

    def _wait_if_paused(self):
        """Attende se in pausa. Ritorna True se si può continuare, False se stoppato."""
        while self.is_paused and self.is_running:
            time.sleep(0.1)
        return self.is_running

    def _is_model_on_gpu(self, emb_gen, model_key):
        """Verifica se un modello è allocato su GPU (qualsiasi backend: cuda, mps, directml)."""
        try:
            device = emb_gen._device_for(model_key)
            return str(device) != 'cpu'
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────
    # RUN — Orchestratore principale
    # ─────────────────────────────────────────────────────────────
    def run(self):
        """Fase 0 (prep sequenziale) + Fase 1 (modelli paralleli)"""
        try:
            import sys
            sys.path.insert(0, str(get_app_dir()))

            from db_manager_new import DatabaseManager
            from raw_processor import RAWProcessor
            from embedding_generator import EmbeddingGenerator

            # === CARICAMENTO CONFIG ===
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            self.log_message.emit("🔧 Config caricato", "info")

            db_path = config['paths']['database']
            db_path_obj = Path(db_path)
            if not db_path_obj.parent.exists():
                db_path_obj.parent.mkdir(parents=True, exist_ok=True)

            db_manager = DatabaseManager(db_path)
            raw_processor = RAWProcessor(config)

            # === EMBEDDING GENERATOR ===
            embedding_enabled = config.get('embedding', {}).get('enabled', False)
            embedding_generator = None

            # Configurazione LLM dal YAML
            llm_auto_import = config.get('embedding', {}).get('models', {}).get('llm_vision', {}).get('auto_import', {})
            llm_gen_config = {
                'tags': {
                    'enabled': llm_auto_import.get('tags', {}).get('enabled', False),
                    'overwrite': llm_auto_import.get('tags', {}).get('overwrite', False),
                    'max': llm_auto_import.get('tags', {}).get('max_tags', 10),
                },
                'description': {
                    'enabled': llm_auto_import.get('description', {}).get('enabled', False),
                    'overwrite': llm_auto_import.get('description', {}).get('overwrite', False),
                    'max': llm_auto_import.get('description', {}).get('max_words', 100),
                },
                'title': {
                    'enabled': llm_auto_import.get('title', {}).get('enabled', False),
                    'overwrite': llm_auto_import.get('title', {}).get('overwrite', False),
                    'max': llm_auto_import.get('title', {}).get('max_words', 5),
                },
            }

            # Log configurazione LLM
            gen_items = []
            for k, cfg in llm_gen_config.items():
                if cfg['enabled']:
                    gen_items.append(f"{k} (max:{cfg['max']}, sovr:{cfg['overwrite']})")
            if gen_items:
                self.log_message.emit(f"🤖 LLM Auto-import attivo: {', '.join(gen_items)}", "info")
            else:
                self.log_message.emit("🤖 LLM Auto-import: disabilitato", "info")

            models_status = {}  # disponibilità reale dei modelli

            if embedding_enabled:
                if self.embedding_gen:
                    self.log_message.emit("🧠 Utilizzo EmbeddingGenerator già inizializzato", "info")
                    embedding_generator = self.embedding_gen
                else:
                    self.log_message.emit("🧠 Inizializzazione EmbeddingGenerator...", "info")
                    embedding_generator = EmbeddingGenerator(config)

                models_status = embedding_generator.test_models()
                for model_name, available in models_status.items():
                    status = "[✓ OK]" if available else "[❌ NO]"
                    self.log_message.emit(f"  {status} {model_name.upper()}", "info")

                if not any(models_status.values()):
                    self.log_message.emit("⚠️ Nessun modello AI disponibile - processing senza embedding", "warning")
                    embedding_generator = None
                    embedding_enabled = False
            else:
                self.log_message.emit("➡️ Embedding disabilitato nel config", "info")

            # === GEO ENRICHER: plugin o builtin ===
            # Se è presente e abilitato un plugin con plugin_type='geo_enricher',
            # viene usato al posto del builtin. Nessun flag esplicito: basta controllare
            # la presenza del manifest e lo stato della checkbox in processing tab.
            _geo_plugin = None
            _geo_plugin_cfg = {}
            try:
                _plugins_dir = get_app_dir() / 'plugins'
                for _manifest_path in _plugins_dir.glob('*/manifest.json'):
                    try:
                        with open(_manifest_path, 'r', encoding='utf-8') as _f:
                            _m = json.load(_f)
                        if _m.get('plugin_type') == 'geo_enricher' and _m.get('replaces_builtin') == 'geo_enricher':
                            _plugin_id = _m.get('id', '')
                            _plugin_cfg_path = _manifest_path.parent / 'config.json'
                            if _plugin_cfg_path.exists():
                                with open(_plugin_cfg_path, 'r', encoding='utf-8') as _f:
                                    _geo_plugin_cfg = json.load(_f)
                            # Carica il plugin tramite importlib
                            import importlib.util as _ilu
                            _core_file = _manifest_path.parent / f"{_plugin_id}.py"
                            if _core_file.exists():
                                _spec = _ilu.spec_from_file_location(f"{_plugin_id}_geo", str(_core_file))
                                _mod = _ilu.module_from_spec(_spec)
                                _spec.loader.exec_module(_mod)
                                if hasattr(_mod, 'GeoNamesEnricher'):
                                    _geo_plugin = _mod.GeoNamesEnricher(_geo_plugin_cfg)
                                    if _geo_plugin.is_ready():
                                        _only_no_gps = _geo_plugin_cfg.get('only_no_gps', False)
                                        _mode_label = "Solo no-GPS" if _only_no_gps else "Solo GPS"
                                        self.log_message.emit(f"🌍 Geo enricher: plugin {_plugin_id} attivo [{_mode_label}]", "info")
                                    else:
                                        self.log_message.emit(f"⚠️ Plugin {_plugin_id} non pronto (DB mancante?) — fallback builtin", "warning")
                                        _geo_plugin = None
                            break
                    except Exception as _e:
                        logger.debug(f"Errore caricamento plugin geo_enricher: {_e}")
            except Exception as _e:
                logger.debug(f"Errore scan plugin geo_enricher: {_e}")

            # === SCANSIONE IMMAGINI ===
            supported_formats = config.get('image_processing', {}).get('supported_formats', [])
            if not supported_formats:
                self.log_message.emit("❌ Nessun formato supportato configurato", "error")
                self.finished.emit({'total': 0, 'processed': 0, 'errors': 1})
                return

            if self.image_list is not None:
                all_images = list(self.image_list)
                self.log_message.emit(f"📋 Sorgente: catalogo — {len(all_images)} immagini", "info")
            else:
                input_dir = self.input_directory
                if not input_dir or not input_dir.exists():
                    self.log_message.emit(f"❌ Directory input non trovata: {input_dir}", "error")
                    self.finished.emit({'total': 0, 'processed': 0, 'errors': 1})
                    return
                all_images = []
                seen_files = set()
                for ext in supported_formats:
                    for pattern in [f"*{ext}", f"*{ext.upper()}"]:
                        found = input_dir.rglob(pattern) if self.include_subdirs else input_dir.glob(pattern)
                        for fp in found:
                            if fp.name.startswith('.'):
                                continue
                            dk = str(fp).lower() if self.include_subdirs else fp.name.lower()
                            if dk not in seen_files:
                                seen_files.add(dk)
                                all_images.append(fp)

            if not all_images:
                self.log_message.emit("⚠️ Nessuna immagine trovata nella directory input", "warning")
                self.finished.emit({'total': 0, 'processed': 0, 'errors': 0})
                return

            self.log_message.emit(f"🔍 Trovate {len(all_images)} immagini uniche", "info")

            # === FILTRO MODALITÀ ===
            processing_mode = self.options.get('processing_mode', 'new_only')
            images_to_process = []
            for image_path in all_images:
                should = False
                if processing_mode == 'new_only':
                    should = not db_manager.image_exists(image_path.name)
                elif processing_mode == 'reprocess_all':
                    should = True
                elif processing_mode == 'new_plus_errors':
                    has_err = hasattr(db_manager, 'had_processing_errors') and db_manager.had_processing_errors(image_path.name)
                    should = not db_manager.image_exists(image_path.name) or has_err
                if should:
                    images_to_process.append(image_path)

            total_to_process = len(images_to_process)
            skipped_count = len(all_images) - total_to_process

            if skipped_count > 0:
                self.log_message.emit(f"⏭️ {skipped_count} già processate, {total_to_process} da elaborare", "info")
            if total_to_process == 0:
                self.log_message.emit("✅ Tutte le immagini sono già state processate", "info")
                self.finished.emit({'total': len(all_images), 'processed': len(all_images),
                                    'errors': 0, 'skipped_existing': len(all_images)})
                return

            # Stats thread-safe
            stats = {
                'total': len(all_images), 'processed': 0, 'success': 0,
                'errors': 0, 'with_embedding': 0, 'with_tags': 0,
                'skipped_existing': skipped_count,
                # Contatori per-modello
                'clip': 0, 'dinov2': 0, 'aesthetic': 0, 'technical': 0,
                'bioclip': 0, 'llm_tags': 0, 'llm_desc': 0, 'llm_title': 0,
                'geospecies_skipped_no_gps': 0,
            }
            start_time = time.time()

            emb_flags = self.options.get('embedding_model_flags', {})

            # Dizionario condiviso: filename → dict con metadata (NO PIL, work thumb su disco)
            prep_cache = {}

            # Directory cache temporanea work thumbnail
            temp_dir = self._resolve_temp_dir(config)
            temp_dir.mkdir(parents=True, exist_ok=True)
            self._cleanup_temp_cache(temp_dir)  # pulizia run precedente

            # ─── AVVIO THREAD PARALLELI (ExifTool produttore + modelli consumatori) ───
            self.log_message.emit("═" * 50, "info")
            self.log_message.emit("Avvio thread paralleli (ExifTool + modelli AI)", "info")
            self.log_message.emit("═" * 50, "info")

            # Strutture condivise per dipendenza BioCLIP→LLM
            llm_queue = queue.Queue()
            bioclip_results = {}  # filename → {'context': str, 'category_hint': str}
            bioclip_lock = threading.Lock()

            # Mappa disponibilità reale modelli (test_models usa 'musiq', UI usa 'technical')
            _models_avail = models_status if embedding_enabled else {}
            _avail_map = {
                'clip': _models_avail.get('clip', False),
                'dinov2': _models_avail.get('dinov2', False),
                'aesthetic': _models_avail.get('aesthetic', False),
                'technical': _models_avail.get('musiq', False),
                'bioclip': _models_avail.get('bioclip', False),
            }

            bioclip_active = (emb_flags.get('bioclip', {}).get('active', False)
                              and embedding_enabled and embedding_generator is not None
                              and _avail_map.get('bioclip', False))
            llm_active = (llm_gen_config.get('tags', {}).get('enabled') or
                          llm_gen_config.get('description', {}).get('enabled') or
                          llm_gen_config.get('title', {}).get('enabled'))

            # Generatore per LLM: indipendente dai modelli embedding.
            # embedding_generator può essere None se tutti i modelli sono disabilitati,
            # ma LLM usa solo Ollama e non richiede modelli locali.
            llm_generator = None
            if llm_active:
                llm_generator = embedding_generator or self.embedding_gen
                if llm_generator is None:
                    self.log_message.emit("🧠 Inizializzazione EmbeddingGenerator per LLM...", "info")
                    llm_generator = EmbeddingGenerator(config, initialization_mode='llm_only')

            # Tutti le immagini — ogni thread attende ExifTool tramite polling
            model_images = images_to_process
            model_total = len(model_images)

            model_threads = []

            # Thread embedding indipendenti (CLIP, DINOv2, Aesthetic, MUSIQ)
            _emb_thread_defs = [
                ('clip', self._thread_clip),
                ('dinov2', self._thread_dinov2),
                ('aesthetic', self._thread_aesthetic),
                ('technical', self._thread_musiq),
            ]
            for model_key, thread_func in _emb_thread_defs:
                if not emb_flags.get(model_key, {}).get('active', False):
                    continue
                if not (embedding_enabled and embedding_generator is not None):
                    continue
                if not _avail_map.get(model_key, False):
                    self.log_message.emit(
                        f"⚠️ {model_key.upper()} selezionato ma non caricato — thread saltato", "warning")
                    continue
                t = threading.Thread(
                    target=thread_func,
                    args=(model_images, prep_cache, embedding_generator, db_manager,
                          emb_flags.get(model_key, {}), stats, model_total,
                          processing_mode),
                    name=f"model-{model_key}", daemon=True
                )
                model_threads.append(t)
                self.log_message.emit(f"🚀 Thread {model_key.upper()} pronto ({model_total} immagini)", "info")

            # Thread BioCLIP (produce risultati per LLM via queue)
            if (emb_flags.get('bioclip', {}).get('active', False)
                    and not _avail_map.get('bioclip', False)):
                self.log_message.emit(
                    "⚠️ BIOCLIP selezionato ma non caricato — thread saltato", "warning")
            if bioclip_active:
                t = threading.Thread(
                    target=self._thread_bioclip,
                    args=(model_images, prep_cache, embedding_generator, db_manager,
                          emb_flags.get('bioclip', {}), stats, model_total,
                          bioclip_results, bioclip_lock, llm_queue, llm_active,
                          processing_mode),
                    name="model-bioclip", daemon=True
                )
                model_threads.append(t)
                self.log_message.emit(f"🚀 Thread BIOCLIP pronto ({model_total} immagini)", "info")

            # Thread LLM Vision
            if llm_active and llm_generator is not None:
                # Nota: la coda llm_queue viene alimentata da _thread_exiftool (se bioclip_active=False)
                # oppure da _thread_bioclip (se bioclip_active=True) — NON pre-riempita qui
                t = threading.Thread(
                    target=self._thread_llm,
                    args=(prep_cache, llm_generator, db_manager,
                          llm_gen_config, stats, model_total,
                          bioclip_results, bioclip_lock, llm_queue),
                    name="model-llm", daemon=True
                )
                model_threads.append(t)
                self.log_message.emit(f"🚀 Thread LLM pronto ({model_total} immagini)", "info")

            # Thread ExifTool (produttore — avvia insieme ai modelli)
            exif_thread = threading.Thread(
                target=self._thread_exiftool,
                args=(images_to_process, prep_cache, temp_dir,
                      raw_processor, config, db_manager,
                      processing_mode, emb_flags, llm_gen_config,
                      stats, total_to_process, llm_queue, llm_active, bioclip_active,
                      _geo_plugin, _geo_plugin_cfg),
                name="model-exiftool", daemon=True
            )
            model_threads.append(exif_thread)
            self.log_message.emit(f"🚀 Thread ExifTool pronto ({total_to_process} immagini)", "info")

            self._model_threads = model_threads

            # Avvia ExifTool per primo con head start di 50 foto (o meno se batch piccolo)
            exif_thread.start()
            head_start = min(50, total_to_process)
            if head_start > 0:
                self.log_message.emit(f"⏳ Head start ExifTool: attendo {head_start} foto prima di avviare i modelli...", "info")
                while self.is_running and len(prep_cache) < head_start:
                    time.sleep(0.1)
                if self.is_running:
                    self.log_message.emit(f"🚀 Buffer pronto ({len(prep_cache)} foto) — avvio modelli AI", "info")

            # Avvia i thread modello (ExifTool è già in esecuzione)
            for t in model_threads:
                if t.name != "model-exiftool":
                    t.start()

            # Attendi completamento con check is_running (permette stop reattivo)
            for t in model_threads:
                while t.is_alive():
                    t.join(timeout=0.5)
                    if not self.is_running:
                        # Stop richiesto: i thread controllano is_running e si fermeranno
                        # Svuota llm_queue per sbloccare il thread LLM se in attesa
                        # (incluso se ExifTool sta ancora accodando)
                        try:
                            while not llm_queue.empty():
                                llm_queue.get_nowait()
                        except queue.Empty:
                            pass
                        llm_queue.put(None)  # sentinella per sbloccare get()
                        break

            # Attendi termine effettivo di tutti i thread
            # LLM può avere una chiamata HTTP in corso (fino a ~30s), timeout generoso
            for t in model_threads:
                if 'llm' in t.name:
                    _timeout = 60
                elif 'exiftool' in t.name:
                    _timeout = 30
                else:
                    _timeout = 15
                t.join(timeout=_timeout)
                if t.is_alive():
                    self.log_message.emit(f"⚠️ Thread {t.name} non terminato in tempo", "warning")

            self._model_threads = []

            # Pulizia work thumbnail temporanei
            self._cleanup_temp_cache(temp_dir)

            # Libera VRAM al termine di tutti i modelli
            self._cleanup_gpu_memory()

            # === STATISTICHE FINALI ===
            total_time = time.time() - start_time
            stats['processing_time'] = total_time

            self.log_message.emit("═" * 50, "info")
            self.log_message.emit("PROCESSING COMPLETATO", "info")
            self.log_message.emit(f"Totali: {stats['total']}  |  Nuove: {stats['processed']}  |  Già indicizzate: {stats['skipped_existing']}  |  Errori: {stats['errors']}", "info")
            self.log_message.emit(f"Tempo totale: {total_time // 60:02.0f}:{total_time % 60:02.0f}", "info")

            # Conteggi per-modello (solo modelli che hanno lavorato)
            model_parts = []
            if stats['clip']:       model_parts.append(f"CLIP: {stats['clip']}")
            if stats['dinov2']:     model_parts.append(f"DINOv2: {stats['dinov2']}")
            if stats['aesthetic']:  model_parts.append(f"Aesthetic: {stats['aesthetic']}")
            if stats['technical']:  model_parts.append(f"MUSIQ: {stats['technical']}")
            if stats['bioclip']:    model_parts.append(f"BioCLIP: {stats['bioclip']}")
            if stats['llm_tags']:   model_parts.append(f"Tags: {stats['llm_tags']}")
            if stats['llm_desc']:   model_parts.append(f"Descrizioni: {stats['llm_desc']}")
            if stats['llm_title']:  model_parts.append(f"Titoli: {stats['llm_title']}")
            if model_parts:
                self.log_message.emit("  ".join(model_parts), "info")

            # Avviso GeoSpecies non attivo per foto senza GPS
            geo_skipped = stats.get('geospecies_skipped_no_gps', 0)
            if geo_skipped > 0 and stats.get('bioclip', 0) > 0:
                self.log_message.emit(
                    f"ℹ️ GeoSpecies non attivo per {geo_skipped} foto: GPS assente — "
                    f"BioCLIP ha usato TreeOfLife globale (450k specie)",
                    "info"
                )

            self.log_message.emit("═" * 50, "info")

            self.finished.emit(stats)

        except Exception as e:
            self.log_message.emit(f"❌ Errore critico processing: {e}", "error")
            import traceback
            self.log_message.emit(f"Traceback: {traceback.format_exc()}", "error")
            self.finished.emit({'total': 0, 'processed': 0, 'errors': 1})

    # ─────────────────────────────────────────────────────────────
    # FASE 0 — Preparazione singola immagine
    # ─────────────────────────────────────────────────────────────
    def _prep_image(self, image_path, raw_processor, config, db_manager,
                    processing_mode, emb_flags, llm_gen_config,
                    temp_dir=None, geo_plugin=None, geo_plugin_cfg=None):
        """Estrae EXIF + thumbnail + geo + hash, inserisce/aggiorna record DB base.
        Salva work thumbnail su disco (temp_dir) invece di tenerlo in RAM.
        Ritorna dict con dati prep oppure None in caso di errore fatale."""
        try:
            fname = image_path.name
            self.log_message.emit(f"📂 Prep: {fname}", "info")
            is_raw = raw_processor.is_raw_file(image_path)

            # --- Estrazione EXIF metadata ---
            try:
                extracted_metadata = raw_processor.extract_raw_metadata(image_path)
            except Exception as e:
                self.log_message.emit(f"⚠️ Errore EXIF {fname}: {e}", "warning")
                extracted_metadata = {}

            image_data = {
                'filename': fname,
                'filepath': str(image_path),
                'file_size': image_path.stat().st_size,
                'file_format': image_path.suffix.lower().replace('.', ''),
                'is_raw': is_raw,
                'success': True,
                'error_message': None,
                'embedding_generated': False,
                'llm_generated': False,
                'app_version': '1.0',
                'tags': json.dumps([], ensure_ascii=False),
            }
            if extracted_metadata:
                for key, value in extracted_metadata.items():
                    if key not in ['is_raw', 'raw_info']:
                        image_data[key] = value

            # --- Hash file ---
            try:
                import hashlib
                md5 = hashlib.md5()
                with open(image_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        md5.update(chunk)
                image_data['file_hash'] = md5.hexdigest()
            except Exception:
                pass

            # --- Geo hierarchy da GPS (plugin o builtin) ---
            geo_hierarchy = None
            location_hint = None
            gps_lat = image_data.get('gps_latitude')
            gps_lon = image_data.get('gps_longitude')

            if gps_lat is not None and gps_lon is not None:
                # Immagine con GPS: reverse geocoding
                try:
                    if geo_plugin is not None:
                        geo_hierarchy = geo_plugin.get_hierarchy(float(gps_lat), float(gps_lon))
                        if geo_hierarchy:
                            image_data['geo_hierarchy'] = geo_hierarchy
                            location_hint = geo_plugin.get_location_hint(geo_hierarchy)
                            self.log_message.emit(f"🌍 {fname}: {geo_hierarchy}", "info")
                    else:
                        from geo_enricher import get_geo_hierarchy, get_location_hint
                        geo_hierarchy = get_geo_hierarchy(float(gps_lat), float(gps_lon))
                        if geo_hierarchy:
                            image_data['geo_hierarchy'] = geo_hierarchy
                            location_hint = get_location_hint(geo_hierarchy)
                            self.log_message.emit(f"🌍 {fname}: {geo_hierarchy}", "info")
                except Exception as geo_err:
                    self.log_message.emit(f"⚠️ Geo enricher {fname}: {geo_err}", "warning")

            elif geo_plugin is not None and (geo_plugin_cfg or {}).get('only_no_gps', False):
                # Immagine senza GPS + plugin attivo in modalità only_no_gps:
                # assegna last_location configurata nel plugin
                try:
                    _last = (geo_plugin_cfg or {}).get('last_location', {}) or {}
                    _lat = _last.get('latitude')
                    _lon = _last.get('longitude')
                    _alt = _last.get('altitude')
                    if _lat is not None and _lon is not None:
                        _preset = _last.get('preset_hierarchy')
                        geo_hierarchy = _preset if _preset else geo_plugin.get_hierarchy(float(_lat), float(_lon))
                        if geo_hierarchy:
                            image_data['gps_latitude']  = _lat
                            image_data['gps_longitude'] = _lon
                            image_data['gps_altitude']  = _alt
                            image_data['geo_hierarchy'] = geo_hierarchy
                            location_hint = geo_plugin.get_location_hint(geo_hierarchy)
                            self.log_message.emit(f"📍 {fname}: posizione assegnata → {geo_hierarchy}", "info")
                except Exception as geo_err:
                    self.log_message.emit(f"⚠️ Geo no-GPS {fname}: {geo_err}", "warning")

            # --- Inserimento/aggiornamento record DB base ---
            image_exists = db_manager.image_exists(fname)
            is_new = False
            ai_fields = {}  # stato campi AI già popolati (per logica overwrite)
            with self._db_lock:
                if image_exists and processing_mode in ['reprocess_all', 'new_plus_errors']:
                    # Leggi stato campi AI PRIMA di aggiornare EXIF
                    ai_fields = db_manager.get_ai_fields_status(fname)
                    db_manager.update_image(fname, image_data)
                    self.log_message.emit(f"🔄 DB aggiornato (reprocess): {fname}", "info")
                elif image_exists:
                    # Già nel DB e mode=new_only: skip silenzioso → log esplicito
                    self.log_message.emit(f"⏭️ Già nel DB, saltato: {fname}", "debug")
                elif not image_exists:
                    image_id = db_manager.insert_image(image_data)
                    is_new = True
                    if image_id:
                        self.log_message.emit(f"✅ DB inserito: {fname} (ID: {image_id})", "info")
                    else:
                        self.log_message.emit(f"❌ DB inserimento fallito: {fname}", "error")
                        return None

            # --- Thumbnail per modelli AI ---
            thumbnail = None
            any_model_active = any(
                emb_flags.get(k, {}).get('active', False)
                for k in ('clip', 'dinov2', 'bioclip', 'aesthetic', 'technical')
            )
            llm_active = (llm_gen_config.get('tags', {}).get('enabled') or
                          llm_gen_config.get('description', {}).get('enabled') or
                          llm_gen_config.get('title', {}).get('enabled'))

            if any_model_active or llm_active:
                # Calcola MAX target size dai profili attivi
                active_profiles = []
                models_cfg = config.get('embedding', {}).get('models', {})
                _profile_map = {
                    'clip': 'clip_embedding', 'dinov2': 'dinov2_embedding',
                    'bioclip': 'bioclip_classification', 'aesthetic': 'aesthetic_score',
                    'technical': 'technical_score',
                }
                for mk, prof in _profile_map.items():
                    if emb_flags.get(mk, {}).get('active', False):
                        active_profiles.append(prof)
                if llm_active:
                    active_profiles.append('llm_vision')

                max_size = raw_processor.get_max_target_size(active_profiles) if active_profiles else 1024
                thumbnail = self._prepare_image_for_ai_corrected(
                    image_path, raw_processor, is_raw, target_size=max_size)

                if thumbnail and hasattr(thumbnail, 'size'):
                    # Salva thumbnail cache gallery con correzione orientazione
                    try:
                        from utils.thumb_cache import save_gallery_thumb
                        from PIL import Image as _PILImage
                        _ORIENT_OPS = {
                            2: [_PILImage.Transpose.FLIP_LEFT_RIGHT],
                            3: [_PILImage.Transpose.ROTATE_180],
                            4: [_PILImage.Transpose.FLIP_TOP_BOTTOM],
                            5: [_PILImage.Transpose.FLIP_LEFT_RIGHT, _PILImage.Transpose.ROTATE_90],
                            6: [_PILImage.Transpose.ROTATE_270],
                            7: [_PILImage.Transpose.FLIP_LEFT_RIGHT, _PILImage.Transpose.ROTATE_270],
                            8: [_PILImage.Transpose.ROTATE_90],
                        }
                        orientation = image_data.get('orientation')
                        ops = _ORIENT_OPS.get(int(orientation), []) if orientation and orientation != 1 else []
                        if ops:
                            thumb_oriented = thumbnail.copy()
                            for op in ops:
                                thumb_oriented = thumb_oriented.transpose(op)
                            save_gallery_thumb(image_path, thumb_oriented)
                        else:
                            save_gallery_thumb(image_path, thumbnail)
                    except Exception as _e:
                        logger.warning(f"Errore thumbnail cache gallery: {_e}")

                    # Salva work thumbnail su disco (rilascia PIL dalla RAM)
                    work_thumb_path = None
                    if temp_dir:
                        wtp = self._get_work_thumb_path(image_path, temp_dir)
                        if self._save_work_thumb(thumbnail, wtp):
                            work_thumb_path = wtp
                    thumbnail = None  # libera dalla RAM
                else:
                    work_thumb_path = None
                    if is_raw:
                        self.log_message.emit(
                            f"⚠️ {fname}: nessuna immagine estraibile dal RAW — "
                            f"embedding e LLM saltati", "warning")

            else:
                work_thumb_path = None

            return {
                'image_path': image_path,
                'work_thumb_path': work_thumb_path,
                'image_data': image_data,
                'geo_hierarchy': geo_hierarchy,
                'location_hint': location_hint,
                'is_new': is_new,
                'ai_fields': ai_fields,  # campi AI già popolati nel DB
            }

        except Exception as e:
            self.log_message.emit(f"❌ Errore prep {image_path.name}: {e}", "error")
            import traceback
            self.log_message.emit(f"Traceback: {traceback.format_exc()}", "error")
            return None

    # ─────────────────────────────────────────────────────────────
    # THREAD MODELLI EMBEDDING
    # ─────────────────────────────────────────────────────────────
    def _thread_clip(self, images, prep_cache, emb_gen, db_manager, flags, stats, total,
                     processing_mode='new_only'):
        """Thread CLIP: genera embedding 768-dim per tutte le immagini."""
        import numpy as np
        overwrite = flags.get('overwrite', False)
        use_gpu = self._is_model_on_gpu(emb_gen, 'clip')
        for i, image_path in enumerate(images, 1):
            if not self._wait_if_paused():
                break
            fname = image_path.name
            # Attendi che ExifTool abbia preparato questa foto
            while fname not in prep_cache:
                if not self.is_running:
                    return
                time.sleep(0.05)
            prep = prep_cache[fname]
            if prep is None:
                self.model_progress.emit('clip', i, total)
                continue
            # Skip se overwrite OFF e campo già popolato nel DB
            if not overwrite and not prep.get('is_new', True):
                if prep.get('ai_fields', {}).get('clip_embedding', False):
                    self.model_progress.emit('clip', i, total)
                    continue
            work_thumb_path = prep.get('work_thumb_path')
            if work_thumb_path is None:
                self.model_progress.emit('clip', i, total)
                continue
            thumb = self._load_work_thumb(work_thumb_path)
            if thumb is None:
                self.model_progress.emit('clip', i, total)
                continue
            try:
                # Serializza inferenza GPU per evitare contesa tra thread
                if use_gpu:
                    self._gpu_lock.acquire()
                try:
                    clip_emb = emb_gen._generate_clip_embedding(thumb, 'pil')
                finally:
                    if use_gpu:
                        self._gpu_lock.release()
                if clip_emb is not None and isinstance(clip_emb, np.ndarray):
                    if np.any(np.isnan(clip_emb)):
                        self.log_message.emit(f"🚨 CLIP NaN: {fname}", "error")
                    else:
                        with self._db_lock:
                            db_manager.update_image(fname, {
                                'clip_embedding': clip_emb, 'embedding_generated': True})
                        with self._stats_lock:
                            stats['with_embedding'] += 1
                            stats['clip'] += 1
            except Exception as e:
                self.log_message.emit(f"❌ CLIP {fname}: {e}", "error")
            self.model_progress.emit('clip', i, total)

    def _thread_dinov2(self, images, prep_cache, emb_gen, db_manager, flags, stats, total,
                       processing_mode='new_only'):
        """Thread DINOv2: genera embedding 768-dim per tutte le immagini."""
        import numpy as np
        overwrite = flags.get('overwrite', False)
        use_gpu = self._is_model_on_gpu(emb_gen, 'dinov2')
        for i, image_path in enumerate(images, 1):
            if not self._wait_if_paused():
                break
            fname = image_path.name
            # Attendi che ExifTool abbia preparato questa foto
            while fname not in prep_cache:
                if not self.is_running:
                    return
                time.sleep(0.05)
            prep = prep_cache[fname]
            if prep is None:
                self.model_progress.emit('dinov2', i, total)
                continue
            if not overwrite and not prep.get('is_new', True):
                if prep.get('ai_fields', {}).get('dinov2_embedding', False):
                    self.model_progress.emit('dinov2', i, total)
                    continue
            work_thumb_path = prep.get('work_thumb_path')
            if work_thumb_path is None:
                self.model_progress.emit('dinov2', i, total)
                continue
            thumb = self._load_work_thumb(work_thumb_path)
            if thumb is None:
                self.model_progress.emit('dinov2', i, total)
                continue
            try:
                if use_gpu:
                    self._gpu_lock.acquire()
                try:
                    dinov2_emb = emb_gen._generate_dinov2_embedding(thumb, 'pil')
                finally:
                    if use_gpu:
                        self._gpu_lock.release()
                if dinov2_emb is not None and isinstance(dinov2_emb, np.ndarray):
                    if np.any(np.isnan(dinov2_emb)):
                        self.log_message.emit(f"🚨 DINOv2 NaN: {fname}", "error")
                    else:
                        with self._db_lock:
                            db_manager.update_image(fname, {
                                'dinov2_embedding': dinov2_emb, 'embedding_generated': True})
                        with self._stats_lock:
                            stats['with_embedding'] += 1
                            stats['dinov2'] += 1
            except Exception as e:
                self.log_message.emit(f"❌ DINOv2 {fname}: {e}", "error")
            self.model_progress.emit('dinov2', i, total)

    def _thread_aesthetic(self, images, prep_cache, emb_gen, db_manager, flags, stats, total,
                          processing_mode='new_only'):
        """Thread Aesthetic: calcola punteggio estetico 0-10."""
        overwrite = flags.get('overwrite', False)
        use_gpu = self._is_model_on_gpu(emb_gen, 'aesthetic')
        for i, image_path in enumerate(images, 1):
            if not self._wait_if_paused():
                break
            fname = image_path.name
            # Attendi che ExifTool abbia preparato questa foto
            while fname not in prep_cache:
                if not self.is_running:
                    return
                time.sleep(0.05)
            prep = prep_cache[fname]
            if prep is None:
                self.model_progress.emit('aesthetic', i, total)
                continue
            if not overwrite and not prep.get('is_new', True):
                if prep.get('ai_fields', {}).get('aesthetic_score', False):
                    self.model_progress.emit('aesthetic', i, total)
                    continue
            work_thumb_path = prep.get('work_thumb_path')
            if work_thumb_path is None:
                self.model_progress.emit('aesthetic', i, total)
                continue
            thumb = self._load_work_thumb(work_thumb_path)
            if thumb is None:
                self.model_progress.emit('aesthetic', i, total)
                continue
            try:
                if use_gpu:
                    self._gpu_lock.acquire()
                try:
                    score = emb_gen._generate_aesthetic_score(thumb, 'pil')
                finally:
                    if use_gpu:
                        self._gpu_lock.release()
                if score is not None:
                    with self._db_lock:
                        db_manager.update_image(fname, {'aesthetic_score': score})
                    with self._stats_lock:
                        stats['aesthetic'] += 1
            except Exception as e:
                self.log_message.emit(f"❌ Aesthetic {fname}: {e}", "error")
            self.model_progress.emit('aesthetic', i, total)

    def _thread_musiq(self, images, prep_cache, emb_gen, db_manager, flags, stats, total,
                      processing_mode='new_only'):
        """Thread MUSIQ/Technical: calcola punteggio qualità tecnica ~0-100."""
        overwrite = flags.get('overwrite', False)
        use_gpu = self._is_model_on_gpu(emb_gen, 'technical')
        for i, image_path in enumerate(images, 1):
            if not self._wait_if_paused():
                break
            fname = image_path.name
            # Attendi che ExifTool abbia preparato questa foto
            while fname not in prep_cache:
                if not self.is_running:
                    return
                time.sleep(0.05)
            prep = prep_cache[fname]
            if prep is None:
                self.model_progress.emit('technical', i, total)
                continue
            if not overwrite and not prep.get('is_new', True):
                if prep.get('ai_fields', {}).get('technical_score', False):
                    self.model_progress.emit('technical', i, total)
                    continue
            work_thumb_path = prep.get('work_thumb_path')
            if work_thumb_path is None:
                self.model_progress.emit('technical', i, total)
                continue
            thumb = self._load_work_thumb(work_thumb_path)
            if thumb is None:
                self.model_progress.emit('technical', i, total)
                continue
            try:
                if use_gpu:
                    self._gpu_lock.acquire()
                try:
                    score = emb_gen._generate_musiq_score(thumb)
                finally:
                    if use_gpu:
                        self._gpu_lock.release()
                if score is not None:
                    with self._db_lock:
                        db_manager.update_image(fname, {'technical_score': score})
                    with self._stats_lock:
                        stats['technical'] += 1
            except Exception as e:
                self.log_message.emit(f"❌ Technical {fname}: {e}", "error")
            self.model_progress.emit('technical', i, total)

    # ─────────────────────────────────────────────────────────────
    # THREAD BIOCLIP (produce per LLM)
    # ─────────────────────────────────────────────────────────────
    def _thread_bioclip(self, images, prep_cache, emb_gen, db_manager, flags, stats, total,
                        bioclip_results, bioclip_lock, llm_queue, llm_active,
                        processing_mode='new_only'):
        """Thread BioCLIP: tassonomia + alimenta coda LLM."""
        from embedding_generator import EmbeddingGenerator
        overwrite = flags.get('overwrite', False)
        use_gpu = self._is_model_on_gpu(emb_gen, 'bioclip')

        for i, image_path in enumerate(images, 1):
            if not self._wait_if_paused():
                # Stop: metti sentinella per sbloccare LLM
                if llm_active:
                    llm_queue.put(None)
                break
            fname = image_path.name
            # Attendi che ExifTool abbia preparato questa foto
            while fname not in prep_cache:
                if not self.is_running:
                    if llm_active:
                        llm_queue.put(None)
                    return
                time.sleep(0.05)
            prep = prep_cache[fname]
            if prep is None:
                if llm_active:
                    llm_queue.put(image_path)
                self.model_progress.emit('bioclip', i, total)
                continue
            is_new = prep.get('is_new', True)

            skip_bioclip = (not overwrite and not is_new
                            and prep.get('ai_fields', {}).get('bioclip_taxonomy', False))

            if not skip_bioclip:
                work_thumb_path = prep.get('work_thumb_path')
                if work_thumb_path is None:
                    # Nessuna immagine disponibile: accoda per LLM e passa al prossimo
                    if llm_active:
                        llm_queue.put(image_path)
                    self.model_progress.emit('bioclip', i, total)
                    continue
                thumb = self._load_work_thumb(work_thumb_path)
                if thumb is None:
                    if llm_active:
                        llm_queue.put(image_path)
                    self.model_progress.emit('bioclip', i, total)
                    continue
                try:
                    # Passa geo_hierarchy a generate_bioclip_tags per GeoSpecies (solo cache locale)
                    _geo_hierarchy = prep.get('geo_hierarchy')
                    if use_gpu:
                        self._gpu_lock.acquire()
                    try:
                        bioclip_tags, bioclip_taxonomy = emb_gen.generate_bioclip_tags(thumb, geo_hierarchy=_geo_hierarchy)
                    finally:
                        if use_gpu:
                            self._gpu_lock.release()

                    if bioclip_taxonomy and isinstance(bioclip_taxonomy, list):
                        with self._db_lock:
                            db_manager.update_image(fname, {
                                'bioclip_taxonomy': json.dumps(bioclip_taxonomy, ensure_ascii=False)
                            })
                        with self._stats_lock:
                            stats['bioclip'] += 1
                        self.log_message.emit(
                            f"🌿 BioCLIP {fname}: {len([l for l in bioclip_taxonomy if l])} livelli", "info")

                    # Aggiorna contatore GeoSpecies skipped (foto senza GPS)
                    with self._stats_lock:
                        stats['geospecies_skipped_no_gps'] = emb_gen.geospecies_skipped_no_gps

                    # Estrai contesto per LLM
                    ctx = EmbeddingGenerator.extract_bioclip_context(bioclip_tags or [])
                    cat = EmbeddingGenerator.extract_category_hint(bioclip_taxonomy or [])
                    with bioclip_lock:
                        bioclip_results[fname] = {'context': ctx, 'category_hint': cat}

                except Exception as e:
                    self.log_message.emit(f"❌ BioCLIP {fname}: {e}", "error")

            # Accoda per LLM (anche se BioCLIP è stato saltato)
            if llm_active:
                llm_queue.put(image_path)

            self.model_progress.emit('bioclip', i, total)

        # Sentinella fine coda per LLM
        if llm_active:
            llm_queue.put(None)

    # ─────────────────────────────────────────────────────────────
    # THREAD LLM VISION
    # ─────────────────────────────────────────────────────────────
    def _thread_llm(self, prep_cache, emb_gen, db_manager, llm_gen_config, stats, total,
                    bioclip_results, bioclip_lock, llm_queue):
        """Thread LLM: consuma dalla coda, genera tags/descrizione/titolo."""
        gen_tags_cfg = llm_gen_config.get('tags', {})
        gen_desc_cfg = llm_gen_config.get('description', {})
        gen_title_cfg = llm_gen_config.get('title', {})
        processed = 0

        while self.is_running:
            # Attendi prossima immagine dalla coda (timeout per controllare is_running)
            try:
                image_path = llm_queue.get(timeout=2.0)
            except queue.Empty:
                continue

            if image_path is None:
                break  # sentinella: fine coda

            if not self._wait_if_paused():
                break

            fname = image_path.name
            t_start = time.time()

            # Attendi che ExifTool abbia preparato questa foto
            while fname not in prep_cache:
                if not self.is_running:
                    return
                time.sleep(0.05)
            t_prep_wait = time.time()

            prep = prep_cache.get(fname)
            work_thumb_path = prep.get('work_thumb_path') if prep else None
            if not prep or work_thumb_path is None:
                processed += 1
                self.model_progress.emit('llm', processed, total)
                continue

            thumb = self._load_work_thumb(work_thumb_path)
            t_thumb_load = time.time()
            if thumb is None:
                processed += 1
                self.model_progress.emit('llm', processed, total)
                continue

            # Contesto BioCLIP (potrebbe non esserci se BioCLIP disabilitato)
            with bioclip_lock:
                bc = bioclip_results.get(fname, {})
            bioclip_context = bc.get('context')
            category_hint = bc.get('category_hint')
            location_hint = prep.get('location_hint')
            geo_hierarchy = prep.get('geo_hierarchy')


            try:
                # Determina cosa generare (rispettando overwrite)
                # Usa ai_fields per sapere se tags/desc/title sono già nel DB
                ai_fields = prep.get('ai_fields', {})
                is_new = prep.get('is_new', True)

                # Tags: se overwrite OFF e campo già popolato, non rigenerare
                should_gen_tags = gen_tags_cfg.get('enabled', False)
                if should_gen_tags and not gen_tags_cfg.get('overwrite') and not is_new:
                    if ai_fields.get('tags', False):
                        should_gen_tags = False

                should_gen_desc = gen_desc_cfg.get('enabled', False)
                if should_gen_desc and not gen_desc_cfg.get('overwrite') and not is_new:
                    if ai_fields.get('description', False):
                        should_gen_desc = False

                should_gen_title = gen_title_cfg.get('enabled', False)
                if should_gen_title and not gen_title_cfg.get('overwrite') and not is_new:
                    if ai_fields.get('title', False):
                        should_gen_title = False

                # Carica tags esistenti per merge (solo se non sovrascriviamo)
                existing_tags = []
                img_data = prep.get('image_data', {})
                if img_data.get('tags') and not gen_tags_cfg.get('overwrite'):
                    try:
                        existing_tags = json.loads(img_data['tags'])
                    except (json.JSONDecodeError, TypeError):
                        existing_tags = []

                if not (should_gen_tags or should_gen_desc or should_gen_title):
                    processed += 1
                    self.model_progress.emit('llm', processed, total)
                    continue

                self.log_message.emit(f"🤖 LLM: {fname}", "info")

                # Chiamata combinata unica — tutti i modi in un solo round-trip Ollama.
                modes = []
                if should_gen_tags:    modes.append('tags')
                if should_gen_desc:    modes.append('description')
                if should_gen_title:   modes.append('title')

                llm_results = {'tags': None, 'description': None, 'title': None}
                t_llm_start = time.time()
                try:
                    # Sempre una sola chiamata con nucleo analitico unificato,
                    # indipendentemente dal numero di campi richiesti
                    combined = emb_gen.generate_llm_combined(
                        thumb, modes,
                        max_tags=gen_tags_cfg.get('max', 10),
                        max_description_words=gen_desc_cfg.get('max', 100),
                        max_title_words=gen_title_cfg.get('max', 5),
                        bioclip_context=bioclip_context,
                        category_hint=category_hint,
                        location_hint=location_hint,
                    )
                    llm_results.update(combined)
                except Exception as e:
                    self.log_message.emit(f"⚠️ LLM {fname}: {e}", "warning")
                t_llm_end = time.time()

                # Pulisci cache immagine LLM
                emb_gen._cleanup_llm_image_cache()

                # ⏱ Timer diagnostico per-fase LLM
                queue_wait_ms = (t_prep_wait - t_start) * 1000
                thumb_load_ms = (t_thumb_load - t_prep_wait) * 1000
                llm_call_ms = (t_llm_end - t_llm_start) * 1000
                total_ms = (t_llm_end - t_start) * 1000
                overhead_ms = total_ms - llm_call_ms
                self.log_message.emit(
                    f"⏱ LLM {fname}: totale {total_ms:.0f}ms "
                    f"(coda {queue_wait_ms:.0f}ms + thumb {thumb_load_ms:.0f}ms + "
                    f"LLM {llm_call_ms:.0f}ms + overhead {overhead_ms - queue_wait_ms - thumb_load_ms:.0f}ms)",
                    "debug"
                )

                # Costruisci update dict per DB
                update_data = {'llm_generated': True}

                # Tags
                if llm_results['tags']:
                    llm_tags = llm_results['tags']
                    # Estrai nome scientifico da bioclip_context per normalize_tags
                    sci_name = None
                    if bioclip_context:
                        sci_name = bioclip_context.split('(')[0].split(',')[0].strip() or None

                    if gen_tags_cfg.get('overwrite'):
                        final_tags = normalize_tags(llm_tags, scientific_name=sci_name)
                    else:
                        # Merge: unione senza duplicati, poi normalize
                        merged = list(existing_tags)
                        existing_lower = {t.lower() for t in existing_tags}
                        for t in llm_tags:
                            if t.lower() not in existing_lower:
                                merged.append(t)
                        final_tags = normalize_tags(merged, scientific_name=sci_name)

                    # Aggiungi città geo come tag (plugin o builtin)
                    if geo_hierarchy:
                        try:
                            if _geo_plugin is not None:
                                city_tag = _geo_plugin.get_geo_leaf(geo_hierarchy)
                            else:
                                from geo_enricher import get_geo_leaf
                                city_tag = get_geo_leaf(geo_hierarchy)
                            if city_tag and city_tag.lower() not in {t.lower() for t in final_tags}:
                                final_tags.append(city_tag)
                        except Exception:
                            pass

                    update_data['tags'] = json.dumps(final_tags, ensure_ascii=False)
                    self.log_message.emit(f"🏷️ LLM tags {fname}: {len(final_tags)} tag", "info")
                    with self._stats_lock:
                        stats['with_tags'] += 1
                        stats['llm_tags'] += 1

                # Descrizione
                if llm_results['description']:
                    update_data['description'] = llm_results['description']
                    self.log_message.emit(f"📝 LLM desc {fname}: {len(llm_results['description'])} car", "info")
                    with self._stats_lock:
                        stats['llm_desc'] += 1

                # Titolo
                if llm_results['title']:
                    update_data['title'] = llm_results['title']
                    self.log_message.emit(f"📌 LLM title {fname}: {llm_results['title']}", "info")
                    with self._stats_lock:
                        stats['llm_title'] += 1

                # Aggiorna DB
                with self._db_lock:
                    db_manager.update_image(fname, update_data)

            except Exception as e:
                self.log_message.emit(f"❌ LLM {fname}: {e}", "error")
                import traceback
                self.log_message.emit(f"Traceback: {traceback.format_exc()}", "error")

            processed += 1
            self.model_progress.emit('llm', processed, total)

    # ─────────────────────────────────────────────────────────────
    # THREAD EXIFTOOL (produttore — estrae EXIF + salva work thumb)
    # ─────────────────────────────────────────────────────────────
    def _thread_exiftool(self, images_to_process, prep_cache, temp_dir,
                         raw_processor, config, db_manager,
                         processing_mode, emb_flags, llm_gen_config,
                         stats, total_to_process, llm_queue, llm_active, bioclip_active,
                         geo_plugin=None, geo_plugin_cfg=None):
        """Thread ExifTool: estrae EXIF + salva work thumbnail su disco per ogni immagine."""
        for i, image_path in enumerate(images_to_process, 1):
            if not self._wait_if_paused():
                break
            prep = self._prep_image(
                image_path, raw_processor, config, db_manager,
                processing_mode, emb_flags, llm_gen_config,
                temp_dir=temp_dir,
                geo_plugin=geo_plugin, geo_plugin_cfg=geo_plugin_cfg
            )
            if prep:
                prep_cache[image_path.name] = prep
                with self._stats_lock:
                    stats['success'] += 1
                    stats['processed'] += 1
                # Se LLM attivo e BioCLIP non attivo: accoda subito per LLM
                if llm_active and not bioclip_active:
                    llm_queue.put(image_path)
            else:
                # Marker None: sblocca i thread modello in attesa su prep_cache
                prep_cache[image_path.name] = None
                with self._stats_lock:
                    stats['errors'] += 1
            self.model_progress.emit('exiftool', i, total_to_process)

        # Fine: se LLM senza BioCLIP, manda sentinella
        if llm_active and not bioclip_active:
            llm_queue.put(None)

        self.log_message.emit(
            f"✅ ExifTool completato: {stats.get('success', 0)}/{total_to_process} immagini preparate",
            "info"
        )

    # ─────────────────────────────────────────────────────────────
    # UTILITY
    # ─────────────────────────────────────────────────────────────
    def _cleanup_gpu_memory(self):
        """Libera memoria GPU al termine del processing."""
        try:
            import torch
            import gc
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif torch.backends.mps.is_available():
                torch.mps.empty_cache()
            gc.collect()
        except Exception:
            pass

    def _prepare_image_for_ai_corrected(self, image_path, raw_processor, is_raw, target_size=1024):
        """Prepara immagine PIL per modelli AI con dimensioni ottimali.
        Estrae a risoluzione massima per cache condivisa fra tutti i modelli."""
        try:
            if is_raw:
                self.log_message.emit(f"🔄 Preparazione RAW: {image_path.name}", "info")
                pil_image = raw_processor.extract_thumbnail(image_path, target_size=target_size)
                if pil_image:
                    return pil_image
                else:
                    self.log_message.emit(f"❌ Conversione RAW fallita: {image_path.name}", "error")
                    return None
            else:
                try:
                    from PIL import Image
                    with Image.open(image_path) as img:
                        pil_image = img.copy()
                        if pil_image.mode not in ['RGB', 'L']:
                            pil_image = pil_image.convert('RGB')
                        if max(pil_image.size) > target_size:
                            pil_image.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
                        return pil_image
                except Exception as e:
                    self.log_message.emit(f"❌ Errore immagine {image_path.name}: {e}", "error")
                    return None
        except Exception as e:
            self.log_message.emit(f"❌ Errore prepare_image {image_path.name}: {e}", "error")
            return None

    # ─────────────────────────────────────────────────────────────
    # UTILITY — Disk cache work thumbnail
    # ─────────────────────────────────────────────────────────────
    def _resolve_temp_dir(self, config) -> 'Path':
        """Risolve la directory cache temporanea per i work thumbnail."""
        from utils.paths import get_app_dir
        temp_rel = config.get('paths', {}).get('temp_cache_dir', 'temp_cache')
        p = Path(temp_rel)
        if not p.is_absolute():
            p = get_app_dir() / p
        return p

    def _get_work_thumb_path(self, image_path: 'Path', temp_dir: 'Path') -> 'Path':
        """Genera il percorso del work thumbnail su disco."""
        import hashlib
        stem = image_path.stem[:40]
        suffix_hash = hashlib.md5(str(image_path).encode()).hexdigest()[:8]
        return temp_dir / f"{stem}_{suffix_hash}.jpg"

    def _save_work_thumb(self, thumbnail, work_thumb_path: 'Path') -> bool:
        """Salva work thumbnail su disco come JPEG qualità 85."""
        try:
            thumbnail.save(work_thumb_path, 'JPEG', quality=85)
            return True
        except Exception as e:
            logger.warning(f"Errore salvataggio work thumb: {e}")
            return False

    def _load_work_thumb(self, work_thumb_path: 'Path'):
        """Carica work thumbnail da disco come PIL Image."""
        try:
            from PIL import Image
            return Image.open(work_thumb_path).convert('RGB')
        except Exception as e:
            logger.warning(f"Errore caricamento work thumb {work_thumb_path}: {e}")
            return None

    def _cleanup_temp_cache(self, temp_dir: 'Path'):
        """Cancella tutti i work thumbnail dalla directory temp."""
        try:
            if temp_dir.exists():
                for f in temp_dir.glob('*.jpg'):
                    try:
                        f.unlink()
                    except Exception:
                        pass
                logger.info(f"Cache temporanea svuotata: {temp_dir}")
        except Exception as e:
            logger.warning(f"Errore cleanup cache temp: {e}")

    def stop(self):
        """Ferma processing — tutti i thread controllano is_running e si fermano."""
        self.is_running = False

    def pause(self):
        """Pausa processing — tutti i thread si bloccano in _wait_if_paused()."""
        self.is_paused = True

    def resume(self):
        """Riprendi processing"""
        self.is_paused = False


class PluginStdoutReader(QThread):
    """Legge stdout di un subprocess plugin e traduce PROGRESS:n:total in signal."""

    plugin_progress = pyqtSignal(str, int, int)  # plugin_id, current, total
    plugin_log      = pyqtSignal(str, str)        # message, level
    plugin_finished = pyqtSignal(str)             # plugin_id

    def __init__(self, plugin_id: str, process: subprocess.Popen):
        super().__init__()
        self.plugin_id = plugin_id
        self.process   = process

    def run(self):
        try:
            for raw_line in self.process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("PROGRESS:"):
                    # Formato atteso: PROGRESS:<current>:<total>
                    parts = line.split(":")
                    if len(parts) == 3:
                        try:
                            current = int(parts[1])
                            total   = int(parts[2])
                            self.plugin_progress.emit(self.plugin_id, current, total)
                        except ValueError:
                            pass
                elif line.startswith("DONE:"):
                    # Formato: DONE:<total>:<matched>:<not_matched>
                    parts = line.split(":")
                    if len(parts) == 4:
                        try:
                            total       = int(parts[1])
                            matched     = int(parts[2])
                            not_matched = int(parts[3])
                            self.plugin_log.emit(
                                f"[{self.plugin_id}] ✓ {matched} con nome  ✗ {not_matched} senza  (tot. {total})",
                                "success"
                            )
                        except ValueError:
                            pass
                elif line.startswith("ERROR:"):
                    self.plugin_log.emit(f"[{self.plugin_id}] {line}", "error")
                else:
                    self.plugin_log.emit(f"[{self.plugin_id}] {line}", "info")
            self.process.wait()
        except Exception as e:
            self.plugin_log.emit(f"[{self.plugin_id}] Errore lettura output: {e}", "error")
        finally:
            self.plugin_finished.emit(self.plugin_id)


class ProcessingTab(QWidget):
    # Emesso per bloccare/sbloccare il tab Plugin mentre i plugin girano
    plugins_lock = pyqtSignal(bool)  # True = blocca, False = sblocca

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

        # Plugin standalone scoperti via manifest (autodiscovery)
        self._discovered_plugins: list[dict] = []
        # Riferimenti UI per riga plugin: plugin_id → {check, bar, pb_widget}
        self._plugin_rows: dict[str, dict] = {}
        # Label modalità geo enricher (aggiornata in on_activated)
        self._geo_mode_label: 'QLabel | None' = None
        self._geo_mode_manifest: dict | None = None
        # Reader thread attivi durante esecuzione post-import
        self._active_plugin_readers: list[PluginStdoutReader] = []
        # Contatore plugin ancora in esecuzione (per sapere quando sbloccare il tab)
        self._plugins_running = 0

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

    # ─────────────────────────────────────────────────────────────
    # PLUGIN AUTODISCOVERY
    # ─────────────────────────────────────────────────────────────

    def _discover_standalone_plugins(self) -> list[dict]:
        """Scansiona plugins/**/manifest.json e ritorna i plugin di tipo 'standalone',
        ordinati per priority (default 100 se assente)."""
        plugins_dir = get_app_dir() / 'plugins'
        found = []
        if not plugins_dir.is_dir():
            return found
        for manifest_path in sorted(plugins_dir.rglob('manifest.json')):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                if manifest.get('type') == 'standalone':
                    manifest['_dir'] = str(manifest_path.parent)
                    found.append(manifest)
            except Exception as e:
                logger.warning(f"Errore lettura manifest {manifest_path}: {e}")
        found.sort(key=lambda m: m.get('priority', 100))
        return found

    def _build_plugins_section(self, parent_layout: 'QVBoxLayout'):
        """Costruisce il pannello Plugin nella colonna destra del GroupBox Generazione AI.

        Riceve un QVBoxLayout in cui aggiungere il titolo e le righe plugin.
        Se non ci sono plugin installati, non aggiunge nulla.
        """
        self._discovered_plugins = self._discover_standalone_plugins()
        if not self._discovered_plugins:
            return

        # Stile progress bar plugin: gradiente blu, distinto dal gold dei modelli
        _pb_plugin_style = """
            QProgressBar { border: 1px solid #555; background: #2a2a2a;
                           border-radius: 3px; max-height: 8px; }
            QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #2563a8, stop:1 #4a90d9); border-radius: 2px; }
        """

        # Intestazione colonna Plugin (stile analogo ai separatori nella griglia modelli)
        hdr_w = QWidget()
        hdr_lay = QHBoxLayout(hdr_w)
        hdr_lay.setContentsMargins(0, 0, 0, 2)
        hdr_lay.setSpacing(4)
        hdr_l = QLabel("")
        hdr_l.setFixedHeight(1)
        hdr_l.setStyleSheet("background-color: #2563a8;")
        hdr_lay.addWidget(hdr_l, stretch=1)
        hdr_lbl = QLabel("Plugin")
        hdr_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #4a90d9;")
        hdr_lay.addWidget(hdr_lbl)
        hdr_r = QLabel("")
        hdr_r.setFixedHeight(1)
        hdr_r.setStyleSheet("background-color: #2563a8;")
        hdr_lay.addWidget(hdr_r, stretch=1)
        parent_layout.addWidget(hdr_w)

        # Raggruppa plugin per pipeline_stage; plugin senza stage → post_import
        _stage_order = ['pre_llm', 'post_import']
        _stage_labels = {'pre_llm': 'Pre-LLM', 'post_import': 'Post-import'}
        _stage_colors = {'pre_llm': ('#b87333', '#d4924a'), 'post_import': ('#4a7c59', '#6aad7e')}

        from collections import defaultdict
        _by_stage: dict[str, list] = defaultdict(list)
        for m in self._discovered_plugins:
            stage = m.get('pipeline_stage', 'post_import')
            _by_stage[stage].append(m)

        # Aggiungi stage non standard in coda
        extra_stages = [s for s in _by_stage if s not in _stage_order]
        stages_to_show = [s for s in _stage_order if s in _by_stage] + extra_stages

        # Helper: sotto-separatore stage
        def _make_stage_sep(label: str, color_line: str, color_text: str) -> QWidget:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(8, 4, 0, 2)
            lay.setSpacing(4)
            l = QLabel("")
            l.setFixedHeight(1)
            l.setStyleSheet(f"background-color: {color_line};")
            lay.addWidget(l, stretch=1)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"font-size: 9px; font-weight: bold; color: {color_text};")
            lay.addWidget(lbl)
            r = QLabel("")
            r.setFixedHeight(1)
            r.setStyleSheet(f"background-color: {color_line};")
            lay.addWidget(r, stretch=3)
            return w

        for stage in stages_to_show:
            if len(stages_to_show) > 1 or len(_by_stage[stage]) > 0:
                cl, ct = _stage_colors.get(stage, ('#555', '#aaa'))
                stage_label = _stage_labels.get(stage, stage)
                parent_layout.addWidget(_make_stage_sep(stage_label, cl, ct))

            for manifest in _by_stage[stage]:
                plugin_id   = manifest.get('id', '')
                plugin_name = manifest.get('name', plugin_id)
                plugin_desc = manifest.get('description', '')
                is_geo_enricher = manifest.get('plugin_type') == 'geo_enricher'
                # Descrizione breve: prima frase, max 40 caratteri
                short_desc = (plugin_desc[:40] + '…') if len(plugin_desc) > 40 else plugin_desc

                # Riga plugin: [checkbox] [nome] [desc/modalità] [progress bar]
                row_w = QWidget()
                row_lay = QHBoxLayout(row_w)
                row_lay.setContentsMargins(0, 2, 0, 2)
                row_lay.setSpacing(4)

                # Contenitore larghezza fissa per checkbox o indicatore — garantisce allineamento
                chk_container = QWidget()
                chk_container.setFixedWidth(20)
                chk_lay = QHBoxLayout(chk_container)
                chk_lay.setContentsMargins(0, 0, 0, 0)
                chk_lay.setSpacing(0)

                chk = QCheckBox()
                if is_geo_enricher:
                    # Checkbox sempre attiva e non modificabile — stesso stile degli altri plugin
                    chk.setChecked(True)
                    chk.setEnabled(False)
                    chk.setToolTip("Plugin sempre attivo nella pipeline")
                    chk.setStyleSheet(
                        "QCheckBox::indicator:disabled:checked {"
                        "  background-color: #4a90d9;"
                        "  border: 1px solid #4a90d9;"
                        "  image: url(none);"
                        "}"
                    )
                    chk_lay.addWidget(chk)
                else:
                    chk.setToolTip(f"Esegui {plugin_name} al termine dell'import")
                    chk_lay.addWidget(chk)
                row_lay.addWidget(chk_container)

                lbl = QLabel(plugin_name)
                lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #4a90d9;")
                lbl.setFixedWidth(120)
                row_lay.addWidget(lbl)

                if is_geo_enricher:
                    # Mostra la modalità corrente in ambra (letta dalla config del plugin)
                    _ui_lang = 'it'
                    try:
                        import yaml as _yaml_ui
                        _app_cfg = _yaml_ui.safe_load(
                            (get_app_dir() / 'config_new.yaml').read_text(encoding='utf-8')
                        ) or {}
                        _ui_lang = _app_cfg.get('ui', {}).get('language', 'it')
                    except Exception:
                        pass
                    _geo_cfg_path = manifest.get('_dir', '') and \
                        (get_app_dir() / 'plugins' / plugin_id / 'config.json')
                    _only_no_gps = False
                    try:
                        if _geo_cfg_path and Path(_geo_cfg_path).exists():
                            import json as _json_ui
                            _only_no_gps = _json_ui.loads(
                                Path(_geo_cfg_path).read_text(encoding='utf-8')
                            ).get('only_no_gps', False)
                    except Exception:
                        pass
                    _labels = manifest.get('labels', {}).get(_ui_lang, manifest.get('labels', {}).get('it', {}))
                    if _only_no_gps:
                        _mode_str = _labels.get('processing.mode.only_no_gps', 'Solo no-GPS')
                    else:
                        _mode_str = _labels.get('processing.mode.all_gps', 'Solo GPS')
                    mode_lbl = QLabel(_mode_str)
                    mode_lbl.setStyleSheet("font-size: 9px; color: #C88B2E; font-weight: bold;")
                    row_lay.addWidget(mode_lbl)
                    # Salva riferimento per aggiornamento in on_activated()
                    self._geo_mode_label = mode_lbl
                    self._geo_mode_manifest = manifest
                elif short_desc:
                    desc_lbl = QLabel(short_desc)
                    desc_lbl.setStyleSheet("font-size: 9px; color: #7f8c8d;")
                    row_lay.addWidget(desc_lbl)

                # Progress bar a destra della riga, si espande nello spazio rimasto
                pb = QProgressBar()
                pb.setRange(0, 100)
                pb.setValue(0)
                pb.setTextVisible(False)
                pb.setStyleSheet(_pb_plugin_style)
                pb.setFixedHeight(8)
                pb.setMinimumWidth(60)
                pb.setVisible(False)
                row_lay.addWidget(pb, stretch=1)

                parent_layout.addWidget(row_w)
                self._plugin_rows[plugin_id] = {'check': chk, 'bar': pb}

        parent_layout.addStretch()

    def on_activated(self) -> None:
        """Chiamato da main_window quando si passa alla processing tab.
        Rilegge la config del geo enricher e aggiorna la label modalità."""
        if self._geo_mode_label is None or self._geo_mode_manifest is None:
            return
        manifest = self._geo_mode_manifest
        plugin_id = manifest.get('id', '')
        _ui_lang = 'it'
        try:
            import yaml as _yaml_oa
            _app_cfg = _yaml_oa.safe_load(
                (get_app_dir() / 'config_new.yaml').read_text(encoding='utf-8')
            ) or {}
            _ui_lang = _app_cfg.get('ui', {}).get('language', 'it')
        except Exception:
            pass
        _only_no_gps = False
        try:
            _geo_cfg_path = get_app_dir() / 'plugins' / plugin_id / 'config.json'
            if _geo_cfg_path.exists():
                import json as _json_oa
                _only_no_gps = _json_oa.loads(
                    _geo_cfg_path.read_text(encoding='utf-8')
                ).get('only_no_gps', False)
        except Exception:
            pass
        _labels = manifest.get('labels', {}).get(_ui_lang, manifest.get('labels', {}).get('it', {}))
        if _only_no_gps:
            _mode_str = _labels.get('processing.mode.only_no_gps', 'Geotag: solo foto senza GPS')
        else:
            _mode_str = _labels.get('processing.mode.all_gps', 'Geotag: tutte le foto')
        self._geo_mode_label.setText(_mode_str)

    # ─────────────────────────────────────────────────────────────
    # LANCIO PLUGIN POST-IMPORT
    # ─────────────────────────────────────────────────────────────

    def _launch_post_import_plugins(self):
        """Lancia in sequenza i plugin abilitati dopo il completamento dell'import."""
        # Determina quali plugin sono abilitati
        to_run = [
            m for m in self._discovered_plugins
            if self._plugin_rows.get(m.get('id', ''), {}).get('check', QCheckBox()).isChecked()
        ]
        if not to_run:
            return

        # Ottieni percorso DB dalla config
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
            db_path = cfg.get('paths', {}).get('database', '')
        except Exception:
            db_path = ''

        # Directory corrente selezionata
        current_dir = self.input_dir_label.text() if self.source_dir_radio.isChecked() else ''

        # Assicura che le colonne richieste dai plugin esistano nel DB
        if db_path:
            try:
                from db_manager_new import DatabaseManager
                _tmp_db = DatabaseManager(db_path)
                for _m in to_run:
                    _tmp_db.ensure_plugin_columns(_m)
                _tmp_db.close()
            except Exception as _e:
                logger.warning(f"ensure_plugin_columns: {_e}")

        # Blocca tab Plugin finché almeno un plugin gira
        self._plugins_running = len(to_run)
        self.plugins_lock.emit(True)

        # Lancia sequenzialmente: ogni plugin parte quando il precedente finisce
        # — implementato concatenando il signal plugin_finished
        self._plugin_queue = list(to_run)
        self._plugin_db_path = db_path
        self._plugin_dir = current_dir
        self._launch_next_plugin()

    def _launch_next_plugin(self):
        """Lancia il prossimo plugin nella coda, se presente."""
        if not self._plugin_queue:
            return

        manifest   = self._plugin_queue.pop(0)
        plugin_id  = manifest.get('id', '')
        plugin_dir = manifest.get('_dir', '')
        entry_point = manifest.get('entry_point', '')

        # Plugin config_only o geo_enricher: operano nella pipeline interna,
        # non come subprocess autonomo. Saltiamo silenziosamente.
        if manifest.get('config_only', False) or manifest.get('plugin_type') == 'geo_enricher':
            self._on_plugin_finished(plugin_id)
            return

        entry_path = Path(plugin_dir) / entry_point
        if not entry_path.exists():
            self.add_log_message(
                f"⚠️ Plugin {plugin_id}: entry point non trovato ({entry_path})", "warning"
            )
            self._on_plugin_finished(plugin_id)
            return

        # Mostra progress bar
        row = self._plugin_rows.get(plugin_id, {})
        if row.get('bar'):
            row['bar'].setValue(0)
            row['bar'].setVisible(True)

        self.add_log_message(f"▶ Avvio plugin: {manifest.get('name', plugin_id)}", "info")

        # Costruisce comando — modalità headless (niente finestra Qt)
        cmd = [sys.executable, str(entry_path)]
        if self._plugin_db_path:
            cmd += ['--db', self._plugin_db_path]
        if self._plugin_dir:
            cmd += ['--directory', self._plugin_dir]
            cmd += ['--mode', 'directory']
        else:
            cmd += ['--mode', 'unprocessed']
        config_json = Path(plugin_dir) / 'config.json'
        if config_json.exists():
            cmd += ['--config', str(config_json)]
        # Applica run_condition: bioclip_not_null → passa flag al subprocess
        if manifest.get('run_condition') == 'bioclip_not_null':
            cmd += ['--filter-bioclip']
        cmd += ['--headless']

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
        except Exception as e:
            self.add_log_message(f"⚠️ Plugin {plugin_id}: errore avvio — {e}", "error")
            self._on_plugin_finished(plugin_id)
            return

        # Avvia reader thread
        reader = PluginStdoutReader(plugin_id, proc)
        reader.plugin_progress.connect(self._on_plugin_progress)
        reader.plugin_log.connect(self.add_log_message)
        reader.plugin_finished.connect(self._on_plugin_finished)
        self._active_plugin_readers.append(reader)
        reader.start()

    def _on_plugin_progress(self, plugin_id: str, current: int, total: int):
        """Aggiorna la progress bar del plugin in base a PROGRESS:n:total."""
        row = self._plugin_rows.get(plugin_id, {})
        pb = row.get('bar')
        if pb and total > 0:
            pb.setValue(int(current * 100 / total))

    def _on_plugin_finished(self, plugin_id: str):
        """Chiamato quando un plugin subprocess termina."""
        row = self._plugin_rows.get(plugin_id, {})
        pb = row.get('bar')
        if pb:
            pb.setValue(100)

        self.add_log_message(f"✅ Plugin completato: {plugin_id}", "success")

        self._plugins_running -= 1

        # Se ci sono altri plugin in coda, lancia il prossimo
        if self._plugin_queue:
            self._launch_next_plugin()
        elif self._plugins_running <= 0:
            # Tutti i plugin terminati: riabilita tab Plugin e pulsante Start
            self.plugins_lock.emit(False)
            self.start_btn.setEnabled(True)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 2)
        layout.setSpacing(2)

        path_label_style = """
            QLabel {
                color: #2c3e50; padding: 4px 8px;
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 3px; font-size: 11px;
            }
        """

        # ===== SORGENTE IMMAGINI (unica sezione per dir + catalogo) =====
        source_group = QGroupBox(t("processing.group.source_icon"))
        source_grid = QGridLayout()
        source_grid.setVerticalSpacing(2)
        source_grid.setHorizontalSpacing(6)

        self.source_btn_group = QButtonGroup()

        # --- Riga 0: Directory ---
        self.source_dir_radio = QRadioButton(t("processing.radio.source_dir_colon"))
        self.source_dir_radio.setChecked(True)
        self.source_dir_radio.setToolTip(t("processing.tooltip.source_dir"))
        self.source_btn_group.addButton(self.source_dir_radio, 0)
        source_grid.addWidget(self.source_dir_radio, 0, 0)

        self.input_dir_label = QLabel(t("processing.label.no_dir"))
        self.input_dir_label.setStyleSheet(path_label_style)
        source_grid.addWidget(self.input_dir_label, 0, 1)

        self.browse_btn = QPushButton(t("processing.btn.select"))
        self.browse_btn.clicked.connect(self.select_input_directory)
        self.browse_btn.setFixedWidth(90)
        source_grid.addWidget(self.browse_btn, 0, 2)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.clicked.connect(self.refresh_scan)
        self.refresh_btn.setFixedWidth(32)
        self.refresh_btn.setToolTip(t("processing.tooltip.refresh"))
        source_grid.addWidget(self.refresh_btn, 0, 3)

        self.include_subdirs_cb = QCheckBox(t("processing.check.subdirs"))
        self.include_subdirs_cb.setToolTip(t("processing.tooltip.subdirs"))
        self.include_subdirs_cb.stateChanged.connect(self._on_subdirs_changed)
        source_grid.addWidget(self.include_subdirs_cb, 0, 4)

        # --- Riga 1: Catalogo Lightroom ---
        self.source_catalog_radio = QRadioButton(t("processing.radio.source_catalog_colon"))
        self.source_catalog_radio.setToolTip(t("processing.tooltip.source_catalog"))
        self.source_btn_group.addButton(self.source_catalog_radio, 1)
        source_grid.addWidget(self.source_catalog_radio, 1, 0)

        self.catalog_path_label = QLabel(t("processing.label.no_catalog_selected"))
        self.catalog_path_label.setStyleSheet(path_label_style)
        source_grid.addWidget(self.catalog_path_label, 1, 1)

        self.catalog_browse_btn = QPushButton(t("processing.btn.select"))
        self.catalog_browse_btn.setFixedWidth(90)
        self.catalog_browse_btn.clicked.connect(self.select_catalog)
        self.catalog_browse_btn.setEnabled(False)
        source_grid.addWidget(self.catalog_browse_btn, 1, 2)

        # Info catalogo (span colonne 1-4)
        self.catalog_info_label = QLabel("")
        self.catalog_info_label.setStyleSheet("color: #27ae60; font-size: 10px; font-style: italic;")
        self.catalog_info_label.setVisible(False)
        source_grid.addWidget(self.catalog_info_label, 2, 1, 1, 4)

        # Riga status integrata nel gruppo sorgente (risparmia un QGroupBox)
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        self.scan_label = QLabel(t("processing.label.select_source"))
        self.scan_label.setStyleSheet("font-size: 10px; color: #7f8c8d;")
        status_row.addWidget(self.scan_label)
        status_row.addStretch()
        source_grid.addLayout(status_row, 3, 0, 1, 5)

        source_grid.setColumnStretch(1, 1)  # Path label si espande
        source_group.setLayout(source_grid)
        layout.addWidget(source_group)

        self.source_btn_group.idClicked.connect(self._on_source_changed)

        # ===== MODALITÀ + GENERAZIONE AI (fianco a fianco) =====
        mid_layout = QHBoxLayout()
        mid_layout.setSpacing(4)

        # --- Modalità Processing ---
        options_group = QGroupBox(t("processing.group.mode"))
        options_layout = QVBoxLayout()
        options_layout.setContentsMargins(6, 4, 6, 4)
        options_layout.setSpacing(2)

        self.processing_mode_group = QButtonGroup()

        self.mode_new_only = QRadioButton(t("processing.radio.new_only"))
        self.mode_new_only.setChecked(True)
        self.mode_new_only.setToolTip(t("processing.tooltip.mode_new_only"))
        self.processing_mode_group.addButton(self.mode_new_only, 0)
        options_layout.addWidget(self.mode_new_only)

        self.mode_new_plus_errors = QRadioButton(t("processing.radio.new_errors"))
        self.mode_new_plus_errors.setToolTip(t("processing.tooltip.mode_new_errors"))
        self.processing_mode_group.addButton(self.mode_new_plus_errors, 1)
        options_layout.addWidget(self.mode_new_plus_errors)

        self.mode_reprocess_all = QRadioButton(t("processing.radio.reprocess_all"))
        self.mode_reprocess_all.setToolTip(t("processing.tooltip.mode_reprocess_all"))
        self.mode_reprocess_all.setStyleSheet("color: #f57500; font-weight: bold;")
        self.processing_mode_group.addButton(self.mode_reprocess_all, 2)

        options_layout.addWidget(self.mode_reprocess_all)

        self.processing_mode_group.idClicked.connect(self.update_start_button_state)

        self.enable_file_log_cb = QCheckBox(t("processing.check.file_log"))
        self.enable_file_log_cb.setToolTip(t("processing.tooltip.file_log"))
        self.enable_file_log_cb.setChecked(False)
        options_layout.addWidget(self.enable_file_log_cb)
        options_layout.addStretch()

        options_group.setLayout(options_layout)
        mid_layout.addWidget(options_group, stretch=1)

        # --- Modelli AI (griglia unica: embedding + LLM con progress bar per modello) ---
        models_group = QGroupBox(t("processing.group.gen_ai"))
        models_grid = QGridLayout()
        models_grid.setHorizontalSpacing(4)
        models_grid.setVerticalSpacing(1)
        models_grid.setContentsMargins(6, 3, 6, 3)

        # Stile progress bar compatta per singolo modello
        _pb_style = """
            QProgressBar { border: 1px solid #555; background: #2a2a2a;
                           border-radius: 3px; max-height: 8px; }
            QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #C88B2E, stop:1 #E0A84A); border-radius: 2px; }
        """

        # Colonne: 0=Nome  1=Genera  2=Sovrascrivi  3=Max  4=ProgressBar
        #
        # Riga 0: header
        _COL_NAME, _COL_GEN, _COL_OVR, _COL_MAX, _COL_BAR = range(5)
        _hdr_style = "font-weight: bold; font-size: 10px;"

        # Header: solo Genera / Sovrascrivi / Max (le altre colonne senza header)
        for ci, col_text in [(_COL_GEN, t("processing.label.col_generate")),
                             (_COL_OVR, t("processing.label.col_overwrite")),
                             (_COL_MAX, t("processing.label.col_max"))]:
            _h = QLabel(col_text)
            _h.setStyleSheet(_hdr_style)
            _h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            models_grid.addWidget(_h, 0, ci)

        _cur_row = 1  # riga corrente nella griglia

        # === Separatore Preparazione + riga ExifTool ===
        _sep_prep = QWidget()
        _sep_prep_lay = QHBoxLayout(_sep_prep)
        _sep_prep_lay.setContentsMargins(0, 2, 0, 1)
        _sep_prep_lay.setSpacing(4)
        _sep_prep_l = QLabel("")
        _sep_prep_l.setFixedHeight(1)
        _sep_prep_l.setStyleSheet("background-color: #bdc3c7;")
        _sep_prep_lay.addWidget(_sep_prep_l, stretch=1)
        _sep_prep_lbl = QLabel(t("processing.label.preparation"))
        _sep_prep_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #7f8c8d;")
        _sep_prep_lay.addWidget(_sep_prep_lbl)
        _sep_prep_r = QLabel("")
        _sep_prep_r.setFixedHeight(1)
        _sep_prep_r.setStyleSheet("background-color: #bdc3c7;")
        _sep_prep_lay.addWidget(_sep_prep_r, stretch=1)
        models_grid.addWidget(_sep_prep, _cur_row, 0, 1, 5); _cur_row += 1

        # Riga ExifTool (estrazione metadati + thumbnail)
        _exif_name_w = QWidget()
        _exif_name_lay = QHBoxLayout(_exif_name_w)
        _exif_name_lay.setContentsMargins(0, 0, 0, 0)
        _exif_name_lay.setSpacing(4)
        _exif_lbl = QLabel("ExifTool")
        _exif_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
        _exif_name_lay.addWidget(_exif_lbl)
        _exif_desc = QLabel(t("processing.check.exiftool"))
        _exif_desc.setStyleSheet("font-size: 9px; color: #7f8c8d;")
        _exif_name_lay.addWidget(_exif_desc)
        _exif_name_lay.addStretch()
        models_grid.addWidget(_exif_name_w, _cur_row, _COL_NAME)
        self.pt_exif_bar = QProgressBar()
        self.pt_exif_bar.setRange(0, 100)
        self.pt_exif_bar.setValue(0)
        self.pt_exif_bar.setTextVisible(False)
        self.pt_exif_bar.setStyleSheet(_pb_style)
        self.pt_exif_bar.setFixedHeight(8)
        models_grid.addWidget(self.pt_exif_bar, _cur_row, _COL_BAR)
        _cur_row += 1

        # === Separatore Modelli Embedding ===
        _sep_emb = QWidget()
        _sep_emb_lay = QHBoxLayout(_sep_emb)
        _sep_emb_lay.setContentsMargins(0, 2, 0, 1)
        _sep_emb_lay.setSpacing(4)
        _sep_emb_l = QLabel("")
        _sep_emb_l.setFixedHeight(1)
        _sep_emb_l.setStyleSheet("background-color: #bdc3c7;")
        _sep_emb_lay.addWidget(_sep_emb_l, stretch=1)
        _sep_emb_lbl = QLabel(t("processing.label.embedding_models"))
        _sep_emb_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #7f8c8d;")
        _sep_emb_lay.addWidget(_sep_emb_lbl)
        _sep_emb_r = QLabel("")
        _sep_emb_r.setFixedHeight(1)
        _sep_emb_r.setStyleSheet("background-color: #bdc3c7;")
        _sep_emb_lay.addWidget(_sep_emb_r, stretch=1)
        models_grid.addWidget(_sep_emb, _cur_row, 0, 1, 5); _cur_row += 1

        # === Helper: aggiunge riga modello embedding ===
        def _add_emb_row(row, label, description):
            # Nome + descrizione nella stessa cella
            name_w = QWidget()
            name_lay = QHBoxLayout(name_w)
            name_lay.setContentsMargins(0, 0, 0, 0)
            name_lay.setSpacing(4)
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
            name_lay.addWidget(lbl)
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet("font-size: 9px; color: #7f8c8d;")
            name_lay.addWidget(desc_lbl)
            name_lay.addStretch()
            models_grid.addWidget(name_w, row, _COL_NAME)
            chk = QCheckBox()
            chk.setToolTip(t("processing.tooltip.model_enable", model=label))
            models_grid.addWidget(chk, row, _COL_GEN, alignment=Qt.AlignmentFlag.AlignCenter)
            sovr = QCheckBox()
            sovr.setToolTip(t("processing.tooltip.model_overwrite", model=label))
            sovr.setEnabled(False)
            models_grid.addWidget(sovr, row, _COL_OVR, alignment=Qt.AlignmentFlag.AlignCenter)
            # Col Max vuota per embedding
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setValue(0)
            pb.setTextVisible(False)
            pb.setStyleSheet(_pb_style)
            pb.setFixedHeight(8)
            models_grid.addWidget(pb, row, _COL_BAR)
            chk.stateChanged.connect(lambda state, s=sovr: s.setEnabled(state == 2))
            return chk, sovr, pb

        self.pt_clip_check, self.pt_clip_overwrite, self.pt_clip_bar = \
            _add_emb_row(_cur_row, 'CLIP', t("processing.check.clip")); _cur_row += 1

        self.pt_dinov2_check, self.pt_dinov2_overwrite, self.pt_dinov2_bar = \
            _add_emb_row(_cur_row, 'DINOv2', t("processing.check.dinov2")); _cur_row += 1

        self.pt_bioclip_check, self.pt_bioclip_overwrite, self.pt_bioclip_bar = \
            _add_emb_row(_cur_row, 'BioCLIP', t("processing.check.bioclip")); _cur_row += 1

        self.pt_aesthetic_check, self.pt_aesthetic_overwrite, self.pt_aesthetic_bar = \
            _add_emb_row(_cur_row, 'Aesthetic', t("processing.check.aesthetic")); _cur_row += 1

        self.pt_musiq_check, self.pt_musiq_overwrite, self.pt_musiq_bar = \
            _add_emb_row(_cur_row, 'Technical', t("processing.check.technical")); _cur_row += 1

        # Separatore embedding / LLM con label
        _sep_w = QWidget()
        _sep_lay = QHBoxLayout(_sep_w)
        _sep_lay.setContentsMargins(0, 2, 0, 1)
        _sep_lay.setSpacing(4)
        _sep_line_l = QLabel("")
        _sep_line_l.setFixedHeight(1)
        _sep_line_l.setStyleSheet("background-color: #bdc3c7;")
        _sep_lay.addWidget(_sep_line_l, stretch=1)
        _sep_lbl = QLabel("LLM Vision")
        _sep_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #7f8c8d;")
        _sep_lay.addWidget(_sep_lbl)
        _sep_line_r = QLabel("")
        _sep_line_r.setFixedHeight(1)
        _sep_line_r.setStyleSheet("background-color: #bdc3c7;")
        _sep_lay.addWidget(_sep_line_r, stretch=1)
        models_grid.addWidget(_sep_w, _cur_row, 0, 1, 5); _cur_row += 1

        # === Helper: aggiunge riga LLM (senza progress bar individuale) ===
        def _add_llm_row(row, label, tooltip_chk, tooltip_sovr, spin_min, spin_max, spin_val):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px;")
            models_grid.addWidget(lbl, row, _COL_NAME)
            chk = QCheckBox()
            chk.setToolTip(tooltip_chk)
            models_grid.addWidget(chk, row, _COL_GEN, alignment=Qt.AlignmentFlag.AlignCenter)
            sovr = QCheckBox()
            sovr.setToolTip(tooltip_sovr)
            sovr.setEnabled(False)
            models_grid.addWidget(sovr, row, _COL_OVR, alignment=Qt.AlignmentFlag.AlignCenter)
            spin = QSpinBox()
            spin.setRange(spin_min, spin_max)
            spin.setValue(spin_val)
            spin.setEnabled(False)
            spin.setFixedWidth(50)
            models_grid.addWidget(spin, row, _COL_MAX)
            chk.stateChanged.connect(lambda state, s=sovr, sp=spin: (
                s.setEnabled(state == 2), sp.setEnabled(state == 2)))
            return chk, sovr, spin

        self.pt_gen_tags_check, self.pt_gen_tags_overwrite, self.pt_llm_max_tags = \
            _add_llm_row(_cur_row, t("processing.label.row_tags_colon"),
                         t("processing.tooltip.gen_tags"), t("processing.tooltip.overwrite_tags"),
                         1, 20, 10); _cur_row += 1

        self.pt_gen_desc_check, self.pt_gen_desc_overwrite, self.pt_llm_max_words = \
            _add_llm_row(_cur_row, t("processing.label.row_desc_colon"),
                         t("processing.tooltip.gen_desc"), t("processing.tooltip.overwrite_desc"),
                         20, 300, 100); _cur_row += 1

        self.pt_gen_title_check, self.pt_gen_title_overwrite, self.pt_llm_max_title = \
            _add_llm_row(_cur_row, t("processing.label.row_title_colon"),
                         t("processing.tooltip.gen_title"), t("processing.tooltip.overwrite_title"),
                         1, 10, 5)

        # Auto-salvataggio impostazioni LLM: ogni modifica è persista nel YAML
        for _chk in (self.pt_gen_tags_check, self.pt_gen_tags_overwrite,
                     self.pt_gen_desc_check, self.pt_gen_desc_overwrite,
                     self.pt_gen_title_check, self.pt_gen_title_overwrite):
            _chk.toggled.connect(self._autosave_llm_config)
        for _spin in (self.pt_llm_max_tags, self.pt_llm_max_words, self.pt_llm_max_title):
            _spin.editingFinished.connect(self._autosave_llm_config)

        # Progress bar unica LLM (span su tutte e 3 le righe LLM, colonna BAR+LED)
        self.pt_llm_bar = QProgressBar()
        self.pt_llm_bar.setRange(0, 100)
        self.pt_llm_bar.setValue(0)
        self.pt_llm_bar.setTextVisible(False)
        self.pt_llm_bar.setStyleSheet(_pb_style)
        self.pt_llm_bar.setFixedHeight(8)
        _llm_first_row = _cur_row - 2  # prima riga LLM (Tags)
        models_grid.addWidget(self.pt_llm_bar, _llm_first_row, _COL_BAR, 3, 1)
        _cur_row += 1

        # (riga info rimossa — lo spazio è recuperato per ExifTool)

        # Larghezze colonne
        models_grid.setColumnMinimumWidth(_COL_NAME, 75)
        models_grid.setColumnMinimumWidth(_COL_GEN, 22)
        models_grid.setColumnMinimumWidth(_COL_OVR, 22)
        models_grid.setColumnMinimumWidth(_COL_MAX, 40)
        models_grid.setColumnStretch(_COL_BAR, 1)  # progress bar si espande

        # Layout interno del GroupBox: griglia modelli a sinistra, plugin a destra
        _inner_layout = QHBoxLayout()
        _inner_layout.setSpacing(8)
        _inner_layout.setContentsMargins(0, 0, 0, 0)

        _models_widget = QWidget()
        _models_widget.setLayout(models_grid)
        _inner_layout.addWidget(_models_widget, stretch=3)

        # Separatore verticale tra modelli e plugin
        _vsep = QWidget()
        _vsep.setFixedWidth(1)
        _vsep.setStyleSheet("background-color: #444;")
        _inner_layout.addWidget(_vsep)

        # Colonna Plugin (costruita da _build_plugins_section)
        _plugins_col = QVBoxLayout()
        _plugins_col.setSpacing(2)
        _plugins_col.setContentsMargins(4, 3, 4, 3)
        self._build_plugins_section(_plugins_col)

        _plugins_widget = QWidget()
        _plugins_widget.setLayout(_plugins_col)
        _inner_layout.addWidget(_plugins_widget, stretch=2)

        models_group.setLayout(_inner_layout)
        mid_layout.addWidget(models_group, stretch=2)

        layout.addLayout(mid_layout)

        # ===== CONTROLLI =====
        controls_group = QGroupBox(t("processing.group.controls"))
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(6, 2, 6, 2)

        self.start_btn = QPushButton(t("processing.btn.start"))
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setStyleSheet("font-weight: bold; background-color: #2e7d32; min-width: 90px;")
        controls_layout.addWidget(self.start_btn)

        self.pause_btn = QPushButton(t("processing.btn.pause"))
        self.pause_btn.clicked.connect(self.pause_processing)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setStyleSheet("min-width: 90px;")
        controls_layout.addWidget(self.pause_btn)

        self.stop_btn = QPushButton(t("processing.btn.stop"))
        self.stop_btn.clicked.connect(self.stop_processing)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("min-width: 90px;")
        controls_layout.addWidget(self.stop_btn)

        controls_layout.addStretch()
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # ===== TERMINAL LOG (si espande per riempire lo spazio disponibile) =====
        terminal_group = QGroupBox(t("processing.group.terminal_log"))
        self._terminal_group = terminal_group
        terminal_layout = QVBoxLayout()
        terminal_layout.setContentsMargins(5, 5, 5, 5)

        self.log_display = QTextEdit()
        self.log_display.setMinimumHeight(120)
        self.log_display.setFont(QFont("Courier New", 10))
        self.log_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.log_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #000000; color: #00ff00;
                border: 2px solid #333333; border-radius: 6px; padding: 6px;
                font-family: 'Courier New', 'Monaco', monospace; font-size: 10px;
            }
            QScrollBar:vertical { background-color: #1a1a1a; width: 14px;
                border: 1px solid #333333; border-radius: 7px; }
            QScrollBar::handle:vertical { background-color: #00ff00; border-radius: 6px;
                min-height: 20px; margin: 2px; }
            QScrollBar::handle:vertical:hover { background-color: #00cc00; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        self.log_display.setReadOnly(True)
        self.log_display.textChanged.connect(self._auto_scroll_terminal)

        terminal_layout.addWidget(self.log_display)
        terminal_group.setLayout(terminal_layout)
        layout.addWidget(terminal_group, stretch=1)  # stretch=1: prende tutto lo spazio rimanente

        # Carica directory salvata e impostazioni LLM
        self.load_saved_input_directory()

        # Messaggio di benvenuto nel terminale
        self._init_terminal_welcome()
    
    def _auto_scroll_terminal(self):
        """Auto-scroll del terminale alle ultime righe"""
        try:
            scrollbar = self.log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            logger.debug(f"Errore auto-scroll: {e}")
    
    def _init_terminal_welcome(self):
        """Inizializza il terminale con messaggio di benvenuto e scarica il log di avvio."""
        try:
            self.log_display.clear()
            welcome_msg = """<span style="color: #00ff00; font-weight: bold;">
==================================================
    OFFGALLERY PROCESSING TERMINAL v1.0
==================================================</span>
<span style="color: #00cc00;">System initialized and ready for image processing...</span>
"""
            self.log_display.append(welcome_msg)

            # Scarica i messaggi accumulati durante il caricamento modelli (prima che la tab esistesse)
            if self.embedding_gen and self.embedding_gen.startup_log:
                self.add_log_message("── Log avvio modelli AI ──────────────────────────", "info")
                for msg, level in self.embedding_gen.startup_log:
                    self.add_log_message(msg, level)
                self.add_log_message("─────────────────────────────────────────────────", "info")
                self.embedding_gen.startup_log.clear()

        except Exception as e:
            logger.debug(f"Errore init terminale: {e}")
    
    def select_input_directory(self):
        """Apre dialog per selezione directory input"""
        from PyQt6.QtWidgets import QFileDialog
        
        previous_folder = self.input_dir_label.text()
        directory = QFileDialog.getExistingDirectory(
            self,
            t("processing.group.source_icon"),
            previous_folder if Path(previous_folder).exists() else str(Path.home())
        )
        
        if directory:
            self.set_input_directory(directory)
    
    def set_input_directory(self, directory_path):
        """Imposta directory input e salva in config"""
        try:
            directory = Path(directory_path)
            if not directory.exists():
                QMessageBox.warning(self, t("processing.msg.error_title"), t("processing.msg.dir_not_exist", path=directory))
                return
            
            # Aggiorna UI
            self.input_dir_label.setText(str(directory))
            self.input_dir_label.setStyleSheet("""
                QLabel {
                    color: #2c3e50; padding: 4px 8px;
                    background-color: #ecf0f1;
                    border: 1px solid #bdc3c7;
                    border-radius: 3px; font-size: 11px;
                }
            """)
            # Directory selezionata, abilita processing
            
            # Salva in config
            self.save_input_directory_to_config(str(directory))
            
            # Auto-scansiona
            self.scan_directory()
            
        except Exception as e:
            QMessageBox.critical(self, t("processing.msg.error_title"), t("processing.msg.dir_set_error", error=e))
    
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

    def _autosave_llm_config(self):
        """Salva le impostazioni LLM nel YAML ogni volta che l'utente cambia
        un valore — così le preferenze sono persistite anche senza cliccare Avvia."""
        try:
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
            self._save_llm_config_to_yaml(llm_gen_config)
        except Exception:
            pass

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
            logger.warning(f"Errore salvataggio directory in config: {e}")
    
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
                # Path Windows (es. D:\...) ignorato su Linux/macOS
                import re as _re
                import platform as _platform
                is_windows_path = bool(_re.match(r'^[A-Za-z]:[/\\]', str(input_dir)))
                if is_windows_path and _platform.system() != 'Windows':
                    input_dir = ''
                if input_dir and Path(input_dir).exists():
                    self.set_input_directory(input_dir)
                elif input_dir:
                    self.input_dir_label.setText(t("processing.label.dir_not_available"))
                    self.input_dir_label.setStyleSheet("color: #cc3333;")

            # Carica stato Active modelli embedding da config
            models_cfg = config.get('embedding', {}).get('models', {})
            emb_mapping = [
                (self.pt_clip_check, 'clip'),
                (self.pt_dinov2_check, 'dinov2'),
                (self.pt_bioclip_check, 'bioclip'),
                (self.pt_aesthetic_check, 'aesthetic'),
                (self.pt_musiq_check, 'technical'),
            ]
            for chk, key in emb_mapping:
                model_enabled = models_cfg.get(key, {}).get('enabled', False)
                if not model_enabled:
                    # Modello impostato su OFF in Config Tab: non selezionabile
                    chk.setChecked(False)
                    chk.setEnabled(False)
                    chk.setToolTip(t("processing.tooltip.model_disabled_config"))
                else:
                    chk.setChecked(True)
                    chk.setEnabled(True)
                    chk.setToolTip(t("processing.tooltip.model_enable", model=key.upper()))

            # Carica impostazioni generazione AI (tags/desc/title)
            auto_import = (config.get('embedding', {})
                           .get('models', {})
                           .get('llm_vision', {})
                           .get('auto_import', {}))

            tags_cfg = auto_import.get('tags', {})
            self.pt_gen_tags_check.setChecked(tags_cfg.get('enabled', False))
            self.pt_gen_tags_overwrite.setChecked(tags_cfg.get('overwrite', False))
            self.pt_llm_max_tags.setValue(tags_cfg.get('max_tags', 10))

            desc_cfg = auto_import.get('description', {})
            self.pt_gen_desc_check.setChecked(desc_cfg.get('enabled', False))
            self.pt_gen_desc_overwrite.setChecked(desc_cfg.get('overwrite', False))
            self.pt_llm_max_words.setValue(desc_cfg.get('max_words', 100))

            title_cfg = auto_import.get('title', {})
            self.pt_gen_title_check.setChecked(title_cfg.get('enabled', False))
            self.pt_gen_title_overwrite.setChecked(title_cfg.get('overwrite', False))
            self.pt_llm_max_title.setValue(title_cfg.get('max_words', 5))

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Errore caricamento config in processing tab: {e}")

    def _on_subdirs_changed(self, state):
        """Ri-scansiona quando cambia il checkbox sotto-cartelle"""
        input_dir_text = self.input_dir_label.text()
        if input_dir_text not in [t("processing.label.no_dir"), t("processing.label.dir_not_available")]:
            self.scan_directory()

    def _on_source_changed(self, source_id):
        """Abilita/disabilita controlli in base alla sorgente selezionata"""
        is_catalog = (source_id == 1)
        # Controlli directory
        self.browse_btn.setEnabled(not is_catalog)
        self.refresh_btn.setEnabled(not is_catalog)
        self.include_subdirs_cb.setEnabled(not is_catalog)
        # Controlli catalogo
        self.catalog_browse_btn.setEnabled(is_catalog)
        # Aggiorna stato pulsante avvia
        self.update_start_button_state()

    def _save_models_config_to_yaml(self):
        """Salva stato Active dei modelli embedding nel YAML per la prossima sessione."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            models = config.setdefault('embedding', {}).setdefault('models', {})

            # Non scriviamo 'enabled' qui: il caricamento dei modelli è controllato
            # esclusivamente dalla Config Tab (combo GPU/CPU/OFF). Il processing tab
            # gestisce solo la scelta di QUALI modelli usare in questa esecuzione.

            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Errore salvataggio config modelli: {e}")


    def select_catalog(self):
        """Apre dialog per selezione catalogo Lightroom"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("processing.dialog.select_catalog"),
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
            QMessageBox.warning(self, t("processing.msg.catalog_error_title"), str(e))

    def refresh_scan(self):
        """Aggiorna scansione directory e stato database"""
        try:
            input_dir_text = self.input_dir_label.text()
            if input_dir_text in [t("processing.label.no_dir"), t("processing.label.dir_not_available")]:
                QMessageBox.warning(self, t("processing.msg.warning_title"), t("processing.msg.select_dir_first"))
                return

            # Feedback visivo
            self.scan_label.setText(t("processing.msg.refresh_updating"))
            QApplication.processEvents()

            # Esegui scansione
            self.scan_directory()

            logger.debug("Refresh completato")

        except Exception as e:
            logger.error(f"Errore refresh: {e}")
            self.scan_label.setText(f"❌ Errore refresh: {e}")

    def scan_directory(self):
        """Scansiona directory per contare immagini NON processate"""
        try:
            # Ottieni directory input dall'UI
            input_dir_text = self.input_dir_label.text()
            if input_dir_text in [t("processing.label.no_dir"), t("processing.label.dir_not_available")]:
                self.scan_label.setText(t("processing.msg.select_dir_stats"))
                return

            input_dir = Path(input_dir_text)
            if not input_dir.exists():
                self.scan_label.setText(t("processing.msg.dir_not_exist_scan", path=input_dir))
                return

            # Carica config per formati supportati e database
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            db_path = Path(config['paths']['database'])
            supported_formats = config.get('image_processing', {}).get('supported_formats', [])

            if not supported_formats:
                self.scan_label.setText(t("processing.msg.no_formats"))
                return

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
                        # Salta file nascosti (es. ._filename.jpg su macOS/Linux)
                        if file_path.name.startswith('.'):
                            continue
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

                    # Copertura per-modello — query aggregata veloce anche su 100k foto
                    coverage = db_manager.get_model_coverage()

                except Exception as e:
                    self.scan_label.setText(t("processing.msg.db_error", error=e))
                    return
            else:
                coverage = {}

            total_found = len(all_images)
            to_process = len(images_to_process)

            # Riga copertura modelli in ambra (solo se ci sono file già indicizzati)
            coverage_html = ""
            if coverage and already_processed > 0:
                parts = []
                if coverage.get('clip'):        parts.append(f"CLIP: {coverage['clip']}")
                if coverage.get('dinov2'):      parts.append(f"DINOv2: {coverage['dinov2']}")
                if coverage.get('aesthetic'):   parts.append(f"Aesthetic: {coverage['aesthetic']}")
                if coverage.get('technical'):   parts.append(f"MUSIQ: {coverage['technical']}")
                if coverage.get('bioclip'):     parts.append(f"BioCLIP: {coverage['bioclip']}")
                if coverage.get('tags'):        parts.append(f"Tags: {coverage['tags']}")
                if coverage.get('description'): parts.append(f"Desc: {coverage['description']}")
                if coverage.get('title'):       parts.append(f"Titoli: {coverage['title']}")
                if parts:
                    coverage_html = (
                        '<br><span style="color: #C88B2E;">'
                        + ' &nbsp;|&nbsp; '.join(parts)
                        + '</span>'
                    )

            # Salva il numero di immagini da processare per la logica del pulsante
            self.images_to_process_count = to_process

            if to_process == 0:
                self.scan_label.setText(t("processing.msg.all_processed", total=total_found) + coverage_html)
                # Aggiorna stato pulsante in base alle modalità
                self.update_start_button_state()
            else:
                self.scan_label.setText(
                    t("processing.msg.scan_result", total=total_found, to_process=to_process, already=already_processed)
                    + coverage_html
                )
                # Abilita pulsante se ci sono immagini da processare
                self.start_btn.setEnabled(True)
            
        except Exception as e:
            self.scan_label.setText(t("processing.msg.scan_error", error=e))
    
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
                    self.start_btn.setToolTip(t("processing.tooltip.start_no_new"))
                else:
                    self.start_btn.setEnabled(True)
                    self.start_btn.setToolTip(t("processing.tooltip.start_new"))
            else:  # Altre modalità
                self.start_btn.setEnabled(True)
                if mode_id == 1:  # new_plus_errors
                    self.start_btn.setToolTip(t("processing.tooltip.start_errors"))
                else:  # reprocess_all
                    self.start_btn.setToolTip(t("processing.tooltip.start_reprocess"))
                    
        except Exception as e:
            logger.debug(f"Errore update_start_button_state: {e}")
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
                QMessageBox.warning(self, t("processing.msg.error_title"), t("processing.msg.select_catalog_first"))
                return
        else:
            # Verifica directory selezionata
            input_dir_text = self.input_dir_label.text()
            if input_dir_text in [t("processing.label.no_dir"), t("processing.label.dir_not_available")]:
                QMessageBox.warning(self, t("processing.msg.error_title"), t("processing.msg.select_input_dir_first"))
                return
            if not Path(input_dir_text).exists():
                QMessageBox.warning(self, t("processing.msg.error_title"), t("processing.msg.dir_not_exist", path=input_dir_text))
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

            # Salva valori nel YAML per la prossima sessione
            self._save_llm_config_to_yaml(llm_gen_config)
            self._save_models_config_to_yaml()

            # Configurazione per-modello embedding: Active + Overwrite
            embedding_model_flags = {
                'clip': {'active': self.pt_clip_check.isChecked(), 'overwrite': self.pt_clip_overwrite.isChecked()},
                'dinov2': {'active': self.pt_dinov2_check.isChecked(), 'overwrite': self.pt_dinov2_overwrite.isChecked()},
                'bioclip': {'active': self.pt_bioclip_check.isChecked(), 'overwrite': self.pt_bioclip_overwrite.isChecked()},
                'aesthetic': {'active': self.pt_aesthetic_check.isChecked(), 'overwrite': self.pt_aesthetic_overwrite.isChecked()},
                'technical': {'active': self.pt_musiq_check.isChecked(), 'overwrite': self.pt_musiq_overwrite.isChecked()},
            }

            # Cross-check con il config attuale: se un modello è disabilitato in Config Tab
            # forza active=False anche se il checkbox di processing è rimasto checked
            # (accade quando si disabilita un modello in Config Tab senza riavviare)
            try:
                with open(self.config_path, 'r', encoding='utf-8') as _cf:
                    _cur_cfg = yaml.safe_load(_cf)
                _mcfg = _cur_cfg.get('embedding', {}).get('models', {})
                for _fk, _ck in [('clip', 'clip'), ('dinov2', 'dinov2'), ('aesthetic', 'aesthetic'),
                                  ('technical', 'technical'), ('bioclip', 'bioclip')]:
                    if not _mcfg.get(_ck, {}).get('enabled', True):
                        embedding_model_flags[_fk]['active'] = False
            except Exception:
                pass

            # Reset terminale
            self.log_display.clear()

            # Apri file log se richiesto
            if self.enable_file_log_cb.isChecked():
                self._open_processing_log()

            self.log_display.append("[{}] {}".format(
                datetime.now().strftime("%H:%M:%S"), t("processing.log.starting")
            ))

            # Determina modalità processing
            mode_id = self.processing_mode_group.checkedId()
            if mode_id == 0:
                processing_mode = 'new_only'
                mode_text = t("processing.log.mode_new_only")
            elif mode_id == 1:
                processing_mode = 'new_plus_errors'
                mode_text = t("processing.log.mode_new_errors")
            else:  # mode_id == 2
                processing_mode = 'reprocess_all'
                mode_text = t("processing.log.mode_reprocess_all")

            self.log_display.append(t("processing.log.mode", mode=mode_text))

            if self.processing_log_file:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.processing_log_file.write(f"[{timestamp}] [INFO] {t('processing.log.starting')}\n")
                self.processing_log_file.write(f"[{timestamp}] [INFO] {t('processing.log.mode', mode=mode_text)}\n")
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
                {
                    'processing_mode': processing_mode,
                    'embedding_model_flags': embedding_model_flags,
                },
                include_subdirs=self.include_subdirs_cb.isChecked(),
                image_list=image_list
            )

            # Connetti segnali
            self.worker.progress.connect(self.update_progress)
            self.worker.model_progress.connect(self._update_model_progress)
            self.worker.log_message.connect(self.add_log_message)
            self.worker.stats_update.connect(self.update_stats)
            self.worker.finished.connect(self.processing_finished)

            # Reset progress bar per-modello
            for _bar in (self.pt_exif_bar, self.pt_clip_bar, self.pt_dinov2_bar,
                         self.pt_bioclip_bar, self.pt_aesthetic_bar, self.pt_musiq_bar,
                         self.pt_llm_bar):
                _bar.setValue(0)
                _bar.setRange(0, 100)

            # Reset progress bar plugin (nascondi finché non girano di nuovo)
            for row in self._plugin_rows.values():
                pb = row.get('bar')
                if pb:
                    pb.setValue(0)
                    pb.setVisible(False)

            self.worker.start()

            # UI state
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)

        except Exception as e:
            self.add_log_message(t("processing.log.start_error", error=e), "error")
    
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

            self.add_log_message(t("processing.log.log_file", path=log_path), "info")

        except Exception as e:
            self.processing_log_file = None
            self.add_log_message(t("processing.log.log_file_error", error=e), "warning")

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
                self.pause_btn.setText(t("processing.btn.pause"))
                self.add_log_message(t("processing.log.resumed"), "info")
            else:
                self.worker.pause()
                self.pause_btn.setText(t("processing.btn.start"))
                self.add_log_message(t("processing.log.paused"), "info")
    
    def stop_processing(self):
        """Ferma processing"""
        if self.worker:
            self.worker.stop()
            self.add_log_message(t("processing.log.stopping"), "info")
        # Termina i subprocess plugin ancora in esecuzione
        for reader in list(self._active_plugin_readers):
            try:
                reader.process.terminate()
            except Exception:
                pass
    
    def _update_model_progress(self, model_key, current, total):
        """Aggiorna progress bar del singolo modello"""
        _bar_map = {
            'exiftool': self.pt_exif_bar,
            'clip': self.pt_clip_bar,
            'dinov2': self.pt_dinov2_bar,
            'bioclip': self.pt_bioclip_bar,
            'aesthetic': self.pt_aesthetic_bar,
            'technical': self.pt_musiq_bar,
            'llm': self.pt_llm_bar,
        }
        bar = _bar_map.get(model_key)
        if bar and total > 0:
            bar.setRange(0, total)
            bar.setValue(current)

    def update_progress(self, current, total):
        """Aggiorna progresso generale (le barre per-modello sono già visibili)"""
        # Il conteggio nel titolo terminale è stato rimosso:
        # le progress bar per-modello mostrano già lo stato di ogni componente
        pass
    
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

        # Ripristina titolo terminale
        self._terminal_group.setTitle(t("processing.group.terminal_log"))

        # Statistiche di completamento nel terminale
        total = stats.get('total', 0)
        success = stats.get('success', 0)
        errors = stats.get('errors', 0)
        processed = stats.get('processed', 0)
        processing_time = stats.get('processing_time', 0)

        if total > 0:
            success_rate = round((success / total) * 100, 1)
            completion_text = f"✅ Completato! {success}/{total} ({success_rate}%)"
            if errors > 0:
                completion_text += f" — ⚠️ {errors} errori"
            self.add_log_message(completion_text, "success")
        else:
            self.add_log_message("✅ Completato!", "success")

        # Aggiorna scan per refresh statistiche
        self.scan_directory()

        # Lancia plugin post-import se abilitati (start_btn rimane disabilitato
        # finché tutti i plugin non hanno terminato)
        self._launch_post_import_plugins()
    
