"""
GeoNames UI — configurazione plugin e entry point CLI.

Questo modulo espone:
- ConfigDialog: finestra PyQt6 compatibile con il loader di OffGallery
- main(): entry point headless per elaborazione batch

Requisiti impliciti dal core geonames.py:
- load_config() / save_config(cfg)
- get_database_date()
- get_downloaded_nations(cfg)
- download_and_build_database(progress_callback, status_callback, nation_code)
- GeoNamesEnricher(config)
- process_images(...)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent

_DARK_STYLE = """
QDialog, QWidget { background-color: #2A2A2A; color: #E3E3E3; }
QLabel { color: #E3E3E3; }
QPushButton {
    background-color: #1C4F63; color: #E3E3E3;
    border: none; border-radius: 4px; padding: 5px 12px; font-size: 12px;
}
QPushButton:hover { background-color: #2A6A82; }
QPushButton:disabled { background-color: #3A3A3A; color: #808080; }
QLineEdit, QDoubleSpinBox, QComboBox, QListWidget {
    background-color: #1E1E1E; color: #E3E3E3;
    border: 1px solid #3A3A3A; border-radius: 3px; padding: 3px 6px;
}
QListWidget::item:selected { background-color: #1C4F63; }
QCheckBox { color: #E3E3E3; }
QProgressBar {
    border: 1px solid #555; background: #2a2a2a;
    border-radius: 3px; max-height: 8px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #C88B2E, stop:1 #E0A84A);
    border-radius: 2px;
}
QGroupBox {
    color: #C88B2E; border: 1px solid #3A3A3A; border-radius: 4px;
    margin-top: 8px; padding-top: 6px; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
"""

_BTN_AMBER = (
    "QPushButton { background-color: #C88B2E; color: #1E1E1E; font-weight: bold; "
    "border-radius: 4px; padding: 5px 12px; } "
    "QPushButton:hover { background-color: #E0A84A; } "
    "QPushButton:disabled { background-color: #3A3A3A; color: #808080; }"
)

AVAILABLE_NATIONS = [
    ("AD", "Andorra"), ("AE", "Emirati Arabi"), ("AF", "Afghanistan"), ("AG", "Antigua e Barbuda"),
    ("AL", "Albania"), ("AM", "Armenia"), ("AO", "Angola"), ("AR", "Argentina"), ("AT", "Austria"),
    ("AU", "Australia"), ("AZ", "Azerbaigian"), ("BA", "Bosnia Erzegovina"), ("BB", "Barbados"),
    ("BD", "Bangladesh"), ("BE", "Belgio"), ("BF", "Burkina Faso"), ("BG", "Bulgaria"),
    ("BH", "Bahrain"), ("BI", "Burundi"), ("BJ", "Benin"), ("BN", "Brunei"), ("BO", "Bolivia"),
    ("BR", "Brasile"), ("BS", "Bahamas"), ("BT", "Bhutan"), ("BW", "Botswana"), ("BY", "Bielorussia"),
    ("BZ", "Belize"), ("CA", "Canada"), ("CD", "Congo RD"), ("CF", "Rep. Centrafricana"),
    ("CG", "Congo"), ("CH", "Svizzera"), ("CI", "Costa d'Avorio"), ("CL", "Cile"),
    ("CM", "Camerun"), ("CN", "Cina"), ("CO", "Colombia"), ("CR", "Costa Rica"), ("CU", "Cuba"),
    ("CV", "Capo Verde"), ("CY", "Cipro"), ("CZ", "Rep. Ceca"), ("DE", "Germania"),
    ("DJ", "Gibuti"), ("DK", "Danimarca"), ("DM", "Dominica"), ("DO", "Rep. Dominicana"),
    ("DZ", "Algeria"), ("EC", "Ecuador"), ("EE", "Estonia"), ("EG", "Egitto"),
    ("ER", "Eritrea"), ("ES", "Spagna"), ("ET", "Etiopia"), ("FI", "Finlandia"),
    ("FJ", "Figi"), ("FR", "Francia"), ("GA", "Gabon"), ("GB", "Regno Unito"),
    ("GD", "Grenada"), ("GE", "Georgia"), ("GH", "Ghana"), ("GM", "Gambia"),
    ("GN", "Guinea"), ("GQ", "Guinea Equatoriale"), ("GR", "Grecia"), ("GT", "Guatemala"),
    ("GW", "Guinea-Bissau"), ("GY", "Guyana"), ("HN", "Honduras"), ("HR", "Croazia"),
    ("HT", "Haiti"), ("HU", "Ungheria"), ("ID", "Indonesia"), ("IE", "Irlanda"),
    ("IL", "Israele"), ("IN", "India"), ("IQ", "Iraq"), ("IR", "Iran"),
    ("IS", "Islanda"), ("IT", "Italia"), ("JM", "Giamaica"), ("JO", "Giordania"),
    ("JP", "Giappone"), ("KE", "Kenya"), ("KG", "Kirghizistan"), ("KH", "Cambogia"),
    ("KI", "Kiribati"), ("KM", "Comore"), ("KN", "Saint Kitts e Nevis"), ("KP", "Corea del Nord"),
    ("KR", "Corea del Sud"), ("KW", "Kuwait"), ("KZ", "Kazakhstan"), ("LA", "Laos"),
    ("LB", "Libano"), ("LC", "Saint Lucia"), ("LI", "Liechtenstein"), ("LK", "Sri Lanka"),
    ("LR", "Liberia"), ("LS", "Lesotho"), ("LT", "Lituania"), ("LU", "Lussemburgo"),
    ("LV", "Lettonia"), ("LY", "Libia"), ("MA", "Marocco"), ("MC", "Monaco"),
    ("MD", "Moldavia"), ("ME", "Montenegro"), ("MG", "Madagascar"), ("MK", "Macedonia del Nord"),
    ("ML", "Mali"), ("MM", "Myanmar"), ("MN", "Mongolia"), ("MR", "Mauritania"),
    ("MT", "Malta"), ("MU", "Mauritius"), ("MV", "Maldive"), ("MW", "Malawi"),
    ("MX", "Messico"), ("MY", "Malaysia"), ("MZ", "Mozambico"), ("NA", "Namibia"),
    ("NE", "Niger"), ("NG", "Nigeria"), ("NI", "Nicaragua"), ("NL", "Paesi Bassi"),
    ("NO", "Norvegia"), ("NP", "Nepal"), ("NR", "Nauru"), ("NZ", "Nuova Zelanda"),
    ("OM", "Oman"), ("PA", "Panama"), ("PE", "Peru"), ("PG", "Papua Nuova Guinea"),
    ("PH", "Filippine"), ("PK", "Pakistan"), ("PL", "Polonia"), ("PT", "Portogallo"),
    ("PW", "Palau"), ("PY", "Paraguay"), ("QA", "Qatar"), ("RO", "Romania"),
    ("RS", "Serbia"), ("RU", "Russia"), ("RW", "Ruanda"), ("SA", "Arabia Saudita"),
    ("SB", "Isole Salomone"), ("SC", "Seychelles"), ("SD", "Sudan"), ("SE", "Svezia"),
    ("SG", "Singapore"), ("SI", "Slovenia"), ("SK", "Slovacchia"), ("SL", "Sierra Leone"),
    ("SM", "San Marino"), ("SN", "Senegal"), ("SO", "Somalia"), ("SR", "Suriname"),
    ("SS", "Sudan del Sud"), ("ST", "Sao Tome e Principe"), ("SV", "El Salvador"),
    ("SY", "Siria"), ("SZ", "Eswatini"), ("TD", "Ciad"), ("TG", "Togo"),
    ("TH", "Thailandia"), ("TJ", "Tagikistan"), ("TL", "Timor Est"), ("TM", "Turkmenistan"),
    ("TN", "Tunisia"), ("TO", "Tonga"), ("TR", "Turchia"), ("TT", "Trinidad e Tobago"),
    ("TV", "Tuvalu"), ("TZ", "Tanzania"), ("UA", "Ucraina"), ("UG", "Uganda"),
    ("US", "Stati Uniti"), ("UY", "Uruguay"), ("UZ", "Uzbekistan"), ("VA", "Città del Vaticano"),
    ("VC", "Saint Vincent"), ("VE", "Venezuela"), ("VN", "Vietnam"), ("VU", "Vanuatu"),
    ("WS", "Samoa"), ("XK", "Kosovo"), ("YE", "Yemen"), ("ZA", "Sud Africa"),
    ("ZM", "Zambia"), ("ZW", "Zimbabwe"),
]


def _load_geonames_core():
    core = _PLUGIN_DIR / "geonames.py"
    spec = importlib.util.spec_from_file_location("geonames_core", str(core))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Impossibile caricare il core da {core}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ConfigDialog:
    """Dialog di configurazione GeoNames compatibile con il loader plugin."""

    def __init__(self, *args: Any, **kwargs: Any):
        parent = kwargs.pop("parent", None)
        db_path = kwargs.pop("db_path", None)
        config_path = kwargs.pop("config_path", None)
        count_unprocessed = kwargs.pop("count_unprocessed", None)
        count_processed = kwargs.pop("count_processed", None)
        count_total = kwargs.pop("count_total", None)
        count_gallery = kwargs.pop("count_gallery", None)
        plugin_manifest = kwargs.pop("plugin_manifest", None)

        # Il primo argomento positional è la modalità corrente (da plugins_tab)
        initial_mode = "no_gps"
        if args:
            if isinstance(args[0], str):
                initial_mode = args[0]
                args = args[1:]
            if args and parent is None:
                parent = args[0]
            if len(args) > 1 and db_path is None:
                db_path = args[1]
            if len(args) > 2 and config_path is None:
                config_path = args[2]

        from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
        from PyQt6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QDoubleSpinBox,
            QFileDialog,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QScrollArea,
            QVBoxLayout,
            QWidget,
        )

        self._QDialog = QDialog
        self._Qt = Qt
        self._QTimer = QTimer
        self._QFileDialog = QFileDialog
        self._QMessageBox = QMessageBox
        self._QListWidgetItem = QListWidgetItem
        self._parent = parent
        self._db_path = db_path
        self._config_path = config_path
        self._count_unprocessed = count_unprocessed
        self._count_processed = count_processed
        self._count_total = count_total
        self._count_gallery = count_gallery
        self._plugin_manifest = plugin_manifest or {}
        self._extra_kwargs = kwargs
        self._mode = initial_mode
        self._gn = _load_geonames_core()
        self._cfg = self._safe_load_config()
        self._search_timer = None
        self._selected_hierarchy = None   # gerarchia da ricerca, evita reverse geocoding
        self._selected_lat = None         # coordinate della selezione corrente
        self._selected_lon = None

        class _UiBridge(QObject):
            progress = pyqtSignal(int)
            status = pyqtSignal(str)
            done = pyqtSignal(str)
            error = pyqtSignal(str)

        self._bridge = _UiBridge()

        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle("GeoNames — Configurazione")
        self._dlg.setModal(True)
        self._dlg.setMinimumWidth(560)
        self._dlg.setMinimumHeight(680)
        self._dlg.setStyleSheet(_DARK_STYLE)

        root = QVBoxLayout(self._dlg)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # --- Riga contatori immagini ---
        senza_gps = count_unprocessed if count_unprocessed is not None and count_unprocessed >= 0 else "—"
        con_gps_val = (count_total - count_unprocessed) if (
            count_total is not None and count_total >= 0 and
            count_unprocessed is not None and count_unprocessed >= 0
        ) else (count_processed if count_processed is not None and count_processed >= 0 else "—")
        info = QLabel(f"Immagini senza GPS: {senza_gps}    •    Immagini con GPS: {con_gps_val}")
        info.setStyleSheet("font-size: 10px; color: #B0B0B0;")
        root.addWidget(info)

        # --- Checkbox modalità processing ---
        self._chk_only_no_gps = QCheckBox(
            "Solo immagini senza GPS — assegna la località configurata durante il processing"
        )
        self._chk_only_no_gps.setToolTip(
            "Se attivo: durante il processing, le immagini prive di GPS ricevono automaticamente\n"
            "la località selezionata qui sotto.\n"
            "Se disattivo: il plugin effettua solo il reverse geocoding sulle immagini con GPS."
        )
        self._chk_only_no_gps.setChecked(bool(self._cfg.get("only_no_gps", False)))
        self._chk_only_no_gps.toggled.connect(self._on_only_no_gps_changed)
        root.addWidget(self._chk_only_no_gps)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        grp_coords = QGroupBox("Coordinate dirette")
        lay_coords = QVBoxLayout(grp_coords)
        lay_coords.setSpacing(6)
        note_coords = QLabel(
            "Inserisci le coordinate della località da assegnare alle immagini senza GPS. "
            "Questa località verrà usata automaticamente durante l'import."
        )
        note_coords.setWordWrap(True)
        note_coords.setStyleSheet("font-size: 10px; color: #B0B0B0;")
        lay_coords.addWidget(note_coords)

        last_loc = self._cfg.get("last_location", {}) or {}

        row_lat = QHBoxLayout()
        row_lat.addWidget(QLabel("Latitudine"))
        self._spin_lat = QDoubleSpinBox()
        self._spin_lat.setRange(-90.0, 90.0)
        self._spin_lat.setDecimals(6)
        self._spin_lat.setSingleStep(0.0001)
        self._spin_lat.setFixedWidth(140)
        self._spin_lat.setValue(float(last_loc.get("latitude", 0.0) or 0.0))
        row_lat.addWidget(self._spin_lat)
        row_lat.addStretch()
        lay_coords.addLayout(row_lat)

        row_lon = QHBoxLayout()
        row_lon.addWidget(QLabel("Longitudine"))
        self._spin_lon = QDoubleSpinBox()
        self._spin_lon.setRange(-180.0, 180.0)
        self._spin_lon.setDecimals(6)
        self._spin_lon.setSingleStep(0.0001)
        self._spin_lon.setFixedWidth(140)
        self._spin_lon.setValue(float(last_loc.get("longitude", 0.0) or 0.0))
        row_lon.addWidget(self._spin_lon)
        row_lon.addStretch()
        lay_coords.addLayout(row_lon)

        row_alt = QHBoxLayout()
        row_alt.addWidget(QLabel("Altitudine (m)"))
        self._spin_alt = QDoubleSpinBox()
        self._spin_alt.setRange(-9999.0, 9000.0)
        self._spin_alt.setDecimals(1)
        self._spin_alt.setFixedWidth(140)
        self._spin_alt.setSpecialValueText("—")
        alt_val = last_loc.get("altitude")
        self._spin_alt.setValue(float(alt_val) if alt_val is not None else -9999.0)
        row_alt.addWidget(self._spin_alt)
        row_alt.addStretch()
        lay_coords.addLayout(row_alt)

        self._lbl_coords_hier = QLabel("")
        self._lbl_coords_hier.setStyleSheet("font-size: 10px; color: #E0A84A;")
        self._lbl_coords_hier.setWordWrap(True)
        lay_coords.addWidget(self._lbl_coords_hier)

        btn_verify = QPushButton("Verifica gerarchia")
        btn_verify.setFixedWidth(150)
        btn_verify.clicked.connect(self._on_verify_coords)
        lay_coords.addWidget(btn_verify)

        # Aggiornamento automatico gerarchia al cambio coordinate (debounce 600ms)
        self._spin_lat.valueChanged.connect(self._on_coords_changed)
        self._spin_lon.valueChanged.connect(self._on_coords_changed)
        layout.addWidget(grp_coords)
        self._grp_coords_widget = grp_coords

        grp_search = QGroupBox("Ricerca per nome")
        lay_search = QVBoxLayout(grp_search)
        lay_search.setSpacing(6)
        note_search = QLabel(
            "Digita il nome di una località per cercarla nel database scaricato. "
            "Seleziona un risultato per impostarlo come coordinata predefinita."
        )
        note_search.setWordWrap(True)
        note_search.setStyleSheet("font-size: 10px; color: #B0B0B0;")
        lay_search.addWidget(note_search)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Es.: Barumini, Firenze, Stintino...")
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        lay_search.addWidget(self._search_edit)

        self._search_list = QListWidget()
        self._search_list.setFixedHeight(130)
        self._search_list.itemDoubleClicked.connect(self._on_search_select)
        lay_search.addWidget(self._search_list)

        self._lbl_search_status = QLabel("")
        self._lbl_search_status.setStyleSheet("font-size: 10px; color: #B0B0B0;")
        lay_search.addWidget(self._lbl_search_status)

        btn_use = QPushButton("Usa selezionato")
        btn_use.setFixedWidth(140)
        btn_use.clicked.connect(lambda: self._on_search_select(None))
        lay_search.addWidget(btn_use)
        layout.addWidget(grp_search)
        self._grp_search_widget = grp_search

        grp_nations = QGroupBox("Database per nazione")
        lay_nations = QVBoxLayout(grp_nations)
        lay_nations.setSpacing(6)
        note_nations = QLabel(
            "Seleziona una nazione e scarica i dati GeoNames (borghi, frazioni, città). "
            "Il primo download include anche i dati base di paesi e regioni."
        )
        note_nations.setWordWrap(True)
        note_nations.setStyleSheet("font-size: 10px; color: #B0B0B0;")
        lay_nations.addWidget(note_nations)

        self._combo_nation = QComboBox()
        self._populate_nations_combo()
        lay_nations.addWidget(self._combo_nation)

        row_dl = QHBoxLayout()
        self._btn_download = QPushButton("Scarica nazione")
        self._btn_download.setStyleSheet(_BTN_AMBER)
        self._btn_download.clicked.connect(self._on_download_nation)
        row_dl.addWidget(self._btn_download)

        self._lbl_dl_date = QLabel(self._get_dl_date_text())
        self._lbl_dl_date.setStyleSheet("font-size: 10px; color: #B0B0B0;")
        row_dl.addWidget(self._lbl_dl_date)
        row_dl.addStretch()
        lay_nations.addLayout(row_dl)

        self._pb_download = QProgressBar()
        self._pb_download.setTextVisible(False)
        self._pb_download.setRange(0, 100)
        self._pb_download.hide()
        lay_nations.addWidget(self._pb_download)

        self._lbl_dl_status = QLabel("")
        self._lbl_dl_status.setStyleSheet("font-size: 10px; color: #E0A84A;")
        self._lbl_dl_status.hide()
        lay_nations.addWidget(self._lbl_dl_status)
        layout.addWidget(grp_nations)

        grp_dir = QGroupBox("Directory dati")
        lay_dir = QVBoxLayout(grp_dir)
        lay_dir.setSpacing(6)
        note_dir = QLabel(
            "Cartella dove vengono salvati i file GeoNames scaricati. "
            "Default: cartella del plugin."
        )
        note_dir.setWordWrap(True)
        note_dir.setStyleSheet("font-size: 10px; color: #B0B0B0;")
        lay_dir.addWidget(note_dir)

        row_dir = QHBoxLayout()
        current_dir = self._cfg.get("data_dir")
        if not current_dir or current_dir == "__plugin_dir__":
            current_dir = str(_PLUGIN_DIR / "data")
        self._dir_edit = QLineEdit(str(current_dir))
        row_dir.addWidget(self._dir_edit)
        btn_browse = QPushButton("Sfoglia")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._on_browse_dir)
        row_dir.addWidget(btn_browse)
        lay_dir.addLayout(row_dir)
        layout.addWidget(grp_dir)
        layout.addStretch()

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._on_accept)
        bbox.rejected.connect(self._dlg.reject)
        root.addWidget(bbox)

        self._combo_nation.currentIndexChanged.connect(self._update_dl_date_label)
        self._bridge.progress.connect(self._pb_download.setValue)
        self._bridge.status.connect(self._lbl_dl_status.setText)
        self._bridge.done.connect(self._on_download_done)
        self._bridge.error.connect(self._on_download_error)

        # Visibilità iniziale sezioni coordinate: visibili solo se only_no_gps è attivo
        coords_visible = bool(self._cfg.get("only_no_gps", False))
        self._grp_coords_widget.setVisible(coords_visible)
        self._grp_search_widget.setVisible(coords_visible)

        # Carica subito la gerarchia delle coordinate correnti
        if coords_visible:
            self._update_hier_label()

    def _safe_load_config(self) -> dict:
        try:
            cfg = self._gn.load_config()
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            logger.exception("Impossibile leggere la config GeoNames")
            return {}

    def _populate_nations_combo(self) -> None:
        downloaded = set(self._cfg.get("downloaded_nations", []))
        for code, name in AVAILABLE_NATIONS:
            marker = " ✓" if code in downloaded else ""
            self._combo_nation.addItem(f"{name} ({code}){marker}", userData=code)
        try:
            idx = next(i for i in range(self._combo_nation.count()) if self._combo_nation.itemData(i) == "IT")
            self._combo_nation.setCurrentIndex(idx)
        except StopIteration:
            pass

    def _on_verify_coords(self) -> None:
        self._update_hier_label()

    def _on_coords_changed(self, _val=None) -> None:
        """Aggiorna la label gerarchia con debounce 600ms al cambio coordinate."""
        # Se le coordinate corrispondono alla selezione corrente, non azzera la gerarchia
        # (può capitare se il cambio spinbox è stato fatto programmaticamente ma
        #  blockSignals non ha bloccato tutti i segnali per qualche motivo Qt)
        if self._selected_lat is not None and self._selected_lon is not None:
            if (abs(self._spin_lat.value() - self._selected_lat) < 0.000015 and
                    abs(self._spin_lon.value() - self._selected_lon) < 0.000015):
                # Coordinate identiche alla selezione — nessuna modifica manuale
                return
        # Modifica manuale effettiva: la gerarchia pre-selezionata non è più valida
        self._selected_hierarchy = None
        self._selected_lat = None
        self._selected_lon = None
        if self._search_timer:
            self._search_timer.stop()
        timer = self._QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._update_hier_label)
        timer.start(600)
        self._search_timer = timer

    def _update_hier_label(self) -> None:
        # Se c'è una gerarchia pre-selezionata dalla ricerca, usarla direttamente
        # senza fare reverse geocoding (che troverebbe il comune, non la frazione)
        if self._selected_hierarchy:
            self._lbl_coords_hier.setText(f"→ {self._selected_hierarchy}")
            return
        lat = self._spin_lat.value()
        lon = self._spin_lon.value()
        if lat == 0.0 and lon == 0.0:
            self._lbl_coords_hier.setText("")
            return
        try:
            enricher = self._gn.GeoNamesEnricher(self._cfg)
            hier = enricher.get_hierarchy(lat, lon)
            if hier:
                self._lbl_coords_hier.setText(f"→ {hier}")
            else:
                self._lbl_coords_hier.setText("Nessuna gerarchia trovata (nazione non scaricata?)")
        except Exception as e:
            self._lbl_coords_hier.setText(f"Errore: {e}")

    def _on_search_text_changed(self, text: str) -> None:
        if self._search_timer:
            self._search_timer.stop()
        if len(text.strip()) < 2:
            self._search_list.clear()
            self._lbl_search_status.setText("")
            return
        timer = self._QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._run_search(text))
        timer.start(400)
        self._search_timer = timer

    def _run_search(self, query: str) -> None:
        self._search_list.clear()
        if not query.strip():
            return
        try:
            enricher = self._gn.GeoNamesEnricher(self._cfg)
            results = enricher.search_location(query.strip())
            if not results:
                self._lbl_search_status.setText("Nessun risultato (nazione scaricata?)")
                return
            self._lbl_search_status.setText(f"{len(results)} risultati")
            for r in results:
                parts = [r.get("name", "?")]
                if r.get("admin1"):
                    parts.append(r["admin1"])
                parts.append(r.get("country", r.get("country_code", "")))
                label = ", ".join([p for p in parts if p])
                item = self._QListWidgetItem(label)
                item.setData(self._Qt.ItemDataRole.UserRole, r)
                self._search_list.addItem(item)
        except Exception as e:
            logger.exception("Errore ricerca")
            self._lbl_search_status.setText(f"Errore ricerca: {e}")

    def _on_search_select(self, clicked_item=None) -> None:
        # Se chiamata da itemDoubleClicked usa l'item passato, altrimenti usa currentItem
        item = clicked_item if clicked_item is not None else self._search_list.currentItem()
        if not item:
            return
        # Estrae testo e dati PRIMA di qualsiasi operazione sulla lista
        # (clear() invalida i puntatori C++ degli item)
        try:
            selected_text = item.text()
            r = item.data(self._Qt.ItemDataRole.UserRole)
        except RuntimeError:
            return
        if not r:
            return
        hier = r.get("hierarchy")
        # Memorizza la gerarchia del risultato — usata direttamente in _save_current_config
        # senza ricalcolare via reverse geocoding (che troverebbe il comune, non la frazione)
        self._selected_hierarchy = hier if hier else None
        # Memorizza le coordinate della selezione per permettere a _on_coords_changed
        # di distinguere aggiornamenti programmatici da modifiche manuali
        self._selected_lat = float(r["latitude"])
        self._selected_lon = float(r["longitude"])
        # Blocca i segnali valueChanged prima di settare le spinbox, altrimenti
        # _on_coords_changed azzererebbe subito _selected_hierarchy
        self._spin_lat.blockSignals(True)
        self._spin_lon.blockSignals(True)
        self._spin_lat.setValue(float(r["latitude"]))
        self._spin_lon.setValue(float(r["longitude"]))
        self._spin_lat.blockSignals(False)
        self._spin_lon.blockSignals(False)
        alt = r.get("altitude")
        self._spin_alt.setValue(float(alt) if alt is not None else -9999.0)
        self._lbl_coords_hier.setText(f"→ {hier}" if hier else "")
        self._search_edit.blockSignals(True)
        self._search_edit.clear()
        self._search_edit.blockSignals(False)
        self._search_list.clear()
        self._lbl_search_status.setText(f"Selezionato: {selected_text}")

    def _on_download_nation(self) -> None:
        code = self._combo_nation.currentData()
        if not code:
            return
        self._btn_download.setEnabled(False)
        self._pb_download.setValue(0)
        self._pb_download.show()
        self._lbl_dl_status.setText(f"Download {code} in corso...")
        self._lbl_dl_status.show()
        self._save_current_config()

        def worker():
            try:
                def prog(cur, tot):
                    pct = int((cur * 100) / tot) if tot else 0
                    self._bridge.progress.emit(max(0, min(100, pct)))

                def status(msg):
                    self._bridge.status.emit(str(msg))

                self._gn.download_and_build_database(
                    progress_callback=prog,
                    status_callback=status,
                    nation_code=code,
                )
                self._cfg = self._safe_load_config()
                self._bridge.done.emit(code)
            except Exception as e:
                logger.exception("Download nazione fallito")
                self._bridge.error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_done(self, code: str) -> None:
        self._refresh_combo_markers()
        self._pb_download.setValue(100)
        self._lbl_dl_status.setText(f"{code} scaricato con successo")
        self._update_dl_date_label()
        self._btn_download.setEnabled(True)

    def _on_download_error(self, msg: str) -> None:
        self._lbl_dl_status.setText(f"Errore: {msg}")
        self._btn_download.setEnabled(True)

    def _on_browse_dir(self) -> None:
        path = self._QFileDialog.getExistingDirectory(
            self._dlg, "Seleziona directory dati GeoNames", self._dir_edit.text()
        )
        if path:
            self._dir_edit.setText(path)

    def _on_accept(self) -> None:
        self._save_current_config()
        self._dlg.accept()

    def _save_current_config(self) -> None:
        cfg = self._safe_load_config()
        lat = self._spin_lat.value()
        lon = self._spin_lon.value()
        alt_raw = self._spin_alt.value()
        alt = None if alt_raw <= -9998.0 else alt_raw
        cfg["only_no_gps"] = self._chk_only_no_gps.isChecked()
        cfg["last_location"] = {
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            # Se l'utente ha selezionato dalla ricerca, salva la gerarchia pronta
            # così il processing batch non fa reverse geocoding (troverebbe il comune)
            "preset_hierarchy": self._selected_hierarchy,
        }
        data_dir = self._dir_edit.text().strip()
        cfg["data_dir"] = data_dir if data_dir else str(_PLUGIN_DIR / "data")
        self._gn.save_config(cfg)
        self._cfg = cfg

    def _get_dl_date_text(self) -> str:
        code = self._combo_nation.currentData() if hasattr(self, "_combo_nation") else None
        if not code:
            return ""
        date = self._cfg.get(f"nation_download_date_{code}")
        return f"Ultimo download: {date}" if date else "Non ancora scaricata"

    def _update_dl_date_label(self) -> None:
        if hasattr(self, "_lbl_dl_date"):
            self._lbl_dl_date.setText(self._get_dl_date_text())

    def _refresh_combo_markers(self) -> None:
        downloaded = set(self._cfg.get("downloaded_nations", []))
        for i in range(self._combo_nation.count()):
            code = self._combo_nation.itemData(i)
            base = self._combo_nation.itemText(i).replace(" ✓", "")
            marker = " ✓" if code in downloaded else ""
            self._combo_nation.setItemText(i, f"{base}{marker}")

    def _on_only_no_gps_changed(self, checked: bool) -> None:
        """Mostra/nasconde la sezione coordinate in base alla checkbox only_no_gps."""
        if hasattr(self, "_grp_coords_widget"):
            self._grp_coords_widget.setVisible(checked)
        if hasattr(self, "_grp_search_widget"):
            self._grp_search_widget.setVisible(checked)

    def exec(self) -> int:
        result = self._dlg.exec()
        return 1 if result == self._QDialog.DialogCode.Accepted else 0

    def get_mode(self) -> str:
        """Richiesto da plugins_tab — non usato per geo_enricher (config_only)."""
        return "no_gps"

    def get_location(self) -> dict:
        return self._cfg.get("last_location", {})


def _progress(current: int, total: int) -> None:
    print(f"PROGRESS:{current}:{total}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="GeoNames plugin headless")
    parser.add_argument("--db", required=True)
    parser.add_argument("--config", required=False)
    parser.add_argument("--mode", default="no_gps")
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lon", type=float, default=None)
    parser.add_argument("--alt", type=float, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--ids", default="")
    parser.add_argument("--ids-file", default="")
    parser.add_argument("--directory", default="")     # accettato ma ignorato
    args, _ = parser.parse_known_args()

    # Normalizza modalità: 'directory', 'unprocessed' → 'no_gps'; 'ids'/'selection' → 'overwrite'
    if args.mode in ("ids", "selection"):
        args.mode = "overwrite"
    elif args.mode not in ("no_gps", "overwrite"):
        args.mode = "no_gps"

    core = _load_geonames_core()

    config_path = args.config or str(_PLUGIN_DIR / "config.json")
    config = {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        try:
            config = core.load_config()
        except Exception:
            config = {}

    image_ids = None
    if args.ids_file:
        try:
            with open(args.ids_file, "r", encoding="utf-8") as f:
                image_ids = json.load(f)
        except Exception:
            image_ids = None
    elif args.ids:
        try:
            image_ids = [int(x) for x in args.ids.split(",") if x.strip()]
        except ValueError:
            image_ids = None

    location = None
    if args.mode == "no_gps":
        lat = args.lat
        lon = args.lon
        alt = args.alt
        if lat is None or lon is None:
            loc = config.get("last_location", {})
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            alt = loc.get("altitude")
        if lat is None or lon is None:
            print("ERROR:Nessuna coordinata specificata per modalita' no_gps", flush=True)
            sys.exit(1)
        location = {"latitude": lat, "longitude": lon, "altitude": alt}

    try:
        processed, skipped = core.process_images(
            db_path=args.db,
            config=config,
            image_ids=image_ids,
            mode=args.mode,
            location=location,
            overwrite=args.overwrite,
            progress_cb=_progress,
        )
        total = processed + skipped
        print(f"DONE:{total}:{processed}:{skipped}", flush=True)
    except Exception as e:
        logger.exception("Errore durante process_images")
        print(f"ERROR:{e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
