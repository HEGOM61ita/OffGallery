"""
GeoSpecies UI — ConfigDialog e DownloadDialog.

ConfigDialog: configurazione taxon, cache, parametri download.
DownloadDialog: scarica checklist per paese con gerarchia Continente → Paese.

Entry point headless (subprocess da OffGallery): non utilizzato direttamente —
GeoSpecies opera nella pipeline BioCLIP, non come elaborazione standalone.
"""

import sys
import json
import logging
from pathlib import Path

# Aggiunge la root del progetto al path
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

# ── Stile dark condiviso ──────────────────────────────────────────────────
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
    QPushButton#danger {
        background-color: #6B2020;
    }
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
    """
    Dialog di configurazione GeoSpecies.

    Tab 1 — Taxon: checkboxes per abilitare/disabilitare taxon
    Tab 2 — Cache: directory, durata, lista checklist, svuota
    Tab 3 — Parametri: max specie, timeout

    Firma compatibile con PluginCard di OffGallery (current_mode e conteggi ignorati).
    Fonte dati: solo GBIF (nessuna registrazione richiesta).
    """

    def __init__(self, current_mode=None, count_unprocessed=-1,
                 count_total=-1, count_gallery=-1, parent=None):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QLineEdit, QFileDialog, QCheckBox, QDialogButtonBox,
            QSpinBox, QTabWidget, QWidget, QGroupBox,
            QTreeWidget, QTreeWidgetItem,
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

        # ── Tab 1: Taxon ─────────────────────────────────────────────────
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

        # ── Tab 2: Cache ──────────────────────────────────────────────────
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
            pt("gs.cache_col_taxon"),
            pt("gs.cache_col_area"),
            pt("gs.cache_col_species"),
            pt("gs.cache_col_date"),
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

        # ── Tab 3: Parametri ───────────────────────────────────────────────
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

        # ── Pulsanti dialog ────────────────────────────────────────────────
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
            self._dlg, pt("gs.cache_dir_browse"),
            self._cache_dir_edit.text()
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
                entry["taxon"],
                entry["key"],
                str(entry["species_count"]),
                entry["fetched_at"],
            ])
            item.setData(0, 32, entry["filename"])
            self._cache_tree.addTopLevelItem(item)

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
        """Compatibilità con PluginCard — GeoSpecies non ha modalità elaborazione."""
        return "unprocessed"

    def exec(self) -> int:
        return self._dlg.exec()


