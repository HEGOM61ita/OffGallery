"""
NaturArea UI — entry point per modalità headless (subprocess da OffGallery).
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

# ── Stile dark condiviso con plugins_tab ─────────────────────────────────────
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
    QComboBox {
        background-color: #1E1E1E;
        color: #E3E3E3;
        border: 1px solid #3A3A3A;
        border-radius: 3px;
        padding: 2px 6px;
    }
"""


class ConfigDialog:
    """
    Dialog di configurazione NaturArea.

    Sezioni:
    - Percorso file sorgente WDPA (GeoJSON)
    - Percorso database WDPA (SQLite output)
    - Directory cache tile ESA WorldCover
    - Tolleranza GPS (metri)
    - Modalità elaborazione
    - Bottone Costruisci DB

    Richiede PyQt6 (importato lazy per non bloccare la modalità headless).
    """

    def __init__(self, current_mode: str,
                 count_unprocessed: int = -1, count_total: int = -1,
                 count_gallery: int = -1,
                 parent=None):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QLineEdit, QFileDialog, QButtonGroup, QRadioButton,
            QDialogButtonBox, QFrame, QMessageBox, QProgressBar,
        )
        from PyQt6.QtCore import Qt

        # Aggiunge modulo corrente al path per import naturarea
        _plugin_dir = Path(__file__).parent
        if str(_plugin_dir.parent.parent) not in sys.path:
            sys.path.insert(0, str(_plugin_dir.parent.parent))
        from plugins.naturarea.naturarea import load_config, save_config

        self._load_config  = load_config
        self._save_config  = save_config
        self._current_mode = current_mode
        self._cfg          = load_config()
        self._parent       = parent

        # ── Costruisce il dialog Qt ──────────────────────────────────────────
        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle("NaturArea — Configurazione")
        self._dlg.setModal(True)
        self._dlg.setMinimumWidth(480)
        self._dlg.setStyleSheet(_DARK_STYLE)

        layout = QVBoxLayout(self._dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        def _sep():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet("color: #3A3A3A;")
            return line

        # --- File sorgente WDPA ---
        layout.addWidget(QLabel("<b>File sorgente WDPA (GeoJSON)</b>"))
        note = QLabel("Scarica manualmente da protectedplanet.net → WDPA → GeoJSON")
        note.setStyleSheet("font-size: 10px; color: #B0B0B0; font-style: italic;")
        layout.addWidget(note)
        src_row = QHBoxLayout()
        self._src_edit = QLineEdit(self._cfg.get("wdpa_source_path", ""))
        src_row.addWidget(self._src_edit)
        btn_src = QPushButton("Sfoglia…")
        btn_src.setFixedWidth(80)
        btn_src.clicked.connect(self._browse_source)
        src_row.addWidget(btn_src)
        layout.addLayout(src_row)
        layout.addWidget(_sep())

        # --- Percorso DB WDPA ---
        layout.addWidget(QLabel("<b>Database WDPA (SQLite)</b>"))
        db_row = QHBoxLayout()
        default_db = str(Path(__file__).parent / "data" / "wdpa.db")
        self._db_edit = QLineEdit(self._cfg.get("wdpa_db_path", default_db))
        db_row.addWidget(self._db_edit)
        btn_db = QPushButton("Sfoglia…")
        btn_db.setFixedWidth(80)
        btn_db.clicked.connect(self._browse_db)
        db_row.addWidget(btn_db)
        layout.addLayout(db_row)

        # Bottone costruisci DB
        self._btn_build = QPushButton("⚙  Costruisci database WDPA ora")
        self._btn_build.setStyleSheet(
            "QPushButton { background-color: #C88B2E; color: #1E1E1E; font-weight: bold; "
            "border-radius: 4px; padding: 5px 12px; } "
            "QPushButton:hover { background-color: #E0A84A; }"
        )
        self._btn_build.clicked.connect(self._build_db)
        layout.addWidget(self._btn_build)

        # Progress bar build DB (nascosta)
        self._pb = QProgressBar()
        self._pb.setTextVisible(False)
        self._pb.setRange(0, 100)
        self._pb.hide()
        self._pb.setStyleSheet("""
            QProgressBar { border: 1px solid #555; background: #2a2a2a; border-radius: 3px; max-height: 8px; }
            QProgressBar::chunk { background: #C88B2E; border-radius: 2px; }
        """)
        layout.addWidget(self._pb)
        self._lbl_build_status = QLabel("")
        self._lbl_build_status.setStyleSheet("font-size: 10px; color: #E0A84A;")
        self._lbl_build_status.hide()
        layout.addWidget(self._lbl_build_status)

        layout.addWidget(_sep())

        # --- Directory tile ESA ---
        layout.addWidget(QLabel("<b>Cache tile ESA WorldCover</b>"))
        esa_note = QLabel("Le tile GeoTIFF (~100 MB ciascuna) vengono scaricate automaticamente al primo utilizzo per area geografica.")
        esa_note.setWordWrap(True)
        esa_note.setStyleSheet("font-size: 10px; color: #B0B0B0; font-style: italic;")
        layout.addWidget(esa_note)
        esa_row = QHBoxLayout()
        default_esa = str(Path(__file__).parent / "data" / "esa_tiles")
        self._esa_edit = QLineEdit(self._cfg.get("esa_tiles_dir", default_esa))
        esa_row.addWidget(self._esa_edit)
        btn_esa = QPushButton("Sfoglia…")
        btn_esa.setFixedWidth(80)
        btn_esa.clicked.connect(self._browse_esa)
        esa_row.addWidget(btn_esa)
        layout.addLayout(esa_row)
        layout.addWidget(_sep())

        # --- Tolleranza GPS ---
        layout.addWidget(QLabel("<b>Tolleranza GPS (metri)</b>"))
        tol_row = QHBoxLayout()
        self._tol_edit = QLineEdit(str(self._cfg.get("gps_tolerance_m", 50)))
        self._tol_edit.setFixedWidth(80)
        tol_row.addWidget(self._tol_edit)
        tol_row.addWidget(QLabel("m  (default: 50)"))
        tol_row.addStretch()
        layout.addLayout(tol_row)
        layout.addWidget(_sep())

        # --- Modalità elaborazione ---
        layout.addWidget(QLabel("<b>Modalità elaborazione</b>"))
        self._mode_group = QButtonGroup(self._dlg)
        self._mode_group.setExclusive(True)
        modes = [
            ("unprocessed", "Solo foto non ancora processate"),
            ("all",         "Tutto il database"),
            ("ids",         f"Foto selezionate in Gallery"
                            + (f"  ({count_gallery} foto)" if count_gallery >= 0 else "")),
        ]
        for mode_id, label in modes:
            rb = QRadioButton(label)
            rb.setChecked(self._current_mode == mode_id)
            rb.setProperty("mode_id", mode_id)
            self._mode_group.addButton(rb)
            layout.addWidget(rb)
        layout.addWidget(_sep())

        # --- Bottoni OK/Annulla ---
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._on_accept)
        bbox.rejected.connect(self._dlg.reject)
        layout.addWidget(bbox)

        # Salva riferimenti Qt necessari a metodi successivi
        self._QFileDialog    = QFileDialog
        self._QMessageBox    = QMessageBox
        self._QProgressBar   = QProgressBar

    # ── Slot interfaccia ──────────────────────────────────────────────────────

    def _browse_source(self):
        path, _ = self._QFileDialog.getOpenFileName(
            self._dlg, "Seleziona file GeoJSON WDPA", "", "GeoJSON (*.json *.geojson)"
        )
        if path:
            self._src_edit.setText(path)

    def _browse_db(self):
        path, _ = self._QFileDialog.getSaveFileName(
            self._dlg, "Percorso database WDPA", self._db_edit.text(), "SQLite (*.db)"
        )
        if path:
            self._db_edit.setText(path)

    def _browse_esa(self):
        from PyQt6.QtWidgets import QFileDialog as QFD
        path = QFD.getExistingDirectory(
            self._dlg, "Directory cache tile ESA WorldCover", self._esa_edit.text()
        )
        if path:
            self._esa_edit.setText(path)

    def _build_db(self):
        """Avvia la costruzione del DB WDPA in un thread separato."""
        import threading
        self._save_current_config()
        cfg = self._load_config()
        src = cfg.get("wdpa_source_path", "")
        if not src or not Path(src).exists():
            self._QMessageBox.warning(
                self._dlg, "NaturArea",
                "Configura prima il percorso del file sorgente WDPA."
            )
            return

        self._btn_build.setEnabled(False)
        self._pb.setValue(0)
        self._pb.show()
        self._lbl_build_status.setText("Costruzione in corso...")
        self._lbl_build_status.show()

        def _worker():
            try:
                if str(Path(__file__).parent.parent.parent) not in sys.path:
                    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
                from plugins.naturarea.naturarea import download_and_build_database

                def _prog(cur, tot):
                    if tot > 0:
                        pct = int(cur * 100 / tot)
                        # Aggiorna GUI nel thread principale tramite QMetaObject non disponibile
                        # qui — usiamo un flag semplice, il progress non è critico
                        pass

                download_and_build_database(
                    progress_callback=_prog,
                    status_callback=lambda s: None,
                )
                self._pb.hide()
                self._lbl_build_status.setText("✅ Database costruito con successo")
            except Exception as e:
                self._pb.hide()
                self._lbl_build_status.setText(f"❌ Errore: {e}")
            finally:
                self._btn_build.setEnabled(True)

        threading.Thread(target=_worker, daemon=True).start()

    def _save_current_config(self):
        cfg = self._load_config()
        cfg["wdpa_source_path"] = self._src_edit.text().strip()
        cfg["wdpa_db_path"]     = self._db_edit.text().strip()
        cfg["esa_tiles_dir"]    = self._esa_edit.text().strip()
        try:
            cfg["gps_tolerance_m"] = float(self._tol_edit.text().strip())
        except ValueError:
            cfg["gps_tolerance_m"] = 50.0
        self._save_config(cfg)

    def _on_accept(self):
        self._save_current_config()
        # Legge modalità selezionata
        for btn in self._mode_group.buttons():
            if btn.isChecked():
                self._current_mode = btn.property("mode_id")
                break
        self._dlg.accept()

    # ── API pubblica (compatibile con bionomen_ui.ConfigDialog) ──────────────

    def exec(self) -> int:
        """Esegue il dialog, ritorna 1 (Accepted) o 0 (Rejected)."""
        from PyQt6.QtWidgets import QDialog
        result = self._dlg.exec()
        return 1 if result == QDialog.DialogCode.Accepted else 0

    def get_mode(self) -> str:
        return self._current_mode


