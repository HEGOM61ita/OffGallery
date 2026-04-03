"""
Weather Context UI — entry point per modalità headless (subprocess da OffGallery).
Emette su stdout:
  PROGRESS:n:total
  DONE:total:matched:not_matched
  ERROR:messaggio

Espone anche ConfigDialog per la configurazione da PluginCard.
"""

import sys
import json
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ── Stile dark condiviso ──────────────────────────────────────────────────────
_DARK_STYLE = """
    QDialog, QWidget {
        background-color: #2A2A2A;
        color: #E3E3E3;
    }
    QLabel { color: #E3E3E3; }
    QPushButton {
        background-color: #1C4F63;
        color: #E3E3E3;
        border: none;
        border-radius: 4px;
        padding: 5px 12px;
        font-size: 12px;
    }
    QPushButton:hover { background-color: #2A6A82; }
    QPushButton:disabled { background-color: #3A3A3A; color: #808080; }
    QLineEdit {
        background-color: #1E1E1E;
        color: #E3E3E3;
        border: 1px solid #3A3A3A;
        border-radius: 3px;
        padding: 3px 6px;
    }
    QRadioButton { color: #E3E3E3; }
    QSpinBox {
        background-color: #1E1E1E;
        color: #E3E3E3;
        border: 1px solid #3A3A3A;
        border-radius: 3px;
        padding: 2px 6px;
    }
"""


class ConfigDialog:
    """
    Dialog di configurazione Weather Context.

    Sezioni:
    - Percorso cache SQLite (opzionale, default nella dir del plugin)
    - Timeout richieste HTTP
    - Modalità elaborazione

    Richiede PyQt6 (importato lazy per non bloccare la modalità headless).
    """

    def __init__(self, current_mode: str,
                 count_unprocessed: int = -1, count_total: int = -1,
                 count_gallery: int = -1,
                 parent=None):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QLineEdit, QFileDialog, QButtonGroup, QRadioButton,
            QDialogButtonBox, QFrame, QSpinBox,
        )

        _plugin_dir = Path(__file__).parent
        if str(_plugin_dir.parent.parent) not in sys.path:
            sys.path.insert(0, str(_plugin_dir.parent.parent))
        from plugins.weather_context.weather_context import load_config, save_config

        self._load_config  = load_config
        self._save_config  = save_config
        self._current_mode = current_mode
        self._cfg          = load_config()
        self._parent       = parent

        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle("Meteo — Configurazione")
        self._dlg.setModal(True)
        self._dlg.setMinimumWidth(440)
        self._dlg.setStyleSheet(_DARK_STYLE)

        layout = QVBoxLayout(self._dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        def _sep():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet("color: #3A3A3A;")
            return line

        # --- Cache SQLite ---
        layout.addWidget(QLabel("<b>Cache meteo (SQLite)</b>"))
        note = QLabel("La cache evita query duplicate all'API Open-Meteo per le stesse coordinate e data.")
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 10px; color: #B0B0B0; font-style: italic;")
        layout.addWidget(note)
        cache_row = QHBoxLayout()
        default_cache = str(Path(__file__).parent / "data" / "weather_cache.db")
        self._cache_edit = QLineEdit(self._cfg.get("cache_db_path", "") or default_cache)
        cache_row.addWidget(self._cache_edit)
        btn_cache = QPushButton("Sfoglia…")
        btn_cache.setFixedWidth(80)
        btn_cache.clicked.connect(self._browse_cache)
        cache_row.addWidget(btn_cache)
        layout.addLayout(cache_row)
        layout.addWidget(_sep())

        # --- Timeout ---
        layout.addWidget(QLabel("<b>Timeout richieste (secondi)</b>"))
        timeout_row = QHBoxLayout()
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(3, 120)
        self._timeout_spin.setValue(int(self._cfg.get("request_timeout", 10)))
        self._timeout_spin.setFixedWidth(80)
        timeout_row.addWidget(self._timeout_spin)
        timeout_row.addWidget(QLabel("(default: 10 s)"))
        timeout_row.addStretch()
        layout.addLayout(timeout_row)
        layout.addWidget(_sep())

        # --- Modalità elaborazione ---
        layout.addWidget(QLabel("<b>Modalità elaborazione</b>"))
        self._mode_group = QButtonGroup(self._dlg)
        self._mode_group.setExclusive(True)
        modes = [
            ("unprocessed", "Solo foto non ancora processate"),
            ("all",         "Tutto il database"),
            ("ids",         "Foto selezionate in Gallery"
                            + (f"  ({count_gallery} foto)" if count_gallery >= 0 else "")),
        ]
        for mode_id, label in modes:
            rb = QRadioButton(label)
            rb.setChecked(self._current_mode == mode_id)
            rb.setProperty("mode_id", mode_id)
            self._mode_group.addButton(rb)
            layout.addWidget(rb)
        layout.addWidget(_sep())

        # --- OK/Annulla ---
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._on_accept)
        bbox.rejected.connect(self._dlg.reject)
        layout.addWidget(bbox)

        self._QFileDialog = QFileDialog

    def _browse_cache(self):
        path, _ = self._QFileDialog.getSaveFileName(
            self._dlg, "Percorso cache meteo", self._cache_edit.text(), "SQLite (*.db)"
        )
        if path:
            self._cache_edit.setText(path)

    def _on_accept(self):
        cfg = self._load_config()
        val = self._cache_edit.text().strip()
        cfg["cache_db_path"] = val if val != str(Path(__file__).parent / "data" / "weather_cache.db") else ""
        cfg["request_timeout"] = self._timeout_spin.value()
        self._save_config(cfg)
        for btn in self._mode_group.buttons():
            if btn.isChecked():
                self._current_mode = btn.property("mode_id")
                break
        self._dlg.accept()

    def exec(self) -> int:
        from PyQt6.QtWidgets import QDialog
        result = self._dlg.exec()
        return 1 if result == QDialog.DialogCode.Accepted else 0

    def get_mode(self) -> str:
        return self._current_mode


