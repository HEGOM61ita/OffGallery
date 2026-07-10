"""
GeoNames Gallery — azioni contestuali per la gallery di OffGallery.

Espone tre funzioni chiamate direttamente da gallery_widgets.py:

  show_assign_dialog(target_items, db_path, parent)
      Mostra popup con ricerca/coordinate, assegna GPS + geo_hierarchy
      alle immagini selezionate senza GPS (o tutte se overwrite).

  recalc_hierarchy(target_items, db_path, parent)
      Rielabora localizzazione completa per immagini selezionate:
      legge GPS dal file fisico se assente in DB, ricalcola geo_hierarchy
      tramite GeoNames, poi richiama weather_context e naturarea se presenti.

  clear_gps(target_items, db_path, parent)
      Azzera i dati di localizzazione derivati (geo_hierarchy, weather_context,
      protected_area, habitat). Le coordinate GPS restano nel DB.
"""
# Copyright (C) 2026  OffGallery / HEGOM — All rights reserved.
# Distributed under the OffGallery Plugins License v1.0.

import importlib.util
import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from plugins.plugin_i18n import pt

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent


def _load_core():
    """Carica geonames.py tramite importlib (evita import diretto AGPLv3)."""
    core = _PLUGIN_DIR / "geonames.py"
    spec = importlib.util.spec_from_file_location("geonames_core", str(core))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_config() -> dict:
    try:
        gn = _load_core()
        return gn.load_config()
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# DIALOG ASSEGNA POSIZIONE (al volo dalla gallery)
# ══════════════════════════════════════════════════════════════════════════════

