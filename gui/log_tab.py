"""
Log Tab - Sistema di logging centralizzato
Cattura tutti i log dell'applicazione e li mostra in un widget scrollabile
"""

import sys
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QPushButton, QLabel, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor

# Palette colori
COLORS = {
    'grafite': '#2A2A2A',
    'grafite_light': '#3A3A3A', 
    'grafite_dark': '#1E1E1E',
    'grigio_chiaro': '#E3E3E3',
    'grigio_medio': '#B0B0B0',
    'blu_petrolio': '#1C4F63',
    'verde': '#4A7C59',
    'ambra': '#C88B2E',
    'rosso': '#8B4049',
}

class LogHandler(logging.Handler, QObject):
    """Custom logging handler che emette segnali PyQt"""
    log_received = pyqtSignal(str, str, str)  # timestamp, level, message
    
    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        
    def emit(self, record):
        try:
            timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            level = record.levelname
            message = self.format(record)
            self.log_received.emit(timestamp, level, message)
        except Exception:
            pass  # Non possiamo loggare errori del logging handler


class LogTab(QWidget):
    """Tab per visualizzazione centralizzata dei log"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.log_handler = None
        self._log_entries = []  # Lista di (timestamp, level, message) per filtraggio
        self._max_entries = 500  # Limite massimo entry in memoria e display
        self._is_filtering = False  # Guard per evitare ricorsione durante filter
        self.init_ui()
        self.setup_logging()
        
    def init_ui(self):
        """Inizializza UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Header
        header_layout = QHBoxLayout()
        
        # Titolo
        title = QLabel("📝 Log Console")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['grigio_chiaro']};
                font-size: 16px;
                font-weight: bold;
                padding: 5px;
            }}
        """)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Filtri livello log
        self.level_filters = {}
        levels = [
            ("DEBUG", COLORS['grigio_medio']),
            ("INFO", COLORS['blu_petrolio']),
            ("WARNING", COLORS['ambra']),
            ("ERROR", COLORS['rosso'])
        ]
        
        for level, color in levels:
            cb = QCheckBox(level)
            cb.setChecked(True)
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {color};
                    font-weight: bold;
                    font-size: 11px;
                }}
                QCheckBox::indicator {{
                    width: 12px;
                    height: 12px;
                }}
                QCheckBox::indicator:checked {{
                    background-color: {color};
                    border: 1px solid {color};
                }}
            """)
            cb.toggled.connect(self.filter_logs)
            self.level_filters[level] = cb
            header_layout.addWidget(cb)
        
        # Bottone clear
        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.setFixedSize(80, 30)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['grafite_light']};
                color: {COLORS['grigio_chiaro']};
                border: 1px solid {COLORS['grigio_medio']};
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS['rosso']};
            }}
        """)
        clear_btn.clicked.connect(self.clear_logs)
        header_layout.addWidget(clear_btn)
        
        layout.addLayout(header_layout)
        
        # Separatore
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"color: {COLORS['grafite_light']};")
        layout.addWidget(separator)
        
        # Area log principale
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.log_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['grafite_dark']};
                color: {COLORS['grigio_chiaro']};
                border: 1px solid {COLORS['grafite_light']};
                border-radius: 4px;
                padding: 8px;
                font-family: 'Courier New', 'Consolas', monospace;
                font-size: 11px;
                selection-background-color: {COLORS['blu_petrolio']};
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['grafite']};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['grafite_light']};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['grigio_medio']};
            }}
        """)
        
        # Font monospace per allineamento
        font = QFont("Courier New", 10)
        self.log_display.setFont(font)
        
        layout.addWidget(self.log_display)
        
        # Footer info
        self.info_label = QLabel("Sessione avviata - Log azzerati")
        self.info_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['grigio_medio']};
                font-size: 10px;
                padding: 5px;
            }}
        """)
        layout.addWidget(self.info_label)
        
    def setup_logging(self):
        """Configura il sistema di logging centralizzato"""
        # Crea handler personalizzato
        self.log_handler = LogHandler()
        self.log_handler.log_received.connect(self.append_log)
        
        # Formato log
        formatter = logging.Formatter('%(name)s - %(message)s')
        self.log_handler.setFormatter(formatter)
        
        # Aggiungi al root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        root_logger.setLevel(logging.DEBUG)
        
        # Intercetta print() sostituendo stdout
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = LogCapture(self, "INFO")
        sys.stderr = LogCapture(self, "ERROR")
        
        # Carica log di avvio dalla splash screen
        self._load_startup_logs()

        # Log iniziale
        self.log_info("Log tab initialized - Session started")
        
    def _format_log_entry(self, timestamp, level, message):
        """Formatta un singolo log entry in HTML"""
        colors = {
            "DEBUG": COLORS['grigio_medio'],
            "INFO": COLORS['blu_petrolio'],
            "WARNING": COLORS['ambra'],
            "ERROR": COLORS['rosso'],
            "CRITICAL": COLORS['rosso']
        }
        color = colors.get(level, COLORS['grigio_chiaro'])
        return (f'<span style="color: {COLORS["grigio_medio"]}">[{timestamp}]</span> '
                f'<span style="color: {color}; font-weight: bold;">{level:8}</span> - '
                f'<span style="color: {COLORS["grigio_chiaro"]}">{message}</span>')

    def _is_level_visible(self, level):
        """Controlla se un livello log e' visibile in base ai filtri"""
        # CRITICAL segue il filtro ERROR
        check_level = "ERROR" if level == "CRITICAL" else level
        cb = self.level_filters.get(check_level)
        return cb.isChecked() if cb else True

    def append_log(self, timestamp, level, message):
        """Aggiunge un nuovo log entry"""
        # Salva in lista per filtraggio, con limite memoria
        self._log_entries.append((timestamp, level, message))
        if len(self._log_entries) > self._max_entries:
            self._log_entries = self._log_entries[-self._max_entries:]

        # Mostra solo se il livello e' attivo nei filtri
        if not self._is_level_visible(level):
            return

        formatted = self._format_log_entry(timestamp, level, message)

        # Aggiungi al display
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(formatted + "<br>")

        # Limita buffer display a max_entries righe per evitare degrado GUI
        doc = self.log_display.document()
        if doc.blockCount() > self._max_entries:
            cursor = self.log_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.Down,
                                QTextCursor.MoveMode.KeepAnchor,
                                doc.blockCount() - self._max_entries)
            cursor.removeSelectedText()
            cursor.deleteChar()

        # Auto-scroll verso il basso
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Aggiorna contatore
        self.update_info()
        
    def filter_logs(self):
        """Ri-renderizza i log in base ai filtri livello attivi"""
        if self._is_filtering:
            return
        self._is_filtering = True
        try:
            self.log_display.clear()
            for timestamp, level, message in self._log_entries:
                if self._is_level_visible(level):
                    formatted = self._format_log_entry(timestamp, level, message)
                    cursor = self.log_display.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    cursor.insertHtml(formatted + "<br>")
            # Scroll in fondo
            scrollbar = self.log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        finally:
            self._is_filtering = False
        
    def clear_logs(self):
        """Cancella tutti i log"""
        self._log_entries.clear()
        self.log_display.clear()
        self.log_info("Log cleared by user")
        
    def update_info(self):
        """Aggiorna info footer"""
        current_time = datetime.now().strftime("%H:%M:%S")
        self.info_label.setText(f"Ultimo aggiornamento: {current_time}")
        
    def _load_startup_logs(self):
        """Carica i log di avvio dalla splash screen"""
        try:
            from gui.splash_screen import get_startup_logs
            startup_logs = get_startup_logs()
            if startup_logs:
                # Aggiungi header
                self.append_log(
                    datetime.now().strftime("%H:%M:%S"),
                    "INFO",
                    "═══ LOG AVVIO APPLICAZIONE ═══"
                )
                # Aggiungi tutti i log di avvio
                for timestamp, level, message in startup_logs:
                    self.append_log(timestamp, level, message)
                # Aggiungi separatore
                self.append_log(
                    datetime.now().strftime("%H:%M:%S"),
                    "INFO",
                    "═══ FINE LOG AVVIO ═══"
                )
        except ImportError:
            pass  # splash_screen non disponibile
        except Exception as e:
            print(f"Errore caricamento startup logs: {e}")

    # Metodi convenience per logging
    def log_debug(self, message):
        logging.debug(message)
        
    def log_info(self, message):
        logging.info(message)
        
    def log_warning(self, message):
        logging.warning(message)
        
    def log_error(self, message):
        logging.error(message)
        
    def cleanup(self):
        """Cleanup risorse quando si chiude"""
        if self.log_handler:
            logging.getLogger().removeHandler(self.log_handler)
        
        # Ripristina stdout/stderr originali
        sys.stdout = self.original_stdout 
        sys.stderr = self.original_stderr


class LogCapture:
    """Cattura output di print() e lo redirige al log"""
    
    def __init__(self, log_tab, level="INFO"):
        self.log_tab = log_tab
        self.level = level
        
    def write(self, message):
        # Filtra messaggi vuoti o solo newline
        if message.strip():
            if self.level == "ERROR":
                self.log_tab.log_error(message.strip())
            else:
                self.log_tab.log_info(message.strip())
                
    def flush(self):
        pass  # Non necessario per il nostro uso
