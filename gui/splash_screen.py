"""
Splash Screen - Mostra log di caricamento durante l'avvio
"""

import sys
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QApplication, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap
from pathlib import Path

from utils.paths import get_app_dir

# Riferimento globale alla splash per accesso dai log
_splash_instance = None

# Buffer globale per salvare i log di avvio (accessibile dal LogTab)
startup_logs = []


def get_startup_logs():
    """Ritorna i log di avvio per il LogTab"""
    return startup_logs.copy()


class LogCapture:
    """Cattura stdout/stderr e li inoltra alla splash screen"""

    def __init__(self, original_stream, is_stderr=False):
        self.original = original_stream
        self.is_stderr = is_stderr
        self.buffer = []

    def write(self, text):
        # Aggiungi alla splash se esiste e testo non vuoto
        if text.strip() and _splash_instance:
            try:
                _splash_instance.add_log(text.rstrip())
            except:
                # Fallback: scrivi su terminale se splash fallisce
                if self.original:
                    self.original.write(text)
                    self.original.flush()

    def flush(self):
        if self.original:
            self.original.flush()


class SplashLogHandler(logging.Handler):
    """Handler per catturare log dal modulo logging"""

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter('%(message)s'))

    def emit(self, record):
        if _splash_instance:
            try:
                msg = self.format(record)
                _splash_instance.add_log(msg)
            except:
                pass


class SplashScreen(QWidget):
    """Splash screen con log di caricamento"""

    def __init__(self):
        super().__init__()
        global _splash_instance
        _splash_instance = self

        self.setWindowTitle("OffGallery - Caricamento")
        self.setFixedSize(600, 450)

        # Finestra senza bordi ma con titolo
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        # Centra sullo schermo
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

        self._build_ui()

        # Contatore per progress
        self._log_count = 0

    def _build_ui(self):
        """Costruisce interfaccia splash"""
        self.setStyleSheet("""
            QWidget {
                background-color: #2A2A2A;
                color: #E3E3E3;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Logo
        logo_path = get_app_dir() / 'assets' / 'logo3.jpg'
        if logo_path.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(logo_path))
            scaled = pixmap.scaledToHeight(100, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)
        else:
            title = QLabel("OffGallery")
            title.setFont(QFont("Arial", 28, QFont.Weight.Bold))
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet("color: #C88B2E;")
            layout.addWidget(title)

        # Sottotitolo
        self.subtitle = QLabel("Caricamento modelli AI...")
        self.subtitle.setFont(QFont("Arial", 12))
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setStyleSheet("color: #B0B0B0;")
        layout.addWidget(self.subtitle)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(10)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3A3A3A;
                background-color: #1E1E1E;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #C88B2E, stop:1 #E0A84A);
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress)

        # Area log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #A0A0A0;
                border: 1px solid #3A3A3A;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.log_text, 1)

    def add_log(self, message):
        """Aggiunge messaggio al log e aggiorna progress"""
        global startup_logs

        # Salva nel buffer globale per LogTab
        timestamp = datetime.now().strftime("%H:%M:%S")
        # Determina livello dal contenuto
        if '❌' in message or 'ERROR' in message.upper():
            level = "ERROR"
        elif '⚠️' in message or 'WARNING' in message.upper():
            level = "WARNING"
        elif '✅' in message:
            level = "INFO"
        else:
            level = "DEBUG"
        startup_logs.append((timestamp, level, message))

        # Mostra nella splash
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

        # Aggiorna progress (cresce con i messaggi, max 95%)
        self._log_count += 1
        progress_val = min(95, self._log_count * 3)
        self.progress.setValue(progress_val)

        # Aggiorna sottotitolo con ultimo messaggio significativo
        if any(x in message for x in ['✅', '🔧', 'Caric', 'Inizial', 'Loading']):
            short_msg = message[:50] + "..." if len(message) > 50 else message
            self.subtitle.setText(short_msg)

        # IMPORTANTE: forza aggiornamento UI
        QApplication.processEvents()

    def finish(self):
        """Completa il caricamento"""
        self.progress.setValue(100)
        self.subtitle.setText("✅ Caricamento completato!")
        QApplication.processEvents()


def setup_log_capture():
    """Imposta cattura log PRIMA di creare la splash"""
    global _original_stdout, _original_stderr, _log_handler

    _original_stdout = sys.stdout
    _original_stderr = sys.stderr

    sys.stdout = LogCapture(_original_stdout)
    sys.stderr = LogCapture(_original_stderr, is_stderr=True)

    # Handler per logging module
    _log_handler = SplashLogHandler()
    _log_handler.setLevel(logging.DEBUG)

    # Aggiungi a tutti i logger comuni
    root_logger = logging.getLogger()
    root_logger.addHandler(_log_handler)
    root_logger.setLevel(logging.DEBUG)


def restore_log_capture():
    """Ripristina stdout/stderr originali"""
    global _original_stdout, _original_stderr, _log_handler, _splash_instance

    sys.stdout = _original_stdout
    sys.stderr = _original_stderr

    # Rimuovi handler
    try:
        logging.getLogger().removeHandler(_log_handler)
    except:
        pass

    _splash_instance = None


def run_with_splash():
    """Avvia applicazione con splash screen"""
    # Setup cattura log PRIMA di tutto
    setup_log_capture()

    print("🚀 Avvio OffGallery...")

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Palette scura
    from PyQt6.QtGui import QPalette, QColor
    COLORS = {
        'grafite': '#2A2A2A',
        'grafite_light': '#3A3A3A',
        'grigio_chiaro': '#E3E3E3',
        'blu_petrolio': '#1C4F63',
    }
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

    # Crea e mostra splash
    splash = SplashScreen()
    splash.show()
    splash.add_log("🚀 Inizializzazione OffGallery...")
    QApplication.processEvents()

    # Import e creazione MainWindow (genera i log)
    print("📦 Caricamento moduli...")

    from gui.main_window import MainWindow, shutdown_badge_manager

    print("🔧 Inizializzazione interfaccia...")
    window = MainWindow()

    # Completa splash
    splash.finish()
    QApplication.processEvents()

    # Breve pausa per mostrare "completato"
    import time
    time.sleep(0.3)

    # Ripristina streams e chiudi splash
    restore_log_capture()
    splash.close()

    # Mostra finestra principale
    window.show()

    app.aboutToQuit.connect(shutdown_badge_manager)
    sys.exit(app.exec())
