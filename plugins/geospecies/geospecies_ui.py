"""
GeoSpecies UI — ConfigDialog e DownloadDialog.

DownloadDialog: albero a 4 livelli (Continente → Paese → Macro-area → Zona)
con checkbox tri-state. Il download avviene per zona (bbox → celle 1°×1°).
"""

import sys
import json
import logging
from pathlib import Path

_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
try:
    from plugins.plugin_i18n import pt
except ImportError:
    def pt(key, **kwargs):
        return key

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

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
    QPushButton#danger { background-color: #6B2020; }
    QPushButton#danger:hover { background-color: #8B3030; }
    QLineEdit, QSpinBox {
        background-color: #1E1E1E;
        color: #E3E3E3;
        border: 1px solid #3A3A3A;
        border-radius: 3px;
        padding: 3px 6px;
    }
    QCheckBox { color: #E3E3E3; }
    QGroupBox {
        border: 1px solid #3A3A3A;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
        color: #A0A0A0;
        font-size: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
    }
    QTreeWidget {
        background-color: #1E1E1E;
        color: #E3E3E3;
        border: 1px solid #3A3A3A;
        alternate-background-color: #252525;
    }
    QTreeWidget::item:selected { background-color: #1C4F63; }
    QHeaderView::section {
        background-color: #2A2A2A;
        color: #A0A0A0;
        border: none;
        padding: 3px 6px;
    }
    QTabWidget::pane { border: 1px solid #3A3A3A; }
    QTabBar::tab {
        background-color: #333333;
        color: #A0A0A0;
        padding: 5px 12px;
        border: 1px solid #3A3A3A;
        border-bottom: none;
    }
    QTabBar::tab:selected { background-color: #2A2A2A; color: #E3E3E3; }
    QProgressBar {
        background-color: #1E1E1E;
        border: 1px solid #3A3A3A;
        border-radius: 3px;
        text-align: center;
        color: #E3E3E3;
    }
    QProgressBar::chunk { background-color: #1C4F63; border-radius: 2px; }
"""


class ConfigDialog:
    """Dialog di configurazione GeoSpecies — Tab Taxon, Cache, Parametri."""

    def __init__(self, current_mode=None, count_unprocessed=-1,
                 count_total=-1, count_gallery=-1, parent=None):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QLineEdit, QCheckBox, QDialogButtonBox, QSpinBox,
            QTabWidget, QWidget, QGroupBox, QTreeWidget, QTreeWidgetItem,
        )
        from PyQt6.QtCore import Qt
        from plugins.geospecies.geospecies import (
            load_config, save_config, get_cached_checklists,
            clear_all_cache, delete_checklist, DEFAULT_TAXA,
        )

        self._load_config = load_config
        self._save_config = save_config
        self._cfg = load_config()
        self._parent = parent
        self._DEFAULT_TAXA = DEFAULT_TAXA

        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle(pt("gs.config_title"))
        self._dlg.setModal(True)
        self._dlg.resize(500, 440)
        self._dlg.setMinimumSize(400, 360)
        self._dlg.setStyleSheet(_DARK_STYLE)

        main_layout = QVBoxLayout(self._dlg)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # ── Tab Taxon ─────────────────────────────────────────────────────
        tab_taxon = QWidget()
        taxon_layout = QVBoxLayout(tab_taxon)
        taxon_layout.setContentsMargins(12, 12, 12, 12)
        taxon_layout.setSpacing(6)

        info_taxon = QLabel(pt("gs.taxon_info"))
        info_taxon.setWordWrap(True)
        info_taxon.setStyleSheet("font-size: 10px; color: #B0B0B0; font-style: italic;")
        taxon_layout.addWidget(info_taxon)

        grp_taxa = QGroupBox(pt("gs.taxon_group_all"))
        grp_taxa_layout = QVBoxLayout(grp_taxa)
        grp_taxa_layout.setSpacing(3)

        enabled_taxa = self._cfg.get("enabled_taxa", DEFAULT_TAXA)
        self._taxon_checks = {}
        for taxon in DEFAULT_TAXA:
            cb = QCheckBox(taxon)
            cb.setChecked(taxon in enabled_taxa)
            self._taxon_checks[taxon] = cb
            grp_taxa_layout.addWidget(cb)

        taxon_layout.addWidget(grp_taxa)
        taxon_layout.addStretch()
        tabs.addTab(tab_taxon, pt("gs.tab_taxon"))

        # ── Tab Cache ─────────────────────────────────────────────────────
        tab_cache = QWidget()
        cache_layout = QVBoxLayout(tab_cache)
        cache_layout.setContentsMargins(12, 12, 12, 12)
        cache_layout.setSpacing(8)

        cache_dir_grp = QGroupBox(pt("gs.cache_dir_title"))
        cache_dir_inner = QVBoxLayout(cache_dir_grp)
        cache_dir_row = QHBoxLayout()
        default_cache = str(Path(__file__).parent / "cache")
        self._cache_dir_edit = QLineEdit(self._cfg.get("cache_dir", default_cache))
        cache_dir_row.addWidget(self._cache_dir_edit)
        btn_browse_cache = QPushButton(pt("btn.browse"))
        btn_browse_cache.setFixedWidth(80)
        btn_browse_cache.clicked.connect(self._browse_cache_dir)
        cache_dir_row.addWidget(btn_browse_cache)
        cache_dir_inner.addLayout(cache_dir_row)
        cache_layout.addWidget(cache_dir_grp)

        cache_days_row = QHBoxLayout()
        cache_days_row.addWidget(QLabel(pt("gs.cache_days")))
        self._cache_days_spin = QSpinBox()
        self._cache_days_spin.setRange(1, 3650)
        self._cache_days_spin.setValue(int(self._cfg.get("cache_days", 90)))
        self._cache_days_spin.setFixedWidth(80)
        cache_days_row.addWidget(self._cache_days_spin)
        cache_days_row.addWidget(QLabel(pt("gs.days_unit")))
        cache_days_row.addStretch()
        cache_layout.addLayout(cache_days_row)

        cache_list_lbl = QLabel(pt("gs.cache_list_title"))
        cache_list_lbl.setStyleSheet("font-weight: bold; margin-top: 4px;")
        cache_layout.addWidget(cache_list_lbl)

        self._cache_tree = QTreeWidget()
        self._cache_tree.setHeaderLabels([
            pt("gs.cell_col_taxon"),
            pt("gs.cell_col_cell"),
            pt("gs.cell_col_species"),
            pt("gs.cell_col_date"),
        ])
        self._cache_tree.setAlternatingRowColors(True)
        self._cache_tree.setRootIsDecorated(False)
        self._refresh_cache_list()
        cache_layout.addWidget(self._cache_tree)

        cache_btn_row = QHBoxLayout()
        btn_refresh = QPushButton(pt("gs.cache_refresh"))
        btn_refresh.clicked.connect(self._refresh_cache_list)
        btn_delete = QPushButton(pt("gs.cache_delete_selected"))
        btn_delete.clicked.connect(self._delete_selected_cache)
        btn_clear_all = QPushButton(pt("gs.cache_clear_all"))
        btn_clear_all.setObjectName("danger")
        btn_clear_all.clicked.connect(self._clear_all_cache)
        cache_btn_row.addWidget(btn_refresh)
        cache_btn_row.addWidget(btn_delete)
        cache_btn_row.addStretch()
        cache_btn_row.addWidget(btn_clear_all)
        cache_layout.addLayout(cache_btn_row)
        tabs.addTab(tab_cache, pt("gs.tab_cache"))

        # ── Tab Parametri ─────────────────────────────────────────────────
        tab_params = QWidget()
        params_layout = QVBoxLayout(tab_params)
        params_layout.setContentsMargins(12, 12, 12, 12)
        params_layout.setSpacing(8)

        max_row = QHBoxLayout()
        max_row.addWidget(QLabel(pt("gs.max_species_label")))
        self._max_spin = QSpinBox()
        self._max_spin.setRange(100, 50000)
        self._max_spin.setSingleStep(500)
        self._max_spin.setValue(int(self._cfg.get("max_species_per_taxon", 5000)))
        self._max_spin.setFixedWidth(90)
        max_row.addWidget(self._max_spin)
        max_row.addStretch()
        params_layout.addLayout(max_row)

        timeout_row = QHBoxLayout()
        timeout_row.addWidget(QLabel(pt("gs.timeout_label")))
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(5, 120)
        self._timeout_spin.setValue(int(self._cfg.get("request_timeout", 30)))
        self._timeout_spin.setFixedWidth(70)
        timeout_row.addWidget(self._timeout_spin)
        timeout_row.addWidget(QLabel(pt("gs.timeout_unit")))
        timeout_row.addStretch()
        params_layout.addLayout(timeout_row)

        gbif_note = QLabel(pt("gs.gbif_info"))
        gbif_note.setWordWrap(True)
        gbif_note.setStyleSheet("font-size: 10px; color: #B0B0B0; font-style: italic; margin-top: 8px;")
        params_layout.addWidget(gbif_note)
        params_layout.addStretch()
        tabs.addTab(tab_params, pt("gs.tab_params"))

        # ── Pulsanti dialog ───────────────────────────────────────────────
        btns_row = QHBoxLayout()
        btn_download = QPushButton(pt("gs.btn_download"))
        btn_download.clicked.connect(self._open_download_dialog)
        btns_row.addWidget(btn_download)
        btns_row.addStretch()
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self._dlg.reject)
        btns_row.addWidget(btn_box)
        main_layout.addLayout(btns_row)

    def _browse_cache_dir(self):
        from PyQt6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(
            self._dlg, pt("gs.cache_dir_browse"), self._cache_dir_edit.text()
        )
        if path:
            self._cache_dir_edit.setText(path)

    def _refresh_cache_list(self):
        from plugins.geospecies.geospecies import get_cached_checklists
        self._cache_tree.clear()
        cfg = dict(self._cfg)
        cfg["cache_dir"] = self._cache_dir_edit.text() if hasattr(self, '_cache_dir_edit') else ""
        for entry in get_cached_checklists(cfg):
            from PyQt6.QtWidgets import QTreeWidgetItem
            item = QTreeWidgetItem([
                entry["taxon"], entry["key"],
                str(entry["species_count"]), entry["fetched_at"],
            ])
            item.setData(0, 32, entry["filename"])
            self._cache_tree.addTopLevelItem(item)
        self._cache_tree.resizeColumnToContents(0)
        self._cache_tree.resizeColumnToContents(1)

    def _delete_selected_cache(self):
        from plugins.geospecies.geospecies import delete_checklist
        selected = self._cache_tree.selectedItems()
        if not selected:
            return
        cfg = dict(self._cfg)
        cfg["cache_dir"] = self._cache_dir_edit.text()
        for item in selected:
            filename = item.data(0, 32)
            if filename:
                delete_checklist(filename, cfg)
        self._refresh_cache_list()

    def _clear_all_cache(self):
        from PyQt6.QtWidgets import QMessageBox
        from plugins.geospecies.geospecies import clear_all_cache
        reply = QMessageBox.question(
            self._dlg, pt("gs.cache_clear_confirm_title"),
            pt("gs.cache_clear_confirm_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            cfg = dict(self._cfg)
            cfg["cache_dir"] = self._cache_dir_edit.text()
            count = clear_all_cache(cfg)
            self._refresh_cache_list()
            QMessageBox.information(self._dlg, "GeoSpecies", pt("gs.cache_cleared", n=count))

    def _open_download_dialog(self):
        dlg = DownloadDialog(self._dlg)
        dlg.exec()
        self._refresh_cache_list()

    def _on_accept(self):
        cfg = dict(self._cfg)
        cfg["enabled_taxa"] = [t for t, cb in self._taxon_checks.items() if cb.isChecked()]
        cfg["cache_dir"] = self._cache_dir_edit.text().strip()
        cfg["cache_days"] = self._cache_days_spin.value()
        cfg["max_species_per_taxon"] = self._max_spin.value()
        cfg["request_timeout"] = self._timeout_spin.value()
        self._save_config(cfg)
        self._cfg = cfg
        self._dlg.accept()

    def get_mode(self) -> str:
        return "unprocessed"

    def exec(self) -> int:
        return self._dlg.exec()


class DownloadDialog:
    """
    Dialog per scaricare checklist di specie via GBIF.
    Albero a 4 livelli: Continente → Paese → Macro-area → Zona.
    Checkbox tri-state: spuntare un nodo seleziona tutti i figli.
    Il download avviene per zona (bbox → celle 1°×1°).
    """

    def __init__(self, parent=None):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QTreeWidget, QTreeWidgetItem, QProgressBar, QTextEdit,
        )
        from PyQt6.QtCore import Qt

        self._parent = parent
        self._dl_thread = None
        self._dl_worker = None
        self._abort = None

        from plugins.geospecies.geospecies import load_config, DEFAULT_TAXA
        self._dl_taxa = load_config().get("enabled_taxa", DEFAULT_TAXA)

        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle(pt("gs.download_title"))
        self._dlg.setModal(True)
        self._dlg.resize(460, 580)
        self._dlg.setMinimumSize(400, 480)
        self._dlg.setStyleSheet(_DARK_STYLE)
        self._dlg.closeEvent = self._on_close_event

        layout = QVBoxLayout(self._dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Info ──────────────────────────────────────────────────────────
        info = QLabel(pt("gs.download_info"))
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setStyleSheet(
            "font-size: 10px; color: #B0B0B0; background: #1E2A30; "
            "border: 1px solid #2A4A5A; border-radius: 4px; padding: 8px;"
        )
        layout.addWidget(info)

        taxa_info = QLabel(
            f"<b>{pt('gs.download_taxa')}:</b> {', '.join(self._dl_taxa)}"
        )
        taxa_info.setWordWrap(True)
        taxa_info.setStyleSheet("font-size: 10px; color: #A0C0A0;")
        layout.addWidget(taxa_info)

        # ── Albero aree ───────────────────────────────────────────────────
        layout.addWidget(QLabel(f"<b>{pt('gs.download_countries')}</b>"))

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAlternatingRowColors(True)
        layout.addWidget(self._tree, stretch=1)

        sel_row = QHBoxLayout()
        btn_all = QPushButton(pt("gs.btn_select_all"))
        btn_all.setFixedHeight(22)
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton(pt("gs.btn_select_none"))
        btn_none.setFixedHeight(22)
        btn_none.clicked.connect(self._deselect_all)
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # ── Progress + log ────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(90)
        self._log.setStyleSheet(
            "background-color: #1A1A1A; color: #A0A0A0; "
            "font-family: monospace; font-size: 10px; border: 1px solid #3A3A3A;"
        )
        layout.addWidget(self._log)

        # ── Pulsanti ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_download = QPushButton(pt("gs.btn_start_download"))
        self._btn_download.clicked.connect(self._start_download)
        btn_row.addWidget(self._btn_download)
        btn_row.addStretch()
        btn_close = QPushButton(pt("btn.close"))
        btn_close.clicked.connect(self._dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._build_tree()

    # ── Costruzione albero ────────────────────────────────────────────────

    def _build_tree(self):
        from PyQt6.QtWidgets import QTreeWidgetItem
        from PyQt6.QtCore import Qt
        from plugins.geospecies.geospecies import REGIONS, cells_for_node

        self._tree.blockSignals(True)
        self._tree.clear()

        for continent_name, continent_data in REGIONS.items():
            c_item = self._make_node(continent_name)
            self._tree.addTopLevelItem(c_item)

            for country_name, country_data in continent_data.items():
                if country_name == "_bbox":
                    continue
                co_item = self._make_node(country_name)
                c_item.addChild(co_item)

                for macro_name, macro_data in country_data.items():
                    if macro_name == "_bbox":
                        continue
                    if isinstance(macro_data, tuple):
                        # Foglia diretta (paese senza macro-aree)
                        leaf = self._make_leaf(macro_name, macro_data, cells_for_node(macro_data))
                        co_item.addChild(leaf)
                    else:
                        # Nodo macro-area con sotto-zone
                        ma_item = self._make_node(macro_name)
                        co_item.addChild(ma_item)
                        for zone_name, zone_bbox in macro_data.items():
                            if zone_name == "_bbox":
                                continue
                            n_cells = len(cells_for_node(zone_bbox))
                            leaf = self._make_leaf(zone_name, zone_bbox, n_cells)
                            ma_item.addChild(leaf)

        self._tree.blockSignals(False)

    def _make_node(self, name: str):
        from PyQt6.QtWidgets import QTreeWidgetItem
        from PyQt6.QtCore import Qt
        item = QTreeWidgetItem([name])
        item.setFlags(
            item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsAutoTristate
        )
        item.setCheckState(0, Qt.CheckState.Unchecked)
        return item

    def _make_leaf(self, name: str, bbox: tuple, n_cells):
        from PyQt6.QtWidgets import QTreeWidgetItem
        from PyQt6.QtCore import Qt
        label = f"{name}  ({n_cells} celle)"
        item = QTreeWidgetItem([label])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Unchecked)
        item.setData(0, 32, bbox)   # bbox della zona
        return item

    def _select_all(self):
        from PyQt6.QtCore import Qt
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setCheckState(0, Qt.CheckState.Checked)

    def _deselect_all(self):
        from PyQt6.QtCore import Qt
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setCheckState(0, Qt.CheckState.Unchecked)

    def _get_selected_zones(self) -> list:
        """Restituisce la lista di bbox delle zone foglia selezionate."""
        from PyQt6.QtCore import Qt
        selected = []
        def _walk(item):
            bbox = item.data(0, 32)
            if bbox is not None and item.checkState(0) == Qt.CheckState.Checked:
                selected.append(bbox)
            for i in range(item.childCount()):
                _walk(item.child(i))
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            _walk(root.child(i))
        return selected

    # ── Download ──────────────────────────────────────────────────────────

    def _start_download(self):
        from PyQt6.QtCore import QThread, pyqtSignal, QObject
        import threading

        zones = self._get_selected_zones()
        if not zones:
            self._log_msg(pt("gs.download_no_countries"))
            return

        taxa = self._dl_taxa
        if not taxa:
            self._log_msg(pt("gs.download_no_taxa"))
            return

        from plugins.geospecies.geospecies import load_config, download_zone, cells_for_node
        config = load_config()

        # Totale celle × taxon per progress bar
        total_cells = sum(len(cells_for_node(z)) for z in zones)
        total = total_cells * len(taxa)

        self._progress.setVisible(True)
        self._progress.setMaximum(max(total, 1))
        self._progress.setValue(0)
        self._btn_download.setEnabled(False)
        self._abort = threading.Event()

        class DownloadWorker(QObject):
            progress = pyqtSignal(int)
            status   = pyqtSignal(str)
            finished = pyqtSignal()

            def __init__(self, zones, taxa, config, abort):
                super().__init__()
                self._zones  = zones
                self._taxa   = taxa
                self._config = config
                self._abort  = abort
                self._done   = 0

            def run(self):
                from plugins.geospecies.geospecies import download_zone, cells_for_node
                for bbox in self._zones:
                    if self._abort.is_set():
                        self.status.emit("⚠ Download interrotto.")
                        break
                    n_cells = len(cells_for_node(bbox))
                    for taxon in self._taxa:
                        if self._abort.is_set():
                            break

                        def _cb(msg, _w=self):
                            try:
                                _w.status.emit(msg)
                            except RuntimeError:
                                pass

                        def _cell_cb(done_c, tot_c, _w=self):
                            try:
                                _w.progress.emit(_w._done + done_c)
                            except RuntimeError:
                                pass

                        download_zone(
                            bbox=bbox,
                            zone_name="",
                            taxon=taxon,
                            config=self._config,
                            status_cb=_cb,
                            cell_cb=_cell_cb,
                            abort=self._abort,
                        )
                        self._done += n_cells

                try:
                    self.finished.emit()
                except RuntimeError:
                    pass

        self._dl_thread = QThread()
        self._dl_worker = DownloadWorker(zones, taxa, config, self._abort)
        self._dl_worker.moveToThread(self._dl_thread)
        self._dl_thread.started.connect(self._dl_worker.run)
        self._dl_worker.progress.connect(self._progress.setValue)
        self._dl_worker.status.connect(self._log_msg)
        self._dl_worker.finished.connect(self._dl_thread.quit)
        self._dl_worker.finished.connect(self._on_download_finished)
        self._dl_thread.start()

    def _on_close_event(self, event):
        if self._dl_thread and self._dl_thread.isRunning():
            if self._abort:
                self._abort.set()
            self._dl_thread.quit()
            if not self._dl_thread.wait(15000):
                self._dl_thread.terminate()
                self._dl_thread.wait(2000)
        event.accept()

    def _on_download_finished(self):
        self._btn_download.setEnabled(True)
        self._log_msg(pt("gs.download_complete"))

    def _log_msg(self, msg: str):
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def exec(self) -> int:
        return self._dlg.exec()


def main():
    print("ERROR:GeoSpecies non supporta modalità headless standalone.")
    sys.exit(1)


if __name__ == "__main__":
    main()
