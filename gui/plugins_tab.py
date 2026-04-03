"""
PluginsTab — Tab per la gestione dei plugin di OffGallery.

Auto-discovery: scansiona APP_DIR/plugins cercando manifest.json.
Tipi supportati:
  - "standalone": plugin autonomo (es. BioNomen) → PluginCard completa
  - "llm_backend": plugin LLM Vision (es. Ollama, LM Studio) → LLMPluginCard

PluginCard (standalone):
- Nome, versione, descrizione
- Stato database + bottone azione DB
- Progress bar stile OffGallery
- Counter label
- Bottoni Configura / Avvia (o Interrompi)
- Lanciato come sottoprocesso separato (subprocess.Popen)

LLMPluginCard (llm_backend):
- Nome, versione, descrizione
- Stato connessione (check HTTP health endpoint)
- Bottone Configura → porta l'utente alla Config Tab
"""

import sys
import json
import logging
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

from utils.paths import get_app_dir
from i18n import t

logger = logging.getLogger(__name__)


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


class StdoutReaderThread(QThread):
    """
    Thread che legge stdout di un sottoprocesso e parsa:
      PROGRESS:n:total         → aggiorna progress bar
      SUMMARY:tot:match:nomatch → riepilogo finale
      SOURCE:fonte:specie      → log info fonte consultata
      LOG:level:messaggio      → log warning/error
    """
    progress = pyqtSignal(int, int)
    summary  = pyqtSignal(int, int, int)
    finished = pyqtSignal()

    def __init__(self, process: subprocess.Popen, parent=None):
        super().__init__(parent)
        self._process = process

    def run(self):
        try:
            for line in self._process.stdout:
                line = line.strip()
                if line.startswith("PROGRESS:"):
                    parts = line.split(":")
                    if len(parts) == 3:
                        try:
                            self.progress.emit(int(parts[1]), int(parts[2]))
                        except ValueError:
                            pass
                elif line.startswith("SUMMARY:") or line.startswith("DONE:"):
                    # SUMMARY:tot:match:nomatch  (BioNomen)
                    # DONE:tot:matched:not_matched  (NaturArea, Meteo)
                    parts = line.split(":")
                    if len(parts) == 4:
                        try:
                            self.summary.emit(int(parts[1]), int(parts[2]), int(parts[3]))
                        except ValueError:
                            pass
                elif line.startswith("SOURCE:"):
                    # Formato: SOURCE:fonte:nome_scientifico
                    rest = line[len("SOURCE:"):]
                    sep = rest.find(":")
                    if sep != -1:
                        fonte = rest[:sep]
                        specie = rest[sep+1:]
                        logger.debug(f"Plugin [{fonte}] → {specie}")
                elif line.startswith("LOG:"):
                    # Formato: LOG:level:messaggio
                    rest = line[len("LOG:"):]
                    sep = rest.find(":")
                    if sep != -1:
                        level = rest[:sep].lower()
                        msg = rest[sep+1:]
                        if level == "warning":
                            logger.warning(f"Plugin: {msg}")
                        elif level == "error":
                            logger.error(f"Plugin: {msg}")
                        else:
                            logger.info(f"Plugin: {msg}")
            self._process.wait()
        except Exception as e:
            logger.debug(f"StdoutReaderThread: errore lettura stdout: {e}")
        finally:
            self.finished.emit()


