"""
Main Window - Finestra principale OffGallery
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, 
    QVBoxLayout, QHBoxLayout, QStatusBar, QMessageBox, 
    QSizePolicy, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QSettings
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
from xmp_badge_manager import refresh_xmp_badges
from xmp_badge_manager import shutdown_badge_manager


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
    
    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.app_title = QLabel("Sistema di Catalogazione e Ricerca AI Multimodello di Immagini")
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
        self.subtitle_label = QLabel("Architettura Offline Privacy-First")
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
        
        brand_layout.addStretch()
        
        # QWidget per il brand si espande orizzontalmente
        brand_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(brand_widget, stretch=1)  # Stretch per occupare spazio
        
        # ============ MODEL VERSIONS (DESTRA) ============
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(20, 10, 0, 10)
        info_layout.setSpacing(3)
        
        # Lista modelli con versioni
        models = [
            "CLIP v1.5.1",
            "DINOv2 v2.0", 
            "BioCLIP v1.0",
            "qwen3-vl:4b-instruct",
            "ChromaDB v0.4.x",
            "Ollama v0.14.1"
        ]
        
        for model in models:
            model_label = QLabel(model)
            model_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 11px;
                    color: {COLORS['grigio_medio']};
                    font-weight: normal;
                }}
            """)
            model_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            info_layout.addWidget(model_label)
        
        info_layout.addStretch()
        info_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(info_widget, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    
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
    
    def __init__(self):
        super().__init__()
        
        # Settings per salvare preferenze utente
        self.settings = QSettings('OffGallery', 'OffGalleryApp')

        self.config_path = Path("config_new.yaml")
        # Setup UI

        # === INIZIALIZZAZIONE MODELLI AI CENTRALIZZATA ===
        import yaml
        from embedding_generator import EmbeddingGenerator

        # Carica configurazione
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # Inizializza i modelli AI (non bloccante: l'app parte anche se fallisce)
        self.ai_models = {'initialized': False}
        try:
            self.ai_models['embedding_generator'] = EmbeddingGenerator(self.config)
            self.ai_models['initialized'] = True
            print("✅ Modelli AI centralizzati inizializzati")
        except Exception as e:
            import traceback
            print(f"⚠️ Modelli AI non inizializzati: {e}")
            print("   L'app si avvia ugualmente. Processing non disponibile finché i modelli non sono pronti.")
            print(traceback.format_exc())

        # Warmup Ollama in background (pre-carica LLM in VRAM)
        import threading
        def _ollama_warmup():
            try:
                self.ai_models['embedding_generator'].warmup_ollama()
            except Exception as e:
                print(f"⚠️ Ollama warmup fallito: {e}")
        threading.Thread(target=_ollama_warmup, daemon=True).start()

        # === INIZIALIZZAZIONE DATABASE CENTRALIZZATA ===
        from db_manager_new import DatabaseManager
        
        # Inizializza database manager se configurato
        self.db_manager = None
        if 'paths' in self.config and 'database' in self.config['paths']:
            db_path = self.config['paths']['database']
            if db_path:
                try:
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
        self.setWindowTitle("OffGallery")
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
        self.header = AppHeader()
        layout.addWidget(self.header)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Pronto")
        
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
        else:
            print("⚠️ Database manager non disponibile - tab funzioneranno in modalità limitata")

        
        # Aggiungi tab con icone più grandi
        self.tabs.addTab(self.config_tab, "⚙  Configurazione")
        self.tabs.addTab(self.processing_tab, "▶  Processing")
        self.tabs.addTab(self.search_tab, "🔍  Ricerca")
        self.tabs.addTab(self.gallery_tab, "🖼  Gallery")
        self.tabs.addTab(self.export_tab, "📤 Export")
        self.tabs.addTab(self.stats_tab, "📊  Statistiche")
        self.tabs.addTab(self.log_tab, "📝  Log")
                
        # Connetti segnali
        self.search_tab.search_executed.connect(self.on_search_completed)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.export_tab.export_completed.connect(self.on_export_completed)
        
        layout.addWidget(self.tabs)
        
           
   
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
        about_box.setWindowTitle("About OffGallery")
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
