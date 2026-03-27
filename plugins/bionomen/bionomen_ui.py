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
from typing import Optional

# Configura logging base (senza accedere a OffGallery)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QDialog,
    QButtonGroup, QFrame, QDialogButtonBox,
    QMessageBox, QCheckBox, QLineEdit, QFileDialog,
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
    summary  = pyqtSignal(int, int, int) # (total, matched, not_matched)
    status   = pyqtSignal(str)           # testo descrittivo per lbl_status
    finished = pyqtSignal()
    error = pyqtSignal(str)


class ProcessWorker(QThread):
    """Thread worker per l'elaborazione delle immagini."""

    def __init__(self, db_path: str, mode: str, language: str,
                 ids_file: str = None, directory_filter: str = None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.mode = mode
        self.language = language
        self.ids_file = ids_file
        self.directory_filter = directory_filter
        self.signals = WorkerSignals()
        import threading
        self._stop_event = threading.Event()

    def stop(self):
        """Richiede l'interruzione del worker — il loop si ferma alla prossima specie."""
        self._stop_event.set()

    def run(self):
        """Esegue l'elaborazione in background."""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            import bionomen

            def _progress_cb(current: int, total: int):
                self.signals.progress.emit(current, total)
                print(f"PROGRESS:{current}:{total}", flush=True)

            # Risolve lista ID se modalità ids
            image_ids = None
            if self.mode == "ids" and self.ids_file:
                try:
                    with open(self.ids_file, "r", encoding="utf-8") as f:
                        image_ids = json.load(f)
                    Path(self.ids_file).unlink(missing_ok=True)  # Cancella file temp
                except Exception as e:
                    logger.warning(f"Impossibile leggere ids_file: {e}")

            total, matched, not_matched = bionomen.process_images(
                offgallery_db_path=self.db_path,
                mode=self.mode,
                language=self.language,
                progress_callback=_progress_cb,
                stop_event=self._stop_event,
                image_ids=image_ids,
                directory_filter=self.directory_filter,
            )
            self.signals.summary.emit(total, matched, not_matched)
            self.signals.finished.emit()

        except Exception as e:
            logger.error(f"Errore elaborazione: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class DownloadWorker(QThread):
    """Thread worker per il download bulk GBIF dei taxa configurati."""

    def __init__(self, language: str = None, parent=None):
        super().__init__(parent)
        self.language = language
        self.signals = WorkerSignals()
        import threading
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        """Esegue il download bulk in background."""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            import bionomen

            def _progress_cb(current: int, total: int):
                self.signals.progress.emit(current, total)

            def _status_cb(text: str):
                self.signals.status.emit(text)

            bionomen.download_and_build_database(
                language=getattr(self, "language", None),
                progress_callback=_progress_cb,
                status_callback=_status_cb,
                stop_event=self._stop_event,
            )
            self.signals.finished.emit()

        except Exception as e:
            logger.error(f"Errore download database: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class ConfigDialog(QDialog):
    """
    Dialog configurazione BioNomen.

    Sezioni:
    - Taxa da scaricare (checkbox per Aves, Mammalia, ...)
    - Directory dati (dove salvare i DB per taxon)
    - Modalità elaborazione (4 opzioni)
    """

    def __init__(self, current_mode: str,
                 count_unprocessed: int = -1, count_total: int = -1,
                 count_gallery: int = -1,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("BioNomen — Configurazione")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(_DARK_STYLE)

        self._mode = current_mode
        self._count_unprocessed = count_unprocessed
        self._count_total = count_total
        self._count_gallery = count_gallery

        # Carica config corrente
        sys.path.insert(0, str(Path(__file__).parent))
        import bionomen
        self._cfg = bionomen.load_config()

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        _sep = lambda: self._make_sep()

        # --- Sezione Taxa ---
        taxa_label = QLabel("Taxa da scaricare")
        taxa_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(taxa_label)

        import bionomen
        self._taxa_checks = {}
        enabled = set(self._cfg.get("taxa_enabled", ["aves"]))
        taxa_items = list(bionomen.TAXA.items())
        grid = QHBoxLayout()
        col_left  = QVBoxLayout()
        col_right = QVBoxLayout()
        mid = (len(taxa_items) + 1) // 2
        for i, (taxon_id, info) in enumerate(taxa_items):
            cb = QCheckBox(info["label"])
            cb.setChecked(taxon_id in enabled)
            self._taxa_checks[taxon_id] = cb
            (col_left if i < mid else col_right).addWidget(cb)
        grid.addLayout(col_left)
        grid.addLayout(col_right)
        layout.addLayout(grid)

        layout.addWidget(_sep())

        # --- Sezione Directory dati ---
        dir_label = QLabel("Directory database")
        dir_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(dir_label)

        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit(self._cfg.get("data_dir", ""))
        self._dir_edit.setStyleSheet(
            "background: #1E1E1E; color: #E3E3E3; border: 1px solid #3A3A3A; "
            "border-radius: 3px; padding: 3px 6px;"
        )
        dir_row.addWidget(self._dir_edit)

        btn_browse = QPushButton("Sfoglia…")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(btn_browse)
        layout.addLayout(dir_row)

        layout.addWidget(_sep())

        # --- Sezione Modalità elaborazione ---
        mode_label = QLabel("Modalità elaborazione")
        mode_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(mode_label)

        # Gruppo esclusivo di checkbox (mutua esclusione come radiobutton, stile nativo)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)

        lbl_unprocessed = "Solo foto non ancora processate"
        lbl_all = "Tutto il database"
        lbl_gallery = "Foto selezionate in Gallery"
        lbl_directory = "Scegli directory…"

        if self._count_unprocessed >= 0:
            lbl_unprocessed += f"  ({self._count_unprocessed:,} foto)".replace(",", ".")
        if self._count_total >= 0:
            lbl_all += f"  ({self._count_total:,} foto)".replace(",", ".")
        if self._count_gallery >= 0:
            lbl_gallery += f"  ({self._count_gallery:,} selezionate)".replace(",", ".")

        self.cb_unprocessed = QCheckBox(lbl_unprocessed)
        self.cb_all         = QCheckBox(lbl_all)
        self.cb_gallery     = QCheckBox(lbl_gallery)
        self.cb_directory   = QCheckBox(lbl_directory)

        self._mode_group.addButton(self.cb_unprocessed, 0)
        self._mode_group.addButton(self.cb_all,         1)
        self._mode_group.addButton(self.cb_gallery,     2)
        self._mode_group.addButton(self.cb_directory,   3)

        for cb in (self.cb_unprocessed, self.cb_all, self.cb_gallery, self.cb_directory):
            layout.addWidget(cb)

        # Seleziona modalità corrente
        _map = {"unprocessed": self.cb_unprocessed, "all": self.cb_all,
                "ids": self.cb_gallery, "directory": self.cb_directory}
        _map.get(self._mode, self.cb_unprocessed).setChecked(True)

        layout.addWidget(_sep())

        # --- Bottoni OK/Annulla ---
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        btn_box.button(QDialogButtonBox.StandardButton.Save).setText("Salva")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _make_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    def _browse_dir(self):
        current = self._dir_edit.text() or str(Path(__file__).parent / "data")
        chosen = QFileDialog.getExistingDirectory(self, "Seleziona directory database", current)
        if chosen:
            self._dir_edit.setText(chosen)

    def _on_accept(self):
        # Salva config
        import bionomen
        taxa_enabled = [tid for tid, cb in self._taxa_checks.items() if cb.isChecked()]
        if not taxa_enabled:
            QMessageBox.warning(self, "BioNomen", "Seleziona almeno un taxon.")
            return
        self._cfg["taxa_enabled"] = taxa_enabled
        self._cfg["data_dir"] = self._dir_edit.text().strip()
        self._cfg["mode"] = self.get_mode()
        bionomen.save_config(self._cfg)
        self.accept()

    def get_mode(self) -> str:
        if self.cb_all.isChecked():
            return "all"
        if self.cb_gallery.isChecked():
            return "ids"
        if self.cb_directory.isChecked():
            return "directory"
        return "unprocessed"


class BioNomenWindow(QMainWindow):
    """
    Finestra di elaborazione BioNomen — aperta come subprocess da OffGallery.
    Mostra solo: progress bar, counter foto, label stato, bottone Interrompi.
    Configura/DB/Avvia sono nella PluginCard di OffGallery.
    """

    def __init__(self, db_path: str, config_path: Optional[str] = None):
        super().__init__()
        self.db_path = db_path
        self.config_path = config_path

        self._language = self._load_language_from_config()
        self._mode = "unprocessed"
        self._ids_file = None         # Path file JSON con lista ID (modalità ids)
        self._directory_filter = None # Path directory da filtrare (modalità directory)
        self._worker = None
        self._total = 0

        self.setWindowTitle("BioNomen — elaborazione")
        self.setMinimumSize(520, 160)
        self.resize(580, 180)
        self.setStyleSheet(_DARK_STYLE)

        self._build_ui()

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

        # === Intestazione minimale ===
        header_layout = QHBoxLayout()
        title_label = QLabel("🔤 BioNomen — elaborazione in corso")
        title_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #E0A84A;")
        header_layout.addWidget(title_label)

        self.btn_start = QPushButton("⏹ Interrompi")
        self.btn_start.setFixedWidth(110)
        self.btn_start.clicked.connect(self._on_start_stop)
        header_layout.addWidget(self.btn_start)

        main_layout.addLayout(header_layout)

        # === Progress bar + counter ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(_PB_STYLE)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()

        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_bar)

        self.lbl_counter = QLabel("0 / 0")
        self.lbl_counter.setStyleSheet("font-size: 11px; color: #B0B0B0; min-width: 200px;")
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

    def _on_start_stop(self):
        """Interrompe l'elaborazione se in corso."""
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self.btn_start.setEnabled(False)
            self.lbl_status.setText("Interruzione in corso...")

    def _start_processing(self):
        """Avvia l'elaborazione delle immagini in background."""
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
            ids_file=self._ids_file,
            directory_filter=self._directory_filter,
            parent=self,
        )
        self._worker.signals.progress.connect(self._on_process_progress)
        self._worker.signals.summary.connect(self._on_summary)
        self._worker.signals.finished.connect(self._on_process_finished)
        self._worker.signals.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_process_progress(self, current: int, total: int):
        """Aggiorna progress bar e counter durante l'elaborazione."""
        if total > 0:
            self.progress_bar.setValue(int(current * 100 / total))
        cur_fmt = f"{current:,}".replace(",", ".")
        tot_fmt = f"{total:,}".replace(",", ".")
        self.lbl_counter.setText(f"{cur_fmt} / {tot_fmt}")
        self._total = total

    def _on_summary(self, total: int, matched: int, not_matched: int):
        """Riceve il riepilogo finale."""
        self.lbl_status.setText(
            f"Completate {total}  ✓ {matched} con nome  ✗ {not_matched} senza"
        )

    def _on_process_finished(self):
        """Chiamato al completamento dell'elaborazione."""
        self.btn_start.setEnabled(False)  # non serve più — la finestra può essere chiusa
        self.progress_bar.setValue(100)
        if self.lbl_status.text() == "Elaborazione in corso...":
            self.lbl_status.setText("Elaborazione completata.")
        self._worker = None

    def _on_worker_error(self, error_msg: str):
        """Gestisce errori dal worker."""
        self.progress_bar.hide()
        self.lbl_counter.hide()
        self.lbl_status.setText(f"Errore: {error_msg}")
        self._worker = None
        logger.error(f"Worker error: {error_msg}")

    def closeEvent(self, event):
        """Interrompe il worker se attivo prima di chiudere."""
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        event.accept()


def main():
    parser = argparse.ArgumentParser(description="BioNomen — Nomi comuni biologici GBIF")
    parser.add_argument("--db", required=True,
                        help="Path al database OffGallery")
    parser.add_argument("--config", default=None,
                        help="Path al file config_new.yaml di OffGallery (opzionale)")
    parser.add_argument("--mode", default=None,
                        choices=["unprocessed", "all", "ids", "directory"],
                        help="Modalita' elaborazione. Se fornito, avvia automaticamente.")
    parser.add_argument("--ids-file", default=None,
                        help="Path a file JSON con lista ID immagini (modalita' ids)")
    parser.add_argument("--directory", default=None,
                        help="Path directory da filtrare nel DB (modalita' directory)")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"ERRORE: Database non trovato: {args.db}", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("BioNomen")

    window = BioNomenWindow(db_path=args.db, config_path=args.config)

    # Se modalita' e' passata da OffGallery, avvia elaborazione automaticamente
    if args.mode:
        window._mode = args.mode
        if args.ids_file:
            window._ids_file = args.ids_file
        if args.directory:
            window._directory_filter = args.directory
        window.show()
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, window._start_processing)
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
