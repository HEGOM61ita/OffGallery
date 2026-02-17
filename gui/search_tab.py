"""
Search Tab - Ricerca semplificata
Campo unico con switch semantica/tag + filtri EXIF
CORRECTED: Fix ricerca semantica con embedding_generator corretto
"""

import yaml
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit,
    QRadioButton, QButtonGroup, QFrame, QSlider, QScrollArea,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QCoreApplication

from utils.paths import get_app_dir

# Importa la black box
from retrieval import ImageRetrieval

import unicodedata
import re

def normalize_it(text: str) -> str:
    """Normalizza il testo rimuovendo accenti e convertendo in minuscolo"""
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(text).lower()) if unicodedata.category(c) != 'Mn')


def trigrams(word: str) -> set:
    if len(word) < 3:
        return {word}
    return {word[i:i+3] for i in range(len(word) - 2)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def fuzzy_score_word(term: str, token: str) -> float:
    if term == token:
        return 1.0

    t_norm = normalize_it(term)
    tok_norm = normalize_it(token)

    if t_norm == tok_norm:
        return 0.90

    if tok_norm.startswith(t_norm) or t_norm.startswith(tok_norm):
        return 0.80

    sim = jaccard(trigrams(t_norm), trigrams(tok_norm))

    if sim >= 0.75:
        return 0.75
    if sim >= 0.65:
        return 0.65
    if sim >= 0.55:
        return 0.55

    return 0.0



def fuzzy_score_term(term: str, tokens: list[str]) -> float:
    best = 0.0
    for token in tokens:
        score = fuzzy_score_word(term, token)
        if score > best:
            best = score
            if best >= 0.90:
                break
    return best



def partial_text_match_score(search_terms, tags, description):
    """Match parziale graduato 0.0 → 1.0"""
    matched = 0
    for term in search_terms:
        if (tags and any(term in tag for tag in tags)) or \
           (description and term in description):
            matched += 1
    return matched / len(search_terms) if search_terms else 0.0


class SearchTab(QWidget):
    """Tab ricerca semplificata"""
    
    search_executed = pyqtSignal(list)
    
    def __init__(self, parent=None, ai_models=None):
        super().__init__(parent)
        self.parent_window = parent
        self.ai_models = ai_models  # Modelli centralizzati
        self.config_path = self._get_config_path()
        self.config = {}
        
        # Controllo ricerca dinamica
        self.search_active = False
        self.search_cancelled = False
        
        self.init_ui()
        self.load_config_defaults()
        
        # Popola le combo box camera e lens dal database
        self.on_activated()
    
    def _get_config_path(self):
        """Trova config path come processing_tab"""
        app_dir = get_app_dir()
        possible_configs = [
            app_dir / 'config_new.yaml',
            Path.cwd() / 'config_new.yaml',
            Path.home() / '.offgallery' / 'config_new.yaml',
        ]

        for config_path in possible_configs:
            if config_path.exists():
                return str(config_path)

        return str(app_dir / 'config_new.yaml')

    def _show_loading_popup(self, text):
        """Crea un piccolo pop-up di caricamento al centro."""
        popup = QLabel(text, self)
        popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        popup.setStyleSheet("""
            QLabel {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 2px solid #3498db;
                border-radius: 12px;
                font-weight: bold;
                padding: 15px;
            }
        """)
        popup.setFixedSize(280, 60)
        # Lo posizioniamo al centro esatto della Tab
        x = (self.width() - popup.width()) // 2
        y = (self.height() - popup.height()) // 2
        popup.move(x, y)
        popup.show()
        QCoreApplication.processEvents()
        return popup

    def _build_sql_filters(self):
        """
        Trasforma i widget della GUI in clausole SQL e parametri.
        Questa funzione è il ponte tra l'interfaccia e retrieval.py.
        """
        conditions = []
        params = []
        
        # --- CAMERA (Make + Model combinato) ---
        camera = self.camera_combo.currentText()
        if camera and camera != "Tutte":
            camera_parts = camera.split()
            if len(camera_parts) >= 2:
                possible_make = camera_parts[0]
                possible_model = " ".join(camera_parts[1:])
                conditions.append("(camera_model = ? OR (camera_make = ? AND camera_model = ?) OR (camera_make || ' ' || camera_model) = ?)")
                params.extend([camera, possible_make, possible_model, camera])
            else:
                conditions.append("camera_model = ?")
                params.append(camera)
        
        # --- LENS ---
        lens = self.lens_combo.currentText()
        if lens and lens != "Tutte":
            conditions.append("lens_model = ?")
            params.append(lens)
        
        # --- FILE TYPE ---
        filetype = self.filetype_combo.currentText()
        if filetype == "Solo RAW":
            conditions.append("is_raw = 1")
        elif filetype == "Solo JPEG/PNG":
            conditions.append("(is_raw = 0 OR is_raw IS NULL)")
        
        # --- RAW FORMAT SPECIFICO ---
        raw_format_text = self.raw_format_combo.currentText()
        if raw_format_text and raw_format_text != "Tutti":
            current_index = self.raw_format_combo.currentIndex()
            raw_format_value = self.raw_format_combo.itemData(current_index)
            if raw_format_value:
                conditions.append("raw_format = ?")
                params.append(raw_format_value)
        
        # --- FOCAL LENGTH ---
        if self.focal_min.value() > 0:
            conditions.append("focal_length >= ?")
            params.append(self.focal_min.value())
        if self.focal_max.value() < 2000:
            conditions.append("focal_length <= ?")
            params.append(self.focal_max.value())
            
        # --- ISO ---
        if self.iso_min.value() > 0:
            conditions.append("iso >= ?")
            params.append(self.iso_min.value())
        if self.iso_max.value() < 204800:
            conditions.append("iso <= ?")
            params.append(self.iso_max.value())
            
        # --- APERTURA ---
        if self.aperture_min.value() > 0.0:
            conditions.append("aperture >= ?")
            params.append(self.aperture_min.value())
        if self.aperture_max.value() < 64.0:
            conditions.append("aperture <= ?")
            params.append(self.aperture_max.value())
            
        # --- FLASH ---
        flash = self.flash_combo.currentText()
        if flash == "Sì":
            conditions.append("flash_used = 1")
        elif flash == "No":
            conditions.append("flash_used = 0")
            
        # --- EXPOSURE MODE ---
        exposure = self.exposure_combo.currentText()
        exposure_map = {"Auto": 0, "Manual": 1, "Aperture Priority": 2, "Shutter Priority": 3}
        if exposure in exposure_map:
            conditions.append("exposure_mode = ?")
            params.append(exposure_map[exposure])
            
        # --- FOCAL LENGTH 35mm ---
        if self.focal35_min.value() > 0:
            conditions.append("focal_length_35mm >= ?")
            params.append(self.focal35_min.value())
        if self.focal35_max.value() < 2000:
            conditions.append("focal_length_35mm <= ?")
            params.append(self.focal35_max.value())
            
        # --- EXPOSURE BIAS (EV) ---
        if self.ev_min.value() > -5.0:
            conditions.append("exposure_bias >= ?")
            params.append(self.ev_min.value())
        if self.ev_max.value() < 5.0:
            conditions.append("exposure_bias <= ?")
            params.append(self.ev_max.value())
            
        # --- ORIENTATION ---
        orientation = self.orientation_combo.currentText()
        if orientation == "Portrait":
            conditions.append("(orientation = 6 OR orientation = 8)")
        elif orientation == "Landscape":
            conditions.append("(orientation = 1 OR orientation IS NULL)")
        elif orientation == "Rotated":
            conditions.append("orientation = 3")
            
        # --- QUALITÀ (Aesthetic & Technical) ---
        if self.aesthetic_min.value() > 0.0:
            conditions.append("aesthetic_score >= ?")
            params.append(self.aesthetic_min.value())
        if self.aesthetic_max.value() < 10.0:
            conditions.append("aesthetic_score <= ?")
            params.append(self.aesthetic_max.value())
            
        if self.technical_min.value() > 0.0:
            conditions.append("technical_score >= ?")
            params.append(self.technical_min.value())
        if self.technical_max.value() < 100.0:
            conditions.append("technical_score <= ?")
            params.append(self.technical_max.value())

        # --- RATING (stelle) ---
        rating_min_value = self.rating_min.currentData()
        if rating_min_value and rating_min_value > 0:
            if rating_min_value == 5:
                # Esattamente 5 stelle
                conditions.append("lr_rating = ?")
                params.append(5)
            else:
                # Rating minimo
                conditions.append("lr_rating >= ?")
                params.append(rating_min_value)

        # --- COLOR LABEL ---
        color_label_value = self.color_label_filter.currentData()
        if color_label_value is not None:  # None = "Tutti", stringa vuota = "Senza colore"
            if color_label_value == "":
                # Senza colore
                conditions.append("(color_label IS NULL OR color_label = '')")
            else:
                # Colore specifico
                conditions.append("color_label = ?")
                params.append(color_label_value)

        # --- GPS ---
        if self.gps_only.isChecked():
            conditions.append("gps_latitude IS NOT NULL")
            
        # --- BIANCO E NERO ---
        mono_idx = self.monochrome_combo.currentIndex()
        if mono_idx == 1:    # Colori
            conditions.append("is_monochrome = 0")
        elif mono_idx == 2:  # B/N
            conditions.append("is_monochrome = 1")
            
        # --- SYNC STATE (XMP out of sync) ---
        if self.sync_filter.isChecked():
            conditions.append("(last_xmp_mtime IS NULL OR strftime('%s', datetime_modified) > last_xmp_mtime)")
            
        # --- DATE RANGE ---
        if self.date_filter_enabled.isChecked():
            date_from = self.date_from.date().toString("yyyy-MM-dd")
            date_to = self.date_to.date().toString("yyyy-MM-dd")
            conditions.append("datetime_original >= ?")
            conditions.append("datetime_original <= ?")
            params.append(date_from)
            params.append(date_to + " 23:59:59")

        # Uniamo tutto
        sql_string = " AND ".join(conditions) if conditions else None
        return sql_string, params

    def execute_search(self):
        loading_msg = None
        try:
            query = self.search_input.text().strip()
            has_filters = self._has_filters()
            
            # Controllo: serve almeno query O filtri
            if not query and not has_filters:
                QMessageBox.information(self, "Ricerca", "Inserisci una query di ricerca o imposta almeno un filtro.")
                return

            self.search_active = True
            
            # --- PULIZIA UI ---
            self.results_label.setText("") 
            self.progress_box.setVisible(False) 
            
            # Mostriamo il pop-up al centro
            if query:
                txt = "Analisi CLIP..." if self.semantic_radio.isChecked() else "Ricerca nei Tag..."
            else:
                txt = "Applicando Filtri..."
            loading_msg = self._show_loading_popup(f"🔍 {txt}")
            
            QCoreApplication.processEvents()
            
            # --- LOGICA DI CARICAMENTO ---
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])

            # Usa i modelli centralizzati
            retriever = ImageRetrieval(db_manager, self.ai_models['embedding_generator'], config)  
            
            filters_sql, params = self._build_sql_filters()
            mode = "semantic" if self.semantic_radio.isChecked() else "tags"
            threshold_val = self.threshold_spin.value()
            use_fuzzy = self.fuzzy_check.isChecked()
            use_title = self.title_search_check.isChecked()
            limit_val = self.max_results_spin.value()

            # --- ESECUZIONE (Spacchettamento tupla) ---
            results, total_candidates = retriever.search(
                query_text=query,
                mode=mode,
                filters_sql=filters_sql,
                filter_params=params,
                deep_search=self.deep_search_check.isChecked(),
                min_threshold=threshold_val,
                fuzzy=use_fuzzy,
                strictness=self.strict_slider.value() / 100.0,
                include_description=self.description_check.isChecked(),
                include_title=use_title,
                max_results=limit_val
            )

            # --- FINE ---
            n_mostrate = len(results) # Quante ne vediamo effettivamente (rispetta il limite)
            
            if self.semantic_radio.isChecked() and self.deep_search_check.isChecked():
                # Calcola quante l'AI ha scartato rispetto a quelle passate dai filtri SQL
                filtered_out = total_candidates - n_mostrate
                loading_msg.setText(f"✅ Mostrate {n_mostrate}/{total_candidates} (Smart Filter: -{filtered_out})")
            else:
                # Caso standard: mostra quante ne hai chieste sul totale disponibile
                loading_msg.setText(f"✅ Mostrate {n_mostrate}/{total_candidates} immagini!")
            
            QCoreApplication.processEvents()
            
            import time
            time.sleep(0.5) 
            
            self.search_executed.emit(results)
        except Exception as e:
            import traceback
            import logging
            logging.getLogger(__name__).error(f"Errore ricerca: {traceback.format_exc()}")
            QMessageBox.critical(self, "Errore", f"Problema durante la ricerca: {str(e)}")
        finally:
            if loading_msg:
                loading_msg.deleteLater()
            self.search_active = False

    def log_message(self, message, level):
        """Log messaggi (compatibilità con processing_tab)"""
        if hasattr(self.parent_window, 'log_info'):
            if level == 'error':
                self.parent_window.log_error(message)
            elif level == 'warning':
                self.parent_window.log_warning(message)
            else:
                self.parent_window.log_info(message)
        else:
            print(f"[{level.upper()}] {message}")
    def stop_search(self):
        """Interrompe la ricerca in corso"""
        self.search_cancelled = True
        self.search_active = False
        self.progress_box.setVisible(False)
        self.log_message("🛑 Ricerca interrotta", "warning")
        
        # Se ci sono già risultati parziali, li mostra
        if hasattr(self, 'partial_results') and self.partial_results:
            self.search_executed.emit(self.partial_results)
            self.results_label.setText(f"Risultati: {len(self.partial_results)} (parziali)")
        else:
            self.results_label.setText("Risultati: -")

    def init_ui(self):
        """Inizializza interfaccia con scroll verticale"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area per tutto il contenuto
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(8)

        # Ricerca principale
        layout.addWidget(self.create_search_section())

        # Filtri fotografici (senza groupbox esterno)
        layout.addWidget(self.create_photo_filters_section())

        # Qualità + GPS + Sync + Data + Azioni
        row_bottom = QHBoxLayout()
        row_bottom.addWidget(self.create_quality_section())
        row_bottom.addWidget(self.create_gps_section())
        row_bottom.addWidget(self.create_sync_section())
        row_bottom.addWidget(self.create_date_section())
        row_bottom.addStretch()
        row_bottom.addWidget(self.create_action_buttons())
        layout.addLayout(row_bottom)

        # Risultati con conteggio dinamico e pulsante stop
        results_layout = QHBoxLayout()

        self.results_label = QLabel("Risultati: -")
        self.results_label.setStyleSheet("font-weight: bold; color: #666;")

        # Box conteggio dinamico - Layout pulito senza QGroupBox
        self.progress_box = QWidget()
        self.progress_box.setVisible(False)
        self.progress_box.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                border: 2px solid #999;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        progress_layout = QVBoxLayout()
        progress_layout.setContentsMargins(8, 8, 8, 8)
        progress_layout.setSpacing(5)

        progress_title = QLabel("⏱️ Ricerca in corso")
        progress_title.setStyleSheet("color: #666; font-weight: bold; font-size: 14px;")
        progress_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        count_layout = QHBoxLayout()

        self.count_label = QLabel("Trovate: 0 immagini")
        self.count_label.setStyleSheet("color: #666; font-size: 14px; font-weight: bold;")

        self.stop_button = QPushButton("⏹️ Stop")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #ff8800;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff6600;
            }
            QPushButton:pressed {
                background-color: #cc5500;
            }
        """)
        self.stop_button.clicked.connect(self.stop_search)

        progress_layout.addWidget(progress_title)
        count_layout.addWidget(self.count_label)
        count_layout.addStretch()
        count_layout.addWidget(self.stop_button)
        progress_layout.addLayout(count_layout)
        self.progress_box.setLayout(progress_layout)

        results_layout.addWidget(self.results_label)
        results_layout.addWidget(self.progress_box)
        results_layout.addStretch()

        layout.addLayout(results_layout)
        layout.addStretch()

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        #------------------------------------------------
    def create_search_section(self):
        """Sezione ricerca principale: campo unico + switch + opzioni divise per modalità"""
        group = QGroupBox()  # Rimosso titolo ridondante
        layout = QVBoxLayout()
    
        # --- 1. SWITCH MODALITÀ ---
        mode_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
    
        self.semantic_radio = QRadioButton("Semantica")
        self.semantic_radio.setChecked(True)
        self.mode_group.addButton(self.semantic_radio)
    
        self.tags_radio = QRadioButton("Tag/Testo")
        self.mode_group.addButton(self.tags_radio)
    
        mode_layout.addWidget(self.semantic_radio)
        mode_layout.addWidget(self.tags_radio)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
    
        # --- 2. INPUT RICERCA E HELP ---
        self.help_label = QLabel("Cerca con linguaggio naturale (es: 'montagna con neve al tramonto')")
        self.help_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.help_label)
    
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Inserisci query semantica...")
        self.search_input.setFixedHeight(30)
        self.search_input.returnPressed.connect(self.execute_search)
        layout.addWidget(self.search_input)

        # --- 3. OPZIONI DIVISE PER MODALITÀ ---
        options_container = QHBoxLayout()
        
        # GRUPPO SEMANTICA
        self.semantic_group = QGroupBox("🧠 Ricerca Semantica")
        semantic_layout = QVBoxLayout()
        
        # Soglia semantica
        threshold_layout = QHBoxLayout()
        threshold_label = QLabel("Soglia:")
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.1, 0.9)
        self.threshold_spin.setValue(0.15)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setDecimals(2)
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_spin)
        threshold_layout.addStretch()
        semantic_layout.addLayout(threshold_layout)
        
        # Deep Search
        self.deep_search_check = QCheckBox("Deep Search (AI)")
        semantic_layout.addWidget(self.deep_search_check)
        
        # Match Text slider (solo per deep search)
        self.match_text_container = QWidget()
        match_layout = QHBoxLayout(self.match_text_container)
        match_layout.setContentsMargins(20, 0, 0, 0)  # Indent per mostrare dipendenza
        
        self.strict_label = QLabel("Match Text:")
        self.strict_slider = QSlider(Qt.Orientation.Horizontal)
        self.strict_slider.setRange(0, 100)
        self.strict_slider.setValue(40)
        self.strict_slider.setFixedWidth(150)
        
        self.strict_val_label = QLabel("40%")
        self.strict_slider.valueChanged.connect(lambda v: self.strict_val_label.setText(f"{v}%"))
        
        match_layout.addWidget(self.strict_label)
        match_layout.addWidget(self.strict_slider)
        match_layout.addWidget(self.strict_val_label)
        match_layout.addStretch()
        semantic_layout.addWidget(self.match_text_container)
        
        self.semantic_group.setLayout(semantic_layout)
        
        # GRUPPO TAG/TESTO
        self.tags_group = QGroupBox("🏷️ Ricerca Tag/Testo")
        tags_layout = QVBoxLayout()
        
        # Includi descrizione
        self.description_check = QCheckBox("Includi Descrizione")
        self.description_check.setChecked(True)  # Default abilitato
        tags_layout.addWidget(self.description_check)
        
        # Fuzzy matching
        self.fuzzy_check = QCheckBox("Fuzzy Matching")
        self.fuzzy_check.setChecked(True)  # Default abilitato
        tags_layout.addWidget(self.fuzzy_check)

        # Includi titolo nella ricerca
        self.title_search_check = QCheckBox("Includi Titolo")
        self.title_search_check.setChecked(True)  # Default abilitato
        tags_layout.addWidget(self.title_search_check)

        self.tags_group.setLayout(tags_layout)
        
        # CONTROLLI CONDIVISI
        shared_group = QGroupBox("⚙️ Comuni")
        shared_layout = QVBoxLayout()
        
        max_layout = QHBoxLayout()
        max_results_label = QLabel("Max risultati:")
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(1, 10000)
        self.max_results_spin.setValue(100)
        self.max_results_spin.setKeyboardTracking(False) 
        max_layout.addWidget(max_results_label)
        max_layout.addWidget(self.max_results_spin)
        max_layout.addStretch()
        shared_layout.addLayout(max_layout)
        
        shared_group.setLayout(shared_layout)
        
        # Assembla i gruppi
        options_container.addWidget(self.semantic_group)
        options_container.addWidget(self.tags_group)
        options_container.addWidget(shared_group)
        
        layout.addLayout(options_container)
    
        # Connessioni toggle
        self.semantic_radio.toggled.connect(self.update_search_mode)
        self.tags_radio.toggled.connect(self.update_search_mode)
        self.description_check.toggled.connect(self.update_search_mode)
        self.deep_search_check.toggled.connect(self.update_deep_search_mode)
    
        group.setLayout(layout)
        return group
        #------------------------------------------------
   

    def update_search_mode(self):
        """Aggiorna UI in base a modalità selezionata"""
        is_semantic = self.semantic_radio.isChecked()
        
        # Abilita/disabilita gruppi
        self.semantic_group.setEnabled(is_semantic)
        self.tags_group.setEnabled(not is_semantic)
        
        # Aggiorna help e placeholder
        if is_semantic:
            self.help_label.setText("Cerca con linguaggio naturale (es: 'montagna con neve al tramonto')")
            self.search_input.setPlaceholderText("Inserisci query semantica...")
        else:
            # Modalità tag - help dipende da includi descrizione
            include_desc = self.description_check.isChecked()
            if include_desc:
                self.help_label.setText("Cerca nei tag + descrizioni (es: 'vacanza, famiglia' o 'tramonto sul mare')")
                self.search_input.setPlaceholderText("Inserisci tag o parole da cercare...")
            else:
                self.help_label.setText("Cerca nei tag utente + AI (es: 'vacanza, famiglia')")
                self.search_input.setPlaceholderText("Inserisci tag da cercare...")
        
        # Aggiorna abilitazione Match Text slider
        self.update_deep_search_mode()
    
    def update_deep_search_mode(self):
        """Abilita/disabilita Match Text slider in base a Deep Search"""
        deep_enabled = self.deep_search_check.isChecked()
        self.match_text_container.setEnabled(deep_enabled)
    
    def create_photo_filters_section(self):
        """Filtri fotografici EXIF - layout compatto senza gruppi nidificati"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)

        # --- Riga 1: Camera e Lens ---
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(QLabel("Camera:"))
        self.camera_combo = QComboBox()
        self.camera_combo.addItem("Tutte")
        self.camera_combo.setMinimumWidth(150)
        row1.addWidget(self.camera_combo)
        row1.addWidget(QLabel("Lens:"))
        self.lens_combo = QComboBox()
        self.lens_combo.addItem("Tutte")
        self.lens_combo.setMinimumWidth(150)
        row1.addWidget(self.lens_combo)
        row1.addStretch()
        layout.addLayout(row1)

        # --- Riga 2: Tipo File e Formato RAW ---
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(QLabel("Tipo:"))
        self.filetype_combo = QComboBox()
        self.filetype_combo.addItems(["Tutti", "Solo RAW", "Solo JPEG/PNG"])
        self.filetype_combo.setMinimumWidth(110)
        row2.addWidget(self.filetype_combo)
        row2.addWidget(QLabel("RAW:"))
        self.raw_format_combo = QComboBox()
        self.raw_format_combo.addItem("Tutti")
        self.raw_format_combo.setMinimumWidth(100)
        row2.addWidget(self.raw_format_combo)
        row2.addStretch()
        layout.addLayout(row2)

        # --- Riga 3: Focale e ISO ---
        row3 = QHBoxLayout()
        row3.setSpacing(12)
        row3.addWidget(QLabel("Focale:"))
        self.focal_min = QSpinBox()
        self.focal_min.setRange(0, 2000)
        self.focal_min.setPrefix("≥")
        self.focal_min.setSuffix("mm")
        self.focal_min.setFixedWidth(85)
        row3.addWidget(self.focal_min)
        self.focal_max = QSpinBox()
        self.focal_max.setRange(0, 2000)
        self.focal_max.setValue(2000)
        self.focal_max.setPrefix("≤")
        self.focal_max.setSuffix("mm")
        self.focal_max.setFixedWidth(85)
        row3.addWidget(self.focal_max)
        row3.addWidget(QLabel("ISO:"))
        self.iso_min = QSpinBox()
        self.iso_min.setRange(0, 204800)
        self.iso_min.setPrefix("≥")
        self.iso_min.setFixedWidth(90)
        row3.addWidget(self.iso_min)
        self.iso_max = QSpinBox()
        self.iso_max.setRange(0, 204800)
        self.iso_max.setValue(204800)
        self.iso_max.setPrefix("≤")
        self.iso_max.setFixedWidth(90)
        row3.addWidget(self.iso_max)
        row3.addStretch()
        layout.addLayout(row3)

        # --- Riga 4: Apertura e Flash ---
        row4 = QHBoxLayout()
        row4.setSpacing(12)
        row4.addWidget(QLabel("Aperture:"))
        self.aperture_min = QDoubleSpinBox()
        self.aperture_min.setRange(0.0, 64.0)
        self.aperture_min.setPrefix("f/≥")
        self.aperture_min.setDecimals(1)
        self.aperture_min.setFixedWidth(75)
        row4.addWidget(self.aperture_min)
        self.aperture_max = QDoubleSpinBox()
        self.aperture_max.setRange(0.0, 64.0)
        self.aperture_max.setValue(64.0)
        self.aperture_max.setPrefix("f/≤")
        self.aperture_max.setDecimals(1)
        self.aperture_max.setFixedWidth(75)
        row4.addWidget(self.aperture_max)
        row4.addWidget(QLabel("Flash:"))
        self.flash_combo = QComboBox()
        self.flash_combo.addItems(["Tutti", "Sì", "No"])
        self.flash_combo.setFixedWidth(70)
        row4.addWidget(self.flash_combo)
        row4.addStretch()
        layout.addLayout(row4)

        # --- Riga 5: Exposure e Orientation ---
        row5 = QHBoxLayout()
        row5.setSpacing(12)
        row5.addWidget(QLabel("Exposure:"))
        self.exposure_combo = QComboBox()
        self.exposure_combo.addItems(["Tutti", "Auto", "Manual", "Aperture Priority", "Shutter Priority"])
        self.exposure_combo.setMinimumWidth(130)
        row5.addWidget(self.exposure_combo)
        row5.addWidget(QLabel("Orientation:"))
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["Tutte", "Portrait", "Landscape", "Rotated"])
        self.orientation_combo.setMinimumWidth(100)
        row5.addWidget(self.orientation_combo)
        row5.addStretch()
        layout.addLayout(row5)

        # --- Riga 6: 35mm e EV ---
        row6 = QHBoxLayout()
        row6.setSpacing(12)
        row6.addWidget(QLabel("35mm eq:"))
        self.focal35_min = QSpinBox()
        self.focal35_min.setRange(0, 2000)
        self.focal35_min.setPrefix("≥")
        self.focal35_min.setSuffix("mm")
        self.focal35_min.setFixedWidth(85)
        row6.addWidget(self.focal35_min)
        self.focal35_max = QSpinBox()
        self.focal35_max.setRange(0, 2000)
        self.focal35_max.setValue(2000)
        self.focal35_max.setPrefix("≤")
        self.focal35_max.setSuffix("mm")
        self.focal35_max.setFixedWidth(85)
        row6.addWidget(self.focal35_max)
        row6.addWidget(QLabel("EV:"))
        self.ev_min = QDoubleSpinBox()
        self.ev_min.setRange(-5.0, 5.0)
        self.ev_min.setValue(-5.0)
        self.ev_min.setPrefix("≥")
        self.ev_min.setDecimals(1)
        self.ev_min.setFixedWidth(70)
        row6.addWidget(self.ev_min)
        self.ev_max = QDoubleSpinBox()
        self.ev_max.setRange(-5.0, 5.0)
        self.ev_max.setValue(5.0)
        self.ev_max.setPrefix("≤")
        self.ev_max.setDecimals(1)
        self.ev_max.setFixedWidth(70)
        row6.addWidget(self.ev_max)
        row6.addStretch()
        layout.addLayout(row6)

        return container

    def create_quality_section(self):
        """Filtri qualità"""
        group = QGroupBox("⭐ Qualità & Rating")
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(8, 12, 8, 8)

        # Rating (stelle LR) - riga dedicata
        rating_layout = QHBoxLayout()
        rating_layout.addWidget(QLabel("Rating:"))
        self.rating_min = QComboBox()
        self.rating_min.addItem("Qualsiasi", 0)
        self.rating_min.addItem("≥ ★", 1)
        self.rating_min.addItem("≥ ★★", 2)
        self.rating_min.addItem("≥ ★★★", 3)
        self.rating_min.addItem("≥ ★★★★", 4)
        self.rating_min.addItem("= ★★★★★", 5)
        self.rating_min.setToolTip("Filtra per rating minimo (stelle Lightroom)")
        self.rating_min.setMinimumWidth(110)
        rating_layout.addWidget(self.rating_min)
        rating_layout.addStretch()
        layout.addLayout(rating_layout)

        # Color Label - riga dedicata separata
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Colore:"))
        self.color_label_filter = QComboBox()
        self.color_label_filter.addItem("Tutti", None)
        self.color_label_filter.addItem("🔴 Rosso", "Red")
        self.color_label_filter.addItem("🟡 Giallo", "Yellow")
        self.color_label_filter.addItem("🟢 Verde", "Green")
        self.color_label_filter.addItem("🔵 Blu", "Blue")
        self.color_label_filter.addItem("🟣 Viola", "Purple")
        self.color_label_filter.addItem("Senza colore", "")
        self.color_label_filter.setToolTip("Filtra per color label")
        self.color_label_filter.setMinimumWidth(110)
        color_layout.addWidget(self.color_label_filter)
        color_layout.addStretch()
        layout.addLayout(color_layout)

        # Aesthetic score
        aes_layout = QHBoxLayout()
        aes_layout.addWidget(QLabel("Aesthetic:"))
        self.aesthetic_min = QDoubleSpinBox()
        self.aesthetic_min.setRange(0.0, 10.0)
        self.aesthetic_min.setValue(0.0)
        self.aesthetic_min.setDecimals(1)
        self.aesthetic_min.setPrefix("≥")
        self.aesthetic_min.setMaximumWidth(70)
        aes_layout.addWidget(self.aesthetic_min)
        self.aesthetic_max = QDoubleSpinBox()
        self.aesthetic_max.setRange(0.0, 10.0)
        self.aesthetic_max.setValue(10.0)
        self.aesthetic_max.setDecimals(1)
        self.aesthetic_max.setPrefix("≤")
        self.aesthetic_max.setMaximumWidth(70)
        aes_layout.addWidget(self.aesthetic_max)
        aes_layout.addStretch()
        layout.addLayout(aes_layout)

        # Technical score
        tech_layout = QHBoxLayout()
        tech_layout.addWidget(QLabel("Technical:"))
        self.technical_min = QDoubleSpinBox()
        self.technical_min.setRange(0.0, 100.0)
        self.technical_min.setValue(0.0)
        self.technical_min.setDecimals(1)
        self.technical_min.setPrefix("≥")
        self.technical_min.setMaximumWidth(70)
        tech_layout.addWidget(self.technical_min)
        self.technical_max = QDoubleSpinBox()
        self.technical_max.setRange(0.0, 100.0)
        self.technical_max.setValue(100.0)
        self.technical_max.setDecimals(1)
        self.technical_max.setPrefix("≤")
        self.technical_max.setMaximumWidth(70)
        tech_layout.addWidget(self.technical_max)
        tech_layout.addStretch()
        layout.addLayout(tech_layout)

        group.setLayout(layout)
        return group
    
    def create_gps_section(self):
        """Filtri GPS e Colore"""
        group = QGroupBox("🌍 GPS & Colore")
        layout = QVBoxLayout()
        layout.setSpacing(3)
        
        self.gps_only = QCheckBox("Solo con GPS")
        layout.addWidget(self.gps_only)
        
        # Filtro Bianco/Nero (combo a 3 opzioni)
        row_bn = QHBoxLayout()
        row_bn.addWidget(QLabel("Foto:"))
        self.monochrome_combo = QComboBox()
        self.monochrome_combo.addItems(["Tutte", "Colori", "B/N"])
        self.monochrome_combo.setToolTip("Filtra per tipo colore immagine")
        self.monochrome_combo.setFixedWidth(80)
        row_bn.addWidget(self.monochrome_combo)
        row_bn.addStretch()
        layout.addLayout(row_bn)
        
        group.setLayout(layout)
        return group
    
    def create_sync_section(self):
        """Filtri sync"""
        group = QGroupBox("🔄 Sync")
        layout = QVBoxLayout()
        layout.setSpacing(3)
        
        self.sync_filter = QCheckBox("Solo out-of-sync")
        self.sync_filter.setToolTip("Solo immagini modificate dopo ultimo sync XMP")
        layout.addWidget(self.sync_filter)
        
        group.setLayout(layout)
        return group
    
    def create_date_section(self):
        """Filtri data"""
        group = QGroupBox("📅 Data")
        layout = QVBoxLayout()
        layout.setSpacing(3)
        
        self.date_filter_enabled = QCheckBox("Filtra per data:")
        layout.addWidget(self.date_filter_enabled)
        
        date_layout = QHBoxLayout()
        
        self.date_from = QDateEdit()
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_from.setCalendarPopup(True)
        self.date_from.setEnabled(False)
        date_layout.addWidget(self.date_from)
        
        date_layout.addWidget(QLabel("→"))
        
        self.date_to = QDateEdit()
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setEnabled(False)
        date_layout.addWidget(self.date_to)
        
        layout.addLayout(date_layout)
        
        self.date_filter_enabled.toggled.connect(self.date_from.setEnabled)
        self.date_filter_enabled.toggled.connect(self.date_to.setEnabled)
        
        group.setLayout(layout)
        return group
    
    def create_action_buttons(self):
        """Bottoni azione"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(5)
        
        self.search_btn = QPushButton("🔍 CERCA")
        self.search_btn.clicked.connect(self.execute_search)
        self.search_btn.setStyleSheet("font-weight: bold; padding: 8px; background-color: #2e7d32;")
        layout.addWidget(self.search_btn)
        
        self.clear_btn = QPushButton("🗑 RESET")
        self.clear_btn.clicked.connect(self.clear_filters)
        layout.addWidget(self.clear_btn)
        
        return widget
    
    def load_config_defaults(self):
        """Carica defaults dal config"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            search_config = self.config.get('search', {})
            self.threshold_spin.setValue(search_config.get('semantic_threshold', 0.15))
            self.max_results_spin.setValue(search_config.get('max_results', 100))
            self.fuzzy_check.setChecked(search_config.get('fuzzy_enabled', True))
        except:
            pass
    
    def clear_filters(self):
        """
        Reset con auto-discovery dei parametri config.
        Se esiste config.search.widget_name → usa quel valore
        Altrimenti → usa default hardcoded
        MANTIENE il valore max_results corrente dell'utente
        """
    
        # Salva il valore corrente di max_results prima del reset
        current_max_results = self.max_results_spin.value()
    
        # Carica config
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                print("✅ Config caricato correttamente")
        except Exception as e:
            config = {}
            print(f"⚠️ Errore caricamento config: {e}")
    
        search_config = config.get('search', {})
    
        # DEFAULT HARDCODED (fallback) - usa current_max_results invece di 100
        defaults = {
            'semantic_radio': True,
            'tags_radio': False,
            'description_check': True,
            'fuzzy_check': True,
            'deep_search_check': False,
            'threshold_spin': 0.2,
            'max_results_spin': current_max_results,  # MANTIENE valore utente
            'strict_slider': 40,
            'search_input': '',
            'camera_combo': 0, 'lens_combo': 0, 'filetype_combo': 0, 'raw_format_combo': 0,
            'flash_combo': 0, 'exposure_combo': 0, 'orientation_combo': 0,
            'rating_min': 0, 'color_label_filter': 0,  # NUOVO: rating e color label
            'focal_min': 0, 'focal_max': 2000, 'iso_min': 0, 'iso_max': 204800,
            'aperture_min': 0.0, 'aperture_max': 64.0, 'focal35_min': 0, 'focal35_max': 2000,
            'ev_min': -5.0, 'ev_max': 5.0, 'aesthetic_min': 0.0, 'aesthetic_max': 10.0,
            'technical_min': 0.0, 'technical_max': 100.0,
            'gps_only': False, 'monochrome_combo': 0, 'sync_filter': False,
            'date_filter_enabled': False
        }
        
        # Raccogli widget esistenti
        all_widgets = []
        missing_widgets = []
        for widget_name in defaults.keys():
            widget = getattr(self, widget_name, None)
            if widget:
                all_widgets.append(widget)
            else:
                missing_widgets.append(widget_name)
                
        print(f"✅ Widget esistenti: {len(all_widgets)}")
        if missing_widgets:
            print(f"⚠️ Widget mancanti: {missing_widgets}")
    
        # Blocca segnali
        for w in all_widgets:
            try:
                w.blockSignals(True)
            except Exception as e:
                print(f"❌ Errore blocco segnali: {e}")
                pass
    
        reset_success = 0
        reset_errors = 0
        
        try:
            # AUTO-RESET CON CONFIG DISCOVERY
            for widget_name, default_value in defaults.items():
                widget = getattr(self, widget_name, None)
                if widget is None:
                    continue
                
                try:
                    # CERCA IN CONFIG (prova diverse convenzioni di naming)
                    config_keys = [
                        widget_name,                           # nome_widget
                        widget_name.replace('_', ''),          # nomewidget  
                        widget_name.replace('_spin', ''),      # threshold
                        widget_name.replace('_check', ''),     # fuzzy
                        widget_name.replace('_combo', ''),     # camera
                    ]
                
                    # Cerca il primo match nel config
                    final_value = default_value
                    for key in config_keys:
                        if key in search_config:
                            final_value = search_config[key]
                            break
                
                    # Applica il valore in modo sicuro
                    if hasattr(widget, 'setChecked'):
                        widget.setChecked(bool(final_value))
                    elif hasattr(widget, 'setValue'):
                        widget.setValue(final_value)
                        # Caso speciale: se è lo strict_slider, aggiorna anche il label
                        if widget_name == 'strict_slider' and hasattr(self, 'strict_val_label'):
                            self.strict_val_label.setText(f"{final_value}%")
                    elif hasattr(widget, 'setCurrentIndex'):
                        widget.setCurrentIndex(int(final_value))
                    elif hasattr(widget, 'clear') and final_value == '':
                        widget.clear()
                    elif hasattr(widget, 'setText') and isinstance(final_value, str):
                        widget.setText(final_value)
                        
                    reset_success += 1
                except Exception as e:
                    reset_errors += 1
                    print(f"❌ Errore reset widget {widget_name}: {e}")
                    continue
        
            print(f"📊 Reset completato: {reset_success} successi, {reset_errors} errori")
        
            # Date speciali con controllo sicurezza
            try:
                if hasattr(self, "date_from") and self.date_from:
                    self.date_from.setDate(self.date_from.minimumDate())
                    self.date_from.setEnabled(False)
                    print("✅ date_from reset")
            except Exception as e:
                print(f"⚠️ Errore reset date_from: {e}")
                pass
                
            try:
                if hasattr(self, "date_to") and self.date_to:
                    self.date_to.setDate(self.date_to.maximumDate())
                    self.date_to.setEnabled(False)
                    print("✅ date_to reset")
            except Exception as e:
                print(f"⚠️ Errore reset date_to: {e}")
                pass
        
        finally:
            for w in all_widgets:
                try:
                    w.blockSignals(False)
                except Exception as e:
                    print(f"❌ Errore sblocco segnali: {e}")
                    pass
        
            try:
                self.update_search_mode()
                self.update_deep_search_mode()
                print("✅ Modi di ricerca aggiornati")
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Errore aggiornamento modi: {e}")
                

    def update_search_progress(self, count):
        """Aggiorna il conteggio dinamico durante la ricerca"""
        if self.search_active and not self.search_cancelled:
            self.count_label.setText(f"Trovate: {count} immagini")
            # Forza l'aggiornamento della UI
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.processEvents()

    
   
    
    def on_activated(self):
        """Carica opzioni dinamiche dal DB"""
        self.log_message("🔧 Avvio caricamento filtri dinamici...", "info")
        
        try:
            # Verifica che esista il file config
            if not Path(self.config_path).exists():
                self.log_message(f"❌ Config non trovato: {self.config_path}", "error")
                return
                
            self.log_message(f"✓ Config trovato: {self.config_path}", "info")
                
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Verifica path database
            if 'paths' not in config or 'database' not in config['paths']:
                self.log_message("❌ Path database non configurato nel config", "error")
                return
                
            db_path = config['paths']['database']
            self.log_message(f"📄 Database path dal config: {db_path}", "info")
            
            if not Path(db_path).exists():
                self.log_message(f"❌ Database non trovato: {db_path}", "error")
                return
            
            self.log_message(f"✓ Database trovato: {db_path}", "info")
            
            # Import qui per evitare problemi di percorso
            import sys
            app_dir_str = str(get_app_dir())
            if app_dir_str not in sys.path:
                sys.path.insert(0, app_dir_str)
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(db_path)
            
            self.log_message("✓ DatabaseManager inizializzato", "info")
            
            # Camera - usa colonne database (consistente con ricerca)
            try:
                query = """
                    SELECT DISTINCT camera_make, camera_model
                    FROM images 
                    WHERE camera_model IS NOT NULL AND camera_model != '' AND camera_model != 'Unknown'
                    ORDER BY camera_make, camera_model
                """
                self.log_message("🔍 Eseguo query camera dalle colonne DB...", "info")
                
                db_manager.cursor.execute(query)
                camera_data = db_manager.cursor.fetchall()
                
                # Combina Make + Model per le camera
                cameras = []
                for make, model in camera_data:
                    if make and model:
                        camera_full = f"{make} {model}"
                        if camera_full not in cameras:
                            cameras.append(camera_full)
                    elif model:
                        if model not in cameras:
                            cameras.append(model)
                
                cameras.sort()
                
                self.log_message(f"📷 Trovate {len(cameras)} camera nel database", "info")
                if cameras:
                    self.log_message(f"Prime 3 camera: {cameras[:3]}", "info")
                
                current_camera = self.camera_combo.currentText()
                self.camera_combo.clear()
                self.camera_combo.addItem("Tutte")
                
                if cameras:
                    self.camera_combo.addItems(cameras)
                    self.log_message(f"✓ Caricate {len(cameras)} camera nella combo", "info")
                else:
                    self.log_message("⚠️ Nessuna camera trovata nel database", "warning")
                
                # Ripristina selezione precedente se esisteva
                if current_camera and current_camera != "Tutte":
                    idx = self.camera_combo.findText(current_camera)
                    if idx >= 0:
                        self.camera_combo.setCurrentIndex(idx)
                        self.log_message(f"✓ Ripristinata selezione camera: {current_camera}", "info")
                    
            except Exception as e:
                self.log_message(f"❌ Errore caricamento camera: {e}", "error")
                import traceback
                self.log_message(f"Traceback: {traceback.format_exc()}", "error")
            
            # Lens
            try:
                query = """
                    SELECT DISTINCT lens_model 
                    FROM images 
                    WHERE lens_model IS NOT NULL AND lens_model != '' AND lens_model != 'Unknown'
                    ORDER BY lens_model
                """
                self.log_message("🔍 Eseguo query lens...", "info")
                
                db_manager.cursor.execute(query)
                lenses = [row[0] for row in db_manager.cursor.fetchall()]
                
                self.log_message(f"🔭 Trovate {len(lenses)} lens nel database", "info")
                if lenses:
                    self.log_message(f"Prime 3 lens: {lenses[:3]}", "info")
                
                current_lens = self.lens_combo.currentText()
                self.lens_combo.clear()
                self.lens_combo.addItem("Tutte")
                
                if lenses:
                    self.lens_combo.addItems(lenses)
                    self.log_message(f"✓ Caricate {len(lenses)} lens nella combo", "info")
                else:
                    self.log_message("⚠️ Nessuna lens trovata nel database", "warning")
                
                # Ripristina selezione precedente se esisteva
                if current_lens and current_lens != "Tutte":
                    idx = self.lens_combo.findText(current_lens)
                    if idx >= 0:
                        self.lens_combo.setCurrentIndex(idx)
                        self.log_message(f"✓ Ripristinata selezione lens: {current_lens}", "info")
                    
            except Exception as e:
                self.log_message(f"❌ Errore caricamento lens: {e}", "error")
                import traceback
                self.log_message(f"Traceback: {traceback.format_exc()}", "error")
            
            # Formati RAW
            try:
                query = """
                    SELECT DISTINCT raw_format, COUNT(*) as count
                    FROM images 
                    WHERE is_raw = 1 AND raw_format IS NOT NULL AND raw_format != ''
                                GROUP BY raw_format
                               ORDER BY count DESC, raw_format
                """
                self.log_message("🔍 Eseguo query formati RAW...", "info")
                
                db_manager.cursor.execute(query)
                formats_data = db_manager.cursor.fetchall()
                
                # Formatta con conteggio
                formats = []
                for fmt, count in formats_data:
                    display_name = f"{fmt.upper()} ({count})" if count > 1 else fmt.upper()
                    formats.append((fmt, display_name))
                
                self.log_message(f"📁 Trovati {len(formats)} formati RAW nel database", "info")
                
                current_format = self.raw_format_combo.currentText()
                self.raw_format_combo.clear()
                self.raw_format_combo.addItem("Tutti")
                
                if formats:
                    for fmt_value, fmt_display in formats:
                        self.raw_format_combo.addItem(fmt_display)
                        # Salva il valore reale come user data
                        self.raw_format_combo.setItemData(self.raw_format_combo.count()-1, fmt_value)
                    
                    self.log_message(f"✓ Caricati {len(formats)} formati RAW nella combo", "info")
                else:
                    self.log_message("⚠️ Nessun formato RAW trovato nel database", "warning")
                    
            except Exception as e:
                self.log_message(f"❌ Errore caricamento formati RAW: {e}", "error")
                import traceback
                self.log_message(f"Traceback: {traceback.format_exc()}", "error")
            
            db_manager.close()
            self.log_message("✓ Caricamento filtri completato", "info")
            
        except Exception as e:
            self.log_message(f"❌ Errore generale caricamento filtri: {e}", "error")
            import traceback
            self.log_message(f"Traceback: {traceback.format_exc()}", "error")
    
    def _has_filters(self):
        """Controlla se almeno un filtro è stato impostato"""
        # Camera/Lens/File Type
        if self.camera_combo.currentText() != "Tutte":
            return True
        if self.lens_combo.currentText() != "Tutte":
            return True
        if self.filetype_combo.currentText() != "Tutti":
            return True  
        if self.raw_format_combo.currentText() != "Tutti":
            return True
            
        # Focale
        if self.focal_min.value() > 0:
            return True
        if self.focal_max.value() < 2000:
            return True
            
        # ISO
        if self.iso_min.value() > 0:
            return True
        if self.iso_max.value() < 204800:
            return True
            
        # Apertura
        if self.aperture_min.value() > 0.0:
            return True
        if self.aperture_max.value() < 64.0:
            return True
            
        # Flash
        if self.flash_combo.currentText() != "Tutti":
            return True
            
        # Exposure mode
        if self.exposure_combo.currentText() != "Tutti":
            return True
            
        # Focale 35mm
        if self.focal35_min.value() > 0:
            return True
        if self.focal35_max.value() < 2000:
            return True
            
        # EV
        if self.ev_min.value() > -5.0:
            return True
        if self.ev_max.value() < 5.0:
            return True
            
        # Orientamento
        if self.orientation_combo.currentText() != "Tutti":
            return True
            
        # Data originale
        if self.date_original_enabled.isChecked():
            return True
            
        # Qualità
        if self.aesthetic_min.value() > 0.0:
            return True
        if self.aesthetic_max.value() < 10.0:
            return True
        if self.technical_min.value() > 0.0:
            return True
        if self.technical_max.value() < 100.0:
            return True

        # Rating e Color Label
        if self.rating_min.currentIndex() > 0:
            return True
        if self.color_label_filter.currentIndex() > 0:
            return True

        # GPS
        if self.gps_only.isChecked():
            return True
        
        # Filtro B/N
        if self.monochrome_combo.currentIndex() != 0:
            return True
            
        # Sync
        if self.sync_filter.isChecked():
            return True
            
        # Data
        if self.date_filter_enabled.isChecked():
            return True
            
        return False
