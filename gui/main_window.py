"""
Main Window - Finestra principale OffGallery
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QStatusBar, QMessageBox,
    QSizePolicy, QLabel, QFrame, QComboBox
)
from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette, QColor, QPixmap, QFont
from pathlib import Path

from utils.paths import get_app_dir

# Import tab
from gui.config_tab import ConfigTab
from gui.processing_tab import ProcessingTab
from gui.search_tab import SearchTab
from gui.gallery_tab import GalleryTab
from gui.stats_tab import StatsTab
from gui.export_tab import ExportTab
from gui.log_tab import LogTab
from gui.plugins_tab import PluginsTab
from xmp_badge_manager import refresh_xmp_badges
from xmp_badge_manager import shutdown_badge_manager
from i18n import t


# Palette colori
COLORS = {
    'grafite': '#2A2A2A',
    'grafite_light': '#3A3A3A',
    'grafite_dark': '#1E1E1E',
    'grigio_chiaro': '#E3E3E3',
    'grigio_medio': '#B0B0B0',
    'blu_petrolio': '#1C4F63',
    'blu_petrolio_light': '#2A6A82',
    'blu_petrolio_dark': '#153D4D',
    'ambra': '#C88B2E',
    'ambra_light': '#E0A84A',
}


class AppHeader(QFrame):
    """Header principale con logo OffGallery grande e responsive"""

    language_changed = pyqtSignal(str)  # emette il codice lingua selezionato

    def __init__(self, current_language: str = "it", parent=None):
        super().__init__(parent)
        self._current_language = current_language
        self.setFixedHeight(143)  # 140px logo + 3px border
        self._build_ui()
    
    def _build_ui(self):
        self.setStyleSheet(f"""
            AppHeader {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #1A2B4A,
                    stop:0.34 #1A2B4A,
                    stop:0.6 #1C3F5F,
                    stop:1 {COLORS['blu_petrolio']});
                border-bottom: 3px solid {COLORS['ambra']};
            }}
        """)

    
        # Layout principale senza spacing per controllo preciso
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 30, 0)
        layout.setSpacing(0)  # Zero spacing per controllo preciso

        # Container per logo + separatore fisso
        logo_container = QWidget()
        logo_container.setFixedWidth(409)  # Logo width + separator width (406 + 3)
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(0)
        
        # ============ LOGO (SINISTRA) ============
        self.logo_label = QLabel()
        self.logo_label.setContentsMargins(0, 0, 0, 0)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter |  Qt.AlignmentFlag.AlignVCenter)

        logo_path = get_app_dir() / 'assets' / 'logo3.jpg'
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled_pixmap = pixmap.scaledToHeight(140, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(scaled_pixmap)
            self.logo_label.setFixedSize(scaled_pixmap.width(), scaled_pixmap.height())
        else:
            self.logo_label.setText("OffGallery")
            self.logo_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 48px;
                    font-weight: bold;
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.logo_label.setFixedSize(406, 140)

        logo_layout.addWidget(self.logo_label)

        # ============ SEPARATOR - Fisso al bordo destro del logo ============
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet(f"""
            QFrame {{
                color: {COLORS['ambra']};
                background-color: {COLORS['ambra']};
            }}
        """)
        separator.setFixedWidth(3)
        separator.setFixedHeight(143)
        logo_layout.addWidget(separator)
        
        layout.addWidget(logo_container)
        
        # ============ BRAND TITLE (RESTO DELLO SPAZIO) ============
        brand_widget = QWidget()
        brand_layout = QVBoxLayout(brand_widget)
        brand_layout.setContentsMargins(15, 0, 20, 0)
        brand_layout.setSpacing(3)
        brand_layout.addStretch()
        
        # Titolo principale con "di Immagini"
        self.app_title = QLabel(t("main.label.app_title"))
        self.app_title.setStyleSheet(f"""
            QLabel {{
                font-size: 18px;
                font-weight: bold;
                color: {COLORS['grigio_chiaro']};
                background: transparent;
            }}
        """)
        self.app_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.app_title.setWordWrap(True)
        
        font = self.app_title.font()
        font.setPointSize(18)
        self.app_title.setFont(font)
        
        brand_layout.addWidget(self.app_title)
        
        # Sottotitolo
        self.subtitle_label = QLabel(t("main.label.app_subtitle"))
        self.subtitle_label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {COLORS['ambra_light']};
                font-weight: 500;
                background: transparent;
            }}
        """)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        brand_layout.addWidget(self.subtitle_label)
        brand_layout.addSpacing(10)

        # Selettore lingua — allineato a sinistra, distaccato dal sottotitolo
        self.lang_combo = QComboBox()
        self.lang_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['grafite_dark']};
                color: {COLORS['grigio_medio']};
                border: 1px solid {COLORS['grafite_light']};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['grafite_dark']};
                color: {COLORS['grigio_chiaro']};
                selection-background-color: {COLORS['blu_petrolio']};
            }}
        """)
        self.lang_combo.setFixedWidth(120)

        from i18n import available_languages
        for code, name, flag in available_languages():
            self.lang_combo.addItem(f"{flag} {name}", userData=code)
            if code == self._current_language:
                self.lang_combo.setCurrentIndex(self.lang_combo.count() - 1)

        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        brand_layout.addWidget(self.lang_combo, alignment=Qt.AlignmentFlag.AlignLeft)

        brand_layout.addStretch()

        # QWidget per il brand si espande orizzontalmente
        brand_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(brand_widget, stretch=1)  # Stretch per occupare spazio
        
        # ============ MODEL STATUS (DESTRA) ============
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(20, 8, 0, 8)
        info_layout.setSpacing(2)

        # Indicatori modelli: id → (dot_label, text_label)
        self._model_indicators = {}
        _model_defs = [
            ('clip',      'CLIP'),
            ('dinov2',    'DINOv2'),
            ('bioclip',   'BioCLIP'),
            ('aesthetic', 'Aesthetic'),
            ('technical', 'Technical'),
            ('llm',       'Ollama'),
            ('exiftool',  'ExifTool'),
            ('database',  'Database'),
        ]
        for model_id, model_name in _model_defs:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)

            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet("""
                QLabel {
                    background-color: #606060;
                    border-radius: 4px;
                }
            """)

            lbl = QLabel(model_name)
            lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: 11px;
                    color: {COLORS['grigio_medio']};
                    font-weight: normal;
                    background: transparent;
                }}
            """)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row_layout.addStretch()
            row_layout.addWidget(lbl)
            row_layout.addWidget(dot)
            info_layout.addWidget(row)
            self._model_indicators[model_id] = (dot, lbl)

        info_layout.addStretch()
        info_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(info_widget, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    
    # Colori semaforo
    _STATUS_COLORS = {
        'ok':      '#4CAF50',   # verde — caricato in VRAM
        'cpu':     '#C88B2E',   # ambra — caricato su CPU (VRAM insufficiente)
        'error':   '#E74C3C',   # rosso — abilitato ma non caricato (anomalia)
        'missing': '#606060',   # grigio — disabilitato
    }

    def update_model_status(self, model_id: str, status: str, label: str = None):
        """Aggiorna il semaforo di un modello nell'header.

        Args:
            model_id: chiave del modello ('clip', 'dinov2', 'bioclip',
                      'aesthetic', 'technical', 'llm', 'exiftool', 'database')
            status:   'ok' (VRAM) | 'cpu' (ambra) | 'error' (rosso) | 'missing' (grigio)
            label:    testo opzionale (usato per cambiare 'Ollama' → 'LM Studio')
        """
        if model_id not in self._model_indicators:
            return
        dot, lbl = self._model_indicators[model_id]
        color = self._STATUS_COLORS.get(status, self._STATUS_COLORS['missing'])
        dot.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)
        if label:
            lbl.setText(label)

    def _on_language_changed(self, index: int):
        """Emette il segnale con il codice lingua selezionato"""
        code = self.lang_combo.itemData(index)
        if code and code != self._current_language:
            self._current_language = code
            self.language_changed.emit(code)

    def resizeEvent(self, event):
        """Ridimensiona il font del titolo in base alla larghezza disponibile"""
        super().resizeEvent(event)
        
        # Calcola dimensione font dinamica per il nuovo titolo italiano
        width = self.width()
        
        # Formula: font size proporzionale alla larghezza (base 18px)
        if width > 1400:
            font_size = 18
        elif width > 1200:
            font_size = 16
        elif width > 1000:
            font_size = 14
        elif width > 800:
            font_size = 13
        else:
            font_size = 12
        
        font = self.app_title.font()
        font.setPointSize(font_size)
        self.app_title.setFont(font)


