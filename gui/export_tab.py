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
from gui.gallery_widgets import apply_popup_style
from xmp_badge_manager import refresh_xmp_badges


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
        scroll_layout.addWidget(self._metadata_group())
        scroll_layout.addWidget(self._advanced_group())
        scroll_layout.addWidget(self._selection_group())
        scroll_layout.addWidget(self._export_group())

        scroll_layout.addStretch(1)

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
            self.selection_info.setText("📋 Nessuna immagine selezionata")
            self.export_btn.setEnabled(False)
        else:
            self.selection_info.setText(f"📋 {count} immagine/i selezionate per export")
            self.export_btn.setEnabled(True)



    # ------------------------------------------------------------------
    # EXPORT FORMAT
    # ------------------------------------------------------------------
    
    def _export_format_group(self) -> QGroupBox:
        box = QGroupBox("📄 Modalità Export (combinabili)")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        self.format_sidecar = QCheckBox("Scrivi sidecar XMP (.xmp)")
        self.format_sidecar.setToolTip("File separato accanto all'immagine - standard per RAW")

        self.format_embedded = QCheckBox("Scrivi metadati nel file (JPG/DNG)")
        self.format_embedded.setToolTip("Metadati dentro il file immagine stesso")

        self.format_csv = QCheckBox("Export CSV completo (tutti i campi DB)")
        self.format_csv.setToolTip("Tabella con tutti i metadati database inclusi EXIF")

        self.format_copy = QCheckBox("Copia foto originali")
        self.format_copy.setToolTip("Copia i file immagine nella directory di destinazione")

        self.format_sidecar.setChecked(True)

        # Copia foto richiede directory unica
        self.format_copy.toggled.connect(self._on_copy_toggled)
        # CSV toggle abilita/disabilita campo directory CSV
        self.format_csv.toggled.connect(self._on_csv_toggled)

        layout.addWidget(self.format_sidecar)
        layout.addWidget(self.format_embedded)
        layout.addWidget(self.format_csv)
        layout.addWidget(self.format_copy)

        return box

    def _on_copy_toggled(self, checked):
        """Quando copia foto attiva, forza directory unica"""
        if checked:
            self.path_single.setChecked(True)
            self.path_original.setEnabled(False)
        else:
            self.path_original.setEnabled(True)
    
    # ------------------------------------------------------------------
    # EXPORT PATH
    # ------------------------------------------------------------------
    
    def _export_path_group(self) -> QGroupBox:
        box = QGroupBox("📁 Destinazione Export")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        self.path_original = QRadioButton("Directory originali delle immagini")
        self.path_single = QRadioButton("Directory unica:")
        
        self.path_original.setChecked(True)
        
        self.path_group = QButtonGroup(self)
        self.path_group.addButton(self.path_original, 0)
        self.path_group.addButton(self.path_single, 1)
        
        layout.addWidget(self.path_original)
        
        # Single directory option with picker
        single_layout = QHBoxLayout()
        single_layout.addWidget(self.path_single)
        
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("Seleziona directory...")
        self.output_dir_input.setEnabled(False)
        
        self.browse_btn = QPushButton("📂")
        self.browse_btn.setMaximumWidth(40)
        self.browse_btn.setEnabled(False)
        self.browse_btn.clicked.connect(self._browse_output_dir)
        
        single_layout.addWidget(self.output_dir_input)
        single_layout.addWidget(self.browse_btn)
        layout.addLayout(single_layout)
        
        # Connect radio buttons to enable/disable controls
        self.path_original.toggled.connect(self._on_path_mode_changed)
        self.path_single.toggled.connect(self._on_path_mode_changed)
        
        # --- Directory CSV dedicata ---
        csv_dir_label = QLabel("Directory CSV:")
        self.csv_dir_input = QLineEdit()
        self.csv_dir_input.setPlaceholderText("Seleziona directory per CSV...")
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

        layout.addLayout(csv_dir_layout)

        # Info text
        info = QLabel("Directory originali: XMP accanto alle immagini (raccomandato per Lightroom)")
        info.setWordWrap(True)
        info.setStyleSheet("opacity: 0.7; font-size: 10px;")
        layout.addWidget(info)

        return box
    
    def _browse_output_dir(self):
        """Seleziona directory output"""
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Seleziona Directory Export",
            self.output_dir_input.text() or ""
        )
        if directory:
            self.output_dir_input.setText(directory)
    
    def _browse_csv_dir(self):
        """Seleziona directory output CSV"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Seleziona Directory CSV",
            self.csv_dir_input.text() or ""
        )
        if directory:
            self.csv_dir_input.setText(directory)

    def _on_csv_toggled(self, checked):
        """Abilita/disabilita campo directory CSV in base al checkbox CSV"""
        self.csv_dir_label.setEnabled(checked)
        self.csv_dir_input.setEnabled(checked)
        self.csv_browse_btn.setEnabled(checked)

    def _on_path_mode_changed(self):
        """Abilita/disabilita controlli directory in base a selezione"""
        single_mode = self.path_single.isChecked()
        self.output_dir_input.setEnabled(single_mode)
        self.browse_btn.setEnabled(single_mode)

    # ------------------------------------------------------------------
    # METADATA (existing)
    # ------------------------------------------------------------------

    def _metadata_group(self) -> QGroupBox:
        box = QGroupBox("Metadati XMP")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        self.meta_db = QCheckBox("Includi metadati dal database")
        self.meta_embedded = QCheckBox("Scrivi XMP embedded (se supportato)")
        self.meta_sidecar = QCheckBox("Scrivi XMP sidecar (.xmp)")
        
        # Opzione speciale per DNG
        self.dng_allow_embedded = QCheckBox("Consenti embedded per DNG (richiede conferma)")
        self.dng_allow_embedded.setChecked(False)
        self.dng_allow_embedded.setToolTip("Abilita scrittura metadati embedded nei file DNG")

        self.meta_db.setChecked(True)
        self.meta_sidecar.setChecked(True)

        layout.addWidget(self.meta_db)
        layout.addWidget(self.meta_embedded)
        layout.addWidget(self.meta_sidecar)
        layout.addWidget(self.dng_allow_embedded)

        note = QLabel(
            "Nota: per molti RAW la scrittura embedded può non essere supportata "
            "e verrà automaticamente usato il sidecar."
        )
        note.setWordWrap(True)
        note.setStyleSheet("opacity: 0.7;")
        layout.addWidget(note)

        return box

    # ------------------------------------------------------------------
    # ADVANCED
    # ------------------------------------------------------------------

    def _advanced_group(self) -> QGroupBox:
        box = QGroupBox("🔧 Opzioni Avanzate")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        # Sezione: Opzioni CSV
        csv_section = QGroupBox("📊 Export CSV")
        csv_layout = QVBoxLayout(csv_section)
        
        self.csv_include_gps = QCheckBox("Includi dati GPS completi")
        self.csv_include_gps.setChecked(True)
        
        csv_layout.addWidget(self.csv_include_gps)
        
        layout.addWidget(csv_section)

        # Sezione: Opzioni XMP
        xmp_section = QGroupBox("🏷️ Export XMP")
        xmp_layout = QVBoxLayout(xmp_section)
        
        self.xmp_preserve_existing = QCheckBox("Preserva metadati XMP esistenti")
        self.xmp_preserve_existing.setChecked(True)
        self.xmp_preserve_existing.setToolTip("Non sovrascrive metadati XMP già presenti")
        
        # Nota: Compatibilità Lightroom sempre attiva (standard integrato)
        note = QLabel("✓ Compatibilità Lightroom ottimale sempre attiva")
        note.setStyleSheet("color: gray; font-style: italic; font-size: 10px;")
        
        xmp_layout.addWidget(self.xmp_preserve_existing)
        xmp_layout.addWidget(note)
            
        layout.addWidget(xmp_section)

        # Sezione: Performance
        perf_section = QGroupBox("⚡ Performance")
        perf_layout = QVBoxLayout(perf_section)
        
        self.batch_processing = QCheckBox("Elaborazione batch (più veloce)")
        self.batch_processing.setChecked(True)
        self.batch_processing.setToolTip("Processa più file insieme, riduce I/O")
        
        self.verify_export = QCheckBox("Verifica integrità dopo export")
        self.verify_export.setChecked(False)
        self.verify_export.setToolTip("Rilegge i metadati scritti per verifica")
        
        for cb in [self.batch_processing, self.verify_export]:
            perf_layout.addWidget(cb)
            
        layout.addWidget(perf_section)

        # Sezione AI/Scoring RIMOSSA - Non necessaria per export standard

        return box

    # ------------------------------------------------------------------
    # SELECTION (Esistente)
    # ------------------------------------------------------------------

    def _selection_group(self) -> QGroupBox:
        box = QGroupBox("📂 Selezione")
        layout = QVBoxLayout(box)
    
        self.selection_info = QLabel("📋 Nessuna immagine selezionata")
        layout.addWidget(self.selection_info)
    
        return box

    # ------------------------------------------------------------------
    # EXPORT ACTION
    # ------------------------------------------------------------------

    def _export_group(self) -> QGroupBox:
        box = QGroupBox("🚀 Avvia Export")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        info_label = QLabel("Esporta foto e/o metadati (XMP, CSV)")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # Pulsante export
        self.export_btn = QPushButton("🚀 Avvia Export")
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
            QMessageBox.warning(self, "Errore", "Nessuna immagine selezionata!")
            return

        options = self.get_export_options()

        # Validazione: almeno un formato selezionato
        if not any([options['format']['sidecar'], options['format']['embedded'],
                     options['format']['csv'], options['format']['copy']]):
            QMessageBox.warning(self, "Errore", "Seleziona almeno un formato di export!")
            return

        # Validazione: directory unica richiesta
        if options['path']['single'] and not options['path']['single_dir']:
            QMessageBox.warning(self, "Errore", "Seleziona directory di output per l'opzione 'Directory unica'!")
            return

        if options['format']['copy'] and not options['path']['single_dir']:
            QMessageBox.warning(self, "Errore",
                "La copia foto richiede una directory di destinazione!\n"
                "Seleziona 'Directory unica' e specifica il percorso.")
            return

        # Validazione: directory CSV richiesta se CSV selezionato
        if options['format']['csv'] and not options['path']['csv_dir']:
            QMessageBox.warning(self, "Errore",
                "Seleziona una directory di destinazione per il file CSV!")
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
                export_types.append("Copia foto")

            location_msg = (
                "directory originali" if options['path']['original']
                else f"directory: {options['path']['single_dir']}"
            )

            reply = QMessageBox.question(
                self,
                "Conferma Export",
                f"Esportare {' + '.join(export_types)} per {len(self.images_to_export)} immagini?\n\n"
                f"📁 Destinazione: {location_msg}",
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
                    "Export XMP in corso...",
                    "Annulla",
                    0,
                    len(self.images_to_export),
                    self
                )
                progress.setWindowTitle("Export XMP Metadata")
                progress.setModal(True)
                apply_popup_style(progress)
                progress.show()
                QApplication.processEvents()

                for i, image_item in enumerate(self.images_to_export):
                    if progress.wasCanceled():
                        break

                    progress.setValue(i)
                    filename = image_item.image_data.get('filename', 'unknown')
                    progress.setLabelText(f"Export XMP: {filename}")
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
                            elif caps['is_dng'] and not options['metadata']['dng_allow_embedded']:
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
            if export_copy:
                copy_count, copy_failed = self._copy_photos(self.images_to_export, options)

            # --- Report finale ---
            try:
                report_parts = []
                if export_xmp and success_count > 0:
                    report_parts.append(f"✅ XMP creati: {success_count}")
                if export_xmp and failed_count > 0:
                    report_parts.append(f"❌ Errori XMP: {failed_count}")
                if export_xmp and skipped_count > 0:
                    report_parts.append(f"⚠️ File saltati (embedded non supportato): {skipped_count}")
                if export_csv and csv_success:
                    report_parts.append(f"✅ CSV creato")
                elif export_csv and not csv_success:
                    report_parts.append(f"❌ Errore CSV")
                if export_copy and copy_count > 0:
                    report_parts.append(f"✅ Foto copiate: {copy_count}")
                if export_copy and copy_failed > 0:
                    report_parts.append(f"❌ Errori copia: {copy_failed}")

                if not report_parts:
                    report_parts.append("❌ Nessun export completato")

                message = f"Export completato!\n\n📊 Risultati:\n{chr(10).join(report_parts)}"
                message += f"\n\n📁 Destinazione: {location_msg}"

                try:
                    QMessageBox.information(self, "Export Completato", message)
                except Exception as dialog_error:
                    print(f"❌ Errore dialog finale: {dialog_error}")

            except Exception as report_error:
                print(f"❌ Errore report finale: {report_error}")
                try:
                    QMessageBox.information(self, "Export", "Export completato con errori nel report.")
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
            QMessageBox.critical(self, "Errore Export", f"Errore durante export:\n{e}") 
    
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
            if not options['metadata']['db']:
                return False

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
            cmd = ["exiftool", "-overwrite_original"]

            if not options['advanced']['xmp_preserve_existing']:
                cmd.append("-XMP-dc:Subject=")

            if keywords:
                for kw in keywords:
                    cmd.append(f"-XMP-dc:Subject+={kw}")

            # TITLE
            title = image_item.image_data.get('title', '') or ''
            if not title:
                title = image_item.image_data.get('filename', '').split('.')[0]
            if title:
                cmd.append(f"-XMP-dc:Title={title}")

            # DESCRIPTION
            description = image_item.image_data.get('description', '')
            if description:
                cmd.append(f"-XMP-dc:Description={description}")

            # RATING
            rating = image_item.image_data.get('lr_rating') or image_item.image_data.get('rating')
            if rating is not None and 1 <= int(rating) <= 5:
                cmd.append(f"-XMP-xmp:Rating={int(rating)}")

            # BIOCLIP HIERARCHICAL TAXONOMY → HierarchicalSubject
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

                            cmd.append("-XMP-lr:HierarchicalSubject=")
                            for subject in existing_hier:
                                cmd.append(f"-XMP-lr:HierarchicalSubject+={subject}")
                            cmd.append(f"-XMP-lr:HierarchicalSubject+={hierarchical_path}")
                except Exception as e:
                    print(f"⚠️ Errore scrittura BioCLIP HierarchicalSubject embedded: {e}")

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
            if not options['metadata']['db']:
                return False

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

            # Merge keywords intelligente
            final_keywords = []
            if options['advanced']['xmp_preserve_existing'] and sidecar_path.exists():
                existing_keywords = self._read_existing_keywords_from_xmp(sidecar_path)
                existing_keywords = list(dict.fromkeys(existing_keywords))
                all_keywords = existing_keywords[:]
                for kw in keywords:
                    if kw not in all_keywords:
                        all_keywords.append(kw)
                final_keywords = all_keywords
            else:
                final_keywords = list(dict.fromkeys(keywords))

            # Riscrittura pulita se file XMP esistente
            if sidecar_path.exists():
                try:
                    clear_cmd = ["exiftool", "-overwrite_original", "-XMP-dc:Subject=", str(sidecar_path)]
                    clear_result = subprocess.run(clear_cmd, capture_output=True, text=True, timeout=10)
                    if clear_result.returncode != 0:
                        print(f"⚠️ Errore cancellazione keywords esistenti: {clear_result.stderr}")
                        try:
                            sidecar_path.unlink()
                        except Exception as delete_error:
                            print(f"❌ Impossibile eliminare XMP: {delete_error}")
                            return False
                except Exception as clear_error:
                    print(f"❌ Errore comando clear ExifTool: {clear_error}")
                    return False

            cmd = ["exiftool", "-overwrite_original"]

            if final_keywords:
                for kw in final_keywords:
                    cmd.append(f"-XMP-dc:Subject+={kw}")

            # TITLE
            title = image_item.image_data.get('title', '') or ''
            if not title:
                title = image_item.image_data.get('filename', '').split('.')[0]
            if title:
                cmd.append(f"-XMP-dc:Title={title}")

            # DESCRIPTION
            description = image_item.image_data.get('description', '')
            if description:
                description = description.replace("x-default ", "").strip()
                cmd.append(f"-XMP-dc:Description={description}")

            # RATING
            rating = image_item.image_data.get('lr_rating') or image_item.image_data.get('rating')
            if rating is not None and 1 <= int(rating) <= 5:
                cmd.append(f"-XMP-xmp:Rating={int(rating)}")

            # BIOCLIP HIERARCHICAL TAXONOMY → HierarchicalSubject
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

                            # Cancella e riscrivi HierarchicalSubject
                            cmd.append("-XMP-lr:HierarchicalSubject=")
                            for subject in existing_hier:
                                cmd.append(f"-XMP-lr:HierarchicalSubject+={subject}")
                            cmd.append(f"-XMP-lr:HierarchicalSubject+={hierarchical_path}")
                except Exception as e:
                    print(f"⚠️ Errore scrittura BioCLIP HierarchicalSubject: {e}")

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
        """Copia foto originali nella directory di destinazione"""
        single_dir = options['path']['single_dir']
        if not single_dir:
            return 0, 0

        output_dir = Path(single_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        copy_count = 0
        copy_failed = 0

        progress = QProgressDialog(
            "Copia foto in corso...",
            "Annulla",
            0,
            len(image_items),
            self
        )
        progress.setWindowTitle("Copia Foto")
        progress.setModal(True)
        apply_popup_style(progress)
        progress.show()
        QApplication.processEvents()

        for i, image_item in enumerate(image_items):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            filename = image_item.image_data.get('filename', 'unknown')
            progress.setLabelText(f"Copia: {filename}")
            QApplication.processEvents()

            try:
                source_path = Path(image_item.image_data.get('filepath', ''))
                if not source_path.exists():
                    print(f"❌ File non trovato per copia: {source_path}")
                    copy_failed += 1
                    continue

                stem = source_path.stem
                suffix = source_path.suffix
                dest_path = output_dir / f"{stem} Ofglry{suffix}"

                # Gestione conflitti nome (file con stesso nome da directory diverse)
                if dest_path.exists():
                    counter = 2
                    while dest_path.exists():
                        dest_path = output_dir / f"{stem} Ofglry_{counter}{suffix}"
                        counter += 1

                shutil.copy2(source_path, dest_path)
                copy_count += 1

            except Exception as e:
                print(f"❌ Errore copia {filename}: {e}")
                copy_failed += 1

        progress.setValue(len(image_items))
        progress.close()

        return copy_count, copy_failed

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
        """Restituisce opzioni export complete per workflow professionale"""
        return {
            "format": {
                "sidecar": self.format_sidecar.isChecked(),
                "embedded": self.format_embedded.isChecked(),
                "csv": self.format_csv.isChecked(),
                "copy": self.format_copy.isChecked(),
            },
            "path": {
                "original": self.path_original.isChecked(),
                "single": self.path_single.isChecked(),
                "single_dir": self.output_dir_input.text().strip(),
                "csv_dir": self.csv_dir_input.text().strip(),
            },
            "metadata": {
                "db": self.meta_db.isChecked(),
                "embedded": self.meta_embedded.isChecked(),
                "sidecar": self.meta_sidecar.isChecked(),
                "dng_allow_embedded": self.dng_allow_embedded.isChecked(),
            },
            "advanced": {
                # CSV options (semplificato)
                "csv_include_gps": self.csv_include_gps.isChecked(),
                # XMP options (semplificato - AI tags sempre inclusi nei tag unificati)
                "xmp_preserve_existing": self.xmp_preserve_existing.isChecked(),
                "xmp_lr_compatibility": True,  # Sempre attivo - standard integrato
                # Performance options
                "batch_processing": self.batch_processing.isChecked(),
                "verify_export": self.verify_export.isChecked(),
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
