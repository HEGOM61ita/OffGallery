"""
BioNomen UI — Interfaccia grafica standalone Qt per il plugin BioNomen.

Argomenti CLI:
  --db /path/to/offgallery.db       (obbligatorio)
  --config /path/to/config_new.yaml (opzionale)

Comunicazione con OffGallery tramite stdout: righe PROGRESS:n:total
"""

import sys
import argparse
import json
import logging
from pathlib import Path

# Configura logging base (senza accedere a OffGallery)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QDialog, QComboBox,
    QRadioButton, QButtonGroup, QFrame, QDialogButtonBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont


# Stile progress bar dark-gold (coerente con OffGallery processing_tab)
_PB_STYLE = """
    QProgressBar {
        border: 1px solid #555;
        background: #2a2a2a;
        border-radius: 3px;
        max-height: 8px;
    }
    QProgressBar::chunk {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #C88B2E, stop:1 #E0A84A
        );
        border-radius: 2px;
    }
"""

_DARK_STYLE = """
    QMainWindow, QDialog, QWidget {
        background-color: #2A2A2A;
        color: #E3E3E3;
    }
    QLabel {
        color: #E3E3E3;
    }
    QPushButton {
        background-color: #1C4F63;
        color: #E3E3E3;
        border: none;
        border-radius: 4px;
        padding: 5px 12px;
        font-size: 12px;
    }
    QPushButton:hover {
        background-color: #2A6A82;
    }
    QPushButton:disabled {
        background-color: #3A3A3A;
        color: #808080;
    }
    QComboBox {
        background-color: #1E1E1E;
        color: #E3E3E3;
        border: 1px solid #3A3A3A;
        border-radius: 4px;
        padding: 3px 6px;
    }
    QComboBox QAbstractItemView {
        background-color: #1E1E1E;
        color: #E3E3E3;
        selection-background-color: #1C4F63;
    }
    QRadioButton {
        color: #E3E3E3;
    }
    QFrame[frameShape="4"], QFrame[frameShape="5"] {
        color: #3A3A3A;
    }
"""