def show_assign_dialog(target_items: list, db_path: str, parent=None) -> None:
    """
    Mostra un dialog compatto per assegnare una posizione alle immagini selezionate.

    - Propone la last_location dalla config del plugin
    - L'utente può modificarla o cercare per nome
    - Checkbox 'Sovrascrivi' per agire anche su immagini con GPS esistente
    - Dopo conferma: scrive lat/lon/geo_hierarchy nel DB e aggiorna image_data
    - La locality confermata diventa il nuovo default in config
    """
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QDialogButtonBox, QDoubleSpinBox, QLineEdit, QListWidget,
        QListWidgetItem, QCheckBox, QGroupBox, QProgressBar, QMessageBox,
    )
    from PyQt6.QtCore import Qt, QTimer

    cfg  = _load_config()
    gn   = _load_core()
    last = cfg.get("last_location", {}) or {}

    # Gerarchia pre-calcolata da ricerca (evita reverse geocoding che trova il comune, non la frazione)
    # Inizializzata dal preset_hierarchy salvato in config (impostato dal plugin config dialog)
    _selected_hierarchy = [last.get("preset_hierarchy") or None]
    # Coordinate corrispondenti alla selezione corrente (per distinguere setValue programmatico)
    _selected_lat = [float(last.get("latitude") or 0.0)]
    _selected_lon = [float(last.get("longitude") or 0.0)]

    # Conta immagini senza GPS nella selezione
    no_gps_count = sum(
        1 for it in target_items
        if not it.image_data.get("gps_latitude")
    )
    has_gps_count = len(target_items) - no_gps_count

    _DARK = """
        QDialog, QWidget { background-color: #2A2A2A; color: #E3E3E3; }
        QLabel { color: #E3E3E3; }
        QPushButton {
            background-color: #1C4F63; color: #E3E3E3;
            border: none; border-radius: 4px; padding: 4px 10px;
        }
        QPushButton:hover { background-color: #2A6A82; }
        QPushButton:disabled { background-color: #3A3A3A; color: #808080; }
        QLineEdit, QDoubleSpinBox {
            background-color: #1E1E1E; color: #E3E3E3;
            border: 1px solid #3A3A3A; border-radius: 3px; padding: 3px 6px;
        }
        QListWidget {
            background-color: #1E1E1E; color: #E3E3E3;
            border: 1px solid #3A3A3A; border-radius: 3px;
        }
        QListWidget::item:selected { background-color: #1C4F63; }
        QCheckBox { color: #E3E3E3; }
        QGroupBox {
            color: #C88B2E; border: 1px solid #3A3A3A; border-radius: 4px;
            margin-top: 8px; padding-top: 6px; font-weight: bold;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        QProgressBar {
            border: 1px solid #555; background: #2a2a2a;
            border-radius: 3px; max-height: 8px;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #C88B2E, stop:1 #E0A84A);
            border-radius: 2px;
        }
    """

    dlg = QDialog(parent)
    dlg.setWindowTitle("GeoNames — Assegna posizione")
    dlg.setModal(True)
    dlg.setMinimumWidth(460)
    dlg.setStyleSheet(_DARK)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(16, 14, 16, 12)
    layout.setSpacing(10)

    # Riepilogo selezione
    info_text = f"Selezione: {len(target_items)} foto"
    if no_gps_count:
        info_text += f"  •  Senza GPS: {no_gps_count}"
    if has_gps_count:
        info_text += f"  •  Con GPS: {has_gps_count}"
    lbl_info = QLabel(info_text)
    lbl_info.setStyleSheet("font-size: 10px; color: #B0B0B0;")
    layout.addWidget(lbl_info)

    # Opzione sovrascrivi
    chk_overwrite = QCheckBox("Sovrascrivi immagini con GPS esistente")
    chk_overwrite.setChecked(True)
    layout.addWidget(chk_overwrite)

    # ── Coordinate ────────────────────────────────────────────────────────
    grp_coords = QGroupBox("Coordinate")
    lay_c = QVBoxLayout(grp_coords)
    lay_c.setSpacing(5)

    row_lat = QHBoxLayout()
    row_lat.addWidget(QLabel("Lat:"))
    spin_lat = QDoubleSpinBox()
    spin_lat.setRange(-90.0, 90.0)
    spin_lat.setDecimals(6)
    spin_lat.setSingleStep(0.0001)
    spin_lat.setFixedWidth(130)
    spin_lat.setValue(float(last.get("latitude", 0.0) or 0.0))
    row_lat.addWidget(spin_lat)

    row_lat.addWidget(QLabel("Lon:"))
    spin_lon = QDoubleSpinBox()
    spin_lon.setRange(-180.0, 180.0)
    spin_lon.setDecimals(6)
    spin_lon.setSingleStep(0.0001)
    spin_lon.setFixedWidth(130)
    spin_lon.setValue(float(last.get("longitude", 0.0) or 0.0))
    row_lat.addWidget(spin_lon)
    row_lat.addStretch()
    lay_c.addLayout(row_lat)

    lbl_hier = QLabel("")
    lbl_hier.setStyleSheet("font-size: 10px; color: #E0A84A;")
    lbl_hier.setWordWrap(True)
    lay_c.addWidget(lbl_hier)
    layout.addWidget(grp_coords)

    # Mostra subito la gerarchia delle coordinate iniziali (last_location)
    _coords_timer = [None]

    def _refresh_hier():
        # Se c'è una gerarchia pre-selezionata (da ricerca o da config), usarla direttamente
        if _selected_hierarchy[0]:
            lbl_hier.setText(f"→ {_selected_hierarchy[0]}")
            return
        lat_v = spin_lat.value()
        lon_v = spin_lon.value()
        if lat_v == 0.0 and lon_v == 0.0:
            lbl_hier.setText("")
            return
        try:
            enricher = gn.GeoNamesEnricher(cfg)
            hier = enricher.get_hierarchy(lat_v, lon_v)
            lbl_hier.setText(f"→ {hier}" if hier else "Gerarchia non trovata")
        except Exception as e:
            lbl_hier.setText(f"Errore: {e}")

    def _on_coords_changed(_val=None):
        # Se le coordinate corrispondono alla selezione corrente non azzerare la gerarchia
        if (_selected_lat[0] is not None and
                abs(spin_lat.value() - _selected_lat[0]) < 0.000015 and
                abs(spin_lon.value() - _selected_lon[0]) < 0.000015):
            return
        # Modifica manuale effettiva: azzera la gerarchia pre-selezionata
        _selected_hierarchy[0] = None
        _selected_lat[0] = None
        _selected_lon[0] = None
        if _coords_timer[0]:
            _coords_timer[0].stop()
        t = QTimer()
        t.setSingleShot(True)
        t.timeout.connect(_refresh_hier)
        t.start(600)
        _coords_timer[0] = t

    spin_lat.valueChanged.connect(_on_coords_changed)
    spin_lon.valueChanged.connect(_on_coords_changed)

    # Carica gerarchia iniziale
    _refresh_hier()

    # ── Ricerca per nome ──────────────────────────────────────────────────
    grp_search = QGroupBox("Ricerca per nome")
    lay_s = QVBoxLayout(grp_search)
    lay_s.setSpacing(5)

    search_edit = QLineEdit()
    search_edit.setPlaceholderText("Digita nome localita'...")
    lay_s.addWidget(search_edit)

    search_list = QListWidget()
    search_list.setFixedHeight(110)
    lay_s.addWidget(search_list)

    lbl_search_status = QLabel("")
    lbl_search_status.setStyleSheet("font-size: 10px; color: #B0B0B0;")
    lay_s.addWidget(lbl_search_status)

    btn_verify = QPushButton("Verifica gerarchia")
    btn_verify.setFixedWidth(150)
    btn_verify.setToolTip("Seleziona un risultato dalla lista e clicca per vedere la gerarchia che sarà scritta")
    lay_s.addWidget(btn_verify)
    layout.addWidget(grp_search)

    # ── Progress e stato ──────────────────────────────────────────────────
    pb = QProgressBar()
    pb.setRange(0, 100)
    pb.setTextVisible(False)
    pb.hide()
    layout.addWidget(pb)

    lbl_status = QLabel("")
    lbl_status.setStyleSheet("font-size: 10px; color: #E0A84A;")
    layout.addWidget(lbl_status)

    # ── Bottoni ───────────────────────────────────────────────────────────
    bbox = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok |
        QDialogButtonBox.StandardButton.Cancel
    )
    btn_ok     = bbox.button(QDialogButtonBox.StandardButton.Ok)
    btn_ok.setText("Assegna")
    btn_ok.setStyleSheet(
        "QPushButton { background-color: #C88B2E; color: #1E1E1E; font-weight: bold; "
        "border-radius: 4px; padding: 5px 12px; } "
        "QPushButton:hover { background-color: #E0A84A; }"
    )
    layout.addWidget(bbox)

    # ── Debounce ricerca ──────────────────────────────────────────────────
    _search_timer = [None]

    def _run_search(query: str):
        search_list.clear()
        if not query.strip():
            return
        try:
            enricher = gn.GeoNamesEnricher(cfg)
            results  = enricher.search_location(query.strip())
            if not results:
                lbl_search_status.setText("Nessun risultato")
                return
            lbl_search_status.setText(f"{len(results)} risultati")
            for r in results:
                parts = [r.get("name", "")]
                if r.get("admin1"):
                    parts.append(r["admin1"])
                parts.append(r.get("country", r.get("country_code", "")))
                item = QListWidgetItem(", ".join(p for p in parts if p))
                item.setData(Qt.ItemDataRole.UserRole, r)
                search_list.addItem(item)
        except Exception as e:
            lbl_search_status.setText(f"Errore: {e}")

    def _on_search_changed(text: str):
        if _search_timer[0]:
            _search_timer[0].stop()
        if len(text.strip()) < 2:
            search_list.clear()
            lbl_search_status.setText("")
            return
        t = QTimer()
        t.setSingleShot(True)
        t.timeout.connect(lambda: _run_search(text))
        t.start(400)
        _search_timer[0] = t

    def _on_search_select(clicked_item=None):
        it = clicked_item if clicked_item is not None else search_list.currentItem()
        if not it:
            return
        # Estrae testo e dati PRIMA di clear() (che invalida i puntatori C++)
        try:
            selected_text = it.text()
            r = it.data(Qt.ItemDataRole.UserRole)
        except RuntimeError:
            return
        if not r:
            return
        hier = r.get("hierarchy", "")
        # Memorizza la gerarchia e le coordinate PRIMA di setValue
        # (setValue triggerebbe _on_coords_changed che azzererebbe _selected_hierarchy)
        _selected_hierarchy[0] = hier if hier else None
        _selected_lat[0] = float(r["latitude"])
        _selected_lon[0] = float(r["longitude"])
        spin_lat.blockSignals(True)
        spin_lon.blockSignals(True)
        spin_lat.setValue(float(r["latitude"]))
        spin_lon.setValue(float(r["longitude"]))
        spin_lat.blockSignals(False)
        spin_lon.blockSignals(False)
        lbl_hier.setText(f"→ {hier}" if hier else "")
        search_edit.blockSignals(True)
        search_edit.clear()
        search_edit.blockSignals(False)
        search_list.clear()
        lbl_search_status.setText(f"Selezionato: {selected_text}")

    search_edit.textChanged.connect(_on_search_changed)
    search_list.itemDoubleClicked.connect(_on_search_select)
    btn_verify.clicked.connect(lambda: _on_search_select(None))

    # ── Accettazione e scrittura DB ───────────────────────────────────────
    def _on_accept():
        lat = spin_lat.value()
        lon = spin_lon.value()
        overwrite = chk_overwrite.isChecked()

        # Filtra immagini target
        if overwrite:
            imgs = target_items
        else:
            imgs = [it for it in target_items if not it.image_data.get("gps_latitude")]

        if not imgs:
            QMessageBox.information(
                dlg, "GeoNames",
                "Nessuna immagine da aggiornare con le opzioni selezionate."
            )
            return

        ids = [it.image_id for it in imgs if it.image_id is not None]
        if not ids:
            return

        btn_ok.setEnabled(False)
        pb.setValue(0)
        pb.show()
        lbl_status.setText("Scrittura coordinate in corso...")

        location = {"latitude": lat, "longitude": lon, "altitude": None}

        # Esegue la scrittura nel thread principale con processEvents
        # (gallery gestisce tipicamente poche decine di immagini — nessun freeze percepibile)
        try:
            from PyQt6.QtWidgets import QApplication

            enricher = gn.GeoNamesEnricher(cfg)
            # Se l'utente ha selezionato dalla ricerca, usa la gerarchia già pronta
            # (il reverse geocoding troverebbe il comune, non la frazione specifica)
            if _selected_hierarchy[0]:
                hierarchy = _selected_hierarchy[0]
            else:
                hierarchy = enricher.get_hierarchy(float(lat), float(lon))

            new_leaf = enricher.get_geo_leaf(hierarchy) if hierarchy else None

            conn = sqlite3.connect(db_path)
            processed = 0
            total = len(ids)
            for i, img_id in enumerate(ids):
                # Legge il vecchio geo_hierarchy e tags per aggiornare il leaf nei tag
                row = conn.execute(
                    "SELECT geo_hierarchy, tags FROM images WHERE id=?", (img_id,)
                ).fetchone()
                old_leaf = None
                new_tags_json = None
                if row:
                    old_hier = row[0] or ""
                    if old_hier:
                        old_parts = [p for p in old_hier.split("|") if p and p != "GeOFF"]
                        old_leaf = old_parts[-1] if old_parts else None
                    # Aggiorna tags: rimuove vecchio leaf, aggiunge nuovo (se diverso)
                    try:
                        tags = json.loads(row[1]) if row[1] else []
                        if not isinstance(tags, list):
                            tags = []
                        # Rimuove il vecchio leaf (case-insensitive)
                        if old_leaf:
                            tags = [t for t in tags if t.lower() != old_leaf.lower()]
                        # Aggiunge il nuovo leaf se presente e non già nei tag
                        if new_leaf and new_leaf.lower() not in [t.lower() for t in tags]:
                            tags.insert(0, new_leaf)
                        new_tags_json = json.dumps(tags, ensure_ascii=False)
                    except Exception:
                        new_tags_json = None

                if new_tags_json is not None:
                    conn.execute(
                        """UPDATE images
                           SET gps_latitude=?, gps_longitude=?, gps_altitude=?,
                               geo_hierarchy=?, tags=?, gps_modified=1
                           WHERE id=?""",
                        (lat, lon, location["altitude"], hierarchy, new_tags_json, img_id)
                    )
                else:
                    conn.execute(
                        """UPDATE images
                           SET gps_latitude=?, gps_longitude=?, gps_altitude=?,
                               geo_hierarchy=?, gps_modified=1
                           WHERE id=?""",
                        (lat, lon, location["altitude"], hierarchy, img_id)
                    )
                processed += 1
                pb.setValue(int((i + 1) * 100 / total))
                QApplication.processEvents()
            conn.commit()

            # Aggiorna image_data in memoria e forza repaint delle card
            # Rilegge tags aggiornati dal DB per allineare la memoria
            updated_tags = {}
            for img_id in ids:
                row2 = conn.execute("SELECT tags FROM images WHERE id=?", (img_id,)).fetchone()
                if row2 and row2[0]:
                    try:
                        updated_tags[img_id] = json.loads(row2[0])
                    except Exception:
                        pass

            conn.close()

            for it in imgs:
                if it.image_id is None:
                    continue
                it.image_data["gps_latitude"]  = lat
                it.image_data["gps_longitude"] = lon
                it.image_data["gps_altitude"]  = location["altitude"]
                it.image_data["geo_hierarchy"] = hierarchy
                it.image_data["gps_modified"]  = 1
                if it.image_id in updated_tags:
                    it.image_data["tags"] = updated_tags[it.image_id]
                if hasattr(it, "_cached_semantic_tooltip"):
                    del it._cached_semantic_tooltip
                try:
                    it.update()
                except Exception:
                    pass

            # Salva last_location nella config del plugin, incluso preset_hierarchy
            # così la prossima apertura del dialog mostra già la localita' confermata
            cfg["last_location"] = {
                "latitude": lat,
                "longitude": lon,
                "altitude": location["altitude"],
                "preset_hierarchy": hierarchy,
            }
            gn.save_config(cfg)

            lbl_status.setText(f"Completato: {processed} foto aggiornate")
            pb.setValue(100)
            QApplication.processEvents()
            QTimer.singleShot(800, dlg.accept)

        except Exception as e:
            logger.error(f"GeoNames assign_location: {e}", exc_info=True)
            lbl_status.setText(f"Errore: {e}")
            btn_ok.setEnabled(True)

    bbox.accepted.connect(_on_accept)
    bbox.rejected.connect(dlg.reject)

    dlg.exec()


