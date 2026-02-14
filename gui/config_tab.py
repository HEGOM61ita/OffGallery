"""
Config Tab - Configurazione applicazione
Struttura modulare basata su config_new.yaml
Versione 2.0 - 
"""

import yaml
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QCheckBox, QSpinBox,
    QDoubleSpinBox, QFileDialog, QMessageBox, QScrollArea,
    QGridLayout, QTextEdit, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal

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
        info_label = QLabel("ℹ️  Embedding CLIP e DINOv2 sempre attivi (necessari per ricerca semantica e similarità)")
        info_label.setStyleSheet(f"color: {COLORS['ambra']}; font-size: 11px; padding: 10px; background-color: {COLORS['grafite_dark']}; border-radius: 4px;")
        info_label.setWordWrap(True)
        scroll_layout.addWidget(info_label)
        
        # Device globale
        scroll_layout.addWidget(self.create_device_section())
        
        # Gruppo Embedding Models
        embedding_group = QGroupBox("🧠 Modelli di Embedding (Core)")
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
        ai_group = QGroupBox("🤖 Modelli di Classificazione e Analisi")
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
        ai_layout.addWidget(self.create_quality_scores_section())
        ai_layout.addWidget(self.create_bioclip_section())
        ai_layout.addWidget(self.create_llm_vision_section())
        ai_group.setLayout(ai_layout)
        scroll_layout.addWidget(ai_group)
        
        # Gruppo Image Processing & Performance
        processing_group = QGroupBox("⚡ Elaborazione Immagini & Performance")
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
        search_group = QGroupBox("🔍 Ricerca & Metadati")
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
        search_layout.addWidget(self.create_metadata_section())
        search_layout.addWidget(self.create_similarity_section())
        search_group.setLayout(search_layout)
        scroll_layout.addWidget(search_group)
        
        scroll_layout.addWidget(self.create_logging_section())
        
        # Bottoni Reset e Save
        buttons_layout = QHBoxLayout()
        
        # Bottone Reset
        reset_button = QPushButton("🔄 Reset Default")
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
        save_button = QPushButton("💾 Salva Configurazione")
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
        group_box = QGroupBox("📁 Percorsi & Database")
        group_box.setObjectName("PathsSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#PathsSection {{
                border: 2px solid {COLORS['blu_petrolio']};
            }}
        """)

        layout = QGridLayout()

        # Database Path
        layout.addWidget(QLabel("Database:"), 0, 0)
        self.db_path_edit = QLineEdit()
        self.db_path_edit.setToolTip("Percorso file database SQLite")
        self.db_path_edit.setPlaceholderText("Es: database/offgallery.sqlite")
        layout.addWidget(self.db_path_edit, 0, 1)
        
        db_browse_btn = QPushButton("📂")
        db_browse_btn.setFixedWidth(40)
        db_browse_btn.clicked.connect(lambda: self._select_file(self.db_path_edit, "Seleziona Database", "Database SQLite (*.sqlite)"))
        layout.addWidget(db_browse_btn, 0, 2)

        # Log Directory
        layout.addWidget(QLabel("Logs:"), 1, 0)
        self.log_dir_edit = QLineEdit()
        self.log_dir_edit.setToolTip("Directory salvataggio file log")
        self.log_dir_edit.setPlaceholderText("Es: logs")
        layout.addWidget(self.log_dir_edit, 1, 1)

        log_browse_btn = QPushButton("📂")
        log_browse_btn.setFixedWidth(40)
        log_browse_btn.clicked.connect(lambda: self._select_directory(self.log_dir_edit, "Seleziona Directory Log"))
        layout.addWidget(log_browse_btn, 1, 2)

        group_box.setLayout(layout)
        return group_box
    
    def create_external_editors_section(self):
        """Crea sezione configurazione editor esterni"""
        group_box = QGroupBox("🎨 Editor Esterni")
        group_box.setObjectName("ExternalEditorsSection")
        
        layout = QVBoxLayout()
        
        info_label = QLabel("Configura fino a 3 editor esterni per modificare le immagini dalla gallery")
        info_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 11px; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Grid layout per i 3 editor
        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(1, 1)  # Nome editor si espande
        grid_layout.setColumnStretch(2, 2)  # Percorso si espande di più
        
        # Header
        grid_layout.addWidget(QLabel("Attivo"), 0, 0)
        grid_layout.addWidget(QLabel("Nome Editor"), 0, 1)
        grid_layout.addWidget(QLabel("Percorso Eseguibile"), 0, 2)
        grid_layout.addWidget(QLabel("Argomenti Comando"), 0, 3)
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
            path_edit.setPlaceholderText("Seleziona file .exe...")
            path_edit.setObjectName(f"editor_{i}_path")
            path_edit.textChanged.connect(lambda text, idx=i: self.validate_editor_path(text, idx))
            
            # Argomenti comando (NUOVO)
            args_edit = QLineEdit()
            args_edit.setPlaceholderText("Argomenti opzionali (es: -direct)")
            args_edit.setObjectName(f"editor_{i}_command_args")
            args_edit.setMaxLength(100)
            
            # Pulsante sfoglia
            browse_btn = QPushButton("📁")
            browse_btn.setFixedSize(30, 25)
            browse_btn.setToolTip("Seleziona editor")
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
        """Crea sezione device elaborazione (NUOVO)"""
        group_box = QGroupBox("⚡ Device Elaborazione")
        group_box.setObjectName("DeviceSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#DeviceSection {{
                border: 2px solid {COLORS['ambra']};
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Dropdown device
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("Seleziona device:"))
        
        self.device_combo = NoWheelComboBox()
        self.device_combo.addItem("Auto-detect (consigliato)", "auto")
        self.device_combo.addItem("Forza GPU (CUDA)", "cuda")
        self.device_combo.addItem("Forza CPU", "cpu")
        self.device_combo.setToolTip(
            "Auto-detect: rileva automaticamente GPU e usa CPU come fallback\n"
            "Forza GPU: usa solo GPU (fallback CPU se non disponibile)\n"
            "Forza CPU: disabilita completamente GPU"
        )
        self.device_combo.currentIndexChanged.connect(self._update_gpu_info)
        device_layout.addWidget(self.device_combo)
        device_layout.addStretch()
        
        layout.addLayout(device_layout)
        
        # Label info GPU dinamica
        self.gpu_info_label = QLabel("Rilevamento GPU...")
        self.gpu_info_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; padding: 5px;")
        self.gpu_info_label.setWordWrap(True)
        layout.addWidget(self.gpu_info_label)
        
        # Aggiorna info al caricamento
        self._update_gpu_info()
        
        group_box.setLayout(layout)
        return group_box
    
    def _update_gpu_info(self):
        """Aggiorna label info GPU in base a disponibilità"""
        try:
            import torch
            
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                self.gpu_info_label.setText(f"✅ GPU disponibile: {gpu_name} ({gpu_mem:.1f} GB VRAM)")
                self.gpu_info_label.setStyleSheet(f"color: {COLORS['verde']}; font-weight: bold; font-size: 10px; padding: 5px;")
            else:
                self.gpu_info_label.setText("⚠️ Nessuna GPU rilevata - verrà usata CPU (elaborazione più lenta)")
                self.gpu_info_label.setStyleSheet(f"color: {COLORS['ambra']}; font-size: 10px; padding: 5px;")
        except ImportError:
            self.gpu_info_label.setText("❌ PyTorch non installato - impossibile rilevare GPU")
            self.gpu_info_label.setStyleSheet(f"color: {COLORS['rosso']}; font-size: 10px; padding: 5px;")
        except Exception as e:
            self.gpu_info_label.setText(f"⚠️ Errore rilevamento GPU: {e}")
            self.gpu_info_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; padding: 5px;")

    def create_dinov2_section(self):
        """Crea sezione configurazione DINOv2 (MODIFICATO - rimosso checkbox enabled e device)"""
        group_box = QGroupBox("🔍 Modello DINOv2 (Similarità Visiva)")
        group_box.setObjectName("DINOv2Section")
        
        group_box.setStyleSheet(f"""
            QGroupBox#DINOv2Section {{
                border: 2px solid {COLORS['blu_petrolio_dark']};
            }}
        """)
        
        layout = QGridLayout()

        # Model Name
        layout.addWidget(QLabel("Nome Modello:"), 0, 0)
        self.dinov2_model_name = QLineEdit()
        self.dinov2_model_name.setToolTip("Modello Hugging Face per embedding visuali\nDefault: facebook/dinov2-base")
        layout.addWidget(self.dinov2_model_name, 0, 1)

        # Dimension
        layout.addWidget(QLabel("Dimensione Embedding:"), 1, 0)
        self.dinov2_dimension = NoWheelSpinBox()
        self.dinov2_dimension.setRange(64, 1024)
        self.dinov2_dimension.setSingleStep(64)
        self.dinov2_dimension.setToolTip("Dimensione vettore embedding\nDINOv2-base: 768, DINOv2-small: 384")
        layout.addWidget(self.dinov2_dimension, 1, 1)
        
        # Soglia Similarità (NUOVO)
        layout.addWidget(QLabel("Soglia Similarità (Find Similar):"), 2, 0)
        self.dinov2_similarity_threshold = NoWheelDoubleSpinBox()
        self.dinov2_similarity_threshold.setRange(0.0, 1.0)
        self.dinov2_similarity_threshold.setSingleStep(0.05)
        self.dinov2_similarity_threshold.setDecimals(2)
        self.dinov2_similarity_threshold.setToolTip("Soglia per ricerca immagini simili (0.0-1.0, default 0.7)")
        self.dinov2_similarity_threshold.valueChanged.connect(self.validate_dinov2_threshold)
        layout.addWidget(self.dinov2_similarity_threshold, 2, 1)

        group_box.setLayout(layout)
        return group_box
        
    def create_clip_section(self):
        """Crea sezione configurazione CLIP (MODIFICATO - rimosso checkbox enabled)"""
        group_box = QGroupBox("🔎 Modello CLIP (Ricerca Semantica)")
        group_box.setObjectName("CLIPSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#CLIPSection {{
                border: 2px solid {COLORS['blu_petrolio_light']};
            }}
        """)
        
        layout = QGridLayout()

        # Model Name
        layout.addWidget(QLabel("Nome Modello:"), 0, 0)
        self.clip_model_name = QLineEdit()
        self.clip_model_name.setToolTip("Modello CLIP per ricerca semantica\nDefault: laion/CLIP-ViT-B-32-laion2B-s34B-b79K")
        layout.addWidget(self.clip_model_name, 0, 1)

        # Dimension
        layout.addWidget(QLabel("Dimensione Embedding:"), 1, 0)
        self.clip_dimension = NoWheelSpinBox()
        self.clip_dimension.setRange(64, 1024)
        self.clip_dimension.setSingleStep(64)
        self.clip_dimension.setToolTip("Dimensione vettore embedding\nCLIP-ViT-B-32: 512, CLIP-ViT-L-14: 768")
        layout.addWidget(self.clip_dimension, 1, 1)
        self.clip_dimension.setSingleStep(64)
        layout.addWidget(self.clip_dimension, 1, 1)
        
        group_box.setLayout(layout)
        return group_box

    def create_quality_scores_section(self):
        """Crea sezione configurazione Quality Scores (Aesthetic + Technical)"""
        group_box = QGroupBox("⭐ Quality Scores")
        group_box.setObjectName("QualityScoresSection")

        group_box.setStyleSheet(f"""
            QGroupBox#QualityScoresSection {{
                border: 2px solid {COLORS['ambra']};
            }}
        """)

        layout = QGridLayout()

        # Abilita Aesthetic Score
        self.aesthetic_enabled = QCheckBox("Genera Aesthetic Score (qualità artistica)")
        self.aesthetic_enabled.setToolTip("Punteggio estetico 0-10 basato su composizione e appeal visivo")
        layout.addWidget(self.aesthetic_enabled, 0, 0, 1, 2)

        # Abilita Technical Score (BRISQUE)
        self.technical_enabled = QCheckBox("Genera Technical Score (qualità tecnica)")
        self.technical_enabled.setToolTip("Punteggio tecnico 0-100 basato su nitidezza, rumore, artefatti (BRISQUE)")
        layout.addWidget(self.technical_enabled, 1, 0, 1, 2)

        group_box.setLayout(layout)
        return group_box

    def create_bioclip_section(self):
        """Crea sezione configurazione BioCLIP (MODIFICATO - testo checkbox)"""
        group_box = QGroupBox("🌿 BioCLIP Tagging")
        group_box.setObjectName("BioCLIPSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#BioCLIPSection {{
                border: 2px solid {COLORS['verde']};
            }}
        """)
        
        layout = QGridLayout()

        # Abilita BioCLIP (MODIFICATO)
        self.bioclip_enabled = QCheckBox("Usa BioCLIP nel processing batch (manuale sempre disponibile)")
        self.bioclip_enabled.setToolTip("Se disabilitato, BioCLIP utilizzabile solo manualmente dalla Gallery")
        self.bioclip_enabled.stateChanged.connect(self.toggle_bioclip_params)
        layout.addWidget(self.bioclip_enabled, 0, 0, 1, 2)

        # Soglia
        layout.addWidget(QLabel("Soglia di Rilevanza:"), 1, 0)
        self.bioclip_threshold = NoWheelDoubleSpinBox()
        self.bioclip_threshold.setRange(0.01, 1.0)
        self.bioclip_threshold.setSingleStep(0.01)
        self.bioclip_threshold.setDecimals(3)
        layout.addWidget(self.bioclip_threshold, 1, 1)

        # Max Tag
        layout.addWidget(QLabel("Max Tag per Immagine:"), 2, 0)
        self.bioclip_max_tags = NoWheelSpinBox()
        self.bioclip_max_tags.setRange(1, 20)
        layout.addWidget(self.bioclip_max_tags, 2, 1)
        
        # Inizializza stato
        self.toggle_bioclip_params(False)  # FIXED: inizializza come disabilitato

        group_box.setLayout(layout)
        return group_box

    def create_llm_vision_section(self):
        """Crea sezione configurazione LLM Vision con controlli granulari per generazione"""
        group_box = QGroupBox("🤖 Generazione AI (Tags/Descrizione/Titolo)")
        group_box.setObjectName("LLMVisionSection")

        group_box.setStyleSheet(f"""
            QGroupBox#LLMVisionSection {{
                border: 2px solid {COLORS['ambra']};
            }}
        """)

        layout = QVBoxLayout()

        # --- SEZIONE CONNESSIONE ---
        conn_layout = QGridLayout()

        # Endpoint con validazione
        endpoint_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Endpoint (Ollama/API):"), 0, 0)
        self.llm_vision_endpoint = QLineEdit()
        endpoint_layout.addWidget(self.llm_vision_endpoint)

        # Bottone test connessione
        self.test_endpoint_btn = QPushButton("🔍 Test")
        self.test_endpoint_btn.setFixedWidth(60)
        self.test_endpoint_btn.clicked.connect(self.test_ollama_connection)
        self.test_endpoint_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['blu_petrolio_light']};
                font-size: 10px;
                padding: 2px;
            }}
        """)
        endpoint_layout.addWidget(self.test_endpoint_btn)

        endpoint_widget = QWidget()
        endpoint_widget.setLayout(endpoint_layout)
        conn_layout.addWidget(endpoint_widget, 0, 1)

        # Modello LLM
        conn_layout.addWidget(QLabel("Modello LLM:"), 1, 0)
        self.llm_vision_model = QLineEdit()
        conn_layout.addWidget(self.llm_vision_model, 1, 1)

        # Timeout
        conn_layout.addWidget(QLabel("Timeout (secondi):"), 2, 0)
        self.llm_vision_timeout = NoWheelSpinBox()
        self.llm_vision_timeout.setRange(30, 600)
        self.llm_vision_timeout.setSingleStep(30)
        conn_layout.addWidget(self.llm_vision_timeout, 2, 1)

        layout.addLayout(conn_layout)

        # --- SEZIONE GENERAZIONE AUTO-IMPORT ---
        gen_group = QGroupBox("⚙️ Generazione durante Import Batch")
        gen_group.setStyleSheet(f"QGroupBox {{ color: {COLORS['grigio_medio']}; font-size: 12px; }}")
        gen_layout = QGridLayout()

        # Header colonne
        header_gen = QLabel("Genera")
        header_gen.setStyleSheet(f"font-weight: bold; color: {COLORS['ambra']};")
        gen_layout.addWidget(header_gen, 0, 0)

        header_overwrite = QLabel("Sovrascrivi esistente")
        header_overwrite.setStyleSheet(f"font-weight: bold; color: {COLORS['ambra']};")
        gen_layout.addWidget(header_overwrite, 0, 1)

        header_params = QLabel("Parametri")
        header_params.setStyleSheet(f"font-weight: bold; color: {COLORS['ambra']};")
        gen_layout.addWidget(header_params, 0, 2, 1, 2)

        # --- TAGS ---
        self.gen_tags_check = QCheckBox("Tags")
        self.gen_tags_check.setToolTip("Genera tag automaticamente durante l'import batch")
        self.gen_tags_check.stateChanged.connect(self._toggle_tags_controls)
        gen_layout.addWidget(self.gen_tags_check, 1, 0)

        self.gen_tags_overwrite = QCheckBox()
        self.gen_tags_overwrite.setToolTip("Se attivo, sovrascrive i tag già presenti in XMP/Embedded")
        gen_layout.addWidget(self.gen_tags_overwrite, 1, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        gen_layout.addWidget(QLabel("Max Tags:"), 1, 2)
        self.llm_vision_max_tags = NoWheelSpinBox()
        self.llm_vision_max_tags.setRange(1, 20)
        self.llm_vision_max_tags.setValue(10)
        self.llm_vision_max_tags.setToolTip("Numero massimo di tag da generare")
        gen_layout.addWidget(self.llm_vision_max_tags, 1, 3)

        # --- DESCRIZIONE ---
        self.gen_desc_check = QCheckBox("Descrizione")
        self.gen_desc_check.setToolTip("Genera descrizione automaticamente durante l'import batch")
        self.gen_desc_check.stateChanged.connect(self._toggle_desc_controls)
        gen_layout.addWidget(self.gen_desc_check, 2, 0)

        self.gen_desc_overwrite = QCheckBox()
        self.gen_desc_overwrite.setToolTip("Se attivo, sovrascrive la descrizione già presente in XMP/Embedded")
        gen_layout.addWidget(self.gen_desc_overwrite, 2, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        gen_layout.addWidget(QLabel("Max Parole:"), 2, 2)
        self.llm_vision_max_words = NoWheelSpinBox()
        self.llm_vision_max_words.setRange(20, 300)
        self.llm_vision_max_words.setValue(100)
        self.llm_vision_max_words.setToolTip("Numero massimo di parole per descrizione")
        gen_layout.addWidget(self.llm_vision_max_words, 2, 3)

        # --- TITOLO ---
        self.gen_title_check = QCheckBox("Titolo")
        self.gen_title_check.setToolTip("Genera titolo automaticamente durante l'import batch")
        self.gen_title_check.stateChanged.connect(self._toggle_title_controls)
        gen_layout.addWidget(self.gen_title_check, 3, 0)

        self.gen_title_overwrite = QCheckBox()
        self.gen_title_overwrite.setToolTip("Se attivo, sovrascrive il titolo già presente in XMP/Embedded")
        gen_layout.addWidget(self.gen_title_overwrite, 3, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        gen_layout.addWidget(QLabel("Max Parole:"), 3, 2)
        self.llm_vision_max_title_chars = NoWheelSpinBox()
        self.llm_vision_max_title_chars.setRange(1, 10)
        self.llm_vision_max_title_chars.setValue(5)
        self.llm_vision_max_title_chars.setToolTip("Numero massimo di parole per il titolo generato")
        gen_layout.addWidget(self.llm_vision_max_title_chars, 3, 3)

        gen_group.setLayout(gen_layout)
        layout.addWidget(gen_group)

        # --- SEZIONE PARAMETRI LLM AVANZATI ---
        adv_group = QGroupBox("🎛️ Parametri LLM Avanzati")
        adv_group.setStyleSheet(f"QGroupBox {{ color: {COLORS['grigio_medio']}; font-size: 12px; }}")
        adv_group.setCheckable(True)
        adv_group.setChecked(False)
        adv_group.setToolTip("Espandi per modificare temperature, top_k e top_p del modello LLM")
        adv_layout = QGridLayout()

        adv_layout.addWidget(QLabel("Temperature:"), 0, 0)
        self.llm_temperature = NoWheelDoubleSpinBox()
        self.llm_temperature.setRange(0.0, 2.0)
        self.llm_temperature.setSingleStep(0.1)
        self.llm_temperature.setDecimals(2)
        self.llm_temperature.setValue(0.2)
        self.llm_temperature.setToolTip("Valori bassi (0.1-0.3): preciso e ripetibile. Valori alti (0.7+): creativo ma meno prevedibile")
        adv_layout.addWidget(self.llm_temperature, 0, 1)

        adv_layout.addWidget(QLabel("Top-K:"), 0, 2)
        self.llm_top_k = NoWheelSpinBox()
        self.llm_top_k.setRange(1, 100)
        self.llm_top_k.setValue(20)
        self.llm_top_k.setToolTip("Numero di token candidati ad ogni step. Valori bassi = piu' focalizzato")
        adv_layout.addWidget(self.llm_top_k, 0, 3)

        adv_layout.addWidget(QLabel("Top-P:"), 0, 4)
        self.llm_top_p = NoWheelDoubleSpinBox()
        self.llm_top_p.setRange(0.0, 1.0)
        self.llm_top_p.setSingleStep(0.05)
        self.llm_top_p.setDecimals(2)
        self.llm_top_p.setValue(0.8)
        self.llm_top_p.setToolTip("Nucleus sampling. 0.8 = considera l'80%% dei token piu' probabili")
        adv_layout.addWidget(self.llm_top_p, 0, 5)

        adv_layout.addWidget(QLabel("Num Ctx:"), 1, 0)
        self.llm_num_ctx = NoWheelSpinBox()
        self.llm_num_ctx.setRange(512, 32768)
        self.llm_num_ctx.setSingleStep(512)
        self.llm_num_ctx.setValue(2048)
        self.llm_num_ctx.setToolTip("Dimensione finestra di contesto in token. Valori alti = piu' contesto ma piu' RAM")
        adv_layout.addWidget(self.llm_num_ctx, 1, 1)

        adv_layout.addWidget(QLabel("Num Batch:"), 1, 2)
        self.llm_num_batch = NoWheelSpinBox()
        self.llm_num_batch.setRange(128, 4096)
        self.llm_num_batch.setSingleStep(128)
        self.llm_num_batch.setValue(1024)
        self.llm_num_batch.setToolTip("Dimensione batch per elaborazione prompt. Valori alti = piu' veloce ma piu' RAM")
        adv_layout.addWidget(self.llm_num_batch, 1, 3)

        adv_group.setLayout(adv_layout)
        adv_group.toggled.connect(lambda checked: [w.setVisible(checked) for w in [self.llm_temperature, self.llm_top_k, self.llm_top_p, self.llm_num_ctx, self.llm_num_batch]])
        layout.addWidget(adv_group)

        # Info
        info_label = QLabel("ℹ️ Quando 'Sovrascrivi' è disattivo, i dati esistenti in XMP/Embedded vengono preservati")
        info_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; font-style: italic; padding: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Inizializza stato controlli
        self._toggle_tags_controls(False)
        self._toggle_desc_controls(False)
        self._toggle_title_controls(False)

        group_box.setLayout(layout)
        return group_box

    def _toggle_tags_controls(self, state):
        """Abilita/disabilita controlli tag"""
        enabled = self.gen_tags_check.isChecked()
        self.gen_tags_overwrite.setEnabled(enabled)
        self.llm_vision_max_tags.setEnabled(enabled)

    def _toggle_desc_controls(self, state):
        """Abilita/disabilita controlli descrizione"""
        enabled = self.gen_desc_check.isChecked()
        self.gen_desc_overwrite.setEnabled(enabled)
        self.llm_vision_max_words.setEnabled(enabled)

    def _toggle_title_controls(self, state):
        """Abilita/disabilita controlli titolo"""
        enabled = self.gen_title_check.isChecked()
        self.gen_title_overwrite.setEnabled(enabled)
        self.llm_vision_max_title_chars.setEnabled(enabled)

    def create_image_processing_section(self):
        """Crea sezione configurazione elaborazione immagini"""
        group_box = QGroupBox("🖼️ Elaborazione Immagini")
        group_box.setObjectName("ImageProcessingSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#ImageProcessingSection {{
                border: 2px solid {COLORS['ambra_light']};
            }}
        """)
        
        layout = QGridLayout()

        # Row 0: Convert RAW + JPEG Quality
        self.convert_raw_checkbox = QCheckBox("Converti RAW")
        self.convert_raw_checkbox.setToolTip("Converte automaticamente file RAW in JPEG durante processing")
        layout.addWidget(self.convert_raw_checkbox, 0, 0)
        
        layout.addWidget(QLabel("Qualità JPEG:"), 0, 1)
        self.jpeg_quality_spin = NoWheelSpinBox()
        self.jpeg_quality_spin.setRange(50, 100)
        self.jpeg_quality_spin.setSuffix("%")
        self.jpeg_quality_spin.setToolTip("Qualità compressione JPEG (50-100%)")
        layout.addWidget(self.jpeg_quality_spin, 0, 2)

        # Row 1: Max Dimension + Max Workers  
        layout.addWidget(QLabel("Max Dimensione:"), 1, 0)
        self.max_dimension_spin = NoWheelSpinBox()
        self.max_dimension_spin.setRange(512, 8192)
        self.max_dimension_spin.setSingleStep(256)
        self.max_dimension_spin.setSuffix("px")
        self.max_dimension_spin.setToolTip("Dimensione massima per resize automatico")
        layout.addWidget(self.max_dimension_spin, 1, 1)
        
        layout.addWidget(QLabel("Max Workers:"), 1, 2)
        self.max_workers_spin = NoWheelSpinBox()
        self.max_workers_spin.setRange(1, 16)
        self.max_workers_spin.setToolTip("Thread paralleli per elaborazione")
        layout.addWidget(self.max_workers_spin, 1, 3)

        # Row 2: Resize Images
        self.resize_images_checkbox = QCheckBox("Resize Automatico")
        self.resize_images_checkbox.setToolTip("Ridimensiona automaticamente immagini troppo grandi")
        layout.addWidget(self.resize_images_checkbox, 2, 0, 1, 2)

        # RAW Processing Sub-section
        raw_group = QGroupBox("⚙️ Processing RAW")
        raw_group.setStyleSheet(f"QGroupBox {{ color: {COLORS['grigio_medio']}; font-size: 12px; }}")
        raw_layout = QGridLayout()
        
        # Row 0: Cache enabled + Cache dir
        self.cache_thumbnails_checkbox = QCheckBox("Cache Thumb")
        self.cache_thumbnails_checkbox.setToolTip("Salva thumbnails in cache per velocizzare operazioni")
        raw_layout.addWidget(self.cache_thumbnails_checkbox, 0, 0)
        
        raw_layout.addWidget(QLabel("Dir Cache:"), 0, 1)
        self.cache_dir_edit = QLineEdit()
        self.cache_dir_edit.setToolTip("Directory cache thumbnails RAW")
        self.cache_dir_edit.setPlaceholderText("thumbnails_cache")
        raw_layout.addWidget(self.cache_dir_edit, 0, 2)
        
        # Row 1: Timeout + Fallback size
        raw_layout.addWidget(QLabel("Timeout (s):"), 1, 0)
        self.processing_timeout_spin = NoWheelSpinBox()
        self.processing_timeout_spin.setRange(10, 300)
        self.processing_timeout_spin.setToolTip("Timeout processing RAW file")
        raw_layout.addWidget(self.processing_timeout_spin, 1, 1)
        
        raw_layout.addWidget(QLabel("Fallback Size:"), 1, 2)
        self.fallback_size_spin = NoWheelSpinBox()
        self.fallback_size_spin.setRange(256, 2048)
        self.fallback_size_spin.setSingleStep(128)
        self.fallback_size_spin.setSuffix("px")
        raw_layout.addWidget(self.fallback_size_spin, 1, 3)
        
        # Row 2: Thumbnail strategy + Fallback thumbnail
        raw_layout.addWidget(QLabel("Strategia:"), 2, 0)
        self.thumbnail_strategy_combo = NoWheelComboBox()
        self.thumbnail_strategy_combo.addItems(["embedded", "preview", "full"])
        self.thumbnail_strategy_combo.setToolTip("embedded=thumbnail integrato, preview=anteprima, full=immagine completa")
        raw_layout.addWidget(self.thumbnail_strategy_combo, 2, 1)
        
        self.fallback_thumbnail_checkbox = QCheckBox("Fallback Thumb")
        self.fallback_thumbnail_checkbox.setToolTip("Usa thumbnail di fallback se estrazione fallisce")
        raw_layout.addWidget(self.fallback_thumbnail_checkbox, 2, 2)
        
        raw_group.setLayout(raw_layout)
        layout.addWidget(raw_group, 3, 0, 1, 4)

        # Formati Supportati Sub-section
        formats_group = QGroupBox("📄 Formati File Supportati")
        formats_group.setStyleSheet(f"QGroupBox {{ color: {COLORS['grigio_medio']}; font-size: 12px; }}")
        formats_layout = QVBoxLayout()
        
        # Info
        info_label = QLabel("⚠️ Modifica solo se conosci i formati supportati dal sistema")
        info_label.setStyleSheet(f"color: {COLORS['ambra']}; font-size: 10px; font-style: italic;")
        formats_layout.addWidget(info_label)
        
        # Text area per formati (uno per riga)
        self.supported_formats_text = QTextEdit()
        self.supported_formats_text.setMaximumHeight(120)
        self.supported_formats_text.setToolTip("Un formato per riga (es: .jpg, .png, .cr2)")
        formats_layout.addWidget(self.supported_formats_text)
        
        # Preset buttons per formati comuni
        preset_layout = QHBoxLayout()
        
        preset_basic_btn = QPushButton("📷 Basic")
        preset_basic_btn.setToolTip("Solo JPEG, PNG, TIFF")
        preset_basic_btn.clicked.connect(self.set_basic_formats)
        preset_layout.addWidget(preset_basic_btn)
        
        preset_extended_btn = QPushButton("🎯 Extended") 
        preset_extended_btn.setToolTip("Include RAW comuni (Canon, Nikon, Sony)")
        preset_extended_btn.clicked.connect(self.set_extended_formats)
        preset_layout.addWidget(preset_extended_btn)
        
        preset_all_btn = QPushButton("🌟 Completo")
        preset_all_btn.setToolTip("Tutti i formati supportati")
        preset_all_btn.clicked.connect(self.set_all_formats)
        preset_layout.addWidget(preset_all_btn)
        
        preset_layout.addStretch()
        formats_layout.addLayout(preset_layout)
        
        formats_group.setLayout(formats_layout)
        layout.addWidget(formats_group, 4, 0, 1, 4)

        group_box.setLayout(layout)
        return group_box

    def create_image_optimization_section(self):
        """Crea sezione ottimizzazione profili AI"""
        group_box = QGroupBox("🎯 Profili Ottimizzazione AI")
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
        headers = ["Profilo", "Size", "Quality", "Method", "Resampling"]
        for i, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet(f"font-weight: bold; color: {COLORS['ambra']};")
            profiles_layout.addWidget(label, 0, i)
        
        # Profili configurabili (principali)
        self.profile_widgets = {}
        profiles = [
            ("llm_vision", "LLM Vision"),
            ("clip_embedding", "CLIP"), 
            ("dinov2_embedding", "DINOv2"),
            ("bioclip_classification", "BioCLIP"),
            ("aesthetic_score", "Aesthetic"),
            ("ai_processing", "AI Generic"),
        ]
        
        for row, (profile_key, profile_name) in enumerate(profiles, 1):
            # Nome profilo
            profiles_layout.addWidget(QLabel(profile_name), row, 0)
            
            # Target size
            size_spin = NoWheelSpinBox()
            size_spin.setRange(128, 2048)
            size_spin.setSingleStep(64)
            size_spin.setSuffix("px")
            profiles_layout.addWidget(size_spin, row, 1)
            
            # Quality
            quality_spin = NoWheelSpinBox()
            quality_spin.setRange(50, 100)
            quality_spin.setSuffix("%")
            profiles_layout.addWidget(quality_spin, row, 2)
            
            # Method
            method_combo = NoWheelComboBox()
            method_combo.addItems(["rawpy_full", "high_quality", "preview_optimized", "fast_thumbnail"])
            profiles_layout.addWidget(method_combo, row, 3)
            
            # Resampling
            resampling_combo = NoWheelComboBox()
            resampling_combo.addItems(["LANCZOS", "BILINEAR", "BICUBIC", "NEAREST"])
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
        group_box = QGroupBox("🔍 Ricerca Avanzata")
        group_box.setObjectName("SearchAdvancedSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#SearchAdvancedSection {{
                border: 2px solid {COLORS['grigio_medio']};
            }}
        """)
        
        layout = QGridLayout()

        # Row 0: Fuzzy enabled + Max results
        self.fuzzy_enabled_checkbox = QCheckBox("Ricerca Fuzzy")
        self.fuzzy_enabled_checkbox.setToolTip("Permette ricerca approssimativa (paesagio → paesaggio)")
        layout.addWidget(self.fuzzy_enabled_checkbox, 0, 0)
        
        layout.addWidget(QLabel("Max Risultati:"), 0, 1)
        self.search_max_results_spin = NoWheelSpinBox()
        self.search_max_results_spin.setRange(10, 1000)
        self.search_max_results_spin.setSingleStep(50)
        self.search_max_results_spin.setToolTip("Limite risultati ricerca testuale")
        layout.addWidget(self.search_max_results_spin, 0, 2)

        # Row 1: Semantic threshold
        layout.addWidget(QLabel("Soglia Semantica:"), 1, 0)
        self.semantic_threshold_spin = NoWheelDoubleSpinBox()
        self.semantic_threshold_spin.setRange(0.05, 0.50)
        self.semantic_threshold_spin.setSingleStep(0.05)
        self.semantic_threshold_spin.setDecimals(2)
        self.semantic_threshold_spin.setToolTip("Soglia similarità CLIP per ricerca semantica")
        self.semantic_threshold_spin.valueChanged.connect(self.validate_semantic_threshold)
        layout.addWidget(self.semantic_threshold_spin, 1, 1)

        group_box.setLayout(layout)
        return group_box

    def create_metadata_section(self):
        """Crea sezione configurazione metadati"""
        group_box = QGroupBox("📊 Estrazione Metadati")
        group_box.setObjectName("MetadataSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#MetadataSection {{
                border: 2px solid {COLORS['blu_petrolio_dark']};
            }}
        """)
        
        layout = QGridLayout()

        # EXIF extraction
        self.extract_exif_checkbox = QCheckBox("Estrai EXIF")
        self.extract_exif_checkbox.setToolTip("Estrae metadati tecnici (ISO, apertura, modello camera, ecc.)")
        layout.addWidget(self.extract_exif_checkbox, 0, 0)

        # GPS extraction
        self.gps_enabled_checkbox = QCheckBox("Estrai GPS")
        self.gps_enabled_checkbox.setToolTip("Estrae coordinate GPS per geolocalizzazione (privacy sensitive)")
        layout.addWidget(self.gps_enabled_checkbox, 0, 1)

        group_box.setLayout(layout)
        return group_box

    def create_similarity_section(self):
        """Crea sezione configurazione ricerca globale"""
        group_box = QGroupBox("🔎 Ricerca (Semantica + Tag)")
        group_box.setObjectName("SearchSection")
        
        group_box.setStyleSheet(f"""
            QGroupBox#SearchSection {{
                border: 2px solid {COLORS['grigio_medio']};
            }}
        """)
        
        layout = QGridLayout()
        
        # Descrizione
        desc_label = QLabel("Limiti per ricerca nel tab Ricerca (CLIP semantica + Tag utente)")
        desc_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; font-style: italic;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label, 0, 0, 1, 2)

        # Max Risultati
        layout.addWidget(QLabel("Max Risultati:"), 1, 0)
        self.similarity_max_results = NoWheelSpinBox()
        self.similarity_max_results.setRange(10, 500)
        self.similarity_max_results.setSingleStep(10)
        self.similarity_max_results.setToolTip("Numero massimo di risultati mostrati nel tab Ricerca")
        layout.addWidget(self.similarity_max_results, 1, 1)

        group_box.setLayout(layout)
        return group_box

    def create_logging_section(self):
        """Crea sezione configurazione logging"""
        group_box = QGroupBox("📝 Logging & Debug")
        layout = QVBoxLayout(group_box)
        
        # Checkbox debug
        self.debug_checkbox = QCheckBox("Mostra messaggi DEBUG nel log")
        self.debug_checkbox.setToolTip("Abilita/disabilita la visualizzazione dei messaggi DEBUG nella tab Log")
        self.debug_checkbox.setChecked(True)  # Default: abilitato
        self.debug_checkbox.stateChanged.connect(self.on_debug_setting_changed)
        layout.addWidget(self.debug_checkbox)
        
        # Info sul logging
        info_label = QLabel("ℹ️ I messaggi DEBUG aiutano a diagnosticare problemi ma possono rendere il log molto verboso")
        info_label.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 10px; font-style: italic; padding: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
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

    def toggle_bioclip_params(self, state):
        """Abilita/disabilita parametri BioCLIP"""
        enabled = state == Qt.CheckState.Checked.value
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
            # PATHS (rimossa input_dir)
            # --------------------------------------------------
            paths = self.config['paths']
            self.db_path_edit.setText(paths['database'])
            self.log_dir_edit.setText(paths['log_dir'])

            # --------------------------------------------------
            # EMBEDDING / DEVICE
            # --------------------------------------------------
            embedding = self.config['embedding']
            device = embedding['device']
            idx = self.device_combo.findData(device)
            if idx < 0:
                raise ValueError(f"Device non valido: {device}")
            self.device_combo.setCurrentIndex(idx)

            models = embedding['models']

            # DINOv2
            dino = models['dinov2']
            self.dinov2_model_name.setText(dino['model_name'])
            self.dinov2_dimension.setValue(dino['dimension'])
            self.dinov2_similarity_threshold.setValue(dino['similarity_threshold'])

            # CLIP
            clip = models['clip']
            self.clip_model_name.setText(clip['model_name'])
            self.clip_dimension.setValue(clip['dimension'])

            # Aesthetic Score
            aesthetic = models.get('aesthetic', {})
            self.aesthetic_enabled.setChecked(aesthetic.get('enabled', True))

            # Technical Score (BRISQUE)
            # Non c'è sezione dedicata, usa flag generale
            self.technical_enabled.setChecked(self.config.get('embedding', {}).get('brisque_enabled', True))

            # BioCLIP
            bioclip = models['bioclip']
            self.bioclip_enabled.setChecked(bioclip['enabled'])
            self.bioclip_threshold.setValue(bioclip['threshold'])
            self.bioclip_max_tags.setValue(bioclip['max_tags'])
            self.toggle_bioclip_params(bioclip['enabled'])

            # LLM Vision
            llm = models['llm_vision']
            self.llm_vision_endpoint.setText(llm['endpoint'])
            self.llm_vision_model.setText(llm['model'])
            self.llm_vision_timeout.setValue(llm['timeout'])

            # Parametri generation LLM
            gen_params = llm.get('generation', {})
            self.llm_temperature.setValue(gen_params.get('temperature', 0.2))
            self.llm_top_k.setValue(gen_params.get('top_k', 20))
            self.llm_top_p.setValue(gen_params.get('top_p', 0.8))
            self.llm_num_ctx.setValue(gen_params.get('num_ctx', 2048))
            self.llm_num_batch.setValue(gen_params.get('num_batch', 1024))

            # Parametri auto_import granulari (nuova struttura)
            auto_import = llm.get('auto_import', {})

            # Tags
            tags_cfg = auto_import.get('tags', {})
            self.gen_tags_check.setChecked(tags_cfg.get('enabled', False))
            self.gen_tags_overwrite.setChecked(tags_cfg.get('overwrite', False))
            self.llm_vision_max_tags.setValue(tags_cfg.get('max_tags', 10))
            self._toggle_tags_controls(self.gen_tags_check.isChecked())

            # Descrizione
            desc_cfg = auto_import.get('description', {})
            self.gen_desc_check.setChecked(desc_cfg.get('enabled', False))
            self.gen_desc_overwrite.setChecked(desc_cfg.get('overwrite', False))
            self.llm_vision_max_words.setValue(desc_cfg.get('max_words', 100))
            self._toggle_desc_controls(self.gen_desc_check.isChecked())

            # Titolo
            title_cfg = auto_import.get('title', {})
            self.gen_title_check.setChecked(title_cfg.get('enabled', False))
            self.gen_title_overwrite.setChecked(title_cfg.get('overwrite', False))
            self.llm_vision_max_title_chars.setValue(title_cfg.get('max_words', 5))
            self._toggle_title_controls(self.gen_title_check.isChecked())

            # --------------------------------------------------
            # IMAGE PROCESSING
            # --------------------------------------------------
            img = self.config['image_processing']
            self.convert_raw_checkbox.setChecked(img['convert_raw'])
            self.jpeg_quality_spin.setValue(img['jpeg_quality'])
            self.max_dimension_spin.setValue(img['max_dimension'])
            self.max_workers_spin.setValue(img['max_workers'])
            self.resize_images_checkbox.setChecked(img['resize_images'])

            # Supported formats (se presente nel config)
            if 'supported_formats' in img:
                formats_text = '\n'.join(img['supported_formats'])
                self.supported_formats_text.setPlainText(formats_text)
            else:
                # Fallback per config senza supported_formats
                self.set_extended_formats()

            raw = img['raw_processing']
            self.cache_thumbnails_checkbox.setChecked(raw['cache_thumbnails'])
            self.cache_dir_edit.setText(raw['cache_dir'])
            self.processing_timeout_spin.setValue(raw['processing_timeout'])
            self.fallback_size_spin.setValue(raw['fallback_size'])
            self.thumbnail_strategy_combo.setCurrentText(raw['thumbnail_strategy'])
            self.fallback_thumbnail_checkbox.setChecked(raw['fallback_thumbnail'])

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
            self.search_max_results_spin.setValue(search['max_results'])
            self.semantic_threshold_spin.setValue(search['semantic_threshold'])

            # --------------------------------------------------
            # METADATA
            # --------------------------------------------------
            meta = self.config['metadata']
            self.extract_exif_checkbox.setChecked(meta['extract_exif'])
            self.gps_enabled_checkbox.setChecked(meta['gps_enabled'])

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
                        self.editor_controls[i-1]['path'].setText(editor_data.get('path', ''))
                        self.editor_controls[i-1]['command_args'].setText(editor_data.get('command_args', ''))

            # --------------------------------------------------
            # LOGGING
            # --------------------------------------------------
            self.debug_checkbox.setChecked(self.config['logging']['show_debug'])

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
            # Database & Paths (rimossa input_dir)
            self.db_path_edit.setText('database/offgallery.sqlite')
            self.log_dir_edit.setText('logs')
            
            # Device
            self.device_combo.setCurrentIndex(0)  # auto
            
            # DINOv2
            self.dinov2_model_name.setText('facebook/dinov2-base')
            self.dinov2_dimension.setValue(768)
            self.dinov2_similarity_threshold.setValue(0.25)
            
            # CLIP
            self.clip_model_name.setText('laion/CLIP-ViT-B-32-laion2B-s34B-b79K')
            self.clip_dimension.setValue(512)

            # Quality Scores
            self.aesthetic_enabled.setChecked(True)
            self.technical_enabled.setChecked(True)

            # BioCLIP
            self.bioclip_enabled.setChecked(True)
            self.bioclip_threshold.setValue(0.12)
            self.bioclip_max_tags.setValue(5)
            self.toggle_bioclip_params(True)
            
            # LLM Vision
            self.llm_vision_endpoint.setText('http://localhost:11434')
            self.llm_vision_model.setText('qwen3-vl:4b-instruct')
            self.llm_vision_timeout.setValue(240)

            # Parametri generation LLM
            self.llm_temperature.setValue(0.2)
            self.llm_top_k.setValue(20)
            self.llm_top_p.setValue(0.8)
            self.llm_num_ctx.setValue(2048)
            self.llm_num_batch.setValue(1024)

            # Generazione Auto-Import (default: tutto disabilitato, no sovrascrittura)
            self.gen_tags_check.setChecked(False)
            self.gen_tags_overwrite.setChecked(False)
            self.llm_vision_max_tags.setValue(10)
            self._toggle_tags_controls(False)

            self.gen_desc_check.setChecked(False)
            self.gen_desc_overwrite.setChecked(False)
            self.llm_vision_max_words.setValue(100)
            self._toggle_desc_controls(False)

            self.gen_title_check.setChecked(False)
            self.gen_title_overwrite.setChecked(False)
            self.llm_vision_max_title_chars.setValue(5)
            self._toggle_title_controls(False)
            
            # Image Processing
            self.convert_raw_checkbox.setChecked(True)
            self.jpeg_quality_spin.setValue(95)
            self.max_dimension_spin.setValue(2048)
            self.max_workers_spin.setValue(4)
            self.resize_images_checkbox.setChecked(False)
            
            # RAW Processing
            self.cache_thumbnails_checkbox.setChecked(True)
            self.cache_dir_edit.setText('thumbnails_cache')
            self.processing_timeout_spin.setValue(30)
            self.fallback_size_spin.setValue(512)
            self.thumbnail_strategy_combo.setCurrentText('embedded')
            self.fallback_thumbnail_checkbox.setChecked(True)
            
            # Supported Formats (Default: Extended)
            self.set_extended_formats()
            
            # Image Optimization Profiles (valori ottimali)
            profiles_defaults = {
                'llm_vision': {'size': 1024, 'quality': 95, 'method': 'rawpy_full', 'resampling': 'LANCZOS'},
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
            self.search_max_results_spin.setValue(100)
            self.semantic_threshold_spin.setValue(0.15)
            
            # Metadata
            self.extract_exif_checkbox.setChecked(True)
            self.gps_enabled_checkbox.setChecked(True)
            
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
            }
            
            # Preserva input_dir se presente (gestito solo da processing_tab)
            if 'paths' in self.config and 'input_dir' in self.config['paths']:
                paths_data['input_dir'] = self.config['paths']['input_dir']
            
            self.config['paths'] = paths_data
            
            # Embedding (aggiorna solo sezioni gestite dall'UI)
            if 'embedding' not in self.config:
                self.config['embedding'] = {}
            
            self.config['embedding']['enabled'] = True
            self.config['embedding']['device'] = self.device_combo.currentData()
            
            if 'models' not in self.config['embedding']:
                self.config['embedding']['models'] = {}
            
            # Aggiorna solo modelli gestiti dall'UI
            self.config['embedding']['models']['dinov2'] = {
                'description': 'Similarità visiva (composizione, texture, forma)',
                'enabled': True,
                'model_name': self.dinov2_model_name.text(),
                'dimension': self.dinov2_dimension.value(),
                'similarity_threshold': self.dinov2_similarity_threshold.value(),
            }
            
            self.config['embedding']['models']['clip'] = {
                'description': 'Ricerca semantica (query naturali)',
                'enabled': True,
                'model_name': self.clip_model_name.text(),
                'dimension': self.clip_dimension.value(),
            }

            # Quality Scores
            self.config['embedding']['models']['aesthetic'] = {
                'description': 'Punteggio estetico (qualità artistica)',
                'enabled': self.aesthetic_enabled.isChecked(),
                'model_name': 'aesthetic-predictor',
                'returns_score': True,
            }

            # BRISQUE (technical score) - flag a livello embedding
            self.config['embedding']['brisque_enabled'] = self.technical_enabled.isChecked()

            self.config['embedding']['models']['bioclip'] = {
                'description': 'Classificazione flora/fauna TreeOfLife (~450k specie)',
                'enabled': self.bioclip_enabled.isChecked(),
                'threshold': self.bioclip_threshold.value(),
                'max_tags': self.bioclip_max_tags.value(),
            }
            
            self.config['embedding']['models']['llm_vision'] = {
                'description': 'Genera tag, descrizioni e titoli con LLM vision (richiede Ollama)',
                'enabled': True,  # Sempre true per gallery on-demand
                'endpoint': self.llm_vision_endpoint.text(),
                'model': self.llm_vision_model.text(),
                'timeout': self.llm_vision_timeout.value(),
                'generation': {
                    'temperature': self.llm_temperature.value(),
                    'top_k': self.llm_top_k.value(),
                    'top_p': self.llm_top_p.value(),
                    'num_ctx': self.llm_num_ctx.value(),
                    'num_batch': self.llm_num_batch.value(),
                },
                'auto_import': {
                    'tags': {
                        'enabled': self.gen_tags_check.isChecked(),
                        'overwrite': self.gen_tags_overwrite.isChecked(),
                        'max_tags': self.llm_vision_max_tags.value(),
                    },
                    'description': {
                        'enabled': self.gen_desc_check.isChecked(),
                        'overwrite': self.gen_desc_overwrite.isChecked(),
                        'max_words': self.llm_vision_max_words.value(),
                    },
                    'title': {
                        'enabled': self.gen_title_check.isChecked(),
                        'overwrite': self.gen_title_overwrite.isChecked(),
                        'max_words': self.llm_vision_max_title_chars.value(),
                    },
                }
            }
            
            # Image Processing
            # Estrae formati dalla text area e li converte in lista
            formats_text = self.supported_formats_text.toPlainText().strip()
            supported_formats = [fmt.strip() for fmt in formats_text.split('\n') if fmt.strip()]
            
            self.config['image_processing'] = {
                'convert_raw': self.convert_raw_checkbox.isChecked(),
                'jpeg_quality': self.jpeg_quality_spin.value(),
                'max_dimension': self.max_dimension_spin.value(),
                'max_workers': self.max_workers_spin.value(),
                'resize_images': self.resize_images_checkbox.isChecked(),
                'supported_formats': supported_formats,
                'raw_processing': {
                    'enabled': True,
                    'cache_thumbnails': self.cache_thumbnails_checkbox.isChecked(),
                    'cache_dir': self.cache_dir_edit.text(),
                    'processing_timeout': self.processing_timeout_spin.value(),
                    'fallback_size': self.fallback_size_spin.value(),
                    'thumbnail_strategy': self.thumbnail_strategy_combo.currentText(),
                    'fallback_thumbnail': self.fallback_thumbnail_checkbox.isChecked(),
                }
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
                'max_results': self.search_max_results_spin.value(),
                'semantic_threshold': self.semantic_threshold_spin.value(),
            }
            
            # Metadata
            self.config['metadata'] = {
                'extract_exif': self.extract_exif_checkbox.isChecked(),
                'gps_enabled': self.gps_enabled_checkbox.isChecked(),
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
            
            # PRESERVA tutte le altre sezioni esistenti non gestite dall'UI
            
            # Salva
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            
            QMessageBox.information(self, "Successo", "Configurazione completa salvata!")
            
            if self.parent_window and hasattr(self.parent_window, 'update_status'):
                self.parent_window.update_status("Configurazione salvata")
            
            self.config_saved.emit(self.config)
        
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore salvataggio configurazione:\n{e}")
    
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
            "Reset Configurazione",
            "Sei sicuro di voler resettare TUTTA la configurazione ai valori di default?\n\nQuesta operazione non può essere annullata.",
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
            QMessageBox.information(self, "Reset Completato", "Configurazione resettata ai valori di default e salvata!\n\nBackup della configurazione precedente creato.")
            
            if hasattr(self, 'parent_window') and self.parent_window:
                self.parent_window.log_info("Configurazione resettata ai valori di default")

    def test_ollama_connection(self):
        """Testa la connessione all'endpoint Ollama"""
        endpoint = self.llm_vision_endpoint.text().strip()
        if not endpoint:
            QMessageBox.warning(self, "Endpoint Vuoto", "Inserisci un endpoint valido")
            return
            
        try:
            import requests
            import time
            
            # Cambio colore bottone durante test
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
            
            # Test connessione con timeout breve
            response = requests.get(f"{endpoint}/api/tags", timeout=5)
            
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', 'Unknown') for m in models[:3]]  # Prime 3
                models_text = ', '.join(model_names) if model_names else 'Nessuno'
                
                # Successo - verde
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
                    "Connessione Riuscita", 
                    f"✅ Ollama raggiungibile!\n\nModelli disponibili: {models_text}"
                )
            else:
                raise requests.RequestException(f"Status code: {response.status_code}")
                
        except Exception as e:
            # Errore - rosso
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
                "Connessione Fallita", 
                f"❌ Impossibile connettersi a Ollama:\n{str(e)}\n\nVerifica che Ollama sia avviato e raggiungibile."
            )
        
        # Reset bottone dopo 3 secondi
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, self.reset_test_button)
    
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
            self.dinov2_similarity_threshold.setToolTip("⚠️ Soglia molto bassa - troppi risultati simili")
        elif value > 0.8:
            # Troppo alto - border ambra
            self.dinov2_similarity_threshold.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 2px solid {COLORS['ambra']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.dinov2_similarity_threshold.setToolTip("⚠️ Soglia molto alta - pochi risultati simili")
        else:
            # Valore OK - border normale
            self.dinov2_similarity_threshold.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 1px solid {COLORS['blu_petrolio_light']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.dinov2_similarity_threshold.setToolTip("✅ Soglia ottimale per ricerca similarità")

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
            self.semantic_threshold_spin.setToolTip("⚠️ Soglia molto bassa - troppi risultati poco pertinenti")
        elif value > 0.30:
            # Troppo alto - pochi risultati  
            self.semantic_threshold_spin.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 2px solid {COLORS['ambra']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.semantic_threshold_spin.setToolTip("⚠️ Soglia molto alta - pochi risultati")
        else:
            # Valore OK
            self.semantic_threshold_spin.setStyleSheet(f"""
                QDoubleSpinBox {{
                    border: 1px solid {COLORS['blu_petrolio_light']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            self.semantic_threshold_spin.setToolTip("✅ Soglia ottimale per ricerca semantica")

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
        
        if path.exists() and path.is_file() and path.suffix.lower() == '.exe':
            # Percorso valido
            path_edit.setStyleSheet(f"""
                QLineEdit {{
                    border: 2px solid {COLORS['verde']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            path_edit.setToolTip("✅ Percorso valido")
        else:
            # Percorso non valido
            path_edit.setStyleSheet(f"""
                QLineEdit {{
                    border: 2px solid {COLORS['rosso']};
                    background-color: {COLORS['grafite']};
                    color: {COLORS['grigio_chiaro']};
                }}
            """)
            path_edit.setToolTip("❌ Percorso non valido o non è un .exe")

    def browse_editor_path(self, editor_index):
        """Apri dialog per selezionare editor esterno"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Seleziona Editor {editor_index}",
            "",
            "Eseguibili (*.exe);;Tutti i file (*.*)"
        )
        
        if file_path:
            self.editor_controls[editor_index - 1]['path'].setText(file_path)

