"""
PluginsTab — Tab per la gestione dei plugin standalone di OffGallery.

Auto-discovery: scansiona APP_DIR/plugins cercando manifest.json con "type": "standalone".
I plugin LLM interni (llm_ollama, llm_lmstudio) vengono ignorati (type assente o diverso).

Ogni plugin trovato viene rappresentato da una card QFrame con:
- Nome, versione, descrizione
- Stato database + bottone azione DB
- Progress bar stile OffGallery
- Counter label
- Bottoni Configura / Avvia (o Interrompi)

Il plugin viene lanciato come sottoprocesso separato (subprocess.Popen).
Lo stdout del sottoprocesso viene letto in un QThread dedicato:
le righe "PROGRESS:n:total" aggiornano progress bar e counter.
"""

import sys
import json
import logging
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from utils.paths import get_app_dir
from i18n import t

logger = logging.getLogger(__name__)


# Stile progress bar dark-gold coerente con processing_tab.py
_PB_STYLE = """
    QProgressBar { border: 1px solid #555; background: #2a2a2a;
                   border-radius: 3px; max-height: 8px; }
    QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #C88B2E, stop:1 #E0A84A); border-radius: 2px; }
"""

# Palette colori (coerente con main_window.py)
_COLORS = {
    'grafite': '#2A2A2A',
    'grafite_light': '#3A3A3A',
    'grafite_dark': '#1E1E1E',
    'grigio_chiaro': '#E3E3E3',
    'grigio_medio': '#B0B0B0',
    'blu_petrolio': '#1C4F63',
    'blu_petrolio_light': '#2A6A82',
    'ambra': '#C88B2E',
    'ambra_light': '#E0A84A',
    'verde': '#4CAF50',
    'rosso': '#E74C3C',
}


class StdoutReaderThread(QThread):
    """
    Thread che legge stdout di un sottoprocesso e parsa le righe PROGRESS:n:total.
    Emette progress(current, total) e finished() quando il processo termina.
    """
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, process: subprocess.Popen, parent=None):
        super().__init__(parent)
        self._process = process

    def run(self):
        """Legge stdout riga per riga finche' il processo non termina."""
        try:
            for line in self._process.stdout:
                line = line.strip()
                if line.startswith("PROGRESS:"):
                    # Formato: PROGRESS:current:total
                    parts = line.split(":")
                    if len(parts) == 3:
                        try:
                            current = int(parts[1])
                            total = int(parts[2])
                            self.progress.emit(current, total)
                        except ValueError:
                            pass
            self._process.wait()
        except Exception as e:
            logger.debug(f"StdoutReaderThread: errore lettura stdout: {e}")
        finally:
            self.finished.emit()