# ══════════════════════════════════════════════════════════════════════════════
# HELPER: lettura GPS da file fisico via ExifTool
# ══════════════════════════════════════════════════════════════════════════════

def _read_gps_from_exif(filepath: str) -> tuple:
    """
    Legge coordinate GPS dal file fisico tramite ExifTool.
    Restituisce (lat, lon) come float oppure (None, None).
    """
    import subprocess, re

    def _dms_to_decimal(dms_str, ref):
        if not dms_str:
            return None
        m = re.match(r'(\d+(?:\.\d+)?)\s+deg\s+(\d+(?:\.\d+)?)[\'′]\s*([\d.]+)', str(dms_str).strip())
        if m:
            val = float(m.group(1)) + float(m.group(2)) / 60.0 + float(m.group(3)) / 3600.0
            if ref and ref.upper() in ('S', 'W'):
                val = -val
            return val
        try:
            val = float(dms_str)
            if ref and ref.upper() in ('S', 'W'):
                val = -val
            return val
        except (ValueError, TypeError):
            return None

    try:
        result = subprocess.run(
            ['exiftool', '-s', '-GPSLatitude', '-GPSLatitudeRef',
             '-GPSLongitude', '-GPSLongitudeRef', str(filepath)],
            capture_output=True, text=True, timeout=10
        )
        data = {}
        for line in result.stdout.splitlines():
            if ':' in line:
                k, _, v = line.partition(':')
                data[k.strip()] = v.strip()
        lat = _dms_to_decimal(data.get('GPSLatitude'), data.get('GPSLatitudeRef'))
        lon = _dms_to_decimal(data.get('GPSLongitude'), data.get('GPSLongitudeRef'))
        return lat, lon
    except Exception as e:
        logger.warning(f"GeoNames: lettura GPS da EXIF fallita per {filepath}: {e}")
        return None, None