def _progress(current: int, total: int):
    print(f"PROGRESS:{current}:{total}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Weather Context plugin headless")
    parser.add_argument('--db',        required=True,  help="Percorso database OffGallery")
    parser.add_argument('--config',    required=False, help="Percorso config.json plugin")
    parser.add_argument('--directory', required=False, help="Non usato, per compatibilità")
    parser.add_argument('--mode',      required=False, default='unprocessed',
                        choices=['unprocessed', 'all', 'directory', 'selection', 'ids'])
    parser.add_argument('--ids',       required=False, help="JSON array di image_id inline")
    parser.add_argument('--ids-file',  required=False, dest='ids_file', help="Path a file JSON con array di image_id")
    parser.add_argument('--filter-bioclip', action='store_true',
                        help="Processa solo foto con bioclip_taxonomy non NULL")
    parser.add_argument('--headless',  action='store_true')
    args = parser.parse_args()

    # Carica configurazione
    config = {}
    config_path = args.config or str(Path(__file__).parent / 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception:
        pass

    # Prepara image_ids (modalità 'selection' o 'ids' da gallery)
    image_ids = None
    if args.mode in ('selection', 'ids'):
        try:
            if args.ids_file:
                with open(args.ids_file, 'r', encoding='utf-8') as f:
                    image_ids = json.load(f)
            elif args.ids:
                image_ids = json.loads(args.ids)
        except Exception:
            print("ERROR:ids non validi", flush=True)
            sys.exit(1)

    # Importa core
    try:
        from plugins.weather_context.weather_context import process_images
    except ImportError:
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from plugins.weather_context.weather_context import process_images
        except ImportError as e:
            print(f"ERROR:Import fallito: {e}", flush=True)
            sys.exit(1)

    # Esegui
    try:
        matched, not_matched = process_images(
            db_path=args.db,
            config=config,
            image_ids=image_ids,
            filter_bioclip=args.filter_bioclip,
            unprocessed_only=(args.mode == 'unprocessed'),
            progress_cb=_progress
        )
        total = matched + not_matched
        print(f"DONE:{total}:{matched}:{not_matched}", flush=True)
    except Exception as e:
        print(f"ERROR:{e}", flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