class DownloadDialog:
    """
    Dialog per scaricare checklist di specie per paese via GBIF.
    Gerarchia: Continente → Paese.
    """

    def __init__(self, parent=None):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QTreeWidget, QProgressBar, QWidget, QTextEdit,
        )
        from PyQt6.QtCore import Qt

        self._parent = parent
        self._dl_thread = None
        self._dl_worker = None

        from plugins.geospecies.geospecies import load_config
        self._dl_taxa = load_config().get("enabled_taxa", [])

        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle(pt("gs.download_title"))
        self._dlg.setModal(True)
        self._dlg.resize(420, 480)
        self._dlg.setMinimumSize(350, 380)
        self._dlg.setStyleSheet(_DARK_STYLE)
        self._dlg.closeEvent = self._on_close_event

        layout = QVBoxLayout(self._dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info = QLabel(pt("gs.download_info"))
        info.setWordWrap(True)
        info.setStyleSheet(
            "font-size: 10px; color: #B0B0B0; background: #1E2A30; "
            "border: 1px solid #2A4A5A; border-radius: 4px; padding: 8px;"
        )
        layout.addWidget(info)

        taxa_info = QLabel(f"<b>{pt('gs.download_taxa')}:</b> {', '.join(self._dl_taxa)}")
        taxa_info.setWordWrap(True)
        taxa_info.setStyleSheet("font-size: 10px; color: #A0C0A0; margin-bottom: 4px;")
        layout.addWidget(taxa_info)

        # ── Albero paesi ─────────────────────────────────────────────────
        country_header = QHBoxLayout()
        country_header.addWidget(QLabel(f"<b>{pt('gs.download_countries')}</b>"))
        btn_load = QPushButton(pt("gs.btn_load_countries"))
        btn_load.setFixedHeight(24)
        btn_load.clicked.connect(self._load_countries)
        country_header.addWidget(btn_load)
        layout.addLayout(country_header)

        self._country_tree = QTreeWidget()
        self._country_tree.setHeaderHidden(True)
        self._country_tree.setAlternatingRowColors(True)
        layout.addWidget(self._country_tree, stretch=1)

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
        self._log.setMaximumHeight(80)
        self._log.setStyleSheet(
            "background-color: #1A1A1A; color: #A0A0A0; "
            "font-family: monospace; font-size: 10px; border: 1px solid #3A3A3A;"
        )
        layout.addWidget(self._log)

        # ── Pulsanti ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_download = QPushButton(pt("gs.btn_start_download"))
        self._btn_download.clicked.connect(self._start_download)
        btn_row.addWidget(self._btn_download)
        btn_row.addStretch()
        btn_close = QPushButton(pt("btn.close"))
        btn_close.clicked.connect(self._dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._load_countries()

    def _load_countries(self):
        from PyQt6.QtWidgets import QTreeWidgetItem
        from PyQt6.QtCore import Qt
        from plugins.geospecies.geospecies import get_available_countries
        from plugins.geospecies.geospecies_ui import _get_country_continent_map

        self._country_tree.clear()
        self._log_msg(pt("gs.loading_countries"))

        CONTINENT_LABELS = {
            "Europe":        pt("gs.continent_europe"),
            "Africa":        pt("gs.continent_africa"),
            "Asia":          pt("gs.continent_asia"),
            "North America": pt("gs.continent_namerica"),
            "South America": pt("gs.continent_samerica"),
            "Oceania":       pt("gs.continent_oceania"),
            "Antarctica":    pt("gs.continent_antarctica"),
        }

        country_continent = _get_country_continent_map()
        countries = get_available_countries()
        if not countries:
            self._log_msg(pt("gs.countries_load_error"))
            return

        continent_items = {}
        for c_key, c_label in CONTINENT_LABELS.items():
            item = QTreeWidgetItem([c_label])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            continent_items[c_key] = item
            self._country_tree.addTopLevelItem(item)

        fallback = continent_items.get("Africa")
        for country in countries:
            iso2 = country["iso2"]
            name = country["name"]
            continent = country_continent.get(iso2, "Africa")
            parent_item = continent_items.get(continent, fallback)
            child = QTreeWidgetItem(parent_item, [f"{name} ({iso2})"])
            child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            child.setCheckState(0, Qt.CheckState.Unchecked)
            child.setData(0, 32, iso2)

        self._country_tree.expandAll()
        self._log_msg(pt("gs.countries_loaded", n=len(countries)))

    def _select_all(self):
        from PyQt6.QtCore import Qt
        root = self._country_tree.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setCheckState(0, Qt.CheckState.Checked)

    def _deselect_all(self):
        from PyQt6.QtCore import Qt
        root = self._country_tree.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setCheckState(0, Qt.CheckState.Unchecked)

    def _get_selected_countries(self) -> list:
        from PyQt6.QtCore import Qt
        selected = []
        root = self._country_tree.invisibleRootItem()
        for i in range(root.childCount()):
            continent = root.child(i)
            for j in range(continent.childCount()):
                item = continent.child(j)
                if item.checkState(0) == Qt.CheckState.Checked:
                    iso2 = item.data(0, 32)
                    if iso2:
                        selected.append(iso2)
        return selected

    def _start_download(self):
        from PyQt6.QtCore import QThread, pyqtSignal, QObject

        countries = self._get_selected_countries()
        if not countries:
            self._log_msg(pt("gs.download_no_countries"))
            return

        taxa = self._dl_taxa
        if not taxa:
            self._log_msg(pt("gs.download_no_taxa"))
            return

        from plugins.geospecies.geospecies import load_config, download_area
        config = load_config()
        total = len(countries) * len(taxa)

        self._progress.setVisible(True)
        self._progress.setMaximum(total)
        self._progress.setValue(0)
        self._btn_download.setEnabled(False)

        class DownloadWorker(QObject):
            progress = pyqtSignal(int)
            status   = pyqtSignal(str)
            finished = pyqtSignal()

            def __init__(self, countries, taxa, config):
                super().__init__()
                self._countries = countries
                self._taxa = taxa
                self._config = config

            def run(self):
                done = 0
                for country in self._countries:
                    for taxon in self._taxa:
                        download_area(
                            country_iso2=country,
                            taxon=taxon,
                            config=self._config,
                            status_cb=lambda msg: self.status.emit(msg)
                        )
                        done += 1
                        self.progress.emit(done)
                self.finished.emit()

        self._dl_thread = QThread()
        self._dl_worker = DownloadWorker(countries, taxa, config)
        self._dl_worker.moveToThread(self._dl_thread)
        self._dl_thread.started.connect(self._dl_worker.run)
        self._dl_worker.progress.connect(self._progress.setValue)
        self._dl_worker.status.connect(self._log_msg)
        self._dl_worker.finished.connect(self._dl_thread.quit)
        self._dl_worker.finished.connect(self._on_download_finished)
        self._dl_thread.start()

    def _on_close_event(self, event):
        """Attende la fine del thread prima di chiudere per evitare crash."""
        if self._dl_thread and self._dl_thread.isRunning():
            self._dl_thread.quit()
            self._dl_thread.wait(3000)
        event.accept()

    def _on_download_finished(self):
        self._btn_download.setEnabled(True)
        self._log_msg(pt("gs.download_complete"))

    def _log_msg(self, msg: str):
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def exec(self) -> int:
        return self._dlg.exec()


# ── Mappatura statica paese → continente ──────────────────────────────────

def _get_country_continent_map() -> dict:
    europe = [
        "AL","AD","AT","BY","BE","BA","BG","HR","CY","CZ","DK","EE","FI","FR",
        "DE","GR","HU","IS","IE","IT","XK","LV","LI","LT","LU","MK","MT","MD",
        "MC","ME","NL","NO","PL","PT","RO","SM","RS","SK","SI","ES","SE","CH",
        "UA","GB","VA",
    ]
    africa = [
        "DZ","AO","BJ","BW","BF","BI","CV","CM","CF","TD","KM","CG","CD","CI",
        "DJ","EG","GQ","ER","SZ","ET","GA","GM","GH","GN","GW","KE","LS","LR",
        "LY","MG","MW","ML","MR","MU","YT","MA","MZ","NA","NE","NG","RE","RW",
        "ST","SN","SC","SL","SO","ZA","SS","SD","TZ","TG","TN","UG","EH","ZM","ZW",
    ]
    asia = [
        "AF","AM","AZ","BH","BD","BT","BN","KH","CN","GE","IN","ID","IR","IQ",
        "IL","JP","JO","KZ","KW","KG","LA","LB","MY","MV","MN","MM","NP","KP",
        "OM","PK","PS","PH","QA","SA","SG","LK","SY","TW","TJ","TH","TL","TR",
        "TM","AE","UZ","VN","YE",
    ]
    namerica = [
        "AG","BS","BB","BZ","CA","CR","CU","DM","DO","SV","GD","GT","HT","HN",
        "JM","MX","NI","PA","KN","LC","VC","TT","US",
    ]
    samerica = [
        "AR","BO","BR","CL","CO","EC","GY","PY","PE","SR","UY","VE",
    ]
    oceania = [
        "AU","FJ","KI","MH","FM","NR","NZ","PW","PG","WS","SB","TO","TV","VU",
    ]
    result = {}
    for iso2 in europe:   result[iso2] = "Europe"
    for iso2 in africa:   result[iso2] = "Africa"
    for iso2 in asia:     result[iso2] = "Asia"
    for iso2 in namerica: result[iso2] = "North America"
    for iso2 in samerica: result[iso2] = "South America"
    for iso2 in oceania:  result[iso2] = "Oceania"
    return result


def main():
    print("ERROR:GeoSpecies non supporta modalità headless standalone.")
    sys.exit(1)


if __name__ == "__main__":
    main()