class PluginCard(QFrame):
    """
    Card grafica per un singolo plugin standalone.

    Contiene:
    - Header: nome, versione, descrizione, [Configura] [Avvia/Interrompi]
    - Riga DB: stato database + bottone azione
    - Progress bar + counter (nascosti a riposo)
    """

    def __init__(self, manifest: dict, plugin_dir: Path, db_path: str, config_path: str, parent=None):
        super().__init__(parent)
        self._manifest = manifest
        self._plugin_dir = plugin_dir
        self._db_path = db_path
        self._config_path = config_path

        self._process = None          # subprocess.Popen attivo
        self._reader_thread = None    # StdoutReaderThread attivo

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setStyleSheet(f"""
            PluginCard {{
                background-color: {_COLORS['grafite_dark']};
                border: 1px solid {_COLORS['grafite_light']};
                border-radius: 6px;
            }}
        """)

        self._build_ui()
        self._refresh_db_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # === Riga header: nome + versione + descrizione + [Configura] [Avvia] ===
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        name = self._manifest.get("name", "Plugin")
        version = self._manifest.get("version", "")
        description = self._manifest.get("description", "")

        lbl_name = QLabel(f"🔤 {name}  v{version}")
        lbl_name.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {_COLORS['ambra_light']};"
        )
        header_row.addWidget(lbl_name)

        lbl_desc = QLabel(description)
        lbl_desc.setStyleSheet(
            f"font-size: 11px; color: {_COLORS['grigio_medio']};"
        )
        header_row.addWidget(lbl_desc)
        header_row.addStretch()

        self.btn_configure = QPushButton(t("plugins.button.configure"))
        self.btn_configure.setFixedWidth(100)
        self.btn_configure.setStyleSheet(
            f"QPushButton {{ background-color: {_COLORS['grafite_light']}; "
            f"color: {_COLORS['grigio_chiaro']}; border: none; border-radius: 4px; "
            f"padding: 4px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background-color: {_COLORS['blu_petrolio']}; }}"
        )
        self.btn_configure.clicked.connect(self._on_configure)
        header_row.addWidget(self.btn_configure)

        self.btn_start = QPushButton(t("plugins.button.start"))
        self.btn_start.setFixedWidth(100)
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background-color: {_COLORS['blu_petrolio']}; "
            f"color: {_COLORS['grigio_chiaro']}; border: none; border-radius: 4px; "
            f"padding: 4px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background-color: {_COLORS['blu_petrolio_light']}; }}"
            f"QPushButton:disabled {{ background-color: {_COLORS['grafite_light']}; "
            f"color: {_COLORS['grigio_medio']}; }}"
        )
        self.btn_start.clicked.connect(self._on_start_stop)
        header_row.addWidget(self.btn_start)

        layout.addLayout(header_row)

        # === Riga DB: stato + bottone ===
        db_row = QHBoxLayout()
        db_row.setSpacing(8)

        self.lbl_db = QLabel(t("plugins.label.database_missing"))
        self.lbl_db.setStyleSheet(f"font-size: 11px; color: {_COLORS['grigio_medio']};")
        db_row.addWidget(self.lbl_db)
        db_row.addStretch()

        self.btn_db = QPushButton(t("plugins.button.download_db"))
        self.btn_db.setFixedWidth(180)
        self.btn_db.setStyleSheet(
            f"QPushButton {{ background-color: {_COLORS['grafite_light']}; "
            f"color: {_COLORS['grigio_chiaro']}; border: none; border-radius: 4px; "
            f"padding: 3px 8px; font-size: 11px; }}"
            f"QPushButton:hover {{ background-color: {_COLORS['blu_petrolio']}; }}"
        )
        self.btn_db.clicked.connect(self._on_launch_plugin)
        db_row.addWidget(self.btn_db)

        layout.addLayout(db_row)

        # === Progress row (nascosta a riposo) ===
        self._progress_row = QWidget()
        progress_layout = QHBoxLayout(self._progress_row)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(_PB_STYLE)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.lbl_counter = QLabel("0 / 0")
        self.lbl_counter.setStyleSheet(
            f"font-size: 11px; color: {_COLORS['grigio_medio']}; min-width: 90px;"
        )
        self.lbl_counter.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        progress_layout.addWidget(self.lbl_counter)

        self._progress_row.hide()
        layout.addWidget(self._progress_row)

    def _refresh_db_status(self):
        """
        Aggiorna l'etichetta stato DB e il testo del bottone azione.
        Verifica se il plugin ha una funzione is_database_present().
        """
        entry_point = self._manifest.get("entry_point", "")
        # Cerca bionomen.py nella stessa directory dell'entry point
        bionomen_module = self._plugin_dir / "bionomen.py"
        if not bionomen_module.exists():
            self.lbl_db.setText(t("plugins.label.database_missing"))
            self.btn_start.setEnabled(False)
            return

        try:
            # Carica dinamicamente il modulo bionomen per controllare il DB
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                f"bionomen_core_{self._manifest.get('id', 'plugin')}",
                str(bionomen_module),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if hasattr(mod, "is_database_present") and mod.is_database_present():
                date_str = ""
                if hasattr(mod, "get_database_date"):
                    date_str = mod.get_database_date() or ""
                date_display = date_str if date_str else "data sconosciuta"
                self.lbl_db.setText(
                    t("plugins.label.database_present", date=date_display)
                )
                self.lbl_db.setStyleSheet(
                    f"font-size: 11px; color: {_COLORS['verde']};"
                )
                self.btn_db.setText(t("plugins.button.check_updates"))
                self.btn_start.setEnabled(True)
            else:
                self.lbl_db.setText(t("plugins.label.database_missing"))
                self.lbl_db.setStyleSheet(
                    f"font-size: 11px; color: {_COLORS['rosso']};"
                )
                self.btn_db.setText(t("plugins.button.download_db"))
                self.btn_start.setEnabled(False)

        except Exception as e:
            logger.warning(f"Impossibile verificare stato DB plugin: {e}")
            self.lbl_db.setText(t("plugins.label.database_missing"))
            self.btn_start.setEnabled(False)

    def _get_entry_point_path(self) -> str:
        """Ritorna il path assoluto all'entry point del plugin."""
        entry = self._manifest.get("entry_point", "")
        return str(self._plugin_dir / entry)

    def _on_configure(self):
        """Lancia il plugin in modalita' configurazione (senza argomenti extra)."""
        self._on_launch_plugin()

    def _on_launch_plugin(self):
        """
        Lancia il plugin come sottoprocesso con gli argomenti --db e --config.
        Se il processo e' gia' attivo, non fa nulla.
        """
        if self._process and self._process.poll() is None:
            # Il processo e' gia' in esecuzione
            return

        entry = self._get_entry_point_path()
        if not Path(entry).exists():
            logger.warning(f"Entry point non trovato: {entry}")
            return

        cmd = [sys.executable, entry, "--db", self._db_path]
        if self._config_path:
            cmd += ["--config", self._config_path]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            logger.info(f"Plugin avviato: {' '.join(cmd)}")

            # Avvia reader thread per lo stdout
            self._reader_thread = StdoutReaderThread(self._process, parent=self)
            self._reader_thread.progress.connect(self._on_progress)
            self._reader_thread.finished.connect(self._on_process_finished)
            self._reader_thread.start()

        except Exception as e:
            logger.error(f"Errore avvio plugin: {e}")

    def _on_start_stop(self):
        """Avvia o interrompe l'elaborazione lanciando/terminando il sottoprocesso."""
        if self._process and self._process.poll() is None:
            # Processo attivo → interrompi
            self._process.terminate()
            self.btn_start.setText(t("plugins.button.start"))
            self._progress_row.hide()
            logger.info("Plugin interrotto dall'utente")
        else:
            # Avvia elaborazione
            self._start_processing()

    def _start_processing(self):
        """Avvia il sottoprocesso per l'elaborazione."""
        entry = self._get_entry_point_path()
        if not Path(entry).exists():
            logger.warning(f"Entry point non trovato: {entry}")
            return

        cmd = [sys.executable, entry, "--db", self._db_path]
        if self._config_path:
            cmd += ["--config", self._config_path]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            logger.info(f"Plugin (elaborazione) avviato: {' '.join(cmd)}")

            self.btn_start.setText(t("plugins.button.stop"))
            self.btn_configure.setEnabled(False)
            self.btn_db.setEnabled(False)
            self.progress_bar.setValue(0)
            self._progress_row.show()

            self._reader_thread = StdoutReaderThread(self._process, parent=self)
            self._reader_thread.progress.connect(self._on_progress)
            self._reader_thread.finished.connect(self._on_process_finished)
            self._reader_thread.start()

        except Exception as e:
            logger.error(f"Errore avvio elaborazione plugin: {e}")

    def _on_progress(self, current: int, total: int):
        """Aggiorna progress bar e counter."""
        if total > 0:
            pct = int(current * 100 / total)
            self.progress_bar.setValue(pct)
        cur_fmt = f"{current:,}".replace(",", ".")
        tot_fmt = f"{total:,}".replace(",", ".")
        self.lbl_counter.setText(f"{cur_fmt} / {tot_fmt}")

    def _on_process_finished(self):
        """Chiamato quando il sottoprocesso termina."""
        self.btn_start.setText(t("plugins.button.start"))
        self.btn_configure.setEnabled(True)
        self.btn_db.setEnabled(True)
        self._progress_row.hide()
        self._process = None
        self._reader_thread = None
        # Aggiorna stato DB (potrebbe essere cambiato)
        self._refresh_db_status()


