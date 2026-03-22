"""
Splash Screen - Mostra log di caricamento durante l'avvio
"""

import re
import sys
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit,
    QApplication, QProgressBar
)
from PyQt6.QtCore import Qt, QEventLoop
from PyQt6.QtGui import QFont, QPixmap
from pathlib import Path

from utils.paths import get_app_dir
from i18n import t, load_language

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
        # Forza aggiornamento UI ad ogni write — inclusi i \r di tqdm durante i download.
        # Senza questo, il main thread rimane bloccato per minuti e Windows mostra
        # "Non risponde" perché processEvents() viene chiamato solo da add_log().
        if _splash_instance and not _splash_instance._processing_events:
            _splash_instance._processing_events = True
            try:
                QApplication.processEvents(
                    QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                )
            except Exception:
                pass
            finally:
                _splash_instance._processing_events = False

        if not text:
            return

        if text.startswith('\r'):
            # Aggiornamento progress bar tqdm (es. download HuggingFace):
            # non aggiungere al log principale, ma aggiorna il sottotitolo
            # così l'utente vede qualcosa che "si muove" durante i download lunghi.
            if _splash_instance:
                clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text).strip('\r\n')
                if len(clean) > 5:
                    short = f"⬇️ {clean[:65]}…" if len(clean) > 65 else f"⬇️ {clean}"
                    try:
                        _splash_instance.subtitle.setText(short)
                    except Exception:
                        pass
        else:
            if text.strip() and _splash_instance:
                try:
                    _splash_instance.add_log(text.rstrip())
                except Exception:
                    if self.original:
                        self.original.write(text)
                        self.original.flush()

    def flush(self):
        if self.original:
            self.original.flush()

    def isatty(self):
        # Ritorna True per permettere a tqdm/huggingface_hub di scrivere aggiornamenti
        # continui con \r durante i download. Questi aggiornamenti triggerano processEvents()
        # in write() e mantengono la splash animata — senza questo Windows mostra
        # "Non risponde" durante download da 1-2 GB.
        return True

    def fileno(self):
        # Necessario per compatibilità con io.IOBase; ritorniamo quello
        # del flusso originale se disponibile, altrimenti solleviamo
        # l'eccezione standard per stream non-file.
        if self.original and hasattr(self.original, 'fileno'):
            return self.original.fileno()
        import io
        raise io.UnsupportedOperation("fileno")


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

        self.setWindowTitle(t("splash.window.title"))
        self.setFixedSize(600, 450)

        # Barra di sistema nativa: il caricamento è sincrono (main thread bloccato)
        # quindi solo i controlli gestiti dal window manager (minimizza dal taskbar)
        # funzionano. Disabilitiamo il pulsante chiudi per evitare chiusure accidentali.
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint
        )

        # Centra sullo schermo
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

        self._build_ui()

        # Contatore per progress
        self._log_count = 0
        # Guardia anti-rientranza per processEvents()
        self._processing_events = False

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
        layout.setContentsMargins(20, 15, 20, 20)

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
        self.subtitle = QLabel(t("splash.label.loading_subtitle"))
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
        """Aggiunge messaggio al log e forza aggiornamento UI.

        Con caricamento sincrono il main thread è bloccato — processEvents()
        viene chiamato qui ad ogni messaggio di log per mantenere la finestra
        reattiva (minimizza, repaint). Una guardia anti-rientranza evita che
        processEvents() triggeri un nuovo add_log() → processEvents() ricorsivo.
        """
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

        # Aggiorna widget direttamente (siamo nel main thread, sincrono)
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

        # Aggiorna progress (cresce con i messaggi, max 95%)
        self._log_count += 1
        progress_val = min(95, self._log_count * 3)
        self.progress.setValue(progress_val)

        # Aggiorna sottotitolo con ultimo messaggio significativo
        if any(x in message for x in ['✅', '🔧', '🚀', '📦', 'Caric', 'Inizial', 'Loading', 'Init']):
            short_msg = message[:50] + "..." if len(message) > 50 else message
            self.subtitle.setText(short_msg)

        # Forza aggiornamento UI con guardia anti-rientranza.
        # ExcludeUserInputEvents: processa SOLO repaint/layout/timer, NON click/tastiera.
        # Questo è il contrario di quello che servirebbe per "minimizza", ma è il flag
        # sicuro su macOS/Linux dove processare input utente durante il call stack nativo
        # di torch/ctranslate2 può causare segfault (re-entrance in Metal/xcb).
        # Il pulsante minimizza del window manager funziona comunque: su tutte le
        # piattaforme il WM gestisce la minimizzazione a livello OS, non tramite
        # eventi Qt — il click sulla barra titolo/taskbar è intercettato dal WM prima
        # che arrivi all'event loop dell'applicazione.
        if not self._processing_events:
            self._processing_events = True
            try:
                QApplication.processEvents(
                    QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                )
            finally:
                self._processing_events = False

    def finish(self):
        """Completa il caricamento.
        Non eseguire operazioni Qt qui: su Linux, spacy/ctranslate2 rimangono
        sul call stack nativo anche dopo il caricamento. Qualsiasi widget update
        (setValue, setText) triggera un repaint interno che causa segfault via xcb.
        La splash sta per chiudersi, le operazioni cosmetiche sono superflue."""
        pass


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

    # Silenzia logger librerie HTTP: i loro messaggi TRACE/DEBUG includono
    # header HuggingFace con "X-Error-Code" nel testo, che viene erroneamente
    # classificato come ERROR dal controllo 'ERROR' in message.upper()
    for _noisy in ('httpcore', 'httpx', 'urllib3', 'hpack', 'huggingface_hub.file_download'):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


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