class MainWindow(QMainWindow):
    """Finestra principale OffGallery"""
    
    def __init__(self, preloaded_models: dict = None):
        super().__init__()

        # Settings per salvare preferenze utente
        self.settings = QSettings('OffGallery', 'OffGalleryApp')

        self.config_path = Path("config_new.yaml")

        # === CONFIGURAZIONE ===
        import yaml
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # Carica lingua UI
        import i18n as i18n_module
        user_lang = self.config.get('ui', {}).get('user_language', 'it')
        i18n_module.load_language(user_lang)

        # === MODELLI AI ===
        if preloaded_models is not None:
            # Modelli già inizializzati dal thread di caricamento (caso normale)
            self.ai_models = preloaded_models
            print("✅ Modelli AI ricevuti dal loader thread")
        else:
            # Fallback: inizializzazione sincrona (avvio diretto senza splash)
            from embedding_generator import EmbeddingGenerator
            self.ai_models = {'initialized': False}
            try:
                self.ai_models['embedding_generator'] = EmbeddingGenerator(self.config)
                self.ai_models['initialized'] = True
                print("✅ Modelli AI inizializzati")
            except Exception as e:
                import traceback
                print(f"⚠️ Modelli AI non inizializzati: {e}")
                print(traceback.format_exc())

        # Warmup LLM in background (pre-carica il modello attivo in VRAM)
        import threading
        def _llm_warmup():
            try:
                self.ai_models['embedding_generator'].warmup_llm()
            except Exception as e:
                print(f"⚠️ LLM warmup fallito: {e}")
        threading.Thread(target=_llm_warmup, daemon=True).start()

        # === INIZIALIZZAZIONE DATABASE CENTRALIZZATA ===
        from db_manager_new import DatabaseManager
        
        # Inizializza database manager se configurato
        self.db_manager = None
        if 'paths' in self.config and 'database' in self.config['paths']:
            db_path = self.config['paths']['database']
            if db_path:
                try:
                    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                    self.db_manager = DatabaseManager(db_path)
                    print(f"✅ Database manager inizializzato: {db_path}")
                except Exception as e:
                    print(f"⚠️ Errore inizializzazione database: {e}")
                    self.db_manager = None
        
        if not self.db_manager:
            print("⚠️ Database manager non inizializzato - verificare configurazione")


        self.init_ui()
        
        # Ripristina geometria finestra
        self.restore_geometry()
    
    def init_ui(self):
        """Inizializza interfaccia utente"""
        
        # Finestra principale
        self.setWindowTitle(t("main.window.title"))
        self.setMinimumSize(900, 600)
        
        # Size policy per resize libero
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Applica stile globale
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['grafite']};
            }}
            QTabWidget::pane {{
                border: none;
                background-color: {COLORS['grafite']};
                border-top: 1px solid {COLORS['grafite_light']};
            }}
            QTabBar {{
                background-color: {COLORS['grafite_dark']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['grafite_dark']};
                color: {COLORS['grigio_medio']};
                padding: 12px 24px;
                margin: 0px;
                border: none;
                border-bottom: 3px solid transparent;
                font-size: 12px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                background-color: {COLORS['grafite']};
                color: {COLORS['grigio_chiaro']};
                border-bottom: 3px solid {COLORS['ambra']};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {COLORS['grafite_light']};
                color: {COLORS['grigio_chiaro']};
                border-bottom: 3px solid {COLORS['blu_petrolio']};
            }}
            QStatusBar {{
                background-color: {COLORS['grafite_dark']};
                color: {COLORS['grigio_medio']};
                border-top: 1px solid {COLORS['grafite_light']};
                font-size: 11px;
            }}
            QMenuBar {{
                background-color: {COLORS['grafite_dark']};
                color: {COLORS['grigio_chiaro']};
                border-bottom: 1px solid {COLORS['grafite_light']};
            }}
            QMenuBar::item {{
                padding: 6px 12px;
            }}
            QMenuBar::item:selected {{
                background-color: {COLORS['blu_petrolio']};
            }}
            QMenu {{
                background-color: {COLORS['grafite']};
                color: {COLORS['grigio_chiaro']};
                border: 1px solid {COLORS['grafite_light']};
            }}
            QMenu::item {{
                padding: 8px 24px;
            }}
            QMenu::item:selected {{
                background-color: {COLORS['blu_petrolio']};
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['grafite']};
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['grafite_light']};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['blu_petrolio']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QToolTip {{
                background-color: {COLORS['grafite_dark']};
                color: {COLORS['grigio_chiaro']};
                border: 1px solid {COLORS['ambra']};
                padding: 4px;
                font-size: 12px;
            }}
        """)
        
        # Widget centrale
        central_widget = QWidget()
        central_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(central_widget)
        
        # Layout principale
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header globale
        import i18n as i18n_module
        self.header = AppHeader(current_language=i18n_module.current_language())
        self.header.language_changed.connect(self._on_language_changed)
        layout.addWidget(self.header)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(t("main.status.ready"))
        
        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Crea tab
        self.config_tab = ConfigTab(self)
        self.processing_tab = ProcessingTab(self)
        self.search_tab = SearchTab(self, self.ai_models)  
        self.gallery_tab = GalleryTab(self, self.ai_models)
        self.stats_tab = StatsTab(self)
        self.export_tab = ExportTab(self)
        self.log_tab = LogTab(self)
        self.plugins_tab = PluginsTab(self)

        # === PROPAGA DATABASE MANAGER ALLE TAB ===
        if self.db_manager:
            # Tab che hanno bisogno del database
            if hasattr(self.search_tab, 'set_database_manager'):
                self.search_tab.set_database_manager(self.db_manager)
            if hasattr(self.gallery_tab, 'set_database_manager'):
                self.gallery_tab.set_database_manager(self.db_manager)
            if hasattr(self.stats_tab, 'set_database_manager'):
                self.stats_tab.set_database_manager(self.db_manager)
            if hasattr(self.processing_tab, 'set_database_manager'):
                self.processing_tab.set_database_manager(self.db_manager)
            if hasattr(self.export_tab, 'set_database_manager'):
                self.export_tab.set_database_manager(self.db_manager)
            if hasattr(self.plugins_tab, 'set_database_manager'):
                self.plugins_tab.set_database_manager(self.db_manager)
        else:
            print("⚠️ Database manager non disponibile - tab funzioneranno in modalità limitata")

        
        # Aggiungi tab con icone più grandi
        self.tabs.addTab(self.config_tab, t("main.tab.config"))
        self.tabs.addTab(self.processing_tab, t("main.tab.processing"))
        self.tabs.addTab(self.search_tab, t("main.tab.search"))
        self.tabs.addTab(self.gallery_tab, t("main.tab.gallery"))
        self.tabs.addTab(self.export_tab, t("main.tab.export"))
        self.tabs.addTab(self.stats_tab, t("main.tab.stats"))
        self.tabs.addTab(self.log_tab, t("main.tab.log"))
        self.tabs.addTab(self.plugins_tab, t("main.tab.plugins"))
                
        # Connetti segnali
        self.search_tab.search_executed.connect(self.on_search_completed)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.export_tab.export_completed.connect(self.on_export_completed)
        self.config_tab.config_saved.connect(self._on_config_saved)
        self.plugins_tab.navigate_to_config.connect(self._navigate_to_config_tab)
        self.processing_tab.plugins_lock.connect(self._on_plugins_lock)
        
        layout.addWidget(self.tabs)

        # Aggiorna semafori modelli nell'header (check completo all'avvio)
        self._update_model_status_indicators()

        # Timer periodico: ricontrolla LLM e Database ogni 30 secondi
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(30_000)
        self._status_timer.timeout.connect(self._check_dynamic_status)
        self._status_timer.start()

    def _update_model_status_indicators(self):
        """Legge lo stato dei modelli AI inizializzati e aggiorna i semafori nell'header.

        Logica semafori:
          verde  (ok)      — modello caricato in VRAM (GPU)
          ambra  (cpu)     — modello caricato su CPU (VRAM insufficiente)
          rosso  (error)   — modello abilitato ma non caricato (anomalia)
          grigio (missing) — modello disabilitato dall'utente
        """
        emb_gen = self.ai_models.get('embedding_generator')
        if emb_gen is None:
            return

        emb_cfg = emb_gen.embedding_config.get('models', {})

        # Device per-modello: legge dalla cache dell'embedding_generator
        _devices = getattr(emb_gen, '_model_devices', {})

        def _gpu_status(model_key):
            """Restituisce 'ok' (GPU) o 'cpu' in base al device del modello"""
            dev = str(_devices.get(model_key, 'cpu'))
            return 'ok' if dev != 'cpu' else 'cpu'

        # CLIP
        clip_enabled = emb_cfg.get('clip', {}).get('enabled', False)
        if emb_gen.clip_model is not None:
            self.header.update_model_status('clip', _gpu_status('clip'))
        elif clip_enabled:
            self.header.update_model_status('clip', 'error')
        else:
            self.header.update_model_status('clip', 'missing')

        # DINOv2
        dino_enabled = emb_cfg.get('dinov2', {}).get('enabled', False)
        if emb_gen.dinov2_model is not None:
            self.header.update_model_status('dinov2', _gpu_status('dinov2'))
        elif dino_enabled:
            self.header.update_model_status('dinov2', 'error')
        else:
            self.header.update_model_status('dinov2', 'missing')

        # BioCLIP (ha fallback CPU proprio)
        bio_enabled = emb_cfg.get('bioclip', {}).get('enabled', False)
        if emb_gen.bioclip_classifier is not None:
            if getattr(emb_gen, 'bioclip_on_cpu', False):
                self.header.update_model_status('bioclip', 'cpu')
            else:
                self.header.update_model_status('bioclip', _gpu_status('bioclip'))
        elif bio_enabled:
            self.header.update_model_status('bioclip', 'error')
        else:
            self.header.update_model_status('bioclip', 'missing')

        # Aesthetic
        aes_enabled = emb_cfg.get('aesthetic', {}).get('enabled', False)
        if emb_gen.aesthetic_model is not None:
            self.header.update_model_status('aesthetic', _gpu_status('aesthetic'))
        elif aes_enabled:
            self.header.update_model_status('aesthetic', 'error')
        else:
            self.header.update_model_status('aesthetic', 'missing')

        # Technical (MUSIQ)
        tech_enabled = emb_cfg.get('technical', {}).get('enabled', False)
        if getattr(emb_gen, 'musiq_available', False):
            musiq_dev = str(getattr(emb_gen, 'musiq_device', 'cpu'))
            if musiq_dev != 'cpu':
                self.header.update_model_status('technical', 'ok')
            else:
                self.header.update_model_status('technical', 'cpu')
        elif tech_enabled:
            self.header.update_model_status('technical', 'error')
        else:
            self.header.update_model_status('technical', 'missing')

        # LLM backend — label dinamica in base al plugin attivo
        plugin = getattr(emb_gen, 'llm_plugin', None)
        llm_enabled = emb_cfg.get('llm_vision', {}).get('enabled', False)
        if plugin is not None:
            plugin_class = type(plugin).__name__
            if 'LMStudio' in plugin_class:
                backend_label = 'LM Studio'
            else:
                backend_label = 'Ollama'
            self.header.update_model_status('llm', 'ok', label=backend_label)
        elif llm_enabled:
            self.header.update_model_status('llm', 'error')
        else:
            self.header.update_model_status('llm', 'missing')

        # ExifTool
        try:
            from xmp_manager_extended import XMPManagerExtended
            xmp = XMPManagerExtended(self.config)
            if xmp.exiftool_available:
                self.header.update_model_status('exiftool', 'ok')
            else:
                self.header.update_model_status('exiftool', 'error')
        except Exception:
            self.header.update_model_status('exiftool', 'error')

        # Database
        if self.db_manager is not None:
            try:
                db_path = self.config.get('paths', {}).get('database', '')
                from pathlib import Path as _Path
                if db_path and _Path(db_path).exists():
                    self.header.update_model_status('database', 'ok')
                else:
                    self.header.update_model_status('database', 'error')
            except Exception:
                self.header.update_model_status('database', 'error')
        else:
            self.header.update_model_status('database', 'missing')

    def _check_dynamic_status(self):
        """Ricontrolla in background solo gli stati che possono cambiare a runtime:
        LLM backend (Ollama/LM Studio può andare offline) e Database.
        Chiamato ogni 30 secondi da QTimer.
        """
        emb_gen = self.ai_models.get('embedding_generator')
        if emb_gen is None:
            return

        # LLM: re-verifica disponibilità del plugin (fa un HTTP ping leggero)
        plugin = getattr(emb_gen, 'llm_plugin', None)
        llm_enabled = emb_gen.embedding_config.get('models', {}).get('llm_vision', {}).get('enabled', False)
        if plugin is not None:
            try:
                alive = plugin.is_available()
            except Exception:
                alive = False
            if alive:
                plugin_class = type(plugin).__name__
                label = 'LM Studio' if 'LMStudio' in plugin_class else 'Ollama'
                self.header.update_model_status('llm', 'ok', label=label)
            else:
                plugin_class = type(plugin).__name__
                label = 'LM Studio' if 'LMStudio' in plugin_class else 'Ollama'
                self.header.update_model_status('llm', 'error', label=label)
        elif llm_enabled:
            # Nessun plugin caricato ma LLM abilitato: riprova auto-detect
            try:
                import sys
                from utils.paths import get_app_dir
                _pd = str(get_app_dir() / 'plugins')
                if _pd not in sys.path:
                    sys.path.insert(0, _pd)
                from plugins.loader import load_plugin
                new_plugin = load_plugin(self.config)
                if new_plugin:
                    emb_gen.llm_plugin = new_plugin
                    plugin_class = type(new_plugin).__name__
                    label = 'LM Studio' if 'LMStudio' in plugin_class else 'Ollama'
                    self.header.update_model_status('llm', 'ok', label=label)
            except Exception:
                pass

        # Database: verifica accessibilità del file
        if self.db_manager is not None:
            try:
                db_path = self.config.get('paths', {}).get('database', '')
                from pathlib import Path as _Path
                if db_path and _Path(db_path).exists():
                    self.header.update_model_status('database', 'ok')
                else:
                    self.header.update_model_status('database', 'error')
            except Exception:
                self.header.update_model_status('database', 'error')

    def _navigate_to_config_tab(self):
        """Naviga alla Config Tab (indice 0)."""
        self.tabs.setCurrentWidget(self.config_tab)

    def _on_plugins_lock(self, locked: bool):
        """Abilita/disabilita il tab Plugin durante l'esecuzione post-import dei plugin."""
        plugins_index = self.tabs.indexOf(self.plugins_tab)
        if plugins_index >= 0:
            self.tabs.setTabEnabled(plugins_index, not locked)

    def _on_config_saved(self, new_config):
        """
        Aggiorna il config in-memory dopo un salvataggio da ConfigTab.
        Propaga il nuovo embedding_config all'EmbeddingGenerator condiviso
        senza ricaricare i modelli (già in VRAM).
        """
        import logging
        log = logging.getLogger(__name__)
        self.config = new_config
        emb_gen = self.ai_models.get('embedding_generator')
        if emb_gen is not None:
            emb_gen.config = new_config
            emb_gen.embedding_config = new_config.get('embedding', {})
            log.info("✅ Config ricaricato in EmbeddingGenerator senza riavvio modelli")

    def on_tab_changed(self, index):
        tab_names = [
            "Configurazione",
            "Processing",
            "Ricerca",
            "Gallery",
            "Export",
            "Statistiche"
        ]

        # Removed header.set_status call since we removed status widgets

        if index == 2:
            self.search_tab.on_activated()
        elif index == 3:
            self.gallery_tab.on_activated()
        elif index == 4:
            # Recuperiamo gli oggetti selezionati usando la tua funzione esistente
            selected = self.get_selected_gallery_items()
            # Passiamoli al tab export
            self.export_tab.set_images(selected)
            # --- FINE AGGIUNTA ---
            self.export_tab.on_activated()
        elif index == 5:
            self.stats_tab.on_activated()

        
    def get_selected_gallery_items(self):
        """Restituisce gli items selezionati nella gallery"""
        if hasattr(self.gallery_tab, 'selected_items'):
            return self.gallery_tab.selected_items
        return []

    def on_search_completed(self, results):
        """Gestisce completamento ricerca"""
        self.gallery_tab.display_results(results)
        self.tabs.setCurrentIndex(3)
        self.update_status(f"Mostrati {len(results)} risultati")

    def on_export_completed(self, count, format_type):
        """Gestisce completamento export"""
        try:
            self.update_status(f"Export {format_type} completato: {count} file")
        
            if format_type == 'XMP' and count > 0:
                selected = self.get_selected_gallery_items()
                if selected:
                    # USA IL MANAGER CENTRALIZZATO
                    refresh_xmp_badges(selected, "export_completed")
        
        except Exception as e:
            print(f"❌ ERRORE in on_export_completed: {e}")
            try:
                self.update_status(f"Export completato con errori: {count} file")
            except:
                pass


    def update_status(self, message, timeout=0):
        """Aggiorna status bar e log"""
        self.status_bar.showMessage(message, timeout)
        if hasattr(self, 'log_tab'):
            self.log_tab.log_info(f"Status: {message}")
            
    def log_info(self, message):
        """Log info globale"""
        if hasattr(self, 'log_tab'):
            self.log_tab.log_info(message)
            
    def log_warning(self, message):
        """Log warning globale"""
        if hasattr(self, 'log_tab'):
            self.log_tab.log_warning(message)
            
    def log_error(self, message):
        """Log error globale"""
        if hasattr(self, 'log_tab'):
            self.log_tab.log_error(message)
    
    def show_about(self):
        """Mostra dialog about"""
        about_box = QMessageBox(self)
        about_box.setWindowTitle(t("main.dialog.about_title"))
        about_box.setTextFormat(Qt.TextFormat.RichText)
        about_box.setText(f"""
            <div style="text-align: center;">
            <h2 style="color: {COLORS['blu_petrolio_light']};">OffGallery</h2>
            <p style="font-size: 12px;"><b>Catalogazione e Ricerca AI Offline</b></p>
            <hr>
            <p style="font-size: 11px; color: {COLORS['grigio_medio']};">
            Sistema completo di catalogazione fotografica<br>
            100% offline e privacy-first
            </p>
            <hr>
            <p style="font-size: 11px;">
            • Embedding CLIP + DINOv2<br>
            • BioCLIP flora/fauna (~450k specie)<br>
            • Ricerca semantica e visiva<br>
            • EXIF completi + GPS
            </p>
            <hr>
            <p style="font-size: 10px; color: {COLORS['ambra']};">© 2024 - MIT License</p>
            </div>
        """)
        about_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {COLORS['grafite']};
            }}
            QMessageBox QLabel {{
                color: {COLORS['grigio_chiaro']};
                min-width: 300px;
            }}
            QPushButton {{
                background-color: {COLORS['blu_petrolio']};
                color: {COLORS['grigio_chiaro']};
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['blu_petrolio_light']};
            }}
        """)
        about_box.exec()
    
    def update_database_manager(self, new_db_path=None):
        """Aggiorna il database manager quando cambia la configurazione"""
        try:
            # Chiudi database esistente se presente
            if self.db_manager:
                self.db_manager.close()
            
            # Se non specificato, ricarica dalla config
            if not new_db_path:
                if 'paths' in self.config and 'database' in self.config['paths']:
                    new_db_path = self.config['paths']['database']
            
            # Inizializza nuovo database
            if new_db_path:
                from db_manager_new import DatabaseManager
                self.db_manager = DatabaseManager(new_db_path)
                
                # Propaga alle tab
                self._propagate_database_to_tabs()
                
                return True
            else:
                self.db_manager = None
                print("⚠️ Percorso database non specificato")
                return False
                
        except Exception as e:
            print(f"❌ Errore aggiornamento database manager: {e}")
            self.db_manager = None
            return False
    
    def _propagate_database_to_tabs(self):
        """Propaga il database manager a tutte le tab"""
        if not self.db_manager:
            return
            
        # Lista delle tab che supportano database manager
        tab_list = [
            ('search_tab', 'SearchTab'),
            ('gallery_tab', 'GalleryTab'), 
            ('stats_tab', 'StatsTab'),
            ('processing_tab', 'ProcessingTab'),
            ('export_tab', 'ExportTab')
        ]
        
        for tab_attr, tab_name in tab_list:
            if hasattr(self, tab_attr):
                tab = getattr(self, tab_attr)
                if hasattr(tab, 'set_database_manager'):
                    tab.set_database_manager(self.db_manager)
    
    def reload_config_and_update_database(self):
        """Ricarica config e aggiorna database - chiamato dalla ConfigTab"""
        try:
            # Ricarica configurazione
            import yaml
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            # Aggiorna database manager
            return self.update_database_manager()
            
        except Exception as e:
            print(f"❌ Errore ricarica configurazione: {e}")
            return False
    
    def _on_language_changed(self, lang_code: str):
        """Salva la lingua selezionata e avvisa di riavviare"""
        import yaml
        import i18n as i18n_module
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
            if 'ui' not in cfg:
                cfg['ui'] = {}
            cfg['ui']['user_language'] = lang_code
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Errore salvataggio lingua: {e}")

        _, name, flag = next(
            (x for x in i18n_module.available_languages() if x[0] == lang_code),
            (lang_code, lang_code, "")
        )
        QMessageBox.information(
            self,
            "Lingua / Language",
            f"{flag} {name} selezionata / selected.\n\n"
            f"🇮🇹 Riavvia OffGallery per applicare.\n"
            f"🇬🇧 Restart OffGallery to apply."
        )

    def restore_geometry(self):
        """Ripristina geometria finestra salvata"""
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
    
    def closeEvent(self, event):
        """Gestisce chiusura finestra"""
        # Cleanup database manager
        if hasattr(self, 'db_manager') and self.db_manager:
            try:
                self.db_manager.close()
            except Exception as e:
                print(f"⚠️ Errore chiusura database: {e}")
        
        # Cleanup log tab
        if hasattr(self, 'log_tab'):
            self.log_tab.cleanup()
            
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('current_tab', self.tabs.currentIndex())
        event.accept()


def main():
    """Funzione principale"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Palette scura globale
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS['grafite']))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS['grigio_chiaro']))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS['grafite_light']))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS['grafite']))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS['grigio_chiaro']))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS['grafite_light']))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS['grigio_chiaro']))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS['blu_petrolio']))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS['grigio_chiaro']))
    app.setPalette(palette)
    
    window = MainWindow()
    window.show()
    app.aboutToQuit.connect(shutdown_badge_manager)
    sys.exit(app.exec())
    # Collega shutdown del badge manager
    


if __name__ == '__main__':
    main()