class PluginsTab(QWidget):
    """
    Tab 'Plugin' per OffGallery.

    Auto-discovery: scansiona APP_DIR/plugins cercando manifest.json
    con "type": "standalone". Ogni plugin trovato genera una PluginCard.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db_manager = None
        self._db_path = ""
        self._config_path = str(get_app_dir() / "config_new.yaml")
        self._cards = []

        self._build_ui()

    def set_database_manager(self, db_manager):
        """Riceve il db_manager da main_window e aggiorna il db_path."""
        self._db_manager = db_manager
        if db_manager and hasattr(db_manager, "db_path"):
            # Risolve il path assoluto: db_path potrebbe essere relativo alla app_dir
            raw = db_manager.db_path
            p = Path(raw)
            if not p.is_absolute():
                p = get_app_dir() / p
            self._db_path = str(p.resolve())
            # Ricrea le card con il db_path aggiornato
            self._populate_plugins()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # Titolo sezione
        title = QLabel("🧩  Plugin")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {_COLORS['grigio_chiaro']};"
        )
        main_layout.addWidget(title)

        # Area scrollabile per le card
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {_COLORS['grafite']};")

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._no_plugins_label = QLabel(t("plugins.label.no_plugins"))
        self._no_plugins_label.setStyleSheet(
            f"font-size: 12px; color: {_COLORS['grigio_medio']};"
        )
        self._no_plugins_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cards_layout.addWidget(self._no_plugins_label)

        scroll.setWidget(self._cards_container)
        main_layout.addWidget(scroll)

        # Avvia discovery (senza db_path, lo riceveremo tramite set_database_manager)
        self._populate_plugins()

    def _populate_plugins(self):
        """Scansiona la directory plugins e crea le card per i plugin standalone."""
        # Rimuovi card esistenti
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        plugins_dir = get_app_dir() / "plugins"
        if not plugins_dir.exists():
            self._no_plugins_label.show()
            return

        standalone_found = False
        for manifest_path in sorted(plugins_dir.rglob("manifest.json")):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception as e:
                logger.warning(f"Impossibile leggere manifest {manifest_path}: {e}")
                continue

            # Ignora plugin non standalone (es. llm_ollama, llm_lmstudio)
            if manifest.get("type") != "standalone":
                continue

            plugin_dir = manifest_path.parent

            card = PluginCard(
                manifest=manifest,
                plugin_dir=plugin_dir,
                db_path=self._db_path,
                config_path=self._config_path,
                parent=self._cards_container,
            )
            self._cards_layout.addWidget(card)
            self._cards.append(card)
            standalone_found = True

        if standalone_found:
            self._no_plugins_label.hide()
        else:
            self._no_plugins_label.show()