class DownloadWorker(QThread):
    """
    Thread in-process per il download/inizializzazione del database del plugin.
    Carica dinamicamente il modulo core del plugin tramite <plugin_id>.py.
    """
    progress = pyqtSignal(int, int)
    status   = pyqtSignal(str)
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, plugin_dir: Path, plugin_id: str, language: str = "it", parent=None):
        super().__init__(parent)
        self._plugin_dir = plugin_dir
        self._plugin_id  = plugin_id
        self._language   = language

    def run(self):
        try:
            import importlib.util
            core_file = self._plugin_dir / f"{self._plugin_id}.py"
            spec = importlib.util.spec_from_file_location(
                f"{self._plugin_id}_core_dl", str(core_file)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            def _progress_cb(current, total):
                self.progress.emit(current, total)

            def _status_cb(text):
                self.status.emit(text)

            # Chiama download_and_build_database con i kwargs supportati
            import inspect
            sig = inspect.signature(mod.download_and_build_database)
            kwargs = dict(progress_callback=_progress_cb, status_callback=_status_cb)
            if "language" in sig.parameters:
                kwargs["language"] = self._language

            mod.download_and_build_database(**kwargs)
            self.finished.emit()
        except Exception as e:
            logger.error(f"DownloadWorker errore: {e}")
            self.error.emit(str(e))


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

        # Modalità elaborazione corrente (lingua gestita da config.json del plugin)
        self._mode = "unprocessed"
        self._directory_filter = ""    # path directory selezionate (modalità directory)

        self._process = None           # subprocess.Popen attivo (elaborazione)
        self._reader_thread = None     # StdoutReaderThread attivo
        self._download_worker = None   # DownloadWorker in-process

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
        icon = self._manifest.get("icon", "🧩")

        lbl_name = QLabel(f"{icon} {name}  v{version}")
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
        self.btn_db.clicked.connect(self._on_db_action)
        db_row.addWidget(self.btn_db)

        layout.addLayout(db_row)

        # === Riga modalità: mostra modo corrente e directory selezionate ===
        self.lbl_mode = QLabel()
        self.lbl_mode.setStyleSheet(
            f"font-size: 10px; color: {_COLORS['grigio_medio']}; font-style: italic;"
        )
        self.lbl_mode.hide()
        layout.addWidget(self.lbl_mode)

        # === Progress bar download (nascosta a riposo) ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(_PB_STYLE)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()

        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_bar)

        self.lbl_dl_counter = QLabel("")
        self.lbl_dl_counter.setStyleSheet(
            f"font-size: 10px; color: {_COLORS['grigio_medio']}; min-width: 220px;"
        )
        self.lbl_dl_counter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_dl_counter.hide()
        progress_row.addWidget(self.lbl_dl_counter)

        self.btn_dl_stop = QPushButton("✕ Interrompi")
        self.btn_dl_stop.setFixedWidth(100)
        self.btn_dl_stop.setStyleSheet(
            f"QPushButton {{ background-color: {_COLORS['grafite_light']}; "
            f"color: {_COLORS['grigio_chiaro']}; border: none; border-radius: 4px; "
            f"padding: 3px 8px; font-size: 10px; }}"
            f"QPushButton:hover {{ background-color: {_COLORS['rosso']}; }}"
        )
        self.btn_dl_stop.clicked.connect(self._on_dl_stop)
        self.btn_dl_stop.hide()
        progress_row.addWidget(self.btn_dl_stop)

        layout.addLayout(progress_row)

        self.lbl_dl_status = QLabel("")
        self.lbl_dl_status.setStyleSheet(
            f"font-size: 10px; color: {_COLORS['ambra_light']};"
        )
        self.lbl_dl_status.hide()
        layout.addWidget(self.lbl_dl_status)


    def _load_core_module(self):
        """Carica dinamicamente il modulo core del plugin (<plugin_id>.py).
        Ritorna il modulo o None se non trovato/errore."""
        import importlib.util
        plugin_id   = self._manifest.get("id", "")
        core_file   = self._plugin_dir / f"{plugin_id}.py"
        if not core_file.exists():
            return None
        try:
            spec = importlib.util.spec_from_file_location(
                f"{plugin_id}_core", str(core_file)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as e:
            logger.warning(f"Impossibile caricare modulo core plugin '{plugin_id}': {e}")
            return None

    def _refresh_db_status(self):
        """
        Aggiorna l'etichetta stato DB e il testo del bottone azione.
        Usa le funzioni standard is_database_present() / get_database_date() del modulo core.
        """
        requires_db = self._manifest.get("requires_db", True)

        # Plugin senza DB (es. Meteo che usa cache on-demand) — mostra sempre abilitato
        if not requires_db:
            self.lbl_db.setText("Nessun database richiesto — dati recuperati on-demand")
            self.lbl_db.setStyleSheet(f"font-size: 11px; color: {_COLORS['grigio_medio']};")
            self.btn_db.hide()
            self.btn_start.setEnabled(True)
            return

        mod = self._load_core_module()
        if mod is None:
            self.lbl_db.setText(t("plugins.label.database_missing"))
            self.btn_start.setEnabled(False)
            return

        try:
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

    def _on_db_action(self):
        """Scarica o aggiorna il database del plugin direttamente in-process."""
        from PyQt6.QtWidgets import QMessageBox
        mod = self._load_core_module()
        if mod is None:
            logger.warning(f"Modulo core plugin non trovato per: {self._manifest.get('id')}")
            return

        # Se già presente chiede conferma aggiornamento
        try:
            if hasattr(mod, "is_database_present") and mod.is_database_present():
                plugin_name = self._manifest.get("name", "Plugin")
                reply = QMessageBox.question(
                    self, "Aggiorna database",
                    f"Il database {plugin_name} è già presente.\nVuoi verificare e aggiornare?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
        except Exception as e:
            logger.warning(f"Impossibile verificare DB: {e}")

        self._start_download()

    def _start_download(self):
        """Avvia il DownloadWorker in-process."""
        self.btn_db.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_configure.setEnabled(False)

        # Legge lingua da config_new.yaml se disponibile
        language = self._read_language_from_config()

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.lbl_dl_counter.setText("")
        self.lbl_dl_counter.show()
        self.lbl_dl_status.setText("Inizializzazione...")
        self.lbl_dl_status.show()
        self.btn_dl_stop.show()
        self._dl_start_time = None

        plugin_id = self._manifest.get("id", "plugin")
        self._download_worker = DownloadWorker(self._plugin_dir, plugin_id=plugin_id, language=language, parent=self)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.status.connect(self._on_download_status)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _read_language_from_config(self) -> str:
        """Legge la lingua di output da config_new.yaml di OffGallery."""
        if not self._config_path:
            return "it"
        try:
            import yaml
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            lang = cfg.get("ui", {}).get("llm_output_language", "it")
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

    def _on_dl_stop(self):
        """Interrompe il download in corso."""
        if self._download_worker and self._download_worker.isRunning():
            self._download_worker.stop()
            self.lbl_dl_status.setText("Interruzione in corso...")
            self.btn_dl_stop.setEnabled(False)

    def _on_download_status(self, text: str):
        """Aggiorna label descrittiva durante il download."""
        self.lbl_dl_status.setText(text)

    def _on_download_progress(self, current: int, total: int):
        """Aggiorna progress bar e counter con ETA durante il download."""
        import time as _time
        if not hasattr(self, "_dl_start_time"):
            self._dl_start_time = None
        if self._dl_start_time is None and current > 0:
            self._dl_start_time = _time.monotonic()

        if total > 0:
            pct = int(current * 100 / total)
            self.progress_bar.setValue(pct)

        cur_fmt = f"{current:,}".replace(",", ".")
        tot_fmt = f"{total:,}".replace(",", ".")

        eta_str = ""
        if self._dl_start_time and current > 0 and total > current:
            elapsed   = _time.monotonic() - self._dl_start_time
            rate      = current / elapsed if elapsed > 0 else None
            if rate:
                remaining = (total - current) / rate
                if remaining < 60:
                    eta_str = f"  (~{int(remaining)}s)"
                elif remaining < 3600:
                    eta_str = f"  (~{int(remaining / 60)}min)"
                else:
                    eta_str = f"  (~{remaining / 3600:.1f}h)"

        self.lbl_dl_counter.setText(f"{cur_fmt} / {tot_fmt}{eta_str}")

    def _on_download_finished(self):
        """Chiamato al termine del download."""
        self.progress_bar.hide()
        self.lbl_dl_counter.hide()
        self.lbl_dl_status.hide()
        self.btn_dl_stop.hide()
        self.btn_dl_stop.setEnabled(True)
        self.btn_db.setEnabled(True)
        self.btn_configure.setEnabled(True)
        self._download_worker = None
        self._refresh_db_status()

    def _on_download_error(self, msg: str):
        """Chiamato in caso di errore nel download."""
        self.progress_bar.hide()
        self.lbl_dl_counter.hide()
        self.lbl_dl_status.setText(f"Errore: {msg}")
        self.btn_dl_stop.hide()
        self.btn_dl_stop.setEnabled(True)
        self.btn_db.setEnabled(True)
        self.btn_configure.setEnabled(True)
        self._download_worker = None
        logger.error(f"Errore download DB plugin: {msg}")

    def _on_configure(self):
        """Apre il ConfigDialog del plugin caricando il modulo UI dalla entry_point."""
        try:
            import importlib.util
            plugin_id = self._manifest.get("id", "plugin")
            entry_point = self._manifest.get("entry_point", f"{plugin_id}_ui.py")
            ui_path = self._plugin_dir / entry_point
            spec = importlib.util.spec_from_file_location(f"{plugin_id}_ui", str(ui_path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "ConfigDialog"):
                logger.warning(f"Plugin '{plugin_id}' non espone ConfigDialog in {entry_point}")
                return

            # Conta foto selezionate in gallery
            count_gallery = -1
            main_window = self._get_main_window()
            if main_window and hasattr(main_window, "get_selected_gallery_items"):
                selected = main_window.get_selected_gallery_items()
                count_gallery = len(selected) if selected else 0

            # Calcola conteggi candidati per il dialog (se DB disponibile)
            count_unprocessed, count_total = -1, -1
            if self._db_path:
                try:
                    import sqlite3
                    conn = sqlite3.connect(self._db_path)
                    run_condition = self._manifest.get("run_condition", "")
                    output_fields = self._manifest.get("output_fields", [])

                    # Totale foto processabili (rispettando run_condition)
                    base_where = "bioclip_taxonomy IS NOT NULL" if run_condition == "bioclip_not_null" else "1=1"
                    count_total = conn.execute(
                        f"SELECT COUNT(*) FROM images WHERE {base_where}"
                    ).fetchone()[0]

                    # Foto non ancora processate (tutti gli output_fields sono NULL)
                    if output_fields:
                        null_conds = " AND ".join(f"{f} IS NULL" for f in output_fields)
                        try:
                            count_unprocessed = conn.execute(
                                f"SELECT COUNT(*) FROM images WHERE {base_where} AND ({null_conds})"
                            ).fetchone()[0]
                        except Exception:
                            count_unprocessed = -1

                    conn.close()
                except Exception:
                    pass

            # Legge modalità salvata in config (persistenza tra sessioni)
            try:
                core_mod = self._load_core_module()
                if core_mod and hasattr(core_mod, "load_config"):
                    saved_mode = core_mod.load_config().get("mode", self._mode)
                    if saved_mode not in ("directory",):
                        self._mode = saved_mode
            except Exception:
                pass

            dialog = mod.ConfigDialog(
                self._mode,
                count_unprocessed=count_unprocessed,
                count_total=count_total,
                count_gallery=count_gallery,
                parent=self,
            )
            if dialog.exec():
                self._mode = dialog.get_mode()
                if self._mode == "directory":
                    dir_filter = self._pick_directory()
                    if not dir_filter:
                        self._mode = "unprocessed"
                        self._directory_filter = ""
                        self.lbl_mode.hide()
                    else:
                        self._directory_filter = dir_filter
                        n = len(dir_filter.split("|"))
                        dirs_short = ", ".join(
                            Path(d).name for d in dir_filter.split("|")[:3]
                        )
                        if n > 3:
                            dirs_short += f" (+{n - 3})"
                        self.lbl_mode.setText(f"Directory: {dirs_short}")
                        self.lbl_mode.show()
                else:
                    self._directory_filter = ""
                    self.lbl_mode.hide()
        except Exception as e:
            logger.error(f"Impossibile aprire ConfigDialog: {e}")

    def _get_main_window(self):
        """Risale la gerarchia dei parent per trovare la QMainWindow."""
        widget = self.parent()
        while widget:
            from PyQt6.QtWidgets import QMainWindow
            if isinstance(widget, QMainWindow):
                return widget
            widget = widget.parent()
        return None

    def _on_start_stop(self):
        """Avvia l'elaborazione del plugin."""
        if self._process and self._process.poll() is None:
            return  # Processo già attivo — non fare nulla (btn_start è disabilitato)
        self._start_processing()

    def _start_processing(self):
        """Avvia il sottoprocesso per l'elaborazione."""
        from PyQt6.QtWidgets import QMessageBox
        entry = self._get_entry_point_path()
        if not Path(entry).exists():
            logger.warning(f"Entry point non trovato: {entry}")
            return

        cmd = [sys.executable, entry, "--db", self._db_path,
               "--mode", self._mode]
        if self._config_path:
            cmd += ["--config", self._config_path]

        # Gestione modalità ids: scrivi IDs in file temp e passa il path
        if self._mode == "ids":
            main_window = self._get_main_window()
            selected = []
            if main_window and hasattr(main_window, "get_selected_gallery_items"):
                items = main_window.get_selected_gallery_items()
                selected = [
                    item.image_data.get("id")
                    for item in (items or [])
                    if hasattr(item, "image_data") and item.image_data.get("id") is not None
                ]
            if not selected:
                plugin_name = self._manifest.get("name", "Plugin")
                QMessageBox.warning(
                    self, plugin_name,
                    "Nessuna foto selezionata in Gallery.\n"
                    "Seleziona almeno una foto prima di avviare.",
                )
                return
            import tempfile
            ids_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            json.dump(selected, ids_file)
            ids_file.close()
            cmd += ["--ids-file", ids_file.name]

        # Gestione modalità directory: usa directory già scelte in configurazione
        elif self._mode == "directory":
            if not self._directory_filter:
                # Sicurezza: nessuna directory configurata, apri dialog ora
                dir_filter = self._pick_directory()
                if not dir_filter:
                    return  # Utente ha annullato
                self._directory_filter = dir_filter
            cmd += ["--directory", self._directory_filter]

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

            # Disabilita bottoni durante elaborazione
            self.btn_start.setEnabled(False)
            self.btn_configure.setEnabled(False)
            if self.btn_db.isVisible():
                self.btn_db.setEnabled(False)

            # Mostra progress bar e counter per il feedback visivo
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            self.lbl_dl_counter.setText("In elaborazione...")
            self.lbl_dl_counter.show()
            self.lbl_dl_status.setText("")
            self.lbl_dl_status.hide()

            self._reader_thread = StdoutReaderThread(self._process, parent=self)
            self._reader_thread.progress.connect(self._on_process_progress)
            self._reader_thread.summary.connect(self._on_process_summary)
            self._reader_thread.finished.connect(self._on_process_finished)
            self._reader_thread.start()

        except Exception as e:
            logger.error(f"Errore avvio elaborazione plugin: {e}")

    def _pick_directory(self) -> str:
        """Apre il dialog albero directory del DB OffGallery. Ritorna il path scelto o ''."""
        if not self._db_path:
            return ""
        try:
            import sqlite3
            from gui.directory_dialog import DirectoryTreeDialog
            from PyQt6.QtWidgets import QMessageBox

            # Legge filepath e calcola directory parent (come db_manager.get_directory_image_counts)
            conn = sqlite3.connect(self._db_path)
            run_condition = self._manifest.get("run_condition", "")
            where = "bioclip_taxonomy IS NOT NULL" if run_condition == "bioclip_not_null" else "1=1"
            rows = conn.execute(
                f"SELECT filepath FROM images WHERE {where}"
            ).fetchall()
            conn.close()

            dir_counts = {}
            for (fp,) in rows:
                if fp:
                    parent = str(Path(fp).parent)
                    dir_counts[parent] = dir_counts.get(parent, 0) + 1

            plugin_name = self._manifest.get("name", "Plugin")
            if not dir_counts:
                QMessageBox.information(self, plugin_name, "Nessuna directory nel database.")
                return ""

            dlg = DirectoryTreeDialog(dir_counts, parent=self)
            if dlg.exec() and dlg.selected_directories:
                # Passa tutte le directory selezionate come stringa separata da '|'
                # process_images gestirà il filtro multiplo
                return "|".join(dlg.selected_directories)
            return ""
        except Exception as e:
            logger.error(f"Errore apertura dialog directory: {e}")
            return ""

    def _on_process_progress(self, current: int, total: int):
        """Aggiorna progress bar durante l'elaborazione."""
        if total > 0:
            pct = int(current * 100 / total)
            self.progress_bar.setValue(pct)
        cur_fmt = f"{current:,}".replace(",", ".")
        tot_fmt = f"{total:,}".replace(",", ".")
        self.lbl_dl_counter.setText(f"{cur_fmt} / {tot_fmt}")

    def _on_process_summary(self, total: int, matched: int, not_matched: int):
        """Mostra riepilogo finale dell'elaborazione."""
        self.lbl_dl_status.setText(
            f"✅ {total} foto  —  {matched} processate  —  {not_matched} saltate"
        )
        self.lbl_dl_status.show()

    def _on_process_finished(self):
        """Chiamato quando il sottoprocesso termina."""
        self.progress_bar.hide()
        self.lbl_dl_counter.hide()
        self.btn_start.setEnabled(True)
        self.btn_configure.setEnabled(True)
        if self.btn_db.isVisible() or not self.btn_db.isHidden():
            self.btn_db.setEnabled(True)
        self._process = None
        self._reader_thread = None
        self._refresh_db_status()


class LLMPluginCard(QFrame):
    """
    Card grafica per un plugin LLM backend (type: "llm_backend").

    Mostra nome, versione, descrizione, stato connessione e un bottone
    Configura che porta l'utente alla Config Tab (sezione LLM Vision).
    Nessun DB, nessun Avvia: il backend è gestito esternamente (Ollama / LM Studio).
    """

    # Segnale emesso quando l'utente clicca Configura (il ricevente apre la Config Tab)
    configure_requested = pyqtSignal()

    def __init__(self, manifest: dict, config: dict = None, parent=None):
        super().__init__(parent)
        self._manifest = manifest
        self._config = config or {}

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setStyleSheet(f"""
            LLMPluginCard {{
                background-color: {_COLORS['grafite_dark']};
                border: 1px solid {_COLORS['grafite_light']};
                border-radius: 6px;
            }}
        """)

        self._build_ui()

        # Timer per refresh periodico stato connessione (ogni 10 secondi)
        self._timer = QTimer(self)
        self._timer.setInterval(10_000)
        self._timer.timeout.connect(self._check_connection)
        self._timer.start()
        # Check immediato
        self._check_connection()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # === Riga header: nome + versione + descrizione + [Configura] ===
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        name = self._manifest.get("name", "Plugin LLM")
        version = self._manifest.get("version", "")
        description = self._manifest.get("description", "")

        lbl_name = QLabel(f"🔌 {name}  v{version}")
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
        self.btn_configure.clicked.connect(self.configure_requested.emit)
        header_row.addWidget(self.btn_configure)

        layout.addLayout(header_row)

        # === Riga stato connessione ===
        status_row = QHBoxLayout()
        status_row.setSpacing(6)

        self.lbl_status = QLabel("⏳ Verifica connessione...")
        self.lbl_status.setStyleSheet(
            f"font-size: 11px; color: {_COLORS['grigio_medio']};"
        )
        status_row.addWidget(self.lbl_status)

        endpoint = self._manifest.get("default_endpoint", "")
        if endpoint:
            lbl_endpoint = QLabel(endpoint)
            lbl_endpoint.setStyleSheet(
                f"font-size: 10px; color: {_COLORS['grigio_medio']}; font-style: italic;"
            )
            status_row.addWidget(lbl_endpoint)

        status_row.addStretch()
        layout.addLayout(status_row)

    def _check_connection(self):
        """Verifica in background se l'endpoint del plugin è raggiungibile."""
        # Legge endpoint dalla config utente; fallback al default_endpoint del manifest
        llm_cfg = self._config.get('embedding', {}).get('models', {}).get('llm_vision', {})
        endpoint = llm_cfg.get('endpoint', '').strip() or self._manifest.get("default_endpoint", "")
        health_path = self._manifest.get("health_check_path", "")
        if not endpoint or not health_path:
            self.lbl_status.setText("⚠️ Endpoint non configurato")
            return

        url = endpoint.rstrip("/") + health_path

        def _do_check():
            try:
                import urllib.request
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status == 200
            except Exception:
                return False

        # Esecuzione in thread per non bloccare la UI
        import threading
        def _worker():
            ok = _do_check()
            # Guard: il widget potrebbe essere stato distrutto mentre il thread girava
            try:
                from PyQt6 import sip
                if sip.isdeleted(self.lbl_status):
                    return
            except Exception:
                return
            if ok:
                self.lbl_status.setText("✅ Backend attivo e raggiungibile")
                self.lbl_status.setStyleSheet(
                    f"font-size: 11px; color: {_COLORS['verde']};"
                )
            else:
                self.lbl_status.setText("❌ Backend non raggiungibile")
                self.lbl_status.setStyleSheet(
                    f"font-size: 11px; color: {_COLORS['rosso']};"
                )

        t_check = threading.Thread(target=_worker, daemon=True)
        t_check.start()


class PluginsTab(QWidget):
    """
    Tab 'Plugin' per OffGallery.

    Auto-discovery: scansiona APP_DIR/plugins cercando manifest.json.
    - "standalone" → PluginCard
    - "llm_backend" → LLMPluginCard
    """

    # Segnale emesso quando si vuole navigare alla Config Tab
    navigate_to_config = pyqtSignal()

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
        """Scansiona la directory plugins e crea le card per tutti i plugin riconosciuti."""
        # Rimuovi card esistenti
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        plugins_dir = get_app_dir() / "plugins"
        if not plugins_dir.exists():
            self._no_plugins_label.show()
            return

        # Carica config utente per passarla alle LLMPluginCard
        app_config = {}
        try:
            import yaml
            with open(self._config_path, "r", encoding="utf-8") as f:
                app_config = yaml.safe_load(f) or {}
        except Exception:
            pass

        any_found = False
        for manifest_path in sorted(plugins_dir.rglob("manifest.json")):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception as e:
                logger.warning(f"Impossibile leggere manifest {manifest_path}: {e}")
                continue

            plugin_type = manifest.get("type", "")
            plugin_dir = manifest_path.parent

            if plugin_type == "standalone":
                card = PluginCard(
                    manifest=manifest,
                    plugin_dir=plugin_dir,
                    db_path=self._db_path,
                    config_path=self._config_path,
                    parent=self._cards_container,
                )
                self._cards_layout.addWidget(card)
                self._cards.append(card)
                any_found = True

            elif plugin_type == "llm_backend":
                card = LLMPluginCard(
                    manifest=manifest,
                    config=app_config,
                    parent=self._cards_container,
                )
                card.configure_requested.connect(self.navigate_to_config.emit)
                self._cards_layout.addWidget(card)
                self._cards.append(card)
                any_found = True

            else:
                # Tipo sconosciuto o assente: ignora silenziosamente
                logger.debug(f"Plugin ignorato (tipo non supportato): {manifest_path}")

        if any_found:
            self._no_plugins_label.hide()
        else:
            self._no_plugins_label.show()