def _progress(current: int, total: int):
    print(f"PROGRESS:{current}:{total}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="NaturArea plugin headless")
    parser.add_argument('--db',        required=True,  help="Percorso database OffGallery")
    parser.add_argument('--config',    required=False, help="Percorso config.json plugin")
    parser.add_argument('--directory', required=False, help="Directory immagini (non usato, per compatibilità)")
    parser.add_argument('--mode',      required=False, default='unprocessed',
                        choices=['unprocessed', 'all', 'directory', 'selection', 'ids'],
                        help="Modalità: unprocessed=non processate, all=tutte, selection/ids=da --ids")
    parser.add_argument('--ids',       required=False, help="JSON array di image_id inline")
    parser.add_argument('--ids-file',  required=False, dest='ids_file', help="Path a file JSON con array di image_id")
    parser.add_argument('--filter-bioclip', action='store_true',
                        help="Processa solo foto con bioclip_taxonomy non NULL")
    parser.add_argument('--headless',  action='store_true', help="Modalità headless (nessuna UI Qt)")
    args = parser.parse_args()

    # Carica configurazione
    config = {}
    config_path = args.config or str(Path(__file__).parent / 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception:
        pass

    # Prepara image_ids se modalità selection o ids (da gallery)
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
        from plugins.naturarea.naturarea import process_images
    except ImportError:
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from plugins.naturarea.naturarea import process_images
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