def _load_plugin_module(plugin_name: str):
    """
    Carica il modulo principale di un plugin dalla directory plugins/.
    Restituisce il modulo oppure None se non disponibile.
    """
    plugins_dir = _PLUGIN_DIR.parent
    main_file = plugins_dir / plugin_name / f"{plugin_name}.py"
    if not main_file.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location(plugin_name, str(main_file))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        logger.warning(f"GeoNames: impossibile caricare plugin {plugin_name}: {e}")
        return None


def _load_plugin_config(plugin_name: str) -> dict:
    """Carica config.json di un plugin, restituisce {} se assente."""
    cfg_file = _PLUGIN_DIR.parent / plugin_name / "config.json"
    try:
        with open(cfg_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# RIELABORA LOCALIZZAZIONE (GeoNames + weather + naturarea)
# ══════════════════════════════════════════════════════════════════════════════

def recalc_hierarchy(target_items: list, db_path: str, parent=None) -> None:
    """
    Rielabora la localizzazione completa per le immagini selezionate.

    Per ogni immagine:
    - Legge le coordinate GPS **dal file fisico** via ExifTool (fonte di verità).
      Se il file non ha GPS nativo (foto senza geotag), usa come fallback
      le coordinate presenti nel DB (assegnate manualmente dall'utente).
    - Riscrive gps_latitude/gps_longitude nel DB con i valori reali del file.
    - Ricalcola geo_hierarchy tramite GeoNames.
    - Richiama weather_context.process_images() se il plugin è presente.
    - Richiama naturarea.process_images() se il plugin è presente.
    - Aggiorna image_data in memoria e invalida il tooltip.
    """
    from PyQt6.QtWidgets import QProgressDialog, QApplication, QMessageBox
    from PyQt6.QtCore import Qt

    cfg = _load_config()
    gn  = _load_core()

    # Considera tutti gli item validi — le coordinate vengono lette dal file fisico
    valid_items = [it for it in target_items if it.image_id is not None]
    if not valid_items:
        QMessageBox.information(parent, "GeoNames", "Nessuna immagine selezionata.")
        return

    total = len(valid_items)
    progress = QProgressDialog(
        f"Rielaborazione localizzazione per {total} foto...",
        "Annulla", 0, 100, parent
    )
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setStyleSheet("QProgressDialog { background-color: #2A2A2A; color: #E3E3E3; }")
    progress.setMinimumDuration(0)
    progress.setValue(0)

    cancelled = [False]
    progress.canceled.connect(lambda: cancelled.__setitem__(0, True))

    processed = 0
    skipped = 0
    updated_ids = []

    try:
        enricher = gn.GeoNamesEnricher(cfg)
        conn = sqlite3.connect(db_path)

        # ── Fase 1: GeoNames ──────────────────────────────────────────────────
        for i, it in enumerate(valid_items):
            if cancelled[0]:
                break

            # Fonte di verità: coordinate dal file fisico via ExifTool
            filepath = it.image_data.get("filepath") or it.image_data.get("file_path")
            lat, lon = _read_gps_from_exif(filepath) if filepath else (None, None)

            # Indica se le coordinate vengono dal file fisico (GPS nativo) o dal DB (manuale)
            from_exif = lat is not None and lon is not None

            # Fallback: coordinate nel DB (foto senza GPS nativo, assegnate manualmente)
            if not from_exif:
                lat = it.image_data.get("gps_latitude")
                lon = it.image_data.get("gps_longitude")

            if lat is None or lon is None:
                skipped += 1
                progress.setValue(int((i + 1) * 50 / total))
                QApplication.processEvents()
                continue

            hier = enricher.get_hierarchy(float(lat), float(lon))
            if hier:
                # Se le coordinate vengono dal file fisico, resettiamo gps_modified=0
                # (le coordinate DB tornano ad allinearsi con gli EXIF)
                gps_mod_val = 0 if from_exif else (it.image_data.get("gps_modified") or 0)
                conn.execute(
                    "UPDATE images SET geo_hierarchy=?, gps_latitude=?, gps_longitude=?, gps_modified=? WHERE id=?",
                    (hier, lat, lon, gps_mod_val, it.image_id)
                )
                it.image_data["geo_hierarchy"] = hier
                it.image_data["gps_latitude"] = lat
                it.image_data["gps_longitude"] = lon
                it.image_data["gps_modified"] = gps_mod_val
                updated_ids.append(it.image_id)
                processed += 1
            else:
                skipped += 1

            progress.setValue(int((i + 1) * 50 / total))
            QApplication.processEvents()

        conn.commit()
        conn.close()

        if cancelled[0] or not updated_ids:
            progress.close()
            _set_status(
                parent,
                f"GeoNames: gerarchia ricalcolata per {processed} foto"
                + (f", {skipped} saltate" if skipped else "")
            )
            return

        # ── Fase 2: weather_context ───────────────────────────────────────────
        progress.setLabelText(f"Meteo per {len(updated_ids)} foto...")
        QApplication.processEvents()
        weather_mod = _load_plugin_module("weather_context")
        if weather_mod and hasattr(weather_mod, "process_images"):
            try:
                weather_cfg = _load_plugin_config("weather_context")
                weather_mod.process_images(
                    db_path, weather_cfg,
                    image_ids=updated_ids,
                    unprocessed_only=False
                )
            except Exception as e:
                logger.warning(f"GeoNames: weather_context fallito: {e}")
        progress.setValue(75)
        QApplication.processEvents()

        # ── Fase 3: naturarea ─────────────────────────────────────────────────
        progress.setLabelText(f"NaturArea per {len(updated_ids)} foto...")
        QApplication.processEvents()
        natura_mod = _load_plugin_module("naturarea")
        if natura_mod and hasattr(natura_mod, "process_images"):
            try:
                natura_cfg = _load_plugin_config("naturarea")
                natura_mod.process_images(
                    db_path, natura_cfg,
                    image_ids=updated_ids,
                    unprocessed_only=False
                )
            except Exception as e:
                logger.warning(f"GeoNames: naturarea fallito: {e}")
        progress.setValue(90)
        QApplication.processEvents()

        # ── Fase 4: aggiorna image_data in memoria ────────────────────────────
        id_set = set(updated_ids)
        conn2 = sqlite3.connect(db_path)
        conn2.row_factory = sqlite3.Row
        placeholders = ','.join('?' * len(updated_ids))
        rows = conn2.execute(
            f"SELECT id, geo_hierarchy, weather_context, protected_area, habitat "
            f"FROM images WHERE id IN ({placeholders})",
            updated_ids
        ).fetchall()
        conn2.close()

        db_map = {r["id"]: r for r in rows}
        for it in valid_items:
            if it.image_id not in id_set:
                continue
            row = db_map.get(it.image_id)
            if row:
                for field in ("geo_hierarchy", "weather_context", "protected_area", "habitat"):
                    it.image_data[field] = row[field]
            if hasattr(it, "_cached_semantic_tooltip"):
                del it._cached_semantic_tooltip

        progress.setValue(100)
        progress.close()
        _set_status(
            parent,
            f"GeoNames: localizzazione rielaborata per {processed} foto"
            + (f", {skipped} saltate (no GPS)" if skipped else "")
        )

    except Exception as e:
        logger.error(f"GeoNames recalc_hierarchy: {e}", exc_info=True)
        progress.close()


# ══════════════════════════════════════════════════════════════════════════════
# CANCELLA DATI GPS
# ══════════════════════════════════════════════════════════════════════════════

def clear_gps(target_items: list, db_path: str, parent=None) -> None:
    """
    Azzera i dati di localizzazione derivati (geo_hierarchy, weather_context,
    protected_area, habitat) per tutte le immagini selezionate.
    Le coordinate GPS (gps_latitude, gps_longitude) non vengono toccate:
    rispecchiano gli EXIF del file fisico e rimangono nel DB.
    Chiede conferma prima di procedere.
    """
    from PyQt6.QtWidgets import QMessageBox

    n = len(target_items)
    reply = QMessageBox.question(
        parent,
        pt("gn.clear.title"),
        pt("gn.clear.body", n=n, suffix=("e" if n == 1 else "i")),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    ids = [it.image_id for it in target_items if it.image_id is not None]
    if not ids:
        return

    try:
        gn = _load_core()
        updated = gn.clear_gps(db_path=db_path, image_ids=ids)

        # Aggiorna image_data in memoria — solo campi derivati, non le coordinate
        for it in target_items:
            if it.image_id is None:
                continue
            for field in ("geo_hierarchy", "weather_context",
                          "protected_area", "habitat"):
                it.image_data[field] = None
            it.image_data["gps_modified"] = 0
            if hasattr(it, "_cached_semantic_tooltip"):
                del it._cached_semantic_tooltip

        _set_status(parent, f"GeoNames: dati localizzazione cancellati da {updated} foto")

    except Exception as e:
        logger.error(f"GeoNames clear_gps: {e}")
        QMessageBox.critical(parent, "GeoNames", f"Errore durante la cancellazione:\n{e}")


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY
# ══════════════════════════════════════════════════════════════════════════════

def _set_status(parent, msg: str) -> None:
    """Mostra un messaggio nella status bar della main window se disponibile."""
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        def _do():
            win = QApplication.activeWindow()
            if win and hasattr(win, "update_status"):
                win.update_status(msg, 8000)
            elif win and hasattr(win, "status_bar"):
                win.status_bar.showMessage(msg, 8000)

        QTimer.singleShot(0, _do)
    except Exception:
        pass


def is_plugin_available() -> bool:
    """
    Ritorna True se il plugin GeoNames e' configurato e pronto.
    Usato da gallery_widgets per decidere se mostrare il sottomenu.
    """
    try:
        gn  = _load_core()
        cfg = gn.load_config()
        enricher = gn.GeoNamesEnricher(cfg)
        return enricher.is_ready()
    except Exception:
        return False