# Lingue supportate: (codice, etichetta)
_LANGUAGES = [
    ("it", "Italiano"),
    ("en", "English"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("es", "Español"),
    ("pt", "Português"),
]


class WorkerSignals(QObject):
    """Segnali emessi dal thread worker."""
    progress = pyqtSignal(int, int)      # (current, total)
    finished = pyqtSignal()
    error = pyqtSignal(str)


class ProcessWorker(QThread):
    """Thread worker per l'elaborazione delle immagini."""

    def __init__(self, db_path: str, mode: str, language: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.mode = mode
        self.language = language
        self.signals = WorkerSignals()
        self._stop_flag = False

    def stop(self):
        """Richiede l'interruzione del worker."""
        self._stop_flag = True

    def run(self):
        """Esegue l'elaborazione in background."""
        try:
            # Import locale: bionomen.py e' nella stessa directory
            import os
            sys.path.insert(0, str(Path(__file__).parent))
            import bionomen

            def _progress_cb(current: int, total: int):
                if self._stop_flag:
                    raise InterruptedError("Elaborazione interrotta dall'utente")
                self.signals.progress.emit(current, total)
                # Stampa su stdout per OffGallery
                print(f"PROGRESS:{current}:{total}", flush=True)

            bionomen.process_images(
                offgallery_db_path=self.db_path,
                mode=self.mode,
                language=self.language,
                progress_callback=_progress_cb,
            )
            self.signals.finished.emit()

        except InterruptedError:
            self.signals.finished.emit()
        except Exception as e:
            logger.error(f"Errore elaborazione: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class DownloadWorker(QThread):
    """Thread worker per il download/inizializzazione del database locale."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = WorkerSignals()

    def run(self):
        """Esegue l'inizializzazione del DB in background."""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            import bionomen

            def _progress_cb(current: int, total: int):
                self.signals.progress.emit(current, total)
                print(f"PROGRESS:{current}:{total}", flush=True)

            bionomen.download_and_build_database(progress_callback=_progress_cb)
            self.signals.finished.emit()

        except Exception as e:
            logger.error(f"Errore download database: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class ConfigDialog(QDialog):
    """Dialog modale per la configurazione del plugin."""

    def __init__(self, current_language: str, current_mode: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BioNomen — Configurazione")
        self.setModal(True)
        self.setFixedSize(320, 220)
        self.setStyleSheet(_DARK_STYLE)

        self._language = current_language
        self._mode = current_mode

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Lingua
        lang_label = QLabel("Lingua output")
        lang_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(lang_label)

        self.lang_combo = QComboBox()
        for code, name in _LANGUAGES:
            self.lang_combo.addItem(name, userData=code)
            if code == self._language:
                self.lang_combo.setCurrentIndex(self.lang_combo.count() - 1)
        layout.addWidget(self.lang_combo)

        # Separatore
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Modalita'
        mode_label = QLabel("Modalità")
        mode_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(mode_label)

        self._mode_group = QButtonGroup(self)
        self.radio_unprocessed = QRadioButton("Solo foto non processate")
        self.radio_all = QRadioButton("Tutto il database")
        self._mode_group.addButton(self.radio_unprocessed)
        self._mode_group.addButton(self.radio_all)

        if self._mode == "all":
            self.radio_all.setChecked(True)
        else:
            self.radio_unprocessed.setChecked(True)

        layout.addWidget(self.radio_unprocessed)
        layout.addWidget(self.radio_all)

        # Bottoni
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        btn_box.button(QDialogButtonBox.StandardButton.Save).setText("Salva")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_language(self) -> str:
        return self.lang_combo.currentData()

    def get_mode(self) -> str:
        return "all" if self.radio_all.isChecked() else "unprocessed"


class BioNomenWindow(QMainWindow):
    """Finestra principale del plugin BioNomen."""

    def __init__(self, db_path: str, config_path: Optional[str] = None):
        super().__init__()
        self.db_path = db_path
        self.config_path = config_path

        # Configurazione corrente
        self._language = self._load_language_from_config()
        self._mode = "unprocessed"
        self._worker = None
        self._download_worker = None
        self._total = 0

        self.setWindowTitle("BioNomen")
        self.setFixedSize(600, 300)
        self.setStyleSheet(_DARK_STYLE)

        self._build_ui()
        self._refresh_db_status()

    def _load_language_from_config(self) -> str:
        """Legge la lingua default da config_new.yaml di OffGallery se disponibile."""
        if not self.config_path:
            return "it"
        try:
            import yaml  # type: ignore
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            lang = config.get("ui", {}).get("llm_output_language", "it")
            # Normalizza: "italiano" → "it", "english" → "en", ecc.
            lang_map = {
                "italiano": "it", "italian": "it",
                "english": "en", "inglese": "en",
                "deutsch": "de", "tedesco": "de",
                "francese": "fr", "french": "fr",
                "spagnolo": "es", "spanish": "es",
                "portoghese": "pt", "portuguese": "pt",
            }
            return lang_map.get(lang.lower(), lang[:2].lower() if len(lang) >= 2 else "it")
        except Exception:
            return "it"

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # === Intestazione plugin ===
        header_layout = QHBoxLayout()
        title_label = QLabel("🔤 BioNomen  v1.0")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E0A84A;")
        desc_label = QLabel("Arricchisce tag con nomi comuni biologici da GBIF")
        desc_label.setStyleSheet("font-size: 11px; color: #B0B0B0;")
        header_layout.addWidget(title_label)
        header_layout.addWidget(desc_label)
        header_layout.addStretch()

        # Bottoni Configura / Avvia in alto a destra
        self.btn_configure = QPushButton("⚙ Configura")
        self.btn_configure.setFixedWidth(110)
        self.btn_configure.clicked.connect(self._on_configure)
        header_layout.addWidget(self.btn_configure)

        self.btn_start = QPushButton("▶ Avvia")
        self.btn_start.setFixedWidth(110)
        self.btn_start.clicked.connect(self._on_start_stop)
        header_layout.addWidget(self.btn_start)

        main_layout.addLayout(header_layout)

        # === Separatore ===
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(sep)

        # === Stato database ===
        db_row = QHBoxLayout()
        self.lbl_db_status = QLabel("Database: verifica in corso...")
        self.lbl_db_status.setStyleSheet("font-size: 12px;")
        db_row.addWidget(self.lbl_db_status)
        db_row.addStretch()

        self.btn_db_action = QPushButton("Scarica database")
        self.btn_db_action.setFixedWidth(160)
        self.btn_db_action.clicked.connect(self._on_db_action)
        db_row.addWidget(self.btn_db_action)

        main_layout.addLayout(db_row)

        # === Progress bar + counter (nascosti a riposo) ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(_PB_STYLE)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()

        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_bar)

        self.lbl_counter = QLabel("0 / 0")
        self.lbl_counter.setStyleSheet("font-size: 11px; color: #B0B0B0; min-width: 90px;")
        self.lbl_counter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_counter.hide()
        progress_row.addWidget(self.lbl_counter)

        main_layout.addLayout(progress_row)

        # === Label stato elaborazione ===
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #B0B0B0;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lbl_status)

        main_layout.addStretch()

    def _refresh_db_status(self):
        """Aggiorna la label stato database e il testo del bottone azione."""
        sys.path.insert(0, str(Path(__file__).parent))
        import bionomen

        if bionomen.is_database_present():
            date_str = bionomen.get_database_date() or "data sconosciuta"
            self.lbl_db_status.setText(f"Database: ✓ {date_str}")
            self.lbl_db_status.setStyleSheet("font-size: 12px; color: #4CAF50;")
            self.btn_db_action.setText("Verifica aggiornamenti")
            self.btn_start.setEnabled(True)
        else:
            self.lbl_db_status.setText("Database non presente")
            self.lbl_db_status.setStyleSheet("font-size: 12px; color: #E74C3C;")
            self.btn_db_action.setText("Scarica database ~10MB")
            self.btn_start.setEnabled(False)

    def _on_configure(self):
        """Apre il dialog di configurazione."""
        dialog = ConfigDialog(self._language, self._mode, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._language = dialog.get_language()
            self._mode = dialog.get_mode()

    def _on_db_action(self):
        """Gestisce click su 'Scarica database' o 'Verifica aggiornamenti'."""
        sys.path.insert(0, str(Path(__file__).parent))
        import bionomen

        if bionomen.is_database_present():
            # Verifica aggiornamenti: per ora re-inizializza il DB
            reply = QMessageBox.question(
                self,
                "Aggiorna database",
                "Vuoi aggiornare il database BioNomen?\n"
                "Il database verrà re-inizializzato. I dati in cache verranno mantenuti.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._start_download()

    def _start_download(self):
        """Avvia il download/inizializzazione del database in background."""
        self.btn_db_action.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_configure.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.lbl_counter.show()
        self.lbl_status.setText("Inizializzazione database...")

        self._download_worker = DownloadWorker(parent=self)
        self._download_worker.signals.progress.connect(self._on_download_progress)
        self._download_worker.signals.finished.connect(self._on_download_finished)
        self._download_worker.signals.error.connect(self._on_worker_error)
        self._download_worker.start()

    def _on_download_progress(self, current: int, total: int):
        """Aggiorna la progress bar durante il download."""
        if total > 0:
            pct = int(current * 100 / total)
            self.progress_bar.setValue(pct)
        self.lbl_counter.setText(f"{current:,} / {total:,}".replace(",", "."))

    def _on_download_finished(self):
        """Chiamato al completamento del download."""
        self.progress_bar.hide()
        self.lbl_counter.hide()
        self.btn_db_action.setEnabled(True)
        self.btn_configure.setEnabled(True)
        self._refresh_db_status()
        self.lbl_status.setText("Database inizializzato.")

    def _on_start_stop(self):
        """Avvia o interrompe l'elaborazione."""
        if self._worker and self._worker.isRunning():
            # Interrompi
            self._worker.stop()
            self.btn_start.setText("▶ Avvia")
            self.lbl_status.setText("Interruzione in corso...")
        else:
            # Avvia
            self._start_processing()

    def _start_processing(self):
        """Avvia l'elaborazione delle immagini in background."""
        self.btn_start.setText("⏹ Interrompi")
        self.btn_configure.setEnabled(False)
        self.btn_db_action.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.lbl_counter.setText("0 / 0")
        self.lbl_counter.show()
        self.lbl_status.setText("Elaborazione in corso...")
        self._total = 0

        self._worker = ProcessWorker(
            db_path=self.db_path,
            mode=self._mode,
            language=self._language,
            parent=self,
        )
        self._worker.signals.progress.connect(self._on_process_progress)
        self._worker.signals.finished.connect(self._on_process_finished)
        self._worker.signals.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_process_progress(self, current: int, total: int):
        """Aggiorna progress bar e counter durante l'elaborazione."""
        if total > 0:
            pct = int(current * 100 / total)
            self.progress_bar.setValue(pct)
        # Formato con punto come separatore migliaia (stile italiano)
        cur_fmt = f"{current:,}".replace(",", ".")
        tot_fmt = f"{total:,}".replace(",", ".")
        self.lbl_counter.setText(f"{cur_fmt} / {tot_fmt}")
        self._total = total

    def _on_process_finished(self):
        """Chiamato al completamento dell'elaborazione."""
        self.btn_start.setText("▶ Avvia")
        self.btn_configure.setEnabled(True)
        self.btn_db_action.setEnabled(True)
        self.progress_bar.hide()
        self.lbl_counter.hide()
        self.lbl_status.setText("Elaborazione completata.")
        self._worker = None

    def _on_worker_error(self, error_msg: str):
        """Gestisce errori dal worker."""
        self.btn_start.setText("▶ Avvia")
        self.btn_configure.setEnabled(True)
        self.btn_db_action.setEnabled(True)
        self.progress_bar.hide()
        self.lbl_counter.hide()
        self.lbl_status.setText(f"Errore: {error_msg}")
        self._worker = None
        self._download_worker = None
        logger.error(f"Worker error: {error_msg}")

    def closeEvent(self, event):
        """Interrompe il worker se attivo prima di chiudere."""
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        if self._download_worker and self._download_worker.isRunning():
            self._download_worker.wait(3000)
        event.accept()


# Aggiungi Optional al tipo hint (Python 3.9 compat)
from typing import Optional  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="BioNomen — Nomi comuni biologici GBIF")
    parser.add_argument(
        "--db", required=True,
        help="Path al database OffGallery (offgallery.db)"
    )
    parser.add_argument(
        "--config", default=None,
        help="Path al file config_new.yaml di OffGallery (opzionale)"
    )
    args = parser.parse_args()

    db_path = args.db
    config_path = args.config

    # Verifica che il DB esista
    if not Path(db_path).exists():
        print(f"ERRORE: Database non trovato: {db_path}", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("BioNomen")

    window = BioNomenWindow(db_path=db_path, config_path=config_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
