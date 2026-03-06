from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QPushButton,
    QProgressDialog,
    QFileDialog,
    QMessageBox,
    QApplication,
    QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path
import yaml
import shutil
import json
from datetime import datetime
import logging
from gui.gallery_widgets import apply_popup_style
from xmp_badge_manager import refresh_xmp_badges
from utils.copy_helpers import compute_common_roots, compute_dest_path
from i18n import t

logger = logging.getLogger(__name__)


class ExportTab(QWidget):
    """
    Export Tab - Modalità IBRIDA
    Base: opzioni essenziali
    Avanzate: opzioni tecniche e specialistiche
    """
    export_completed = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None
        self.images_to_export = []
        self._build_ui()
        # self._set_default_output_dir()

    def set_main_window(self, main_window):
        self.main_window = main_window

    # ------------------------------------------------------------------
    # UI ROOT
    # ------------------------------------------------------------------

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        scroll_layout = QVBoxLayout(container)
        scroll_layout.setSpacing(14)
        scroll_layout.setContentsMargins(12, 12, 12, 12)

        # === SEZIONI ===
        scroll_layout.addWidget(self._export_format_group())
        scroll_layout.addWidget(self._export_path_group())
        scroll_layout.addWidget(self._advanced_group())
        scroll_layout.addWidget(self._selection_group())
        scroll_layout.addWidget(self._export_group())

        scroll_layout.addStretch(1)

        # Connetti format_sidecar alla sezione destinazione
        # (embedded e copy sono già collegati nei rispettivi toggle)
        self.format_sidecar.toggled.connect(self._update_destination_ui)

        # Stato iniziale della sezione destinazione
        self._update_destination_ui()

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def set_images(self, images):
        """
        Imposta immagini da esportare (chiamato da Gallery)
    
        Args:
            images: Lista ImageCard selezionate
        """
        self.images_to_export = images
        count = len(images)
    
        if count == 0:
            self.selection_info.setText(t("export.label.no_selection"))
            self.export_btn.setEnabled(False)
        else:
            self.selection_info.setText(t("export.label.selection_count", count=count))
            self.export_btn.setEnabled(True)



    # ------------------------------------------------------------------
    # EXPORT FORMAT
    # ------------------------------------------------------------------
    
    def _export_format_group(self) -> QGroupBox:
        box = QGroupBox(t("export.group.what_to_export"))
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # --- XMP sidecar ---
        self.format_sidecar = QCheckBox(t("export.check.xmp_sidecar"))
        self.format_sidecar.setToolTip(t("export.tooltip.xmp_sidecar"))

        # --- XMP embedded + opzione DNG indentata ---
        self.format_embedded = QCheckBox(t("export.check.xmp_embedded"))
        self.format_embedded.setToolTip(t("export.tooltip.xmp_embedded"))

        self.dng_allow_embedded = QCheckBox(t("export.check.dng_embedded"))
        self.dng_allow_embedded.setChecked(False)
        self.dng_allow_embedded.setEnabled(False)
        self.dng_allow_embedded.setToolTip(t("export.tooltip.dng_embedded"))
        dng_widget = QWidget()
        dng_layout = QVBoxLayout(dng_widget)
        dng_layout.setContentsMargins(24, 2, 0, 2)
        dng_layout.setSpacing(0)
        dng_layout.addWidget(self.dng_allow_embedded)
        self.dng_options_widget = dng_widget

        self.format_embedded.toggled.connect(self._on_embedded_toggled)

        # --- CSV ---
        self.format_csv = QCheckBox(t("export.check.csv"))
        self.format_csv.setToolTip(t("export.tooltip.csv"))

        self.csv_include_gps = QCheckBox(t("export.check.include_gps"))
        self.csv_include_gps.setChecked(True)
        self.csv_include_gps.setToolTip(t("export.tooltip.include_gps"))

        # --- Copia file + opzioni indentate ---
        self.format_copy = QCheckBox(t("export.check.copy_originals"))
        self.format_copy.setToolTip(t("export.tooltip.copy_originals"))

        self.copy_preserve_structure = QCheckBox(t("export.check.preserve_structure"))
        self.copy_preserve_structure.setToolTip(t("export.tooltip.preserve_structure"))
        self.copy_preserve_structure.setEnabled(False)

        self.copy_overwrite = QCheckBox(t("export.check.copy_overwrite"))
        self.copy_overwrite.setToolTip(t("export.tooltip.copy_overwrite"))
        self.copy_overwrite.setEnabled(False)

        copy_options_widget = QWidget()
        copy_options_layout = QVBoxLayout(copy_options_widget)
        copy_options_layout.setContentsMargins(24, 2, 0, 2)
        copy_options_layout.setSpacing(4)
        copy_options_layout.addWidget(self.copy_preserve_structure)
        copy_options_layout.addWidget(self.copy_overwrite)
        self.copy_options_widget = copy_options_widget

        # --- Default e segnali ---
        self.format_sidecar.setChecked(True)
        self.format_copy.toggled.connect(self._on_copy_toggled)
        self.format_csv.toggled.connect(self._on_csv_toggled)

        # --- Layout ---
        layout.addWidget(self.format_sidecar)
        layout.addWidget(self.format_embedded)
        layout.addWidget(self.dng_options_widget)

        csv_row_widget = QWidget()
        csv_row = QHBoxLayout(csv_row_widget)
        csv_row.setContentsMargins(0, 0, 0, 0)
        csv_row.setSpacing(16)
        csv_row.addWidget(self.format_csv)
        csv_row.addWidget(self.csv_include_gps)
        csv_row.addStretch()
        layout.addWidget(csv_row_widget)

        layout.addWidget(self.format_copy)
        layout.addWidget(self.copy_options_widget)

        return box

    def _on_embedded_toggled(self, checked):
        """Abilita/disabilita opzione DNG embedded e aggiorna sezione destinazione"""
        self.dng_allow_embedded.setEnabled(checked)
        if not checked:
            self.dng_allow_embedded.setChecked(False)
        self._update_destination_ui()

    def _on_copy_toggled(self, checked):
        """Abilita opzioni copia e aggiorna sezione destinazione"""
        self.copy_preserve_structure.setEnabled(checked)
        self.copy_overwrite.setEnabled(checked)
        self._update_destination_ui()
    
    # ------------------------------------------------------------------
    # EXPORT PATH
    # ------------------------------------------------------------------
    
    def _export_path_group(self) -> QGroupBox:
        box = QGroupBox(t("export.group.destination"))
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # --- Blocco XMP: visibile solo quando XMP sidecar/embedded è attivo ---
        xmp_dest_widget = QWidget()
        xmp_dest_layout = QVBoxLayout(xmp_dest_widget)
        xmp_dest_layout.setContentsMargins(0, 0, 0, 4)
        xmp_dest_layout.setSpacing(4)

        xmp_dest_header = QLabel(t("export.label.xmp_dest"))
        xmp_dest_header.setStyleSheet("font-weight: bold;")

        self.path_original = QRadioButton(t("export.radio.xmp_original"))
        self.path_original.setToolTip(t("export.tooltip.xmp_original"))
        self.path_single = QRadioButton(t("export.radio.xmp_single"))
        self.path_single.setToolTip(t("export.tooltip.xmp_single"))

        self.path_original.setChecked(True)
        self.path_group = QButtonGroup(self)
        self.path_group.addButton(self.path_original, 0)
        self.path_group.addButton(self.path_single, 1)

        xmp_dest_layout.addWidget(xmp_dest_header)
        xmp_dest_layout.addWidget(self.path_original)
        xmp_dest_layout.addWidget(self.path_single)
        self.xmp_dest_widget = xmp_dest_widget

        # --- Picker directory di output: label e visibilità dinamiche ---
        dir_row_widget = QWidget()
        dir_row_layout = QHBoxLayout(dir_row_widget)
        dir_row_layout.setContentsMargins(0, 0, 0, 0)

        self.output_dir_label = QLabel(t("export.label.dir_output"))
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText(t("export.placeholder.output_dir"))

        self.browse_btn = QPushButton("📂")
        self.browse_btn.setMaximumWidth(40)
        self.browse_btn.clicked.connect(self._browse_output_dir)

        dir_row_layout.addWidget(self.output_dir_label)
        dir_row_layout.addWidget(self.output_dir_input)
        dir_row_layout.addWidget(self.browse_btn)
        self.dir_row_widget = dir_row_widget

        # --- Info contestuale (testo dinamico) ---
        self.path_info = QLabel()
        self.path_info.setWordWrap(True)
        self.path_info.setStyleSheet("color: gray; font-size: 10px;")

        # --- Directory CSV dedicata (opzionale, visibile solo con CSV attivo) ---
        csv_dir_label = QLabel(t("export.label.csv_dir"))
        self.csv_dir_input = QLineEdit()
        self.csv_dir_input.setPlaceholderText(t("export.placeholder.csv_dir"))
        self.csv_dir_input.setEnabled(False)

        self.csv_browse_btn = QPushButton("📂")
        self.csv_browse_btn.setMaximumWidth(40)
        self.csv_browse_btn.setEnabled(False)
        self.csv_browse_btn.clicked.connect(self._browse_csv_dir)

        csv_dir_layout = QHBoxLayout()
        csv_dir_layout.addWidget(csv_dir_label)
        csv_dir_layout.addWidget(self.csv_dir_input)
        csv_dir_layout.addWidget(self.csv_browse_btn)

        self.csv_dir_label = csv_dir_label
        self.csv_dir_label.setEnabled(False)

        # Segnali radio XMP
        self.path_original.toggled.connect(self._on_path_mode_changed)
        self.path_single.toggled.connect(self._on_path_mode_changed)

        # Layout finale
        layout.addWidget(self.xmp_dest_widget)
        layout.addWidget(self.dir_row_widget)
        layout.addWidget(self.path_info)
        layout.addLayout(csv_dir_layout)

        return box

    def _browse_output_dir(self):
        """Seleziona directory output"""
        directory = QFileDialog.getExistingDirectory(
            self,
            t("export.dialog.select_output_dir"),
            self.output_dir_input.text() or ""
        )
        if directory:
            self.output_dir_input.setText(directory)

    def _browse_csv_dir(self):
        """Seleziona directory output CSV"""
        directory = QFileDialog.getExistingDirectory(
            self,
            t("export.dialog.select_csv_dir"),
            self.csv_dir_input.text() or ""
        )
        if directory:
            self.csv_dir_input.setText(directory)

    def _on_csv_toggled(self, checked):
        """Abilita/disabilita campo directory CSV"""
        self.csv_dir_label.setEnabled(checked)
        self.csv_dir_input.setEnabled(checked)
        self.csv_browse_btn.setEnabled(checked)

    def _on_path_mode_changed(self):
        """Aggiorna UI destinazione al cambio radio XMP"""
        self._update_destination_ui()

    def _update_destination_ui(self):
        """
        Aggiorna la sezione Destinazione in base a cosa è selezionato:
        - Blocco radio XMP visibile solo se XMP (sidecar/embedded) è attivo
        - Picker directory visibile e con label contestuale
        - Info text esplicativo della combinazione attiva
        """
        has_xmp  = self.format_sidecar.isChecked() or self.format_embedded.isChecked()
        has_copy = self.format_copy.isChecked()
        xmp_to_output = has_xmp and self.path_single.isChecked()

        # Radio XMP: compare solo se c'è qualcosa da scrivere come XMP
        self.xmp_dest_widget.setVisible(has_xmp)

        # Picker directory: serve per copia (sempre) e per XMP→directory
        need_dir = has_copy or xmp_to_output
        self.dir_row_widget.setVisible(need_dir)

        # Label e info contestuali
        if has_copy and has_xmp:
            self.output_dir_label.setText(t("export.label.dir_output"))
            if self.path_original.isChecked():
                self.path_info.setText(t("export.label.dir_info_xmp_copy"))
            else:
                self.path_info.setText(t("export.label.dir_info_both_output"))
        elif has_copy:
            self.output_dir_label.setText(t("export.label.dir_copy"))
            self.path_info.setText("")
        elif xmp_to_output:
            self.output_dir_label.setText(t("export.label.dir_xmp"))
            self.path_info.setText("")
        else:
            self.path_info.setText("")

    # ------------------------------------------------------------------
    # ADVANCED
    # ------------------------------------------------------------------

    def _advanced_group(self) -> QGroupBox:
        box = QGroupBox(t("export.group.xmp_behavior"))
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # Sezione: Opzioni XMP — controllo indipendente per campo
        xmp_section = QGroupBox(t("export.group.xmp_section"))
        xmp_layout = QVBoxLayout(xmp_section)
        xmp_layout.setSpacing(5)

        self.xmp_merge_keywords = QCheckBox(t("export.check.merge_keywords"))
        self.xmp_merge_keywords.setChecked(True)
        self.xmp_merge_keywords.setToolTip(t("export.tooltip.merge_keywords"))

        self.xmp_preserve_title = QCheckBox(t("export.check.preserve_title"))
        self.xmp_preserve_title.setChecked(True)
        self.xmp_preserve_title.setToolTip(t("export.tooltip.preserve_title"))

        self.xmp_preserve_description = QCheckBox(t("export.check.preserve_description"))
        self.xmp_preserve_description.setChecked(True)
        self.xmp_preserve_description.setToolTip(t("export.tooltip.preserve_description"))

        self.xmp_preserve_rating = QCheckBox(t("export.check.preserve_rating"))
        self.xmp_preserve_rating.setChecked(True)
        self.xmp_preserve_rating.setToolTip(t("export.tooltip.preserve_rating"))

        self.xmp_preserve_color_label = QCheckBox(t("export.check.preserve_color_label"))
        self.xmp_preserve_color_label.setChecked(True)
        self.xmp_preserve_color_label.setToolTip(t("export.tooltip.preserve_color_label"))

        # Nota: namespace Lightroom sempre preservati
        note = QLabel(t("export.label.lr_namespace_note"))
        note.setStyleSheet("color: gray; font-style: italic; font-size: 10px;")

        for cb in [self.xmp_merge_keywords, self.xmp_preserve_title, self.xmp_preserve_description,
                   self.xmp_preserve_rating, self.xmp_preserve_color_label]:
            xmp_layout.addWidget(cb)
        xmp_layout.addWidget(note)

        layout.addWidget(xmp_section)

        return box

    # ------------------------------------------------------------------
    # SELECTION (Esistente)
    # ------------------------------------------------------------------

    def _selection_group(self) -> QGroupBox:
        box = QGroupBox(t("export.group.selection"))
        layout = QVBoxLayout(box)

        self.selection_info = QLabel(t("export.label.no_selection"))
        layout.addWidget(self.selection_info)
    
        return box

    # ------------------------------------------------------------------
    # EXPORT ACTION
    # ------------------------------------------------------------------

    def _export_group(self) -> QGroupBox:
        box = QGroupBox(t("export.group.action"))
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        info_label = QLabel(t("export.label.action_info"))
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # Pulsante export
        self.export_btn = QPushButton(t("export.btn.start_export"))
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._do_export)
        self.export_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                background-color: #2E8B57;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #3CB371;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #999;
            }
        """)
        layout.addWidget(self.export_btn)

        return box
    # ------------------------------------------------------------------
    # EXPORT LOGIC
    # ------------------------------------------------------------------

    def _do_export(self):
        """Export principale: gestisce XMP sidecar, XMP embedded, CSV, copia foto"""
        if not self.images_to_export:
            QMessageBox.warning(self, t("export.msg.error_title"), t("export.label.no_selection"))
            return

        options = self.get_export_options()

        # Validazione: almeno un formato selezionato
        if not any([options['format']['sidecar'], options['format']['embedded'],
                    options['format']['csv'], options['format']['copy']]):
            QMessageBox.warning(self, t("export.msg.error_title"), t("export.msg.no_operation"))
            return

        # Validazione: directory output richiesta per copia e/o XMP in directory unica
        need_output_dir = options['path']['single'] or options['format']['copy']
        if need_output_dir and not options['path']['single_dir']:
            motivi = []
            if options['format']['copy']:
                motivi.append("copia file")
            if options['path']['single']:
                motivi.append("XMP in directory di output")
            QMessageBox.warning(self, t("export.msg.missing_dir_title"),
                t("export.msg.missing_dir", reasons=', '.join(motivi)))
            return

        try:
            export_xmp = options['format']['sidecar'] or options['format']['embedded']
            export_csv = options['format']['csv']
            export_copy = options['format']['copy']

            # Messaggio conferma
            export_types = []
            if options['format']['sidecar']:
                export_types.append("XMP sidecar")
            if options['format']['embedded']:
                export_types.append("XMP embedded")
            if export_csv:
                export_types.append("CSV")
            if export_copy:
                export_types.append(t("export.confirm.copy_photos"))

            xmp_location = (
                t("export.confirm.xmp_original_loc") if options['path']['original']
                else options['path']['single_dir']
            )
            copy_location = options['path']['single_dir'] or t("export.confirm.no_dir")
            if export_xmp and export_copy:
                location_msg = f"XMP → {xmp_location}  |  Copia → {copy_location}"
            elif export_xmp:
                location_msg = f"XMP → {xmp_location}"
            elif export_copy:
                location_msg = f"Copia → {copy_location}"
            else:
                location_msg = options['path']['single_dir'] or t("export.confirm.orig_dir")

            # Riepilogo comportamento per campo
            xmp_mode_note = ""
            if export_xmp:
                adv = options['advanced']

                def _mode(preserve_flag, preserve_label=None, overwrite_label=None):
                    if preserve_label is None:
                        preserve_label = t("export.confirm.field_preserve")
                    if overwrite_label is None:
                        overwrite_label = t("export.confirm.field_overwrite")
                    return preserve_label if adv.get(preserve_flag, True) else overwrite_label

                kw_mode = t("export.confirm.kw_merge") if adv.get('xmp_merge_keywords', True) else t("export.confirm.kw_replace")
                xmp_mode_note = (
                    f"\n\n📋 Comportamento per campo:\n"
                    f"  • Keywords:     {kw_mode}\n"
                    f"  • Title:        {_mode('xmp_preserve_title')}\n"
                    f"  • Descrizione:  {_mode('xmp_preserve_description')}\n"
                    f"  • Rating:       {_mode('xmp_preserve_rating')}\n"
                    f"  • Color Label:  {_mode('xmp_preserve_color_label')}\n"
                    f"  • Namespace Lightroom (crs:, lr:, xmpMM:): sempre preservati"
                )

            reply = QMessageBox.question(
                self,
                t("export.msg.confirm_title"),
                t("export.confirm.question",
                  types=' + '.join(export_types),
                  count=len(self.images_to_export),
                  location=location_msg,
                  xmp_note=xmp_mode_note),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # --- CSV ---
            csv_success = True
            if export_csv:
                csv_success = self._write_csv_export(self.images_to_export, options)

            # --- XMP (sidecar e/o embedded) ---
            success_count = 0
            failed_count = 0
            skipped_count = 0

            if export_xmp:
                progress = QProgressDialog(
                    t("export.progress.xmp_running"),
                    t("export.progress.cancel"),
                    0,
                    len(self.images_to_export),
                    self
                )
                progress.setWindowTitle(t("export.progress.xmp_window"))
                progress.setModal(True)
                apply_popup_style(progress)
                progress.show()
                QApplication.processEvents()

                for i, image_item in enumerate(self.images_to_export):
                    if progress.wasCanceled():
                        break

                    progress.setValue(i)
                    filename = image_item.image_data.get('filename', 'unknown')
                    progress.setLabelText(t("export.progress.xmp_label", filename=filename))
                    QApplication.processEvents()

                    try:
                        source_path = Path(image_item.image_data.get('filepath', ''))
                        if not source_path.exists():
                            print(f"❌ File non esiste: {source_path}")
                            failed_count += 1
                            continue

                        # XMP sidecar
                        if options['format']['sidecar']:
                            if self._write_xmp_sidecar(source_path, image_item, options):
                                success_count += 1
                            else:
                                failed_count += 1

                        # XMP embedded (con validazione compatibilità)
                        if options['format']['embedded']:
                            caps = self._get_file_capabilities(str(source_path))
                            should_skip = False
                            if caps['is_raw'] and not caps['is_dng']:
                                should_skip = True
                            elif caps['is_dng'] and not options['format']['dng_allow_embedded']:
                                should_skip = True
                            elif not caps['can_embedded']:
                                should_skip = True

                            if should_skip:
                                skipped_count += 1
                            else:
                                if self._write_xmp_embedded(source_path, image_item, options):
                                    success_count += 1
                                else:
                                    failed_count += 1

                    except Exception as e:
                        failed_count += 1
                        print(f"❌ Errore export XMP per {filename}: {e}")

                progress.setValue(len(self.images_to_export))
                progress.close()

            # --- Copia foto ---
            copy_count = 0
            copy_failed = 0
            copy_skipped = 0
            if export_copy:
                copy_count, copy_failed, copy_skipped = self._copy_photos(self.images_to_export, options)

            # --- Report finale ---
            try:
                report_parts = []
                if export_xmp and success_count > 0:
                    report_parts.append(t("export.report.xmp_created", n=success_count))
                if export_xmp and failed_count > 0:
                    report_parts.append(t("export.report.xmp_errors", n=failed_count))
                if export_xmp and skipped_count > 0:
                    report_parts.append(t("export.report.xmp_skipped", n=skipped_count))
                if export_csv and csv_success:
                    report_parts.append(t("export.report.csv_ok"))
                elif export_csv and not csv_success:
                    report_parts.append(t("export.report.csv_error"))
                if export_copy and copy_count > 0:
                    report_parts.append(t("export.report.photos_copied", n=copy_count))
                if export_copy and copy_skipped > 0:
                    report_parts.append(t("export.report.photos_skipped", n=copy_skipped))
                if export_copy and copy_failed > 0:
                    report_parts.append(t("export.report.photos_failed", n=copy_failed))

                if not report_parts:
                    report_parts.append(t("export.report.no_export"))

                message = t("export.report.done",
                            results=chr(10).join(report_parts),
                            location=location_msg)

                try:
                    QMessageBox.information(self, t("export.msg.done_title"), message)
                except Exception as dialog_error:
                    print(f"❌ Errore dialog finale: {dialog_error}")

            except Exception as report_error:
                print(f"❌ Errore report finale: {report_error}")
                try:
                    QMessageBox.information(self, t("export.msg.done_title"), t("export.msg.done_fallback"))
                except:
                    pass

            # Segnale completamento
            try:
                export_type = []
                if export_xmp: export_type.append("XMP")
                if export_csv: export_type.append("CSV")
                if export_copy: export_type.append("FOTO")

                total_success = success_count + copy_count + (1 if csv_success and export_csv else 0)
                format_string = "+".join(export_type) if export_type else "NONE"
                self.export_completed.emit(total_success, format_string)

            except Exception as signal_error:
                print(f"❌ Errore emissione signal: {signal_error}")

        except Exception as e:
            print(f"❌ Errore globale in _do_export: {e}")
            QMessageBox.critical(self, t("export.msg.error_export_title"), t("export.msg.error_export", error=e))
    
    def _write_csv_export(self, image_items, options):
        """Esporta metadati completi in formato CSV per workflow fotografico professionale"""
        try:
            import csv

            # Determina path CSV: csv_dir dedicata → single_dir → directory prima immagine
            csv_filename = f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            csv_dir = options['path'].get('csv_dir', '').strip()

            if csv_dir:
                output_dir = Path(csv_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                csv_path = output_dir / csv_filename
            elif options['path']['single'] and options['path']['single_dir']:
                output_dir = Path(options['path']['single_dir'])
                output_dir.mkdir(parents=True, exist_ok=True)
                csv_path = output_dir / csv_filename
            else:
                # Fallback: directory della prima immagine
                if image_items:
                    first_path = Path(image_items[0].image_data.get('filepath', ''))
                    csv_path = first_path.parent / csv_filename
                else:
                    csv_path = Path(csv_filename)
            
            # Scrivi CSV completo
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Header completo per workflow professionale
                headers = [
                    # File base
                    'Filename', 'Filepath', 'File_Size_MB', 'Format', 'Is_RAW', 'RAW_Format',
                    # Dimensioni
                    'Width', 'Height', 'Aspect_Ratio', 'Megapixels',
                    # Camera/Lens
                    'Camera_Make', 'Camera_Model', 'Lens_Model',
                    # Settings fotografici
                    'Focal_Length', 'Focal_Length_35mm', 'Aperture', 'Shutter_Speed', 'ISO',
                    # EXIF avanzato
                    'Exposure_Mode', 'Exposure_Bias', 'Metering_Mode', 'White_Balance',
                    'Flash_Used', 'Flash_Mode', 'Color_Space', 'Orientation',
                    # Date
                    'Date_Original', 'Date_Digitized', 'Date_Modified',
                    # GPS
                    'GPS_Latitude', 'GPS_Longitude', 'GPS_Altitude', 'GPS_Direction',
                    'GPS_City', 'GPS_State', 'GPS_Country', 'GPS_Location',
                    # Metadata autore
                    'Artist', 'Copyright', 'Software',
                    # XMP Lightroom
                    'Title', 'Description', 'Rating', 'Color_Label', 'Instructions',
                    # Tags e AI
                    'Tags', 'Aesthetic_Score', 'Technical_Score', 'Is_Monochrome',
                    'AI_Description', 'Model_Used',
                    # Processing
                    'Processed_Date', 'Processing_Time', 'Embedding_Generated', 'LLM_Generated'
                ]
                writer.writerow(headers)
                
                # Dati per ogni immagine
                for item in image_items:
                    data = item.image_data
                    
                    # Parse tag unificati
                    unified_tags = self._parse_tags(data.get('tags', ''))
                    
                    # File size in MB
                    file_size = data.get('file_size', 0)
                    file_size_mb = file_size / (1024 * 1024) if file_size else 0
                    
                    # Helper per valori booleani leggibili
                    def bool_to_text(val):
                        if val is None or val == '':
                            return ''
                        return 'Sì' if val else 'No'
                    
                    # Helper per valori numerici
                    def safe_float(val, decimals=2):
                        try:
                            return f"{float(val):.{decimals}f}" if val else ''
                        except:
                            return str(val) if val else ''
                    
                    row = [
                        # File base
                        data.get('filename', ''),
                        data.get('filepath', ''),
                        f"{file_size_mb:.2f}" if file_size_mb else '',
                        data.get('file_format', ''),
                        bool_to_text(data.get('is_raw')),
                        data.get('raw_format', ''),
                        # Dimensioni
                        data.get('width', ''),
                        data.get('height', ''),
                        safe_float(data.get('aspect_ratio')),
                        safe_float(data.get('megapixels'), 1),
                        # Camera/Lens
                        data.get('camera_make', ''),
                        data.get('camera_model', ''),
                        data.get('lens_model', ''),
                        # Settings fotografici
                        safe_float(data.get('focal_length'), 0),
                        safe_float(data.get('focal_length_35mm'), 0),
                        safe_float(data.get('aperture'), 1),
                        data.get('shutter_speed', ''),
                        data.get('iso', ''),
                        # EXIF avanzato
                        data.get('exposure_mode', ''),
                        safe_float(data.get('exposure_bias'), 1),
                        data.get('metering_mode', ''),
                        data.get('white_balance', ''),
                        bool_to_text(data.get('flash_used')),
                        data.get('flash_mode', ''),
                        data.get('color_space', ''),
                        data.get('orientation', ''),
                        # Date
                        data.get('datetime_original', ''),
                        data.get('datetime_digitized', ''),
                        data.get('datetime_modified', ''),
                        # GPS
                        safe_float(data.get('gps_latitude'), 6),
                        safe_float(data.get('gps_longitude'), 6),
                        safe_float(data.get('gps_altitude'), 1),
                        safe_float(data.get('gps_direction'), 1),
                        data.get('gps_city', ''),
                        data.get('gps_state', ''),
                        data.get('gps_country', ''),
                        data.get('gps_location', ''),
                        # Metadata autore
                        data.get('artist', ''),
                        data.get('copyright', ''),
                        data.get('software', ''),
                        # XMP Lightroom
                        data.get('title', ''),
                        data.get('description', ''),
                        data.get('lr_rating', '') or data.get('rating', ''),
                        data.get('color_label', ''),
                        data.get('lr_instructions', ''),
                        # Tags e AI
                        '; '.join(unified_tags),
                        safe_float(data.get('aesthetic_score')),
                        safe_float(data.get('technical_score')),
                        bool_to_text(data.get('is_monochrome')),
                        data.get('ai_description_hash', ''),
                        data.get('model_used', ''),
                        # Processing
                        data.get('processed_date', ''),
                        safe_float(data.get('processing_time'), 3),
                        bool_to_text(data.get('embedding_generated')),
                        bool_to_text(data.get('llm_generated'))
                    ]
                    writer.writerow(row)
            
            return True

        except Exception as e:
            print(f"❌ Errore export CSV: {e}")
            return False
    
    def _parse_tags(self, tags_data):
        """Parse tags unificati JSON to list con gestione robusta"""
        if not tags_data:
            return []
        try:
            import json
            if isinstance(tags_data, str):
                # BUGFIX: Gestisci stringhe mal formattate da versioni precedenti
                if tags_data.startswith('[') and not tags_data.startswith('["'):
                    # Stringa tipo "[tag1, tag2]" invece di JSON corretto
                    clean_str = tags_data.strip('[]')
                    return [tag.strip(' "\'') for tag in clean_str.split(',') if tag.strip()]
                else:
                    return json.loads(tags_data)
            elif isinstance(tags_data, list):
                return tags_data
            else:
                return []
        except:
            # Fallback per stringhe malformate
            if isinstance(tags_data, str):
                clean_str = tags_data.strip('[]')
                return [tag.strip(' "\'') for tag in clean_str.split(',') if tag.strip()]
            return []

    def _write_xmp_embedded(self, image_file: Path, image_item, options):
        """Scrivi metadati XMP embedded nel file (JPG, TIFF, DNG)"""
        try:

            # Costruisci lista keywords unificata
            tags_data = image_item.image_data.get('tags', '')
            if not tags_data:
                keywords = []
            else:
                try:
                    if isinstance(tags_data, str) and tags_data.startswith('['):
                        keywords = json.loads(tags_data)
                    elif isinstance(tags_data, str):
                        keywords = [tag.strip() for tag in tags_data.split(',') if tag.strip()]
                    elif isinstance(tags_data, list):
                        keywords = tags_data
                    else:
                        keywords = []
                except:
                    keywords = []

            if keywords:
                keywords = list(dict.fromkeys(keywords))

            import subprocess

            # Flag preserve — stessi del sidecar, applicati al file embedded
            do_merge_kw   = options['advanced'].get('xmp_merge_keywords', True)
            do_pres_title = options['advanced'].get('xmp_preserve_title', True)
            do_pres_desc  = options['advanced'].get('xmp_preserve_description', True)
            do_pres_rate  = options['advanced'].get('xmp_preserve_rating', True)
            do_pres_color = options['advanced'].get('xmp_preserve_color_label', True)

            # Leggi campi esistenti dal file embedded se almeno un flag preserve è attivo
            existing_emb = {}
            any_preserve = do_pres_title or do_pres_desc or do_pres_rate or do_pres_color
            if any_preserve:
                existing_emb = self._read_existing_scalar_fields_from_xmp(image_file)

            cmd = ["exiftool", "-overwrite_original"]

            # KEYWORDS — azzera Subject se merge disattivo, altrimenti += aggiunge ai presenti
            if not do_merge_kw:
                cmd.append("-XMP-dc:Subject=")

            if keywords:
                for kw in keywords:
                    cmd.append(f"-XMP-dc:Subject+={kw}")

            # TITLE
            title = image_item.image_data.get('title', '') or ''
            if not title:
                title = image_item.image_data.get('filename', '').split('.')[0]
            if title:
                if not do_pres_title or not existing_emb.get('title'):
                    cmd.append(f"-XMP-dc:Title={title}")

            # DESCRIPTION
            description = image_item.image_data.get('description', '')
            if description:
                description = description.replace("x-default ", "").strip()
                if not do_pres_desc or not existing_emb.get('description'):
                    cmd.append(f"-XMP-dc:Description={description}")

            # RATING (XMP-xmp:Rating)
            rating = image_item.image_data.get('lr_rating') or image_item.image_data.get('rating')
            if rating is not None:
                try:
                    rating_int = int(rating)
                    if 1 <= rating_int <= 5:
                        if not do_pres_rate or existing_emb.get('rating') is None:
                            cmd.append(f"-XMP-xmp:Rating={rating_int}")
                except (ValueError, TypeError):
                    pass

            # COLOR LABEL (XMP-xmp:Label — standard Adobe/Lightroom)
            color_label = image_item.image_data.get('color_label', '') or ''
            if color_label:
                if not do_pres_color or not existing_emb.get('color_label'):
                    cmd.append(f"-XMP-xmp:Label={color_label}")

            # BIOCLIP HIERARCHICAL TAXONOMY → solo HierarchicalSubject (NON dc:Subject)
            bioclip_taxonomy_raw = image_item.image_data.get('bioclip_taxonomy', '')
            if bioclip_taxonomy_raw:
                try:
                    from embedding_generator import EmbeddingGenerator
                    taxonomy = json.loads(bioclip_taxonomy_raw) if isinstance(bioclip_taxonomy_raw, str) else bioclip_taxonomy_raw
                    if taxonomy and isinstance(taxonomy, list):
                        hierarchical_path = EmbeddingGenerator.build_hierarchical_taxonomy(taxonomy, prefix="AI|Taxonomy")
                        if hierarchical_path:
                            # Leggi HierarchicalSubject esistenti, preserva non-AI
                            existing_hier = []
                            try:
                                hier_result = subprocess.run(
                                    ['exiftool', '-j', '-XMP-lr:HierarchicalSubject', str(image_file)],
                                    capture_output=True, text=True, timeout=10
                                )
                                if hier_result.returncode == 0 and hier_result.stdout.strip():
                                    hier_data = json.loads(hier_result.stdout)
                                    if hier_data:
                                        hs = hier_data[0].get('HierarchicalSubject', [])
                                        if isinstance(hs, str):
                                            hs = [hs]
                                        existing_hier = [s for s in hs if not s.startswith('AI|Taxonomy')]
                            except Exception:
                                pass

                            # HierarchicalSubject: cancella ramo AI e riscrivi
                            cmd.append("-XMP-lr:HierarchicalSubject=")
                            for subject in existing_hier:
                                cmd.append(f"-XMP-lr:HierarchicalSubject+={subject}")
                            cmd.append(f"-XMP-lr:HierarchicalSubject+={hierarchical_path}")
                except Exception as e:
                    print(f"⚠️ Errore scrittura BioCLIP HierarchicalSubject embedded: {e}")

            # GERARCHIA GEOGRAFICA → HierarchicalSubject (solo GeOFF|, separato da AI|Taxonomy)
            geo_hierarchy = image_item.image_data.get('geo_hierarchy', '')
            if geo_hierarchy:
                try:
                    existing_hier_geo = []
                    try:
                        hier_result = subprocess.run(
                            ['exiftool', '-j', '-XMP-lr:HierarchicalSubject', str(image_file)],
                            capture_output=True, text=True, timeout=10
                        )
                        if hier_result.returncode == 0 and hier_result.stdout.strip():
                            hier_data = json.loads(hier_result.stdout)
                            if hier_data:
                                hs = hier_data[0].get('HierarchicalSubject', [])
                                if isinstance(hs, str):
                                    hs = [hs]
                                existing_hier_geo = [s for s in hs if not s.startswith('GeOFF|')]
                    except Exception:
                        pass
                    cmd.append("-XMP-lr:HierarchicalSubject=")
                    for subject in existing_hier_geo:
                        cmd.append(f"-XMP-lr:HierarchicalSubject+={subject}")
                    cmd.append(f"-XMP-lr:HierarchicalSubject+={geo_hierarchy}")
                except Exception as e:
                    print(f"⚠️ Errore scrittura Geo HierarchicalSubject embedded: {e}")

            cmd.append(str(image_file))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return True
            else:
                print(f"❌ ExifTool embedded errore: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ Errore scrittura XMP embedded: {e}")
            return False

    def _write_xmp_sidecar(self, image_file: Path, image_item, options: dict):
        """Scrive XMP sidecar compatibile con Lightroom"""
        try:

            import subprocess

            # Raccogli keywords
            keywords = []
            unified_tags_data = image_item.image_data.get('tags', '')
            if unified_tags_data:
                unified_tags = self._parse_tags(unified_tags_data)
                keywords.extend(unified_tags)
            keywords = list(dict.fromkeys(keywords))

            # Determina path XMP
            if options['path']['original']:
                sidecar_path = image_file.with_suffix('.xmp')
            else:
                single_dir = options['path']['single_dir']
                if not single_dir:
                    print(f"❌ Directory unica non specificata per {image_file.name}")
                    return False
                output_dir = Path(single_dir)
                if not output_dir.exists():
                    output_dir.mkdir(parents=True, exist_ok=True)
                sidecar_path = output_dir / f"{image_file.stem}.xmp"

            # Comportamento per campo — controllo indipendente
            do_merge_keywords = options['advanced'].get('xmp_merge_keywords', True)
            do_preserve_title = options['advanced'].get('xmp_preserve_title', True)
            do_preserve_description = options['advanced'].get('xmp_preserve_description', True)

            # Merge keywords o sostituzione
            final_keywords = []
            if do_merge_keywords and sidecar_path.exists():
                existing_keywords = self._read_existing_keywords_from_xmp(sidecar_path)
                existing_keywords = list(dict.fromkeys(existing_keywords))
                all_keywords = existing_keywords[:]
                for kw in keywords:
                    if kw not in all_keywords:
                        all_keywords.append(kw)
                final_keywords = all_keywords
            else:
                final_keywords = list(dict.fromkeys(keywords))

            # Azzera dc:Subject nel sidecar esistente prima di riscrivere
            # MAI cancellare il file: potrebbe contenere dati Lightroom/altri software non gestiti
            if sidecar_path.exists():
                try:
                    clear_cmd = ["exiftool", "-overwrite_original", "-XMP-dc:Subject=", str(sidecar_path)]
                    clear_result = subprocess.run(clear_cmd, capture_output=True, text=True, timeout=10)
                    if clear_result.returncode != 0:
                        print(f"❌ Errore pulizia Subject nel sidecar, export annullato per sicurezza: {clear_result.stderr}")
                        return False
                except Exception as clear_error:
                    print(f"❌ Errore ExifTool nel clear Subject, export annullato per sicurezza: {clear_error}")
                    return False

            cmd = ["exiftool", "-overwrite_original"]

            if final_keywords:
                for kw in final_keywords:
                    cmd.append(f"-XMP-dc:Subject+={kw}")

            # Comportamento per campo — tutti i flag
            do_preserve_rating = options['advanced'].get('xmp_preserve_rating', True)
            do_preserve_color_label = options['advanced'].get('xmp_preserve_color_label', True)

            # Leggi campi scalari esistenti nel sidecar se almeno un campo è in modalità preserva
            existing_scalar = {}
            any_preserve = (do_preserve_title or do_preserve_description
                            or do_preserve_rating or do_preserve_color_label)
            if any_preserve and sidecar_path.exists():
                existing_scalar = self._read_existing_scalar_fields_from_xmp(sidecar_path)

            # TITLE
            title = image_item.image_data.get('title', '') or ''
            if not title:
                title = image_item.image_data.get('filename', '').split('.')[0]
            if title:
                if not do_preserve_title or not existing_scalar.get('title'):
                    cmd.append(f"-XMP-dc:Title={title}")

            # DESCRIPTION
            description = image_item.image_data.get('description', '')
            if description:
                description = description.replace("x-default ", "").strip()
                if not do_preserve_description or not existing_scalar.get('description'):
                    cmd.append(f"-XMP-dc:Description={description}")

            # RATING (XMP-xmp:Rating)
            rating = image_item.image_data.get('lr_rating') or image_item.image_data.get('rating')
            if rating is not None:
                try:
                    rating_int = int(rating)
                    if 1 <= rating_int <= 5:
                        if not do_preserve_rating or existing_scalar.get('rating') is None:
                            cmd.append(f"-XMP-xmp:Rating={rating_int}")
                except (ValueError, TypeError):
                    pass

            # COLOR LABEL (XMP-xmp:Label — standard Adobe/Lightroom)
            color_label = image_item.image_data.get('color_label', '') or ''
            if color_label:
                if not do_preserve_color_label or not existing_scalar.get('color_label'):
                    cmd.append(f"-XMP-xmp:Label={color_label}")

            # BIOCLIP HIERARCHICAL TAXONOMY → HierarchicalSubject + dc:Subject
            bioclip_taxonomy_raw = image_item.image_data.get('bioclip_taxonomy', '')
            if bioclip_taxonomy_raw:
                try:
                    from embedding_generator import EmbeddingGenerator
                    taxonomy = json.loads(bioclip_taxonomy_raw) if isinstance(bioclip_taxonomy_raw, str) else bioclip_taxonomy_raw
                    if taxonomy and isinstance(taxonomy, list):
                        hierarchical_path = EmbeddingGenerator.build_hierarchical_taxonomy(taxonomy, prefix="AI|Taxonomy")
                        if hierarchical_path:
                            # Leggi HierarchicalSubject esistenti, preserva quelli non-AI
                            existing_hier = []
                            if sidecar_path.exists():
                                try:
                                    hier_result = subprocess.run(
                                        ['exiftool', '-j', '-XMP-lr:HierarchicalSubject', str(sidecar_path)],
                                        capture_output=True, text=True, timeout=10
                                    )
                                    if hier_result.returncode == 0 and hier_result.stdout.strip():
                                        hier_data = json.loads(hier_result.stdout)
                                        if hier_data:
                                            hs = hier_data[0].get('HierarchicalSubject', [])
                                            if isinstance(hs, str):
                                                hs = [hs]
                                            existing_hier = [s for s in hs if not s.startswith('AI|Taxonomy')]
                                except Exception:
                                    pass

                            # HierarchicalSubject: cancella ramo AI e riscrivi
                            # NON scrivere in dc:Subject: BioCLIP resta separato dai tag LLM/utente
                            cmd.append("-XMP-lr:HierarchicalSubject=")
                            for subject in existing_hier:
                                cmd.append(f"-XMP-lr:HierarchicalSubject+={subject}")
                            cmd.append(f"-XMP-lr:HierarchicalSubject+={hierarchical_path}")
                except Exception as e:
                    print(f"⚠️ Errore scrittura BioCLIP HierarchicalSubject: {e}")

            # GERARCHIA GEOGRAFICA → HierarchicalSubject sidecar (solo GeOFF|, separato da AI|Taxonomy)
            geo_hierarchy = image_item.image_data.get('geo_hierarchy', '')
            if geo_hierarchy:
                try:
                    existing_hier_geo = []
                    if sidecar_path.exists():
                        try:
                            hier_result = subprocess.run(
                                ['exiftool', '-j', '-XMP-lr:HierarchicalSubject', str(sidecar_path)],
                                capture_output=True, text=True, timeout=10
                            )
                            if hier_result.returncode == 0 and hier_result.stdout.strip():
                                hier_data = json.loads(hier_result.stdout)
                                if hier_data:
                                    hs = hier_data[0].get('HierarchicalSubject', [])
                                    if isinstance(hs, str):
                                        hs = [hs]
                                    existing_hier_geo = [s for s in hs if not s.startswith('GeOFF|')]
                        except Exception:
                            pass
                    cmd.append("-XMP-lr:HierarchicalSubject=")
                    for subject in existing_hier_geo:
                        cmd.append(f"-XMP-lr:HierarchicalSubject+={subject}")
                    cmd.append(f"-XMP-lr:HierarchicalSubject+={geo_hierarchy}")
                except Exception as e:
                    print(f"⚠️ Errore scrittura Geo HierarchicalSubject sidecar: {e}")

            cmd.append(str(sidecar_path))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                self._update_database_sync_state(image_file, 'PERFECT_SYNC')
                return True
            else:
                print(f"❌ ExifTool errore: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ Errore scrittura XMP Lightroom: {e}")
            return False

    def _update_database_sync_state(self, image_file: Path, new_state: str):
        """Aggiorna sync_state nel database dopo export XMP"""
        try:
            config = self._load_config()
            if not config:
                return
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])
        
            db_manager.cursor.execute(
               "UPDATE images SET sync_state = ? WHERE filepath = ?",
                (new_state, str(image_file))
            )
            db_manager.conn.commit()
            db_manager.close()

        except Exception as e:
            print(f"❌ Errore aggiornamento sync_state: {e}")

    def _read_existing_scalar_fields_from_xmp(self, xmp_path: Path) -> dict:
        """Legge Title, Description, Rating e Color Label dal sidecar per evitare sovrascritture."""
        result = {}
        if not xmp_path.exists():
            return result
        try:
            import subprocess, json
            cmd = [
                "exiftool", "-j",
                "-XMP-dc:Title", "-XMP-dc:Description",
                "-XMP-xmp:Rating", "-XMP-xmp:Label",
                str(xmp_path)
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout)
                if data:
                    title_raw = data[0].get('Title', '')
                    if isinstance(title_raw, dict):
                        title_raw = title_raw.get('x-default', '') or next(iter(title_raw.values()), '')
                    result['title'] = str(title_raw).strip() if title_raw else ''

                    desc_raw = data[0].get('Description', '')
                    if isinstance(desc_raw, dict):
                        desc_raw = desc_raw.get('x-default', '') or next(iter(desc_raw.values()), '')
                    result['description'] = str(desc_raw).strip() if desc_raw else ''

                    rating_raw = data[0].get('Rating', None)
                    if rating_raw is not None:
                        try:
                            result['rating'] = int(rating_raw)
                        except (ValueError, TypeError):
                            pass

                    label_raw = data[0].get('Label', '')
                    result['color_label'] = str(label_raw).strip() if label_raw else ''

        except Exception as e:
            print(f"⚠️ Errore lettura campi scalari da sidecar esistente: {e}")
        return result

    def _read_existing_keywords_from_xmp(self, xmp_path: Path) -> list:
        """Legge keywords esistenti da file XMP per merge intelligente"""
        try:
            if not xmp_path.exists():
                return []
            
            import subprocess
            
            # Usa ExifTool per leggere keywords esistenti
            cmd = ["exiftool", "-XMP-dc:Subject", "-j", str(xmp_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                print(f"⚠️ Errore lettura XMP esistente: {result.stderr}")
                return []
            
            # Parse JSON output di ExifTool
            import json
            data = json.loads(result.stdout)
            
            if not data or not isinstance(data, list) or len(data) == 0:
                return []
            
            # Estrai Subject (keywords)
            subjects = data[0].get('Subject', [])
            
            # Normalizza in lista se è stringa singola
            if isinstance(subjects, str):
                subjects = [subjects]
            elif not isinstance(subjects, list):
                subjects = []
            
            # FILTRA KEYWORDS MALFORMATI (con pipe o altri separatori)
            clean_keywords = []
            for keyword in subjects:
                if '|' in keyword:
                    print(f"🚫 Scartato keyword malformato: {keyword}")
                    continue
                elif keyword.strip():  # Aggiungi solo se non vuoto
                    clean_keywords.append(keyword.strip())
            
            return clean_keywords
            
        except Exception as e:
            print(f"❌ Errore lettura keywords XMP esistenti: {e}")
            return []

    def _copy_photos(self, image_items, options):
        """
        Copia foto originali nella directory di destinazione.

        Se copy_preserve_structure=True usa compute_common_roots/compute_dest_path
        per ricreare la struttura originale, gestendo foto da dischi diversi
        (Windows: C_drive/D_drive, macOS: /Volumes/<Nome>, Linux: /mnt/<nome>).

        Returns:
            tuple: (copy_count, copy_failed, copy_skipped)
        """
        single_dir = options['path']['single_dir']
        if not single_dir:
            return 0, 0, 0

        output_dir = Path(single_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        preserve_structure = options['format'].get('copy_preserve_structure', False)
        overwrite = options['format'].get('copy_overwrite', False)

        copy_count = 0
        copy_failed = 0
        copy_skipped = 0

        # Pre-calcola radici comuni per device se struttura attiva
        common_roots = {}
        if preserve_structure:
            common_roots = compute_common_roots(image_items)
            logger.debug(
                f"Struttura attiva: {len(common_roots)} device rilevati, "
                f"multi-disco={'Sì' if len(common_roots) > 1 else 'No'}"
            )

        progress = QProgressDialog(
            t("export.progress.copy_running"),
            t("export.progress.cancel"),
            0,
            len(image_items),
            self
        )
        progress.setWindowTitle(t("export.group.copy_photos"))
        progress.setModal(True)
        apply_popup_style(progress)
        progress.show()
        QApplication.processEvents()

        for i, image_item in enumerate(image_items):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            filename = image_item.image_data.get('filename', 'unknown')
            progress.setLabelText(t("export.progress.copy_label", filename=filename))
            QApplication.processEvents()

            try:
                source_path = Path(image_item.image_data.get('filepath', ''))
                if not source_path.exists():
                    logger.warning(f"File non trovato per copia: {source_path}")
                    copy_failed += 1
                    continue

                if preserve_structure:
                    # Calcola destinazione mantenendo la struttura originale
                    dest_path = compute_dest_path(source_path, output_dir, common_roots)
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                else:
                    # Copia piatta: nome file invariato nella directory di output
                    dest_path = output_dir / source_path.name

                # Gestione conflitti coerente in entrambe le modalità
                if dest_path.exists():
                    if not overwrite:
                        logger.debug(f"File già presente, saltato: {dest_path.name}")
                        copy_skipped += 1
                        continue
                    # overwrite=True: shutil.copy2 sovrascrive silenziosamente

                shutil.copy2(source_path, dest_path)
                copy_count += 1

            except Exception as e:
                logger.error(f"Errore copia {filename}: {e}")
                copy_failed += 1

        progress.setValue(len(image_items))
        progress.close()

        return copy_count, copy_failed, copy_skipped

    def _get_file_capabilities(self, filepath):
        """Analizza le capacità di scrittura metadata per tipo file"""
        ext = Path(filepath).suffix.lower()
        return {
            'can_embedded': ext in ['.jpg', '.jpeg', '.tif', '.tiff', '.dng'],
            'is_raw': ext in ['.cr2', '.nef', '.arw', '.raf', '.orf', '.rw2', '.cr3', '.rwl', '.srw', '.pef', '.3fr', '.fff', '.iiq', '.mos', '.mrw', '.x3f'],
            'is_dng': ext == '.dng',
            'extension': ext
        }

    def _load_config(self):
        """Carica configurazione"""
        try:
            config_path = Path('config_new.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ Errore caricamento config: {e}")
            return None

    # ------------------------------------------------------------------
    # PUBLIC API (usata dal controller)
    # ------------------------------------------------------------------

    def on_activated(self):
        if not self.main_window:
            return

        selected_items = self.main_window.get_selected_gallery_items()
        self.set_images(selected_items)

    def get_export_options(self) -> dict:
        """Restituisce opzioni export complete"""
        return {
            "format": {
                "sidecar": self.format_sidecar.isChecked(),
                "embedded": self.format_embedded.isChecked(),
                "dng_allow_embedded": self.dng_allow_embedded.isChecked(),
                "csv": self.format_csv.isChecked(),
                "copy": self.format_copy.isChecked(),
                "copy_preserve_structure": self.copy_preserve_structure.isChecked(),
                "copy_overwrite": self.copy_overwrite.isChecked(),
            },
            "path": {
                "original": self.path_original.isChecked(),
                "single": self.path_single.isChecked(),
                "single_dir": self.output_dir_input.text().strip(),
                "csv_dir": self.csv_dir_input.text().strip(),
            },
            "advanced": {
                "csv_include_gps": self.csv_include_gps.isChecked(),
                "xmp_merge_keywords": self.xmp_merge_keywords.isChecked(),
                "xmp_preserve_title": self.xmp_preserve_title.isChecked(),
                "xmp_preserve_description": self.xmp_preserve_description.isChecked(),
                "xmp_preserve_rating": self.xmp_preserve_rating.isChecked(),
                "xmp_preserve_color_label": self.xmp_preserve_color_label.isChecked(),
                "xmp_lr_compatibility": True,
            }
        }

    def _import_xmp_to_unified_tags(self, xmp_data, image_item):
        """Importa keywords XMP nel campo tag unificato"""
        try:
            # Keywords da XMP
            xmp_keywords = xmp_data.get('Keywords', [])
            if isinstance(xmp_keywords, str):
                xmp_keywords = [k.strip() for k in xmp_keywords.split(',') if k.strip()]
            elif not isinstance(xmp_keywords, list):
                xmp_keywords = []
            
            # Tag esistenti dal DB
            existing_tags = self._parse_tags(image_item.image_data.get('tags', ''))
            
            # Merge intelligente: mantieni tutti i tag unici
            combined_tags = list(set(existing_tags + xmp_keywords))
            
            # Aggiorna nel database
            if combined_tags:
                tags_json = json.dumps(combined_tags, ensure_ascii=False)
                return tags_json
            else:
                return None
                
        except Exception as e:
            print(f"Errore import XMP tag unificati: {e}")
            return None