def _check_for_updates(parent_window):
    """Controlla se è disponibile una nuova versione su GitHub.
    Confronta versione locale con ultimo commit remoto.
    In repo git usa git rev-parse, altrimenti legge il file VERSION."""
    try:
        from update import get_local_version, get_remote_version
        app_dir = get_app_dir()

        # In repo git, la versione locale è lo SHA corrente di HEAD
        is_git = (app_dir / '.git').exists()
        if is_git:
            import subprocess
            from utils.subprocess_utils import subprocess_creation_kwargs
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True, cwd=str(app_dir), timeout=5,
                **subprocess_creation_kwargs()
            )
            local = result.stdout.strip() if result.returncode == 0 else get_local_version(app_dir)
        else:
            local = get_local_version(app_dir)

        remote = get_remote_version()

        if remote is None or local == remote:
            return  # Nessun aggiornamento o rete non disponibile

        # In repo git: se il commit remoto è antenato del locale, siamo avanti (commit non pushati)
        if is_git:
            merge_base = subprocess.run(
                ['git', 'merge-base', '--is-ancestor', remote, 'HEAD'],
                capture_output=True, cwd=str(app_dir), timeout=5,
                **subprocess_creation_kwargs()
            )
            if merge_base.returncode == 0:
                return  # Il remoto è un antenato: siamo avanti, nessun aggiornamento necessario

        from PyQt6.QtWidgets import QMessageBox
        msg_key = "update.msg.body_git" if is_git else "update.msg.body"
        body = t(msg_key, local=local, remote=remote)

        QMessageBox.information(parent_window, t("update.msg.title"), body)

    except Exception:
        pass  # Fallimento silenzioso — non bloccare l'avvio


def run_with_splash():
    """Avvia applicazione con splash screen"""
    # Carica lingua prima di creare qualsiasi widget
    try:
        import yaml
        from pathlib import Path
        _cfg_path = Path("config_new.yaml")
        if _cfg_path.exists():
            with open(_cfg_path, encoding="utf-8") as _f:
                _cfg = yaml.safe_load(_f)
            _lang = _cfg.get("ui", {}).get("user_language", "it")
            load_language(_lang)
        else:
            load_language("it")
    except Exception:
        load_language("it")

    # Setup cattura log PRIMA di tutto
    setup_log_capture()

    print(t("splash.msg.starting"))

    # Filtra warning Qt TIFF (null byte in tag EXIF, compressione JPEG non supportata)
    from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
    def qt_message_filter(msg_type, context, message):
        if 'qt.imageformats.tiff' in (context.category or ''):
            return  # Ignora warning TIFF su file RAW
        if 'QBackingStore::endPaint' in message:
            return  # Warning cosmético durante transizione splash→mainwindow, non fatale
        # Scrivi su stdout originale per evitare loop re-entrante:
        # print() → LogCapture.write() → splash.add_log() → Qt update → possibile
        # nuovo messaggio Qt → print() ... Scrivendo direttamente su _original_stdout
        # si bypassa LogCapture e si spezza il ciclo.
        if msg_type == QtMsgType.QtWarningMsg:
            _original_stdout.write(f"Qt Warning: {message}\n")
        elif msg_type == QtMsgType.QtCriticalMsg:
            _original_stdout.write(f"Qt Critical: {message}\n")
        elif msg_type == QtMsgType.QtFatalMsg:
            _original_stdout.write(f"Qt Fatal: {message}\n")
    qInstallMessageHandler(qt_message_filter)

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

    # Carica config per EmbeddingGenerator
    import yaml
    try:
        with open("config_new.yaml", encoding="utf-8") as _f:
            _config = yaml.safe_load(_f)
    except Exception:
        _config = {}

    # === Caricamento sincrono nel main thread ===
    # torch/CUDA/MKL/ctranslate2 inizializzano librerie native che NON sono
    # thread-safe: caricarle in un thread secondario causa crash silenziosi
    # su tutte le piattaforme (segfault Cocoa/Metal su macOS, xcb su Linux,
    # MKL/OpenMP su Windows). Il caricamento sincrono blocca la UI ma è
    # l'unico approccio stabile.

    try:
        from gui.main_window import MainWindow, shutdown_badge_manager
        from embedding_generator import EmbeddingGenerator

        splash.add_log(t("splash.msg.init_loading"))
        emb_gen = EmbeddingGenerator(_config)

        splash.add_log(t("splash.msg.init_ui"))
        window = MainWindow(preloaded_models={
            'embedding_generator': emb_gen,
            'initialized': True,
        })

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        restore_log_capture()
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(t("splash.msg.startup_error_title"))
        msg.setText(t("splash.msg.startup_error", error=e))
        msg.setDetailedText(tb)
        msg.exec()
        sys.exit(1)

    # Transizione splash → finestra principale
    app._main_window = window
    app.aboutToQuit.connect(shutdown_badge_manager)
    splash.finish()

    restore_log_capture()
    window.show()
    splash.hide()
    splash.deleteLater()

    # Controllo aggiornamenti (se abilitato in config)
    if _config.get('updates', {}).get('check_on_startup', True):
        _check_for_updates(window)

    sys.exit(app.exec())
