"""
Config Tab - Configurazione applicazione
Struttura modulare basata su config_new.yaml
Versione 2.0 - 
"""

import yaml
import platform
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
from i18n import t
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QCheckBox, QSpinBox,
    QDoubleSpinBox, QFileDialog, QMessageBox, QScrollArea,
    QGridLayout, QTextEdit, QComboBox, QRadioButton, QButtonGroup,
    QProgressBar, QFrame, QStackedLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject

# Classi custom per prevenire cambi accidentali con scroll wheel
class NoWheelSpinBox(QSpinBox):
    """QSpinBox che richiede click esplicito per abilitare scroll wheel"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # Focus solo con click
        
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
            # Passa l'evento al widget padre (scroll area)
            if self.parent():
                self.parent().wheelEvent(event)

class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox che richiede click esplicito per abilitare scroll wheel"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # Focus solo con click
        
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
            # Passa l'evento al widget padre (scroll area)
            if self.parent():
                self.parent().wheelEvent(event)

class NoWheelComboBox(QComboBox):
    """QComboBox che richiede click esplicito per abilitare scroll wheel"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # Focus solo con click
        
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
            # Passa l'evento al widget padre (scroll area)
            if self.parent():
                self.parent().wheelEvent(event)

class _LlmVramDetector(QObject):
    """Worker che rileva VRAM LLM in background e restituisce info + etichetta."""
    result_ready = pyqtSignal(dict, str)  # info_dict, label_text

    def __init__(self, endpoint: str, model: str, backend: str):
        super().__init__()
        self.endpoint = endpoint
        self.model    = model
        self.backend  = backend

    def run(self):
        logger.info(f"[LLM VRAM worker] run() partito ep={self.endpoint} mdl={self.model} bk={self.backend}")
        try:
            from device_allocator import detect_llm_vram
            cfg = {'embedding': {'models': {'llm_vision': {
                'backend': self.backend, 'endpoint': self.endpoint,
                'model': self.model, 'enabled': True,
            }}}}
            info = detect_llm_vram(cfg)
            logger.info(f"[LLM VRAM worker] detect_llm_vram ritornato: {info}")
            vram = info.get('vram_gb', 0.0)
            src  = info.get('source', 'none')
            if vram > 0:
                src_label = 'API' if src == 'ollama_api' else 'stima'
                lbl = f"~{vram:.1f} GB ({src_label})"
                logger.info(f"[LLM VRAM worker] emit result_ready: {lbl}")
                self.result_ready.emit(info, lbl)
            else:
                empty = {'vram_gb': 0.0, 'source': 'none', 'model_name': self.model}
                logger.info(f"[LLM VRAM worker] emit result_ready: non raggiungibile")
                self.result_ready.emit(empty, "— (non raggiungibile)")
        except Exception as e:
            logger.exception(f"[LLM VRAM worker] eccezione: {e}")
            empty = {'vram_gb': 0.0, 'source': 'none', 'model_name': self.model}
            self.result_ready.emit(empty, "— (errore)")


class _LlmModelsLoader(QObject):
    """Worker che interroga Ollama o LM Studio in background e restituisce la lista modelli."""
    finished = pyqtSignal(list)   # lista di stringhe (nomi modelli)
    failed   = pyqtSignal()       # endpoint non raggiungibile o lista vuota

    def __init__(self, endpoint: str, is_ollama: bool):
        super().__init__()
        self.endpoint  = endpoint.rstrip('/')
        self.is_ollama = is_ollama

    def run(self):
        import requests
        try:
            if self.is_ollama:
                url = f"{self.endpoint}/api/tags"
                r   = requests.get(url, timeout=5)
                if r.status_code == 200:
                    names = [m.get('name', '') for m in r.json().get('models', []) if m.get('name')]
                else:
                    names = []
            else:
                url = f"{self.endpoint}/v1/models"
                r   = requests.get(url, timeout=5)
                if r.status_code == 200:
                    names = [m.get('id', '') for m in r.json().get('data', []) if m.get('id')]
                else:
                    names = []
            if names:
                self.finished.emit(names)
            else:
                self.failed.emit()
        except Exception:
            self.failed.emit()


# Palette colori (definizione completa per lo styling)
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
    'verde': '#4A7C59',
    'rosso': '#8B4049',
}


class ConfigTab(QWidget):
    """Tab configurazione"""

    config_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.config = {}
        self.config_path = Path('config_new.yaml')

        # Inizializzazione sicura per editor controls
        self.editor_controls = []

        self.init_ui()
        self.load_config()

    @staticmethod
    def _llm_plugin_installed() -> bool:
        """Ritorna True se almeno un plugin LLM backend è installato in APP_DIR/plugins/."""
        try:
            from utils.paths import get_app_dir
            plugins_dir = get_app_dir() / "plugins"
            if not plugins_dir.exists():
                return False
            for manifest_path in plugins_dir.rglob("manifest.json"):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        import json as _json
                        m = _json.load(f)
                    if m.get("type") == "llm_backend":
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False
    
    def init_ui(self):
        """Inizializza interfaccia"""
        layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # --- STILE GLOBALE PER I GROUPBOX ---
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['grafite']};
            }}
            QGroupBox {{
                background-color: {COLORS['grafite_light']};
                border-radius: 6px; 
                margin-top: 25px; 
                padding-top: 15px;
                padding-bottom: 10px;
                color: {COLORS['grigio_chiaro']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                left: 10px;
                color: {COLORS['ambra_light']};
                font-weight: bold;
                font-size: 14px;
            }}
            QLabel {{
                color: {COLORS['grigio_medio']};
            }}
            QCheckBox {{
                color: {COLORS['grigio_chiaro']};
            }}
            QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, QTextEdit {{
                background-color: {COLORS['grafite']};
                border: 1px solid {COLORS['blu_petrolio_light']};
                color: {COLORS['grigio_chiaro']};
                padding: 3px;
                border-radius: 3px;
            }}
            /* Feedback visivo chiaro per focus - BORDO ARANCIONE */
            QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
                border: 2px solid {COLORS['ambra']};
                background-color: {COLORS['grafite_light']};
            }}
            QPushButton {{
                background-color: {COLORS['blu_petrolio']};
                color: {COLORS['grigio_chiaro']};
                border: none;
                padding: 6px;
                border-radius: 3px;
            }}
        """)
        # -----------------------------------
        
        # Sezioni Riorganizzate - Gestione Completa
        scroll_layout.addWidget(self.create_paths_section())
        scroll_layout.addWidget(self.create_external_editors_section())
        
        # Info embedding sempre attivi
        info_label = QLabel(t("config.info.embedding_always_active"))
        info_label.setStyleSheet(f"color: {COLORS['ambra']}; font-size: 11px; padding: 10px; background-color: {COLORS['grafite_dark']}; border-radius: 4px;")
        info_label.setWordWrap(True)
        scroll_layout.addWidget(info_label)
        
        # Device globale
        scroll_layout.addWidget(self.create_device_section())
        
        # Gruppo Embedding Models
        embedding_group = QGroupBox(t("config.group.embedding_core"))
        embedding_group.setStyleSheet(f"""
            QGroupBox {{
                background-color: {COLORS['grafite_dark']};
                border: 2px solid {COLORS['blu_petrolio']};
                border-radius: 8px;
                margin-top: 15px;
                padding-top: 20px;
                color: {COLORS['ambra_light']};
                font-weight: bold;
                font-size: 16px;
            }}
        """)
        embedding_layout = QVBoxLayout()
        embedding_layout.addWidget(self.create_dinov2_section())
        embedding_layout.addWidget(self.create_clip_section())
        embedding_group.setLayout(embedding_layout)
        scroll_layout.addWidget(embedding_group)
        
        # Gruppo AI Classification
        ai_group = QGroupBox(t("config.group.ai_classification"))
        ai_group.setStyleSheet(f"""
            QGroupBox {{
                background-color: {COLORS['grafite_dark']};
                border: 2px solid {COLORS['verde']};
                border-radius: 8px;
                margin-top: 15px;
                padding-top: 20px;
                color: {COLORS['ambra_light']};
                font-weight: bold;
                font-size: 16px;
            }}
        """)
        ai_layout = QVBoxLayout()
        ai_layout.addWidget(self.create_bioclip_section())
        ai_layout.addWidget(self._build_llm_vision_with_overlay())
        ai_group.setLayout(ai_layout)
        scroll_layout.addWidget(ai_group)
        
        # Gruppo Image Processing & Performance
        processing_group = QGroupBox(t("config.group.image_processing_perf"))
        processing_group.setStyleSheet(f"""
            QGroupBox {{
                background-color: {COLORS['grafite_dark']};
                border: 2px solid {COLORS['ambra']};
                border-radius: 8px;
                margin-top: 15px;
                padding-top: 20px;
                color: {COLORS['ambra_light']};
                font-weight: bold;
                font-size: 16px;
            }}
        """)
        processing_layout = QVBoxLayout()
        processing_layout.addWidget(self.create_image_processing_section())
        processing_layout.addWidget(self.create_image_optimization_section())
        processing_group.setLayout(processing_layout)
        scroll_layout.addWidget(processing_group)
        
        # Gruppo Search & Metadata  
        search_group = QGroupBox(t("config.group.search_metadata_section"))
        search_group.setStyleSheet(f"""
            QGroupBox {{
                background-color: {COLORS['grafite_dark']};
                border: 2px solid {COLORS['grigio_medio']};
                border-radius: 8px;
                margin-top: 15px;
                padding-top: 20px;
                color: {COLORS['ambra_light']};
                font-weight: bold;
                font-size: 16px;
            }}
        """)
        search_layout = QVBoxLayout()
        search_layout.addWidget(self.create_search_section())
        search_layout.addWidget(self.create_similarity_section())
        search_group.setLayout(search_layout)
        scroll_layout.addWidget(search_group)
        
        scroll_layout.addWidget(self.create_logging_section())
        
        # Bottoni Reset e Save
        buttons_layout = QHBoxLayout()
        
        # Bottone Reset
        reset_button = QPushButton(t("config.btn.reset"))
        reset_button.clicked.connect(self.reset_to_defaults)
        reset_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['ambra']};
                color: {COLORS['grafite_dark']};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 150px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['ambra_light']};
            }}
        """)
        buttons_layout.addWidget(reset_button)
        
        buttons_layout.addStretch()
        
        # Bottone Salva
        save_button = QPushButton(t("config.btn.save"))
        save_button.clicked.connect(self.save_config)
        save_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['verde']};
                color: {COLORS['grigio_chiaro']};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 150px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['blu_petrolio']};
            }}
        """)
        buttons_layout.addWidget(save_button)
        
        scroll_layout.addLayout(buttons_layout)
        
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
    
    def _backup_config_file(self):
        if not self.config_path.exists():
            return

        from datetime import datetime
        import shutil

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.config_path.with_name(
            f"{self.config_path.name}_BACKUP_{timestamp}.yaml"
        )

        shutil.copy2(self.config_path, backup_path)

    def create_paths_section(self):
        """Crea sezione configurazione percorsi completa"""
        group_box = QGroupBox(t("config.group.paths_db"))
        group_box.setObjectName("PathsSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#PathsSection {{
                border: 2px solid {COLORS['blu_petrolio']};
            }}
        """)

        layout = QGridLayout()

        # Database Path
        layout.addWidget(QLabel(t("config.label.database")), 0, 0)
        self.db_path_edit = QLineEdit()
        self.db_path_edit.setPlaceholderText("Es: database/offgallery.sqlite")
        layout.addWidget(self.db_path_edit, 0, 1)

        db_browse_btn = QPushButton("📂")
        db_browse_btn.setFixedWidth(40)
        db_browse_btn.clicked.connect(lambda: self._select_file(self.db_path_edit, t("config.dialog.select_db"), "Database SQLite (*.sqlite)"))
        layout.addWidget(db_browse_btn, 0, 2)

        # Log Directory
        layout.addWidget(QLabel(t("config.label.logs")), 1, 0)
        self.log_dir_edit = QLineEdit()
        self.log_dir_edit.setPlaceholderText("Es: logs")
        layout.addWidget(self.log_dir_edit, 1, 1)

        log_browse_btn = QPushButton("📂")
        log_browse_btn.setFixedWidth(40)
        log_browse_btn.clicked.connect(lambda: self._select_directory(self.log_dir_edit, t("config.dialog.select_log_dir")))
        layout.addWidget(log_browse_btn, 1, 2)

        # Models Directory
        layout.addWidget(QLabel(t("config.label.models_ai")), 2, 0)
        self.models_dir_edit = QLineEdit()
        self.models_dir_edit.setToolTip(t("config.tooltip.models_dir"))
        self.models_dir_edit.setPlaceholderText("Es: Models  oppure  D:\\AI\\Models")
        layout.addWidget(self.models_dir_edit, 2, 1)

        models_dir_browse_btn = QPushButton("📂")
        models_dir_browse_btn.setFixedWidth(40)
        models_dir_browse_btn.clicked.connect(lambda: self._select_directory(self.models_dir_edit, t("config.dialog.select_models_dir")))
        layout.addWidget(models_dir_browse_btn, 2, 2)

        models_dir_warn = QLabel(t("config.warn.models_dir_change"))
        models_dir_warn.setStyleSheet("color: #e6a817; font-size: 10px;")
        layout.addWidget(models_dir_warn, 3, 1)

        # Temp Cache Directory
        layout.addWidget(QLabel(t("config.label.temp_cache")), 4, 0)
        self.temp_cache_edit = QLineEdit()
        self.temp_cache_edit.setToolTip(t("config.tooltip.temp_cache"))
        self.temp_cache_edit.setPlaceholderText("Es: temp_cache")
        layout.addWidget(self.temp_cache_edit, 4, 1)

        temp_cache_browse_btn = QPushButton("📂")
        temp_cache_browse_btn.setFixedWidth(40)
        temp_cache_browse_btn.clicked.connect(lambda: self._select_directory(self.temp_cache_edit, t("config.dialog.select_temp_cache")))
        layout.addWidget(temp_cache_browse_btn, 4, 2)

        temp_cache_info = QLabel(t("config.info.temp_cache"))
        temp_cache_info.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        layout.addWidget(temp_cache_info, 5, 1)

        group_box.setLayout(layout)
        return group_box
    
    def create_external_editors_section(self):
        """Crea sezione configurazione editor esterni"""
        group_box = QGroupBox(t("config.group.editors"))
        group_box.setObjectName("ExternalEditorsSection")

        layout = QVBoxLayout()

        info_label = QLabel(t("config.info.editors"))
        info_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 11px; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Grid layout per i 3 editor
        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(1, 1)  # Nome editor si espande
        grid_layout.setColumnStretch(2, 2)  # Percorso si espande di più
        
        # Header
        grid_layout.addWidget(QLabel(t("config.label.editor_active")), 0, 0)
        grid_layout.addWidget(QLabel(t("config.label.editor_name_col")), 0, 1)
        grid_layout.addWidget(QLabel(t("config.label.editor_path_col")), 0, 2)
        grid_layout.addWidget(QLabel(t("config.label.editor_args_col")), 0, 3)
        grid_layout.addWidget(QLabel(""), 0, 4)  # Per pulsante
        
        # Store references per accesso successivo
        self.editor_controls = []
        
        for i in range(1, 4):
            # Checkbox abilitato
            enabled_cb = QCheckBox()
            enabled_cb.setObjectName(f"editor_{i}_enabled")
            
            # Nome editor
            name_edit = QLineEdit()
            name_edit.setPlaceholderText(f"Editor {i}")
            name_edit.setObjectName(f"editor_{i}_name")
            name_edit.setMaxLength(30)
            
            # Percorso
            path_edit = QLineEdit()
            if platform.system() == "Windows":
                path_edit.setPlaceholderText("Seleziona file .exe...")
            else:
                path_edit.setPlaceholderText("Seleziona eseguibile...")
            path_edit.setObjectName(f"editor_{i}_path")
            path_edit.textChanged.connect(lambda text, idx=i: self.validate_editor_path(text, idx))
            
            # Argomenti comando (NUOVO)
            args_edit = QLineEdit()
            args_edit.setPlaceholderText(t("config.placeholder.editor_args"))
            args_edit.setObjectName(f"editor_{i}_command_args")
            args_edit.setMaxLength(100)
            
            # Pulsante sfoglia
            browse_btn = QPushButton("📁")
            browse_btn.setFixedSize(30, 25)
            browse_btn.setToolTip(t("config.tooltip.select_editor"))
            browse_btn.clicked.connect(lambda checked, idx=i: self.browse_editor_path(idx))
            
            # Aggiungi alla grid (5 colonne ora)
            grid_layout.addWidget(enabled_cb, i, 0)
            grid_layout.addWidget(name_edit, i, 1)
            grid_layout.addWidget(path_edit, i, 2)
            grid_layout.addWidget(args_edit, i, 3)
            grid_layout.addWidget(browse_btn, i, 4)
            
            # Store references
            self.editor_controls.append({
                'enabled': enabled_cb,
                'name': name_edit,
                'path': path_edit,
                'command_args': args_edit,
                'browse': browse_btn
            })
        
        layout.addLayout(grid_layout)
        group_box.setLayout(layout)
        return group_box
    
    def create_device_section(self):
        """Crea sezione device elaborazione con tabella per-modello e auto-ottimizzazione"""
        from device_allocator import (
            detect_hardware, auto_allocate, MODEL_VRAM_ESTIMATES,
            ALL_MODELS, get_vram_budget_info
        )

        group_box = QGroupBox(t("config.group.device_section"))
        group_box.setObjectName("DeviceSection")

        group_box.setStyleSheet(f"""
            QGroupBox#DeviceSection {{
                border: 2px solid {COLORS['ambra']};
            }}
        """)

        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Rileva hardware una sola volta
        self._hw_info = detect_hardware()

        # Label info GPU dinamica
        self.gpu_info_label = QLabel(t("config.msg.gpu_detecting"))
        self.gpu_info_label.setStyleSheet(
            f"color: {COLORS['grigio_medio']}; font-size: 10px; padding: 5px;")
        self.gpu_info_label.setWordWrap(True)
        layout.addWidget(self.gpu_info_label)
        self._update_gpu_info()

        # Tabella per-modello: Modello | VRAM | Device
        header_label = QLabel(t("config.label.model_device_header"))
        header_label.setStyleSheet(f"color: {COLORS['grigio_chiaro']}; font-weight: bold; padding-top: 5px;")
        layout.addWidget(header_label)

        grid = QGridLayout()
        grid.setSpacing(6)

        # Header riga
        for col, key in enumerate(["config.label.model_col", "config.label.vram_col", "config.label.device_col"]):
            lbl = QLabel(t(key))
            lbl.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; font-weight: bold;")
            grid.addWidget(lbl, 0, col)

        # Nomi modelli per la UI
        _model_display = {
            'clip': 'CLIP',
            'dinov2': 'DINOv2',
            'aesthetic': 'Aesthetic',
            'bioclip': 'BioCLIP',
            'technical': 'MUSIQ',
        }

        self.model_device_combos = {}
        gpu_available = self._hw_info['backend'] != 'cpu'

        for row_idx, model_key in enumerate(ALL_MODELS, start=1):
            # Nome modello
            name_lbl = QLabel(_model_display.get(model_key, model_key))
            name_lbl.setStyleSheet(f"color: {COLORS['grigio_chiaro']};")
            grid.addWidget(name_lbl, row_idx, 0)

            # VRAM stimata
            vram_est = MODEL_VRAM_ESTIMATES.get(model_key, 0)
            vram_lbl = QLabel(f"~{vram_est:.1f} GB")
            vram_lbl.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px;")
            grid.addWidget(vram_lbl, row_idx, 1)

            # ComboBox GPU/CPU/OFF
            combo = NoWheelComboBox()
            combo.addItem(t("config.combo.model_device_gpu"), "gpu")
            combo.addItem(t("config.combo.model_device_cpu"), "cpu")
            combo.addItem(t("config.combo.model_device_off"), "off")
            combo.setFixedWidth(90)
            if not gpu_available:
                combo.setCurrentIndex(1)  # CPU
                combo.setEnabled(False)
            combo.currentIndexChanged.connect(self._update_vram_budget)
            combo.currentIndexChanged.connect(
                lambda _, mk=model_key: self._on_device_combo_changed(mk))
            self.model_device_combos[model_key] = combo
            grid.addWidget(combo, row_idx, 2)

        # Riga LLM Vision (VRAM reale + toggle attivo/non attivo)
        llm_row = len(ALL_MODELS) + 1
        llm_name = QLabel("LLM Vision")
        llm_name.setStyleSheet(f"color: {COLORS['grigio_chiaro']};")
        grid.addWidget(llm_name, llm_row, 0)

        self._llm_vram_label = QLabel("—")
        self._llm_vram_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px;")
        grid.addWidget(self._llm_vram_label, llm_row, 1)

        self.llm_enabled_combo = NoWheelComboBox()
        self.llm_enabled_combo.addItem(t("config.device.on"),  'on')
        self.llm_enabled_combo.addItem(t("config.device.off"), 'off')
        self.llm_enabled_combo.currentIndexChanged.connect(self._on_llm_enabled_changed)
        grid.addWidget(self.llm_enabled_combo, llm_row, 2)

        # VRAM LLM: aggiornata in _load_config quando la config è disponibile
        self._llm_vram_info = {'vram_gb': 0.0, 'source': 'none', 'model_name': ''}

        layout.addLayout(grid)

        # Barra budget VRAM
        budget_layout = QHBoxLayout()
        budget_label = QLabel(t("config.label.vram_budget"))
        budget_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px;")
        budget_layout.addWidget(budget_label)

        self.vram_budget_bar = QProgressBar()
        self.vram_budget_bar.setFixedHeight(16)
        self.vram_budget_bar.setTextVisible(True)
        self.vram_budget_bar.setMaximum(100)
        budget_layout.addWidget(self.vram_budget_bar)
        layout.addLayout(budget_layout)

        # Label budget dettaglio
        self.vram_budget_label = QLabel("")
        self.vram_budget_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; padding: 2px;")
        self.vram_budget_label.setWordWrap(True)
        layout.addWidget(self.vram_budget_label)

        # Nascondi barra su MPS (unified memory) o CPU-only
        if self._hw_info['is_unified_memory']:
            self.vram_budget_bar.setVisible(False)
            self.vram_budget_label.setText(t("config.msg.vram_unified"))
            self.vram_budget_label.setStyleSheet(
                f"color: {COLORS['verde']}; font-size: 10px; padding: 2px;")
        elif not gpu_available:
            self.vram_budget_bar.setVisible(False)
            self.vram_budget_label.setText(t("config.msg.vram_cpu_only"))

        # Bottone Auto-ottimizza
        auto_btn = QPushButton(f"🔧 {t('config.btn.auto_optimize')}")
        auto_btn.setToolTip(t("config.tooltip.auto_optimize"))
        auto_btn.setFixedWidth(180)
        auto_btn.clicked.connect(self._on_auto_optimize)
        if not gpu_available:
            auto_btn.setEnabled(False)
        refresh_btn = QPushButton("🔄 Ricalcola")
        refresh_btn.setToolTip("Ricalcola VRAM LLM leggendo da config corrente")
        refresh_btn.setFixedWidth(110)
        refresh_btn.clicked.connect(self._refresh_llm_vram_if_active)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(auto_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Label "riavvia per applicare" — accanto al bottone, nascosta di default
        self._device_restart_label = QLabel(t("config.msg.device_restart"))
        self._device_restart_label.setStyleSheet(
            f"color: {COLORS['ambra']}; font-size: 9px; font-style: italic; padding: 2px;")
        self._device_restart_label.setVisible(False)
        btn_layout.addWidget(self._device_restart_label)

        # Aggiorna budget iniziale (senza mostrare messaggio restart)
        self._update_vram_budget()
        self._device_restart_label.setVisible(False)

        group_box.setLayout(layout)
        return group_box

    def _update_gpu_info(self):
        """Aggiorna label info GPU in base a hardware rilevato"""
        hw = self._hw_info
        if hw['backend'] == 'cuda':
            self.gpu_info_label.setText(
                t("config.msg.gpu_detected", name=hw['gpu_name'], mem=hw['vram_total_gb']))
            self.gpu_info_label.setStyleSheet(
                f"color: {COLORS['verde']}; font-weight: bold; font-size: 10px; padding: 5px;")
        elif hw['backend'] == 'mps':
            self.gpu_info_label.setText(
                t("config.msg.gpu_mps_detected", name=hw['gpu_name'] or 'Apple Silicon'))
            self.gpu_info_label.setStyleSheet(
                f"color: {COLORS['verde']}; font-weight: bold; font-size: 10px; padding: 5px;")
        elif hw['backend'] == 'directml':
            self.gpu_info_label.setText(
                t("config.msg.gpu_detected", name=hw['gpu_name'] or 'DirectML', mem=hw['vram_total_gb'] or 0))
            self.gpu_info_label.setStyleSheet(
                f"color: {COLORS['verde']}; font-weight: bold; font-size: 10px; padding: 5px;")
        else:
            self.gpu_info_label.setText(t("config.msg.gpu_none"))
            self.gpu_info_label.setStyleSheet(
                f"color: {COLORS['ambra']}; font-size: 10px; padding: 5px;")

    def _on_device_combo_changed(self, model_key: str):
        """Aggiorna lo stato dei widget dipendenti dal combo device.
        I combo sono la fonte di verità — OFF = non caricato, GPU/CPU = caricato."""
        combo = self.model_device_combos.get(model_key)
        if combo is None:
            return
        is_enabled = combo.currentData() != 'off'
        if model_key == 'bioclip':
            self.toggle_bioclip_params(is_enabled)

    def _on_auto_optimize(self):
        """Esegue auto-allocazione GPU/CPU in base alla VRAM e popola i combo.
        Non tocca mai modelli impostati su OFF — l'utente li ha esclusi esplicitamente."""
        from device_allocator import auto_allocate
        # Considera solo modelli NON impostati su OFF
        enabled = [
            mk for mk, combo in self.model_device_combos.items()
            if combo.currentData() != 'off'
        ]
        _llm_on = getattr(self, 'llm_enabled_combo', None)
        llm_vram = (getattr(self, '_llm_vram_info', {}).get('vram_gb', 0.0)
                    if (_llm_on is None or _llm_on.currentData() != 'off') else 0.0)
        allocation = auto_allocate(self._hw_info, enabled, llm_vram_gb=llm_vram)
        for model_key, device in allocation.items():
            combo = self.model_device_combos.get(model_key)
            if combo:
                idx = combo.findData(device)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _update_vram_budget(self):
        """Aggiorna barra e label budget VRAM in base ai combo correnti"""
        from device_allocator import get_vram_budget_info
        allocation = {k: combo.currentData() for k, combo in self.model_device_combos.items()}
        _llm_on = getattr(self, 'llm_enabled_combo', None)
        llm_vram = (getattr(self, '_llm_vram_info', {}).get('vram_gb', 0.0)
                    if (_llm_on is None or _llm_on.currentData() != 'off') else 0.0)
        info = get_vram_budget_info(allocation, self._hw_info.get('vram_total_gb'), llm_vram)

        # Aggiorna barra
        if self._hw_info['is_unified_memory'] or self._hw_info['backend'] == 'cpu':
            return  # Barra nascosta

        pct = min(info['percentage'], 100)
        self.vram_budget_bar.setValue(int(pct))

        # Colore barra
        if info['status'] == 'ok':
            bar_color = COLORS['verde']
        elif info['status'] == 'warning':
            bar_color = COLORS['ambra']
        else:
            bar_color = COLORS['rosso']

        self.vram_budget_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['grafite_dark']};
                border: 1px solid {COLORS['grigio_medio']};
                border-radius: 3px;
                text-align: center;
                color: {COLORS['grigio_chiaro']};
                font-size: 10px;
            }}
            QProgressBar::chunk {{
                background-color: {bar_color};
                border-radius: 2px;
            }}
        """)
        self.vram_budget_bar.setFormat(f"{info['used_gb']:.1f} / {info['total_gb']:.1f} GB")

        # Label dettaglio
        if info['status'] == 'over':
            self.vram_budget_label.setText(
                t("config.msg.vram_over_budget", used=info['used_gb'], total=info['total_gb']))
            self.vram_budget_label.setStyleSheet(
                f"color: {COLORS['rosso']}; font-size: 10px; padding: 2px;")
        else:
            self.vram_budget_label.setText(
                t("config.msg.vram_budget_ok", used=info['used_gb'], total=info['total_gb'], pct=info['percentage']))
            self.vram_budget_label.setStyleSheet(
                f"color: {COLORS['grigio_medio']}; font-size: 10px; padding: 2px;")

        # Mostra "riavvia per applicare" quando un combo cambia
        if hasattr(self, '_device_restart_label'):
            self._device_restart_label.setVisible(True)

    def _on_llm_enabled_changed(self):
        """Gestisce cambio toggle Attivo/Non attivo per LLM Vision."""
        import threading, yaml
        enabled = self.llm_enabled_combo.currentData() == 'on'
        # Legge endpoint/model/backend da YAML (fonte di verità)
        try:
            with open(self.config_path, 'r', encoding='utf-8') as _f:
                _cfg = yaml.safe_load(_f) or {}
        except Exception:
            _cfg = self.config
        _llm = _cfg.get('embedding', {}).get('models', {}).get('llm_vision', {})
        ep  = _llm.get('endpoint', '').strip()
        mdl = _llm.get('model',    '').strip()
        bk  = _llm.get('backend',  'ollama')

        if not enabled:
            self._llm_vram_label.setText("— (non attivo)")
            self._llm_vram_info = {'vram_gb': 0.0, 'source': 'none', 'model_name': ''}
            self._update_vram_budget()
            def _unload(ep=ep, mdl=mdl, bk=bk):
                try:
                    import requests as _req
                    if not ep or not mdl:
                        return
                    if bk == 'ollama':
                        _req.post(f"{ep}/api/generate",
                                  json={"model": mdl, "keep_alive": 0}, timeout=5)
                    elif bk == 'lmstudio':
                        _req.post(f"{ep}/api/v0/models/unload",
                                  json={"identifier": mdl}, timeout=5)
                except Exception:
                    pass
            threading.Thread(target=_unload, daemon=True).start()
        else:
            self._refresh_llm_vram_if_active()

    def _refresh_llm_vram_if_active(self):
        """Ricalcola VRAM LLM leggendo endpoint/model da config_new.yaml."""
        logger.info("[LLM VRAM] _refresh_llm_vram_if_active chiamato")
        if getattr(self, 'llm_enabled_combo', None) is None:
            logger.info("[LLM VRAM] llm_enabled_combo non esiste, esco")
            return
        if self.llm_enabled_combo.currentData() != 'on':
            logger.info(f"[LLM VRAM] toggle non è 'on' (={self.llm_enabled_combo.currentData()}), esco")
            return
        import yaml
        logger.info(f"[LLM VRAM] leggo config_path={self.config_path} (absolute={Path(self.config_path).resolve()})")
        try:
            with open(self.config_path, 'r', encoding='utf-8') as _f:
                _cfg = yaml.safe_load(_f) or {}
            logger.info(f"[LLM VRAM] YAML letto ok")
        except Exception as _e:
            logger.warning(f"[LLM VRAM] errore lettura YAML: {_e}, uso self.config")
            _cfg = self.config
        _llm     = _cfg.get('embedding', {}).get('models', {}).get('llm_vision', {})
        model    = _llm.get('model',    '').strip()
        endpoint = _llm.get('endpoint', '').strip()
        backend  = _llm.get('backend',  'ollama')
        logger.info(f"[LLM VRAM] model='{model}' endpoint='{endpoint}' backend='{backend}'")
        if not model:
            self._llm_vram_info = {'vram_gb': 0.0, 'source': 'none', 'model_name': ''}
            self._llm_vram_label.setText("— (nessun modello)")
            self._update_vram_budget()
            return
        if not endpoint:
            self._llm_vram_info = {'vram_gb': 0.0, 'source': 'none', 'model_name': model}
            self._llm_vram_label.setText("— (nessun endpoint)")
            self._update_vram_budget()
            return
        logger.info(f"[LLM VRAM] avvio QThread detector con ep={endpoint} mdl={model} bk={backend}")
        self._llm_vram_label.setText("— (verifica…)")
        self._llm_vram_info = {'vram_gb': 0.0, 'source': 'none', 'model_name': model}
        self._update_vram_budget()
        from PyQt6.QtCore import QThread
        worker = _LlmVramDetector(endpoint, model, backend)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.result_ready.connect(self._on_llm_vram_result)
        worker.result_ready.connect(lambda _i, _l: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # Mantiene riferimento per evitare garbage collection
        self._llm_vram_thread = thread
        self._llm_vram_worker = worker
        thread.start()
        logger.info("[LLM VRAM] QThread partito")

    def _on_llm_vram_result(self, info: dict, label: str):
        """Riceve il risultato del rilevamento VRAM LLM dal QThread e aggiorna la GUI."""
        logger.info(f"[LLM VRAM] _on_llm_vram_result ricevuto: info={info} label={label}")
        if getattr(self, 'llm_enabled_combo', None) is None:
            logger.info("[LLM VRAM] llm_enabled_combo sparito, ignoro")
            return
        if self.llm_enabled_combo.currentData() != 'on':
            logger.info("[LLM VRAM] toggle non più 'on', ignoro")
            return
        # Endpoint irraggiungibile o errore: forza toggle a 'Non attivo'
        if info.get('vram_gb', 0.0) <= 0 and info.get('source', 'none') == 'none':
            logger.info("[LLM VRAM] endpoint non raggiungibile → forzo toggle a 'off'")
            idx_off = self.llm_enabled_combo.findData('off')
            if idx_off >= 0:
                self.llm_enabled_combo.setCurrentIndex(idx_off)
            return
        self._llm_vram_info = info
        self._llm_vram_label.setText(label)
        self._update_vram_budget()
        logger.info("[LLM VRAM] GUI aggiornata")

    def _save_llm_vision_to_yaml(self):
        """Salva immediatamente endpoint/model/backend LLM Vision in config_new.yaml."""
        import yaml
        try:
            with open(self.config_path, 'r', encoding='utf-8') as _f:
                _cfg = yaml.safe_load(_f) or {}
            _llm = (_cfg.setdefault('embedding', {})
                        .setdefault('models', {})
                        .setdefault('llm_vision', {}))
            _llm['backend']  = 'lmstudio' if self.llm_radio_lmstudio.isChecked() else 'ollama'
            _llm['endpoint'] = self.llm_vision_endpoint.text().strip()
            _llm['model']    = self.llm_vision_model.currentText().strip()
            with open(self.config_path, 'w', encoding='utf-8') as _f:
                yaml.dump(_cfg, _f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.warning(f"Impossibile salvare llm_vision su YAML: {e}")

    def create_dinov2_section(self):
        """Crea sezione configurazione DINOv2 (MODIFICATO - rimosso checkbox enabled e device)"""
        group_box = QGroupBox(t("config.group.dinov2"))
        group_box.setObjectName("DINOv2Section")
        
        group_box.setStyleSheet(f"""
            QGroupBox#DINOv2Section {{
                border: 2px solid {COLORS['blu_petrolio_dark']};
            }}
        """)
        
        layout = QGridLayout()

        # Model Name
        layout.addWidget(QLabel(t("config.label.model_name")), 0, 0)
        self.dinov2_model_name = QLineEdit()
        layout.addWidget(self.dinov2_model_name, 0, 1)

        # Soglia Similarità
        layout.addWidget(QLabel(t("config.label.similarity_threshold")), 1, 0)
        self.dinov2_similarity_threshold = NoWheelDoubleSpinBox()
        self.dinov2_similarity_threshold.setRange(0.0, 1.0)
        self.dinov2_similarity_threshold.setSingleStep(0.05)
        self.dinov2_similarity_threshold.setDecimals(2)
        self.dinov2_similarity_threshold.setToolTip(t("config.tooltip.dinov2_threshold"))
        self.dinov2_similarity_threshold.valueChanged.connect(self.validate_dinov2_threshold)
        layout.addWidget(self.dinov2_similarity_threshold, 1, 1)

        group_box.setLayout(layout)
        return group_box
        
    def create_clip_section(self):
        """Crea sezione configurazione CLIP (MODIFICATO - rimosso checkbox enabled)"""
        group_box = QGroupBox(t("config.group.clip"))
        group_box.setObjectName("CLIPSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#CLIPSection {{
                border: 2px solid {COLORS['blu_petrolio_light']};
            }}
        """)
        
        layout = QGridLayout()

        # Model Name
        layout.addWidget(QLabel(t("config.label.model_name")), 0, 0)
        self.clip_model_name = QLineEdit()
        layout.addWidget(self.clip_model_name, 0, 1)

        group_box.setLayout(layout)
        return group_box

    def create_bioclip_section(self):
        """Crea sezione configurazione BioCLIP (MODIFICATO - testo checkbox)"""
        group_box = QGroupBox(t("config.group.bioclip"))
        group_box.setObjectName("BioCLIPSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#BioCLIPSection {{
                border: 2px solid {COLORS['verde']};
            }}
        """)
        
        layout = QGridLayout()

        # Soglia
        layout.addWidget(QLabel(t("config.label.relevance_threshold")), 0, 0)
        self.bioclip_threshold = NoWheelDoubleSpinBox()
        self.bioclip_threshold.setRange(0.01, 1.0)
        self.bioclip_threshold.setSingleStep(0.01)
        self.bioclip_threshold.setDecimals(3)
        layout.addWidget(self.bioclip_threshold, 0, 1)

        # Max Tag
        layout.addWidget(QLabel(t("config.label.max_tags_per_image")), 1, 0)
        self.bioclip_max_tags = NoWheelSpinBox()
        self.bioclip_max_tags.setRange(1, 20)
        layout.addWidget(self.bioclip_max_tags, 1, 1)
        
        # Inizializza stato
        self.toggle_bioclip_params(False)  # FIXED: inizializza come disabilitato

        group_box.setLayout(layout)
        return group_box

    def create_llm_vision_section(self):
        """Crea sezione configurazione LLM Vision con selezione backend e parametri generazione"""
        group_box = QGroupBox(t("config.group.llm_vision"))
        group_box.setObjectName("LLMVisionSection")
        group_box.setStyleSheet(f"""
            QGroupBox#LLMVisionSection {{
                border: 2px solid {COLORS['ambra']};
            }}
        """)
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # --- SELEZIONE BACKEND ---
        backend_row = QHBoxLayout()
        backend_row.addWidget(QLabel(t("config.label.llm_backend")))

        self.llm_backend_group = QButtonGroup(self)
        self.llm_radio_ollama   = QRadioButton("Ollama")
        self.llm_radio_lmstudio = QRadioButton("LM Studio")
        self.llm_radio_ollama.setChecked(True)
        self.llm_backend_group.addButton(self.llm_radio_ollama,   0)
        self.llm_backend_group.addButton(self.llm_radio_lmstudio, 1)
        self.llm_backend_group.idClicked.connect(self._on_llm_backend_changed)

        backend_row.addWidget(self.llm_radio_ollama)
        backend_row.addWidget(self.llm_radio_lmstudio)
        backend_row.addStretch()
        layout.addLayout(backend_row)

        # --- CONNESSIONE ---
        conn_layout = QGridLayout()
        conn_layout.setVerticalSpacing(6)

        conn_layout.addWidget(QLabel(t("config.label.llm_endpoint")), 0, 0)
        endpoint_row = QHBoxLayout()
        self.llm_vision_endpoint = QLineEdit()
        self.llm_vision_endpoint.editingFinished.connect(self._load_llm_models)
        self.llm_vision_endpoint.editingFinished.connect(self._save_llm_vision_to_yaml)
        endpoint_row.addWidget(self.llm_vision_endpoint)
        self.test_endpoint_btn = QPushButton("🔍 Test")
        self.test_endpoint_btn.setFixedWidth(60)
        self.test_endpoint_btn.clicked.connect(self.test_llm_connection)
        self.test_endpoint_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['blu_petrolio_light']};
                font-size: 10px;
                padding: 2px;
            }}
        """)
        endpoint_row.addWidget(self.test_endpoint_btn)
        endpoint_widget = QWidget()
        endpoint_widget.setLayout(endpoint_row)
        conn_layout.addWidget(endpoint_widget, 0, 1)

        conn_layout.addWidget(QLabel(t("config.label.llm_model")), 1, 0)
        self.llm_vision_model = NoWheelComboBox()
        self.llm_vision_model.setEditable(True)
        self.llm_vision_model.setMaxVisibleItems(4)
        self.llm_vision_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.llm_vision_model.activated.connect(lambda _: self._save_llm_vision_to_yaml())
        self.llm_vision_model.lineEdit().editingFinished.connect(self._save_llm_vision_to_yaml)
        conn_layout.addWidget(self.llm_vision_model, 1, 1)

        conn_layout.addWidget(QLabel(t("config.label.llm_timeout")), 2, 0)
        self.llm_vision_timeout = NoWheelSpinBox()
        self.llm_vision_timeout.setRange(30, 600)
        self.llm_vision_timeout.setSingleStep(30)
        conn_layout.addWidget(self.llm_vision_timeout, 2, 1)

        layout.addLayout(conn_layout)

        # --- PARAMETRI GENERAZIONE (compatti, senza groupbox annidato) ---
        sep = QLabel(t("config.label.llm_params_sep"))
        sep.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 11px; margin-top: 4px;")
        layout.addWidget(sep)

        adv_layout = QGridLayout()
        adv_layout.setVerticalSpacing(4)

        adv_layout.addWidget(QLabel("Temperature:"), 0, 0)
        self.llm_temperature = NoWheelDoubleSpinBox()
        self.llm_temperature.setRange(0.0, 2.0)
        self.llm_temperature.setSingleStep(0.1)
        self.llm_temperature.setDecimals(2)
        self.llm_temperature.setValue(0.2)
        self.llm_temperature.setToolTip(t("config.tooltip.temperature"))
        adv_layout.addWidget(self.llm_temperature, 0, 1)

        adv_layout.addWidget(QLabel("Top-K:"), 0, 2)
        self.llm_top_k = NoWheelSpinBox()
        self.llm_top_k.setRange(1, 100)
        self.llm_top_k.setValue(40)
        self.llm_top_k.setToolTip(t("config.tooltip.top_k"))
        adv_layout.addWidget(self.llm_top_k, 0, 3)

        adv_layout.addWidget(QLabel("Top-P:"), 0, 4)
        self.llm_top_p = NoWheelDoubleSpinBox()
        self.llm_top_p.setRange(0.0, 1.0)
        self.llm_top_p.setSingleStep(0.05)
        self.llm_top_p.setDecimals(2)
        self.llm_top_p.setValue(0.8)
        self.llm_top_p.setToolTip(t("config.tooltip.top_p"))
        adv_layout.addWidget(self.llm_top_p, 0, 5)

        adv_layout.addWidget(QLabel("Num Ctx:"), 1, 0)
        self.llm_num_ctx = NoWheelSpinBox()
        self.llm_num_ctx.setRange(512, 32768)
        self.llm_num_ctx.setSingleStep(512)
        self.llm_num_ctx.setValue(4096)
        self.llm_num_ctx.setToolTip(t("config.tooltip.num_ctx"))
        adv_layout.addWidget(self.llm_num_ctx, 1, 1)

        adv_layout.addWidget(QLabel("Num Batch:"), 1, 2)
        self.llm_num_batch = NoWheelSpinBox()
        self.llm_num_batch.setRange(128, 4096)
        self.llm_num_batch.setSingleStep(128)
        self.llm_num_batch.setValue(1024)
        self.llm_num_batch.setToolTip(t("config.tooltip.num_batch"))
        adv_layout.addWidget(self.llm_num_batch, 1, 3)

        self.llm_keep_alive = QCheckBox(t("config.check.keep_alive"))
        self.llm_keep_alive.setChecked(True)
        self.llm_keep_alive.setToolTip(t("config.tooltip.keep_alive"))
        adv_layout.addWidget(self.llm_keep_alive, 1, 4, 1, 2)

        adv_layout.addWidget(QLabel(t("config.label.llm_output_lang")), 2, 0)
        self.llm_output_lang_combo = NoWheelComboBox()
        for code, label in [
            ("it", "🇮🇹 Italiano"),
            ("en", "🇬🇧 English"),
            ("fr", "🇫🇷 Français"),
            ("de", "🇩🇪 Deutsch"),
            ("es", "🇪🇸 Español"),
            ("pt", "🇵🇹 Português"),
        ]:
            self.llm_output_lang_combo.addItem(label, code)
        self.llm_output_lang_combo.setToolTip(t("config.tooltip.llm_output_lang"))
        adv_layout.addWidget(self.llm_output_lang_combo, 2, 1, 1, 2)

        layout.addLayout(adv_layout)
        group_box.setLayout(layout)
        return group_box

    def _on_llm_backend_changed(self, btn_id: int):
        """Aggiorna endpoint di default al cambio backend, solo se non personalizzato."""
        _OLLAMA_DEFAULT   = 'http://localhost:11434'
        _LMSTUDIO_DEFAULT = 'http://localhost:1234'
        current = self.llm_vision_endpoint.text().strip()
        if btn_id == 0:  # Ollama
            if current == _LMSTUDIO_DEFAULT:
                self.llm_vision_endpoint.setText(_OLLAMA_DEFAULT)
        else:            # LM Studio
            if current == _OLLAMA_DEFAULT:
                self.llm_vision_endpoint.setText(_LMSTUDIO_DEFAULT)
        # Ricarica modelli e salva backend su YAML
        self._load_llm_models()
        self._save_llm_vision_to_yaml()

    def _load_llm_models(self):
        """Interroga il backend LLM in background e popola il combobox modelli.

        Chiamata automaticamente all'apertura della tab (se endpoint configurato),
        al cambio endpoint e al cambio backend. Silenziosa in caso di errore.
        Usa un contatore di richiesta per ignorare risposte di thread obsoleti.
        """
        endpoint = self.llm_vision_endpoint.text().strip()
        if not endpoint:
            return
        is_ollama = self.llm_radio_ollama.isChecked()

        # Incrementa il contatore: le risposte con ID diverso da quello corrente vengono scartate
        if not hasattr(self, '_llm_load_request_id'):
            self._llm_load_request_id = 0
        self._llm_load_request_id += 1
        request_id = self._llm_load_request_id

        # Mantieni il valore attuale per riselezionarlo dopo il caricamento
        current_model = self.llm_vision_model.currentText().strip()

        thread = QThread()
        worker = _LlmModelsLoader(endpoint, is_ollama)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(
            lambda names: self._on_llm_models_loaded(names, current_model, request_id))
        worker.failed.connect(
            lambda: self._on_llm_models_failed(request_id))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        # Mantieni riferimento per evitare garbage collection prematura
        self._llm_loader_thread = thread
        self._llm_loader_worker = worker
        thread.start()

    def _on_llm_models_loaded(self, names: list, previous_model: str, request_id: int):
        """Popola il combobox con i modelli ricevuti dal backend.

        Scarta la risposta se nel frattempo è partita una richiesta più recente.
        """
        if request_id != getattr(self, '_llm_load_request_id', request_id):
            return  # Risposta obsoleta: ignorata
        self.llm_vision_model.blockSignals(True)
        self.llm_vision_model.clear()
        for name in names:
            self.llm_vision_model.addItem(name)
        # Ripristina il modello precedente se ancora presente, altrimenti lascia il testo
        idx = self.llm_vision_model.findText(previous_model)
        if idx >= 0:
            self.llm_vision_model.setCurrentIndex(idx)
        else:
            self.llm_vision_model.setCurrentText(previous_model)
        self.llm_vision_model.blockSignals(False)
        # Rimuovi eventuale placeholder di errore precedente
        self.llm_vision_model.lineEdit().setPlaceholderText('')

    def _on_llm_models_failed(self, request_id: int):
        """Svuota il combobox e mostra placeholder quando il backend non è raggiungibile."""
        if request_id != getattr(self, '_llm_load_request_id', request_id):
            return  # Risposta obsoleta: ignorata
        backend = "Ollama" if self.llm_radio_ollama.isChecked() else "LM Studio"
        self.llm_vision_model.blockSignals(True)
        self.llm_vision_model.clear()
        self.llm_vision_model.lineEdit().setPlaceholderText(
            f"{backend} non raggiungibile — digita il modello manualmente")
        self.llm_vision_model.blockSignals(False)

    def _build_llm_vision_with_overlay(self) -> QWidget:
        """
        Ritorna il widget della sezione LLM Vision.
        Se nessun plugin LLM backend è installato, il widget è disabilitato
        e sovrapposto da un overlay con call-to-action.
        """
        llm_section = self.create_llm_vision_section()

        if self._llm_plugin_installed():
            # Plugin presente: sezione abilitata, nessun overlay
            return llm_section

        # Plugin assente: disabilita la sezione
        llm_section.setEnabled(False)

        # Contenitore con layout sovrapposto
        container = QWidget()
        stacked = QStackedLayout(container)
        stacked.setStackingMode(QStackedLayout.StackingMode.StackAll)

        stacked.addWidget(llm_section)

        # Overlay semi-trasparente con call-to-action
        overlay = QFrame(container)
        overlay.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 30, 30, 200);
                border-radius: 6px;
            }}
        """)
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.setSpacing(6)

        lbl_icon = QLabel("🔌")
        lbl_icon.setStyleSheet("font-size: 28px; background: transparent;")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(lbl_icon)

        lbl_title = QLabel(t("config.overlay.llm_plugin_missing"))
        lbl_title.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {COLORS['grigio_chiaro']}; background: transparent;"
        )
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(lbl_title)

        lbl_desc = QLabel(t("config.overlay.llm_plugin_desc"))
        lbl_desc.setStyleSheet(
            f"font-size: 11px; color: {COLORS['grigio_medio']}; background: transparent;"
        )
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        overlay_layout.addWidget(lbl_desc)

        lbl_request = QLabel(t("config.overlay.llm_plugin_request"))
        lbl_request.setStyleSheet(
            f"font-size: 11px; color: {COLORS['grigio_chiaro']}; background: transparent;"
        )
        lbl_request.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(lbl_request)

        lbl_contact = QLabel(
            f'<a href="mailto:offgallery.ai.info@gmail.com" style="color: {COLORS["ambra_light"]};">'
            f'offgallery.ai.info@gmail.com</a>'
        )
        lbl_contact.setStyleSheet("background: transparent; font-size: 12px; font-weight: bold;")
        lbl_contact.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_contact.setOpenExternalLinks(True)
        overlay_layout.addWidget(lbl_contact)

        lbl_note = QLabel(t("config.overlay.llm_plugin_note"))
        lbl_note.setStyleSheet(
            f"font-size: 10px; color: {COLORS['grigio_medio']}; background: transparent; font-style: italic;"
        )
        lbl_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(lbl_note)

        stacked.addWidget(overlay)
        stacked.setCurrentIndex(1)  # Mostra overlay sopra

        return container

    def create_image_processing_section(self):
        """Crea sezione configurazione formati file supportati"""
        formats_group = QGroupBox(t("config.group.file_formats"))
        formats_group.setObjectName("ImageProcessingSection")

        formats_group.setStyleSheet(f"""
            QGroupBox#ImageProcessingSection {{
                border: 2px solid {COLORS['ambra_light']};
                color: {COLORS['grigio_medio']};
                font-size: 12px;
            }}
        """)
        formats_layout = QVBoxLayout()
        
        # Info
        info_label = QLabel(t("config.info.formats_warning"))
        info_label.setStyleSheet(f"color: {COLORS['ambra']}; font-size: 10px; font-style: italic;")
        formats_layout.addWidget(info_label)
        
        # Text area per formati (uno per riga)
        self.supported_formats_text = QTextEdit()
        self.supported_formats_text.setMaximumHeight(120)
        self.supported_formats_text.setToolTip(t("config.tooltip.formats"))
        formats_layout.addWidget(self.supported_formats_text)
        
        # Preset buttons per formati comuni
        preset_layout = QHBoxLayout()
        
        preset_basic_btn = QPushButton("📷 Basic")
        preset_basic_btn.setToolTip(t("config.tooltip.preset_basic"))
        preset_basic_btn.clicked.connect(self.set_basic_formats)
        preset_layout.addWidget(preset_basic_btn)
        
        preset_extended_btn = QPushButton("🎯 Extended") 
        preset_extended_btn.setToolTip(t("config.tooltip.preset_extended"))
        preset_extended_btn.clicked.connect(self.set_extended_formats)
        preset_layout.addWidget(preset_extended_btn)
        
        preset_all_btn = QPushButton("🌟 Completo")
        preset_all_btn.setToolTip(t("config.tooltip.preset_all"))
        preset_all_btn.clicked.connect(self.set_all_formats)
        preset_layout.addWidget(preset_all_btn)
        
        preset_layout.addStretch()
        formats_layout.addLayout(preset_layout)
        
        formats_group.setLayout(formats_layout)
        return formats_group

    def create_image_optimization_section(self):
        """Crea sezione ottimizzazione profili AI"""
        group_box = QGroupBox(t("config.group.ai_profiles"))
        group_box.setObjectName("ImageOptimizationSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#ImageOptimizationSection {{
                border: 2px solid {COLORS['verde']};
            }}
        """)
        
        layout = QVBoxLayout()
        
        # Info header
        info_label = QLabel("⚡ Profili ottimizzati per ogni modello AI (target_size, quality, method)")
        info_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; font-style: italic;")
        layout.addWidget(info_label)
        
        # Contenitore scrollabile per profili
        scroll_profiles = QScrollArea()
        scroll_profiles.setMaximumHeight(200)
        scroll_profiles.setWidgetResizable(True)
        
        profiles_widget = QWidget()
        profiles_layout = QGridLayout()
        
        # Headers
        headers = [t("config.label.profile_col"), "Size", "Quality", "Method", "Resampling"]
        for i, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet(f"font-weight: bold; color: {COLORS['ambra']};")
            profiles_layout.addWidget(label, 0, i)
        
        # Profili configurabili (principali)
        self.profile_widgets = {}
        _llm_installed = self._llm_plugin_installed()
        profiles = [
            ("llm_vision", "LLM Vision"),
            ("clip_embedding", "CLIP"),
            ("dinov2_embedding", "DINOv2"),
            ("bioclip_classification", "BioCLIP"),
            ("aesthetic_score", "Aesthetic"),
            ("ai_processing", "AI Generic"),
        ]

        for row, (profile_key, profile_name) in enumerate(profiles, 1):
            # Nasconde la riga LLM Vision se il plugin non è installato
            visible = not (profile_key == "llm_vision" and not _llm_installed)

            lbl_name = QLabel(profile_name)
            if not visible:
                lbl_name.hide()
            profiles_layout.addWidget(lbl_name, row, 0)

            # Target size
            size_spin = NoWheelSpinBox()
            size_spin.setRange(128, 2048)
            size_spin.setSingleStep(64)
            size_spin.setSuffix("px")
            if not visible:
                size_spin.hide()
            profiles_layout.addWidget(size_spin, row, 1)

            # Quality
            quality_spin = NoWheelSpinBox()
            quality_spin.setRange(50, 100)
            quality_spin.setSuffix("%")
            if not visible:
                quality_spin.hide()
            profiles_layout.addWidget(quality_spin, row, 2)

            # Method
            method_combo = NoWheelComboBox()
            method_combo.addItems(["rawpy_full", "high_quality", "preview_optimized", "fast_thumbnail"])
            if not visible:
                method_combo.hide()
            profiles_layout.addWidget(method_combo, row, 3)

            # Resampling
            resampling_combo = NoWheelComboBox()
            resampling_combo.addItems(["LANCZOS", "BILINEAR", "BICUBIC", "NEAREST"])
            if not visible:
                resampling_combo.hide()
            profiles_layout.addWidget(resampling_combo, row, 4)

            # Store widgets
            self.profile_widgets[profile_key] = {
                'size': size_spin,
                'quality': quality_spin,
                'method': method_combo,
                'resampling': resampling_combo
            }

        profiles_widget.setLayout(profiles_layout)
        scroll_profiles.setWidget(profiles_widget)
        layout.addWidget(scroll_profiles)

        group_box.setLayout(layout)
        return group_box

    def create_search_section(self):
        """Crea sezione configurazione ricerca avanzata"""
        group_box = QGroupBox(t("config.group.search_advanced"))
        group_box.setObjectName("SearchAdvancedSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#SearchAdvancedSection {{
                border: 2px solid {COLORS['grigio_medio']};
            }}
        """)
        
        layout = QGridLayout()

        # Row 0: Fuzzy enabled
        self.fuzzy_enabled_checkbox = QCheckBox(t("config.check.fuzzy"))
        layout.addWidget(self.fuzzy_enabled_checkbox, 0, 0)

        # Row 1: Semantic threshold
        layout.addWidget(QLabel(t("config.label.semantic_threshold")), 1, 0)
        self.semantic_threshold_spin = NoWheelDoubleSpinBox()
        self.semantic_threshold_spin.setRange(0.05, 0.50)
        self.semantic_threshold_spin.setSingleStep(0.05)
        self.semantic_threshold_spin.setDecimals(2)
        self.semantic_threshold_spin.setToolTip(t("config.tooltip.semantic_threshold"))
        self.semantic_threshold_spin.valueChanged.connect(self.validate_semantic_threshold)
        layout.addWidget(self.semantic_threshold_spin, 1, 1)

        group_box.setLayout(layout)
        return group_box

    def create_similarity_section(self):
        """Crea sezione configurazione ricerca globale"""
        group_box = QGroupBox(t("config.group.search_combined"))
        group_box.setObjectName("SearchSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#SearchSection {{
                border: 2px solid {COLORS['grigio_medio']};
            }}
        """)
        
        layout = QGridLayout()
        
        # Descrizione
        desc_label = QLabel(t("config.desc.search_limits"))
        desc_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; font-style: italic;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label, 0, 0, 1, 2)

        # Max Risultati
        layout.addWidget(QLabel(t("config.label.max_results")), 1, 0)
        self.similarity_max_results = NoWheelSpinBox()
        self.similarity_max_results.setRange(10, 500)
        self.similarity_max_results.setSingleStep(10)
        self.similarity_max_results.setToolTip(t("config.tooltip.similarity_max"))
        layout.addWidget(self.similarity_max_results, 1, 1)

        group_box.setLayout(layout)
        return group_box

    def create_logging_section(self):
        """Crea sezione configurazione logging"""
        group_box = QGroupBox(t("config.group.logging"))
        layout = QVBoxLayout(group_box)

        # Checkbox debug
        self.debug_checkbox = QCheckBox(t("config.check.debug_messages"))
        self.debug_checkbox.setChecked(True)  # Default: abilitato
        self.debug_checkbox.stateChanged.connect(self.on_debug_setting_changed)
        layout.addWidget(self.debug_checkbox)

        # Info sul logging
        info_label = QLabel(t("config.info.debug_verbose"))
        info_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; font-style: italic; padding: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Checkbox controllo aggiornamenti
        self.check_updates_checkbox = QCheckBox(t("config.check.check_updates"))
        self.check_updates_checkbox.setChecked(True)  # Default: abilitato
        layout.addWidget(self.check_updates_checkbox)

        # Info aggiornamenti
        updates_info = QLabel(t("config.info.check_updates"))
        updates_info.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; font-style: italic; padding: 5px;")
        updates_info.setWordWrap(True)
        layout.addWidget(updates_info)

        return group_box

    # --- Utility Functions ---

    def _select_file(self, line_edit, caption, filter_str):
        """Handler per selezione file"""
        file_name, _ = QFileDialog.getOpenFileName(self, caption, "", filter_str)
        if file_name:
            line_edit.setText(file_name)

    def _select_directory(self, line_edit, caption):
        """Handler per selezione cartella"""
        dir_name = QFileDialog.getExistingDirectory(self, caption, "")
        if dir_name:
            line_edit.setText(dir_name)

    def toggle_bioclip_params(self, enabled):
        """Abilita/disabilita parametri BioCLIP in base allo stato del combo device."""
        if isinstance(enabled, int):
            # Compatibilità con stateChanged (Qt checkbox) — non più usato ma per sicurezza
            enabled = bool(enabled)
        self.bioclip_threshold.setEnabled(enabled)
        self.bioclip_max_tags.setEnabled(enabled)
    
    # --- Load & Save (MODIFICATO) ---

    def load_config(self):
        """
        Carica TUTTA la configurazione.
        Se il file contiene chiavi non rappresentate dalla UI → errore bloccante.
        """
        if not self.config_path.exists():
            raise RuntimeError("File di configurazione mancante")

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)

            if not isinstance(self.config, dict):
                raise ValueError("Configurazione non valida (root non è una mappa)")

            # --------------------------------------------------
            # PATHS
            # --------------------------------------------------
            paths = self.config['paths']
            self.db_path_edit.setText(paths['database'])
            self.log_dir_edit.setText(paths['log_dir'])
            models_dir_val = self.config.get('models_repository', {}).get('models_dir', 'Models')
            self.models_dir_edit.setText(str(models_dir_val))
            self.temp_cache_edit.setText(paths.get('temp_cache_dir', 'temp_cache'))

            # --------------------------------------------------
            # EMBEDDING / DEVICE PER-MODELLO
            # --------------------------------------------------
            embedding = self.config['embedding']
            models_cfg = embedding.get('models', {})
            for model_key, combo in self.model_device_combos.items():
                model_cfg_entry = models_cfg.get(model_key, {})
                if not model_cfg_entry.get('enabled', True):
                    idx = combo.findData('off')
                else:
                    idx = combo.findData(model_cfg_entry.get('device', 'gpu'))
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            # Rileva VRAM LLM:
            # - con plugin installato: usa config (endpoint + modello configurati)
            # - senza plugin: interroga comunque gli endpoint default per rilevare
            #   qualsiasi LLM esterno attivo che stia occupando VRAM reale
            if self._llm_plugin_installed():
                from device_allocator import detect_llm_vram
                self._llm_vram_info = detect_llm_vram(self.config)
                if self._llm_vram_info['vram_gb'] > 0:
                    src = "API" if self._llm_vram_info['source'] == 'ollama_api' else "stima"
                    self._llm_vram_label.setText(f"~{self._llm_vram_info['vram_gb']:.1f} GB ({src})")
                else:
                    self._llm_vram_label.setText("— (non attivo)")
            else:
                from device_allocator import detect_external_llm_vram
                self._llm_vram_info = detect_external_llm_vram(self.config)

            self._update_vram_budget()
            # Nasconde messaggio restart dopo load (non è un cambio utente)
            if hasattr(self, '_device_restart_label'):
                self._device_restart_label.setVisible(False)

            models = embedding['models']

            # DINOv2
            dino = models['dinov2']
            self.dinov2_model_name.setText(dino['model_name'])
            self.dinov2_similarity_threshold.setValue(dino['similarity_threshold'])

            # CLIP
            clip = models['clip']
            self.clip_model_name.setText(clip['model_name'])

            # BioCLIP
            bioclip = models['bioclip']
            self.bioclip_threshold.setValue(bioclip['threshold'])
            self.bioclip_max_tags.setValue(bioclip['max_tags'])
            bioclip_combo = self.model_device_combos.get('bioclip')
            bioclip_on = bioclip_combo.currentData() != 'off' if bioclip_combo else bioclip.get('enabled', True)
            self.toggle_bioclip_params(bioclip_on)

            # LLM Vision
            llm = models['llm_vision']
            backend = llm.get('backend', 'ollama')
            if backend == 'lmstudio':
                self.llm_radio_lmstudio.setChecked(True)
            else:
                self.llm_radio_ollama.setChecked(True)
            self.llm_vision_endpoint.setText(llm['endpoint'])
            self.llm_vision_model.setCurrentText(llm['model'])
            self.llm_vision_timeout.setValue(llm['timeout'])
            # Toggle attivo/non attivo
            _llm_on = llm.get('enabled', True)
            _idx_llm = self.llm_enabled_combo.findData('on' if _llm_on else 'off')
            if _idx_llm >= 0:
                self.llm_enabled_combo.setCurrentIndex(_idx_llm)
            # Carica automaticamente la lista modelli dal backend configurato
            self._load_llm_models()

            # Lingua output LLM
            llm_lang = self.config.get('ui', {}).get('llm_output_language', 'it')
            idx = self.llm_output_lang_combo.findData(llm_lang)
            if idx >= 0:
                self.llm_output_lang_combo.setCurrentIndex(idx)

            # Parametri generation LLM
            gen_params = llm.get('generation', {})
            self.llm_temperature.setValue(gen_params.get('temperature', 0.2))
            self.llm_top_k.setValue(gen_params.get('top_k', 20))
            self.llm_top_p.setValue(gen_params.get('top_p', 0.8))
            self.llm_num_ctx.setValue(gen_params.get('num_ctx', 2048))
            self.llm_num_batch.setValue(gen_params.get('num_batch', 1024))
            self.llm_keep_alive.setChecked(gen_params.get('keep_alive', -1) == -1)

            # --------------------------------------------------
            # IMAGE PROCESSING
            # --------------------------------------------------
            img = self.config['image_processing']

            # Supported formats (se presente nel config)
            if 'supported_formats' in img:
                formats_text = '\n'.join(img['supported_formats'])
                self.supported_formats_text.setPlainText(formats_text)
            else:
                # Fallback per config senza supported_formats
                self.set_extended_formats()

            # --------------------------------------------------
            # IMAGE OPTIMIZATION
            # --------------------------------------------------
            profiles = self.config['image_optimization']['profiles']
            for key, widgets in self.profile_widgets.items():
                profile = profiles[key]
                widgets['size'].setValue(profile['target_size'])
                widgets['quality'].setValue(profile['quality'])
                widgets['method'].setCurrentText(profile['method'])
                widgets['resampling'].setCurrentText(profile['resampling'])

            # --------------------------------------------------
            # SEARCH
            # --------------------------------------------------
            search = self.config['search']
            self.fuzzy_enabled_checkbox.setChecked(search['fuzzy_enabled'])
            self.semantic_threshold_spin.setValue(search['semantic_threshold'])

            # --------------------------------------------------
            # SIMILARITY
            # --------------------------------------------------
            self.similarity_max_results.setValue(self.config['similarity']['max_results'])

            # --------------------------------------------------
            # EXTERNAL EDITORS
            # --------------------------------------------------
            external_editors = self.config.get('external_editors', {})
            if hasattr(self, 'editor_controls') and len(self.editor_controls) >= 3:
                for i in range(1, 4):
                    editor_key = f'editor_{i}'
                    if editor_key in external_editors:
                        editor_data = external_editors[editor_key]
                        self.editor_controls[i-1]['enabled'].setChecked(editor_data.get('enabled', False))
                        self.editor_controls[i-1]['name'].setText(editor_data.get('name', ''))
                        # Path Windows (es. C:\...) ignorato su Linux/macOS
                        raw_path = editor_data.get('path', '')
                        import re as _re
                        is_windows_path = bool(_re.match(r'^[A-Za-z]:[/\\]', raw_path))
                        safe_path = '' if (is_windows_path and platform.system() != 'Windows') else raw_path
                        self.editor_controls[i-1]['path'].setText(safe_path)
                        self.editor_controls[i-1]['command_args'].setText(editor_data.get('command_args', ''))

            # --------------------------------------------------
            # LOGGING
            # --------------------------------------------------
            self.debug_checkbox.setChecked(self.config['logging']['show_debug'])

            # --------------------------------------------------
            # UPDATES
            # --------------------------------------------------
            self.check_updates_checkbox.setChecked(
                self.config.get('updates', {}).get('check_on_startup', True)
            )

        except KeyError as e:
            raise RuntimeError(f"Configurazione incoerente: chiave mancante {e}")

        except Exception as e:
            raise RuntimeError(f"Errore caricamento configurazione: {e}")

    def _backup_config_file(self):
        """
        Crea un backup versionato del file di configurazione esistente.
        Formato: config_new.yaml_BACKUP_YYYYMMDD_HHMMSS.yaml
        """
        try:
            if not self.config_path.exists():
                return  # Nulla da backuppare

            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            backup_path = self.config_path.with_name(
                f"{self.config_path.name}_BACKUP_{timestamp}.yaml"
            )

            import shutil
            shutil.copy2(self.config_path, backup_path)

        except Exception as e:
            # BACKUP FAILURE = ERRORE BLOCCANTE
            raise RuntimeError(f"Impossibile creare backup configurazione: {e}")

    def set_default_values(self):
        """Imposta valori di default completi"""
        try:
            # Database & Paths
            self.db_path_edit.setText('database/offgallery.sqlite')
            self.log_dir_edit.setText('logs')
            self.models_dir_edit.setText('Models')
            self.temp_cache_edit.setText('temp_cache')
            
            # Device per-modello: auto-ottimizza al reset
            self._on_auto_optimize()
            
            # DINOv2
            self.dinov2_model_name.setText('facebook/dinov2-base')
            self.dinov2_similarity_threshold.setValue(0.25)
            
            # CLIP
            self.clip_model_name.setText('laion/CLIP-ViT-B-32-laion2B-s34B-b79K')

            # BioCLIP
            self.bioclip_threshold.setValue(0.12)
            self.bioclip_max_tags.setValue(5)
            bioclip_combo = self.model_device_combos.get('bioclip')
            bioclip_on = bioclip_combo.currentData() != 'off' if bioclip_combo else True
            self.toggle_bioclip_params(bioclip_on)
            
            # LLM Vision
            self.llm_vision_endpoint.setText('http://localhost:11434')
            self.llm_vision_model.setCurrentText('qwen3.5:4b-q4_K_M')
            self.llm_vision_timeout.setValue(240)

            # Parametri generation LLM
            self.llm_temperature.setValue(0.2)
            self.llm_top_k.setValue(20)
            self.llm_top_p.setValue(0.8)
            self.llm_num_ctx.setValue(2048)
            self.llm_num_batch.setValue(1024)
            self.llm_keep_alive.setChecked(True)

            # Supported Formats (Default: Extended)
            self.set_extended_formats()
            
            # Image Optimization Profiles (valori ottimali)
            profiles_defaults = {
                'llm_vision': {'size': 512, 'quality': 85, 'method': 'preview_optimized', 'resampling': 'LANCZOS'},
                'clip_embedding': {'size': 512, 'quality': 90, 'method': 'high_quality', 'resampling': 'LANCZOS'},
                'dinov2_embedding': {'size': 518, 'quality': 90, 'method': 'high_quality', 'resampling': 'LANCZOS'},
                'bioclip_classification': {'size': 384, 'quality': 90, 'method': 'high_quality', 'resampling': 'LANCZOS'},
                'aesthetic_score': {'size': 336, 'quality': 85, 'method': 'preview_optimized', 'resampling': 'BILINEAR'},
                'ai_processing': {'size': 512, 'quality': 85, 'method': 'preview_optimized', 'resampling': 'LANCZOS'},
            }
            
            for profile_key, defaults in profiles_defaults.items():
                if profile_key in self.profile_widgets:
                    widgets = self.profile_widgets[profile_key]
                    widgets['size'].setValue(defaults['size'])
                    widgets['quality'].setValue(defaults['quality'])
                    widgets['method'].setCurrentText(defaults['method'])
                    widgets['resampling'].setCurrentText(defaults['resampling'])
            
            # Search
            self.fuzzy_enabled_checkbox.setChecked(True)
            self.semantic_threshold_spin.setValue(0.15)
            
            # Similarity (rimane come prima)
            self.similarity_max_results.setValue(20)
            
            # Logging
            self.debug_checkbox.setChecked(True)
            
            # External Editors - Reset a valori vuoti
            if hasattr(self, 'editor_controls') and len(self.editor_controls) >= 3:
                for i in range(3):
                    self.editor_controls[i]['enabled'].setChecked(False)
                    self.editor_controls[i]['name'].setText('')
                    self.editor_controls[i]['path'].setText('')
                    self.editor_controls[i]['command_args'].setText('')
            
        except Exception as e:
            print(f"ERRORE in set_default_values: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(self, 'parent_window') and self.parent_window:
                self.parent_window.log_error(f"Errore setting default values: {e}")
            else:
                print(f"CRITICAL: Cannot set default values: {e}")

    def save_config(self):
        """Salva config completa su file preservando sezioni non gestite"""
        self._backup_config_file()
        try:
            # Database & Paths - PRESERVA input_dir se esiste
            paths_data = {
                'database': self.db_path_edit.text(),
                'log_dir': self.log_dir_edit.text(),
                'temp_cache_dir': self.temp_cache_edit.text().strip() or 'temp_cache',
            }

            # Preserva input_dir se presente (gestito solo da processing_tab)
            if 'paths' in self.config and 'input_dir' in self.config['paths']:
                paths_data['input_dir'] = self.config['paths']['input_dir']

            self.config['paths'] = paths_data

            # models_dir (sotto models_repository)
            if 'models_repository' not in self.config:
                self.config['models_repository'] = {}
            self.config['models_repository']['models_dir'] = self.models_dir_edit.text().strip() or 'Models'
            
            # Embedding (aggiorna solo sezioni gestite dall'UI)
            if 'embedding' not in self.config:
                self.config['embedding'] = {}
            
            self.config['embedding']['enabled'] = True
            # Salva device + enabled per-modello (combo è fonte di verità: OFF = non caricato)
            for model_key, combo in self.model_device_combos.items():
                device_val = combo.currentData()
                node = self.config['embedding'].setdefault('models', {}).setdefault(model_key, {})
                if device_val == 'off':
                    node['enabled'] = False
                else:
                    node['enabled'] = True
                    node['device'] = device_val
            
            if 'models' not in self.config['embedding']:
                self.config['embedding']['models'] = {}
            
            # Aggiorna solo modelli gestiti dall'UI (preserva device per-modello)
            _models = self.config['embedding']['models']

            _models.setdefault('dinov2', {}).update({
                'description': 'Similarità visiva (composizione, texture, forma)',
                'model_name': self.dinov2_model_name.text(),
                'similarity_threshold': self.dinov2_similarity_threshold.value(),
            })

            _models.setdefault('clip', {}).update({
                'description': 'Ricerca semantica (query naturali)',
                'model_name': self.clip_model_name.text(),
            })

            # Quality Scores
            _models.setdefault('aesthetic', {}).update({
                'description': 'Punteggio estetico (qualità artistica)',
                'model_name': 'aesthetic-predictor',
                'returns_score': True,
            })

            # Technical score (MUSIQ) - enabled gestito dal combo device
            _models.setdefault('technical', {})

            _models.setdefault('bioclip', {}).update({
                'description': 'Classificazione flora/fauna TreeOfLife (~450k specie)',
                'threshold': self.bioclip_threshold.value(),
                'max_tags': self.bioclip_max_tags.value(),
            })
            
            _llm_backend = 'lmstudio' if self.llm_radio_lmstudio.isChecked() else 'ollama'
            _models.setdefault('llm_vision', {}).update({
                'description': 'Genera tag, descrizioni e titoli con LLM Vision',
                'enabled': self.llm_enabled_combo.currentData() == 'on',
                'backend': _llm_backend,
                'endpoint': self.llm_vision_endpoint.text(),
                'model': self.llm_vision_model.currentText(),
                'timeout': self.llm_vision_timeout.value(),
                'generation': {
                    'temperature': self.llm_temperature.value(),
                    'top_k': self.llm_top_k.value(),
                    'top_p': self.llm_top_p.value(),
                    'num_ctx': self.llm_num_ctx.value(),
                    'num_batch': self.llm_num_batch.value(),
                    'keep_alive': -1 if self.llm_keep_alive.isChecked() else 300,
                },
            })
            
            # Image Processing
            # Estrae formati dalla text area e li converte in lista
            formats_text = self.supported_formats_text.toPlainText().strip()
            supported_formats = [fmt.strip() for fmt in formats_text.split('\n') if fmt.strip()]
            
            self.config['image_processing'] = {
                'supported_formats': supported_formats,
            }
            
            # Image Optimization
            if 'image_optimization' not in self.config:
                self.config['image_optimization'] = {'enabled': True}
            
            if 'profiles' not in self.config['image_optimization']:
                self.config['image_optimization']['profiles'] = {}
                
            # Salva solo profili gestiti dall'UI
            for profile_key, widgets in self.profile_widgets.items():
                self.config['image_optimization']['profiles'][profile_key] = {
                    'target_size': widgets['size'].value(),
                    'quality': widgets['quality'].value(),
                    'method': widgets['method'].currentText(),
                    'resampling': widgets['resampling'].currentText(),
                    'upscale': False  # Fisso
                }
            
            # Search
            self.config['search'] = {
                'fuzzy_enabled': self.fuzzy_enabled_checkbox.isChecked(),
                'max_results': self.config.get('search', {}).get('max_results', 100),
                'semantic_threshold': self.semantic_threshold_spin.value(),
            }
            
            # Similarity (ricerca similarità)
            self.config['similarity'] = {
                'max_results': self.similarity_max_results.value(),
            }
            
            # External Editors
            self.config['external_editors'] = {}
            if hasattr(self, 'editor_controls') and len(self.editor_controls) >= 3:
                for i in range(1, 4):
                    editor_key = f'editor_{i}'
                    self.config['external_editors'][editor_key] = {
                        'name': self.editor_controls[i-1]['name'].text().strip(),
                        'path': self.editor_controls[i-1]['path'].text().strip(),
                        'command_args': self.editor_controls[i-1]['command_args'].text().strip(),
                        'enabled': self.editor_controls[i-1]['enabled'].isChecked()
                    }
            else:
                # Valori di default se i controlli non sono disponibili
                for i in range(1, 4):
                    editor_key = f'editor_{i}'
                    self.config['external_editors'][editor_key] = {
                        'name': '',
                        'path': '',
                        'command_args': '',
                        'enabled': False
                    }
            
            # Logging
            self.config['logging'] = {
                'show_debug': self.debug_checkbox.isChecked()
            }

            # Updates
            self.config['updates'] = {
                'check_on_startup': self.check_updates_checkbox.isChecked()
            }

            # UI (preserva user_language, aggiorna llm_output_language)
            if 'ui' not in self.config:
                self.config['ui'] = {}
            self.config['ui']['llm_output_language'] = self.llm_output_lang_combo.currentData()
            
            # PRESERVA tutte le altre sezioni esistenti non gestite dall'UI
            
            # Salva
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            
            QMessageBox.information(self, t("config.msg.success_title"), t("config.msg.saved_ok_full"))

            if self.parent_window and hasattr(self.parent_window, 'update_status'):
                self.parent_window.update_status(t("config.msg.saved_ok"))

            self.config_saved.emit(self.config)

        except Exception as e:
            QMessageBox.critical(self, t("config.msg.error_title"), t("config.msg.save_error", error=e))
    
    def get_config(self):
        """Ritorna config corrente"""
        return self.config
    
    def on_debug_setting_changed(self, state):
        """Handler cambio setting debug"""
        try:
            debug_enabled = self.debug_checkbox.isChecked()
            
            # Notifica LogTab del cambio (senza auto-save per evitare spam)
            self.notify_log_tab_config_changed()
            
            # Log del cambio
            status = "abilitati" if debug_enabled else "disabilitati"
            if hasattr(self, 'parent_window') and self.parent_window:
                self.parent_window.log_info(f"Messaggi DEBUG {status} dalla configurazione")
                
        except Exception as e:
            print(f"Errore handler debug setting: {e}")
            # Non crashare per questo
    
    def notify_log_tab_config_changed(self):
        """Notifica la LogTab che la config è cambiata"""
        try:
            if hasattr(self, 'parent_window') and self.parent_window:
                if hasattr(self.parent_window, 'log_tab'):
                    self.parent_window.log_tab.refresh_debug_filter()
        except Exception as e:
            print(f"Errore notifica log tab: {e}")
            # Non fare crash per questo
    
    def reset_to_defaults(self):
        """Reset configurazione ai valori di default"""
        reply = QMessageBox.question(
            self,
            t("config.msg.reset_title"),
            t("config.msg.reset_confirm_full"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Backup della configurazione corrente prima del reset
            self._backup_config_file()

            # Reset a valori di default
            self.set_default_values()

            # Auto-save dopo reset
            self.save_config()

            # Notifica
            QMessageBox.information(self, t("config.msg.reset_done_title"), t("config.msg.reset_done"))
            
            if hasattr(self, 'parent_window') and self.parent_window:
                self.parent_window.log_info("Configurazione resettata ai valori di default")

    def test_llm_connection(self):
        """Testa la connessione all'endpoint LLM attivo (Ollama o LM Studio)."""
        endpoint = self.llm_vision_endpoint.text().strip()
        if not endpoint:
            QMessageBox.warning(self, t("config.msg.endpoint_empty_title"), t("config.msg.endpoint_empty_msg"))
            return

        is_ollama = self.llm_radio_ollama.isChecked()
        provider_name = "Ollama" if is_ollama else "LM Studio"

        try:
            import requests

            self.test_endpoint_btn.setText("⏳")
            self.test_endpoint_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['ambra']};
                    color: {COLORS['grafite_dark']};
                    font-size: 10px;
                    padding: 2px;
                }}
            """)
            self.test_endpoint_btn.repaint()

            # Endpoint di verifica diverso per i due backend
            if is_ollama:
                check_url = f"{endpoint}/api/tags"
            else:
                check_url = f"{endpoint}/v1/models"

            response = requests.get(check_url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if is_ollama:
                    items = data.get('models', [])
                    names = [m.get('name', '?') for m in items[:3]]
                else:
                    items = data.get('data', [])
                    names = [m.get('id', '?') for m in items[:3]]
                models_text = ', '.join(names) if names else t("config.msg.no_models")

                self.test_endpoint_btn.setText("✓")
                self.test_endpoint_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {COLORS['verde']};
                        color: white;
                        font-size: 10px;
                        padding: 2px;
                    }}
                """)
                QMessageBox.information(
                    self,
                    t("config.msg.connection_ok_title"),
                    t("config.msg.connection_ok_detail", provider=provider_name, models=models_text)
                )
            else:
                raise requests.RequestException(f"Status code: {response.status_code}")

        except Exception as e:
            self.test_endpoint_btn.setText("✗")
            self.test_endpoint_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['rosso']};
                    color: white;
                    font-size: 10px;
                    padding: 2px;
                }}
            """)
            QMessageBox.warning(
                self,
                t("config.msg.connection_fail_title"),
                t("config.msg.connection_fail_detail", provider=provider_name, error=str(e))
            )

        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, self.reset_test_button)

    # Manteniamo il vecchio nome come alias per compatibilità con eventuali riferimenti esterni
    def test_ollama_connection(self):
        self.test_llm_connection()
    
    def reset_test_button(self):
        """Reset aspetto bottone test endpoint"""
        self.test_endpoint_btn.setText("🔍 Test")
        self.test_endpoint_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['blu_petrolio_light']};
                font-size: 10px;
                padding: 2px;
            }}
        """)

    def validate_dinov2_threshold(self, value):
        """Validazione real-time soglia DINOv2 con feedback visivo"""
        if value < 0.25:
            # Troppo basso - border rosso
            self.dinov2_similarity_threshold.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 2px solid {COLORS['rosso']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.dinov2_similarity_threshold.setToolTip(t("config.tooltip.dinov2_low"))
        elif value > 0.8:
            # Troppo alto - border ambra
            self.dinov2_similarity_threshold.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 2px solid {COLORS['ambra']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.dinov2_similarity_threshold.setToolTip(t("config.tooltip.dinov2_high"))
        else:
            # Valore OK - border normale
            self.dinov2_similarity_threshold.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 1px solid {COLORS['blu_petrolio_light']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.dinov2_similarity_threshold.setToolTip(t("config.tooltip.dinov2_ok"))

    def validate_semantic_threshold(self, value):
        """Validazione real-time soglia ricerca semantica con feedback visivo"""
        if value < 0.10:
            # Troppo basso - troppi risultati
            self.semantic_threshold_spin.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 2px solid {COLORS['rosso']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.semantic_threshold_spin.setToolTip(t("config.tooltip.semantic_low"))
        elif value > 0.30:
            # Troppo alto - pochi risultati
            self.semantic_threshold_spin.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 2px solid {COLORS['ambra']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.semantic_threshold_spin.setToolTip(t("config.tooltip.semantic_high"))
        else:
            # Valore OK
            self.semantic_threshold_spin.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 1px solid {COLORS['blu_petrolio_light']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.semantic_threshold_spin.setToolTip(t("config.tooltip.semantic_ok"))

    def set_basic_formats(self):
        """Imposta formati basic (JPEG, PNG, TIFF)"""
        basic_formats = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"]
        self.supported_formats_text.setPlainText("\n".join(basic_formats))

    def set_extended_formats(self):
        """Imposta formati estesi (Basic + RAW comuni)"""
        extended_formats = [
            ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".heic",
            ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf", ".rw2", ".dng"
        ]
        self.supported_formats_text.setPlainText("\n".join(extended_formats))

    def set_all_formats(self):
        """Imposta tutti i formati supportati"""
        all_formats = [
            ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".heic",
            ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", 
            ".orf", ".rw2", ".raw", ".pef", ".ptx", ".dng", ".rwl", ".3fr", ".iiq", ".x3f"
        ]
        self.supported_formats_text.setPlainText("\n".join(all_formats))

    def validate_editor_path(self, path_text, editor_index):
        """Valida il percorso dell'editor esterno"""
        if not path_text.strip():
            return
            
        path = Path(path_text.strip())
        path_edit = self.editor_controls[editor_index - 1]['path']
        
        import os
        if platform.system() == "Windows":
            is_valid_exec = path.exists() and path.is_file() and path.suffix.lower() == '.exe'
        else:
            is_valid_exec = path.exists() and path.is_file() and os.access(str(path), os.X_OK)

        if is_valid_exec:
            # Percorso valido
            path_edit.setStyleSheet(f"""
                QLineEdit {{
                    border: 2px solid {COLORS['verde']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            path_edit.setToolTip(t("config.tooltip.path_valid"))
        else:
            # Percorso non valido
            path_edit.setStyleSheet(f"""
                QLineEdit {{
                    border: 2px solid {COLORS['rosso']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            if platform.system() == "Windows":
                path_edit.setToolTip(t("config.tooltip.path_invalid_exe"))
            else:
                path_edit.setToolTip(t("config.tooltip.path_invalid"))

    def browse_editor_path(self, editor_index):
        """Apri dialog per selezionare editor esterno"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Seleziona Editor {editor_index}",
            "",
            "Eseguibili (*.exe);;Tutti i file (*.*)" if platform.system() == "Windows"
            else "Tutti i file (*)"
        )
        
        if file_path:
            self.editor_controls[editor_index - 1]['path'].setText(file_path)

