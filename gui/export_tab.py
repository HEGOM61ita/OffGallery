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
        box = QGroupBox("📄 Modalità Export")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        self.format_sidecar = QRadioButton("Scrivi sidecar XMP (.xmp)")
        self.format_sidecar.setToolTip("File separato accanto all'immagine - standard per RAW")
        
        self.format_embedded = QRadioButton("Scrivi metadati nel file (JPG/DNG)")
        self.format_embedded.setToolTip("Metadati dentro il file immagine stesso")
        
        self.format_csv = QRadioButton("Export CSV completo (tutti i campi DB)") 
        self.format_csv.setToolTip("Tabella con tutti i metadati database inclusi EXIF")

        self.format_sidecar.setChecked(True)
        
        self.format_group = QButtonGroup(self)
        self.format_group.addButton(self.format_sidecar, 0)
        self.format_group.addButton(self.format_embedded, 1)
        self.format_group.addButton(self.format_csv, 2) 

        layout.addWidget(self.format_sidecar)
        layout.addWidget(self.format_embedded)
        layout.addWidget(self.format_csv)

        return box
    
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
        
        from PyQt6.QtWidgets import QFileDialog
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
        
        # Info text
        info = QLabel("Directory originali: XMP accanto alle immagini (raccomandato per Lightroom)")
        info.setWordWrap(True)
        info.setStyleSheet("opacity: 0.7; font-size: 10px;")
        layout.addWidget(info)

        return box
    
    def _browse_output_dir(self):
        """Seleziona directory output"""
        from PyQt6.QtWidgets import QFileDialog
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Seleziona Directory Export",
            self.output_dir_input.text() or ""
        )
        if directory:
            self.output_dir_input.setText(directory)
    
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
    # RAW
    # ------------------------------------------------------------------

    def _raw_group(self) -> QGroupBox:
        box = QGroupBox("Gestione file RAW")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        self.raw_export_preview = QRadioButton("Esporta preview JPEG")
        self.raw_export_processed = QRadioButton("Esporta RAW processato")
        self.raw_export_original = QRadioButton("Mantieni RAW originale")

        self.raw_export_preview.setChecked(True)

        layout.addWidget(self.raw_export_preview)
        layout.addWidget(self.raw_export_processed)
        layout.addWidget(self.raw_export_original)

        return box

    # ------------------------------------------------------------------
    # QUALITY
    # ------------------------------------------------------------------

    def _quality_group(self) -> QGroupBox:
        box = QGroupBox("Qualità e punteggi")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        self.include_aesthetic = QCheckBox("Includi punteggio estetico")
        self.include_technical = QCheckBox("Includi punteggio tecnico")

        self.include_aesthetic.setChecked(True)
        self.include_technical.setChecked(True)

        layout.addWidget(self.include_aesthetic)
        layout.addWidget(self.include_technical)

        note = QLabel(
            "Il punteggio tecnico su file RAW è calcolato sulla preview incorporata "
            "e non sul dato grezzo del sensore."
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
        box = QGroupBox("🚀 Export Metadata")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 10)

        info_label = QLabel("Esporta metadati in formato XMP e/o CSV")
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

    def _choose_output_dir(self):
        """Scelta directory output"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Seleziona Directory di Output",
            str(Path.home() / "Desktop"),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if dir_path:
            self.output_dir = Path(dir_path)
            self.output_dir_label.setText(f"Output: {dir_path}")
            self._update_export_button()

    def _update_export_button(self):
        """Aggiorna stato pulsante export"""
        has_images = len(self.images_to_export) > 0
        has_output = hasattr(self, 'output_dir') and self.output_dir is not None
        self.export_btn.setEnabled(has_images and has_output)

    def _set_default_output_dir(self):
        """Imposta directory default da config INPUT"""
        try:
            config = self._load_config()
            print(f"🔍 Config caricato: {config is not None}")
        
            if config and 'paths' in config:
                input_dir = Path(config['paths']['input_dir'])
                print(f"🔍 Input dir dal config: {input_dir}")
            
                if input_dir.exists():
                    self.output_dir = input_dir
                    self.output_dir_label.setText(f"Output: {input_dir} (default)")
                    if hasattr(self, 'export_btn'):
                    
                        self._update_export_button()
                    print(f"✅ Directory default impostata: {input_dir}")
                else:
                    self.output_dir_label.setText("Directory INPUT non trovata - scegli manualmente")
                    print(f"❌ Directory non esiste: {input_dir}")
            else:
                print("❌ Config o paths non trovati")
            
        except Exception as e:
            self.output_dir_label.setText("Errore config - scegli directory manualmente")
            print(f"❌ Errore caricamento directory default: {e}")

    def _do_export(self):
        """Export solo XMP sidecar - niente immagini"""
        print("🚀 Inizio _do_export_xmp_only")
    
        if not self.images_to_export:
            QMessageBox.warning(self, "Errore", "Nessuna immagine selezionata!")
            return

        # Validazione path options
        options = self.get_export_options()
        if options['path']['single'] and not options['path']['single_dir']:
            QMessageBox.warning(self, "Errore", "Seleziona directory di output per l'opzione 'Directory unica'!")
            return

        try:
            print(f"📋 Numero immagini da processare: {len(self.images_to_export)}")
            location = "directory originali" if options['path']['original'] else  options['path']['single_dir']
            print(f"📁 Destinazione: {location}")
        
            
            print(f"⚙️ Opzioni export: {options}")
        
            # Determina cosa esportare
            export_xmp = options['format']['sidecar'] or options['format']['embedded']
            export_csv = options['format']['csv']
            
            # Analisi preliminare dei file per statistiche
            file_analysis = {
                'total': len(self.images_to_export),
                'raw_count': 0,
                'dng_count': 0, 
                'jpeg_count': 0,
                'other_count': 0,
                'skipped_raw': 0  # RAW saltati per modalità embedded
            }
            
            for image_item in self.images_to_export:
                caps = self._get_file_capabilities(image_item.image_data.get('filepath', ''))
                if caps['is_raw'] and not caps['is_dng']:
                    file_analysis['raw_count'] += 1
                elif caps['is_dng']:
                    file_analysis['dng_count'] += 1
                elif caps['extension'] in ['.jpg', '.jpeg']:
                    file_analysis['jpeg_count'] += 1
                else:
                    file_analysis['other_count'] += 1
            
            print(f"📊 Analisi file: {file_analysis['raw_count']} RAW, {file_analysis['dng_count']} DNG, {file_analysis['jpeg_count']} JPEG, {file_analysis['other_count']} altri")
            
            # Avviso se modalità embedded con file RAW
            if options['format']['embedded'] and file_analysis['raw_count'] > 0:
                print(f"⚠️ ATTENZIONE: {file_analysis['raw_count']} file RAW non saranno processati (modalità embedded non supportata)")
            
            # Messaggio conferma dinamico
            export_types = []
            if export_xmp:
                if options['format']['sidecar']:
                    export_types.append("XMP sidecar")
                elif options['format']['embedded']:
                    export_types.append("XMP embedded")
            if export_csv:
                export_types.append("CSV")
            
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
                print("❌ Export annullato dall'utente")
                return

            print("✅ Utente ha confermato - inizio export")
            
            # Export CSV se richiesto (una volta sola)
            csv_success = True
            if export_csv:
                print("📊 Inizio export CSV...")
                csv_success = self._write_csv_export(self.images_to_export, options)
                if csv_success:
                    print("✅ Export CSV completato")
                else:
                    print("❌ Export CSV fallito")

            # Export XMP se richiesto (per ogni immagine)
            success_count = 0
            failed_count = 0
            skipped_count = 0
            
            if export_xmp:
                # Progress dialog
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
            
                print(f"🔄 Inizio loop XMP su {len(self.images_to_export)} immagini")
            
                for i, image_item in enumerate(self.images_to_export):
                    print(f"\n--- Immagine {i+1}/{len(self.images_to_export)} ---")
                
                    if progress.wasCanceled():
                        print("❌ Processo annullato dall'utente")
                        break

                    # Aggiorna progress
                    progress.setValue(i)
                    filename = image_item.image_data.get('filename', 'unknown')
                    progress.setLabelText(f"Export XMP: {filename}")
                    QApplication.processEvents()
                
                    print(f"🔍 Processing: {filename}")

                    try:
                        # Verifica path file
                        source_path = Path(image_item.image_data.get('filepath', ''))
                        print(f"   📂 Source path: {source_path}")
                    
                        if not source_path.exists():
                            print(f"   ❌ File non esiste: {source_path}")
                            failed_count += 1
                            continue
                
                        # Analisi capacità file
                        caps = self._get_file_capabilities(str(source_path))
                        
                        # Validazione tipo file vs modalità export
                        should_skip = False
                        skip_reason = ""
                        
                        if options['format']['embedded']:
                            # Modalità embedded
                            if caps['is_raw'] and not caps['is_dng']:
                                should_skip = True
                                skip_reason = f"RAW {caps['extension']} non supporta embedded"
                            elif caps['is_dng'] and not options['metadata']['dng_allow_embedded']:
                                should_skip = True
                                skip_reason = "DNG embedded non autorizzato"
                            elif not caps['can_embedded']:
                                should_skip = True
                                skip_reason = f"Formato {caps['extension']} non supporta embedded"
                        
                        if should_skip:
                            print(f"   ⚠️ SALTATO: {skip_reason}")
                            skipped_count += 1
                            file_analysis['skipped_raw'] += 1
                            continue

                        print(f"   ✅ File compatibile, inizio scrittura XMP...")
                    
                        # Scrivi XMP (sidecar o embedded in base alle opzioni)
                        if options['format']['sidecar']:
                            xmp_result = self._write_xmp_sidecar(source_path, image_item, options)
                        else:  # embedded
                            xmp_result = self._write_xmp_embedded(source_path, image_item, options)
                            
                        print(f"   🔧 Risultato scrittura XMP: {xmp_result}")
                    
                        if xmp_result:
                            success_count += 1
                            print(f"   ✅ XMP scritto con successo! Totale successi: {success_count}")
                        else:
                            failed_count += 1
                            print(f"   ❌ Scrittura XMP fallita! Totale errori: {failed_count}")
                        
                    except Exception as e:
                        failed_count += 1
                        print(f"   ❌ ECCEZIONE durante export XMP per {filename}: {e}")
                        import traceback
                        traceback.print_exc()

                # Fine loop XMP
                print(f"\n🏁 Fine processing XMP: {success_count} successi, {failed_count} errori, {skipped_count} saltati")
            
                # Chiudi progress dialog
                progress.setValue(len(self.images_to_export))
                progress.close()
            else:
                print("⏭️ Export XMP saltato (non richiesto)")

            try:
                # Report finale
                print("📊 Mostra report finale...")
                
                report_parts = []
                if export_xmp and success_count > 0:
                    report_parts.append(f"✅ XMP creati: {success_count}")
                if export_xmp and failed_count > 0:
                    report_parts.append(f"❌ Errori XMP: {failed_count}")
                if export_xmp and skipped_count > 0:
                    report_parts.append(f"⚠️ File saltati: {skipped_count}")
                if export_csv and csv_success:
                    report_parts.append(f"✅ CSV creato")
                elif export_csv and not csv_success:
                    report_parts.append(f"❌ Errore CSV")
                    
                if not report_parts:
                    report_parts.append("❌ Nessun export completato")
                
                # Aggiungi dettaglio sui file saltati se presenti
                skip_details = []
                if skipped_count > 0 and options['format']['embedded']:
                    if file_analysis.get('skipped_raw', 0) > 0:
                        skip_details.append(f"• {file_analysis['skipped_raw']} RAW non supportano embedded")
                
                location = (
                    "directory originali" if options['path']['original'] 
                    else options['path']['single_dir']
                )
                
                message = f"Export completato!\n\n📊 Risultati:\n{chr(10).join(report_parts)}"
                if skip_details:
                    message += f"\n\nℹ️ File saltati:\n{chr(10).join(skip_details)}"
                message += f"\n\n📁 Destinazione: {location}"
                
                print("📋 Mostro dialog finale...")
                
                # Mostra dialog in modo protetto
                try:
                    QMessageBox.information(
                        self,
                        "Export Completato", 
                        message
                    )
                    print("✅ Dialog finale mostrato e chiuso")
                except Exception as dialog_error:
                    print(f"❌ Errore dialog finale: {dialog_error}")
                
            except Exception as report_error:
                print(f"❌ Errore nella sezione report finale: {report_error}")
                import traceback
                traceback.print_exc()
                
                # Dialog di fallback minimale
                try:
                    QMessageBox.information(self, "Export", "Export completato con errori nel report.")
                except:
                    print("❌ Anche dialog di fallback fallito")
            
            # Emetti segnale completamento (separato e protetto)
            try:
                export_type = []
                if export_xmp: export_type.append("XMP")
                if export_csv: export_type.append("CSV")
                
                total_success = success_count if export_xmp else (1 if csv_success else 0)
                format_string = "+".join(export_type) if export_type else "NONE"
                
                print(f"📡 Emetto signal: export_completed({total_success}, '{format_string}')")
            
                self.export_completed.emit(total_success, format_string)
                print("✅ Signal emesso con successo")
                
                # Delay per permettere gestione signal completa
                #QApplication.processEvents()
                #import time
                #time.sleep(0.1)  # 100ms delay
                #print("✅ Export completato definitivamente")
                
            except Exception as signal_error:
                print(f"❌ ERRORE emissione signal: {signal_error}")
                import traceback
                traceback.print_exc()

        except Exception as e:
            print(f"❌ ERRORE GLOBALE in _do_export: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Errore Export", f"Errore durante export:\n{e}") 
    
    def _write_csv_export(self, image_items, options):
        """Esporta metadati completi in formato CSV per workflow fotografico professionale"""
        try:
            import csv
            from pathlib import Path
            
            # Determina path CSV
            if options['path']['original']:
                # CSV nella directory della prima immagine (o current dir)
                if image_items:
                    first_path = Path(image_items[0].image_data.get('filepath', ''))
                    csv_path = first_path.parent / f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                else:
                    csv_path = Path(f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            else:
                # CSV nella directory specificata
                single_dir = options['path']['single_dir']
                if not single_dir:
                    return False
                output_dir = Path(single_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                csv_path = output_dir / f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
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
            
            print(f"✅ CSV professionale esportato: {csv_path}")
            print(f"   📊 {len(headers)} campi, {len(image_items)} immagini")
            return True
            
        except Exception as e:
            print(f"❌ Errore export CSV: {e}")
            import traceback
            traceback.print_exc()
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
                print(f"⚠️ Metadati DB disabilitati per {image_file.name}")
                return False

            # Costruisci lista keywords unificata dai tag del database  
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
        
            # Rimuovi duplicati mantenendo ordine
            if keywords:
                keywords = list(dict.fromkeys(keywords))
        
            # Usa ExifTool per scrittura embedded
            import subprocess
        
            cmd = ["exiftool", "-overwrite_original"]
            
            # PRESERVA metadati esistenti se richiesto
            if options['advanced']['xmp_preserve_existing']:
                # Non cancella, aggiunge solo se non presente
                pass  
            else:
                # Cancella keywords esistenti
                cmd.append("-XMP-dc:Subject=")
        
            # KEYWORDS
            if keywords:
                for kw in keywords:
                    cmd.append(f"-XMP-dc:Subject+={kw}") 
            else:
                print(f"ℹ️ Nessun keyword per {image_file.name}, esporto metadati base")
        
            # TITLE (usa campo title dal DB, fallback al filename senza estensione)
            title = image_item.image_data.get('title', '') or ''
            if not title:
                title = image_item.image_data.get('filename', '').split('.')[0]
            if title:
                cmd.append(f"-XMP-dc:Title={title}")

            # DESCRIPTION
            description = image_item.image_data.get('description', '')
            if description:
                cmd.append(f"-XMP-dc:Description={description}")
        
            # RATING (prova lr_rating poi rating)
            rating = image_item.image_data.get('lr_rating') or image_item.image_data.get('rating')
            if rating is not None and 1 <= int(rating) <= 5:
                cmd.append(f"-XMP-xmp:Rating={int(rating)}")

            # Scrivi direttamente nel file originale
            cmd.append(str(image_file))
        
            print(f"🔧 ExifTool embedded command: {' '.join(cmd[:5])}... (+{len(cmd)-5} args)")
        
            # Esegui ExifTool
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
            if result.returncode == 0:
                print(f"✅ XMP embedded scritto: {image_file.name}")
                if keywords:
                    print(f"   🏷️ Keywords: {', '.join(keywords[:3])}{'...' if len(keywords) > 3 else ''}")
                if description:
                    print(f"   📖 Descrizione: {description[:50]}{'...' if len(description) > 50 else ''}")
                if rating:
                    print(f"   ⭐ Rating: {rating}/5")
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
            
            import subprocess  # Moved to top for clear operation
            
            # Raccogli keywords da tutte le fonti
            keywords = []
        
            # Tag unificati
            unified_tags_data = image_item.image_data.get('tags', '')
            if unified_tags_data:
                unified_tags = self._parse_tags(unified_tags_data)
                keywords.extend(unified_tags)
        
            # Rimuovi duplicati mantenendo ordine
            keywords = list(dict.fromkeys(keywords))
        
            # Usa ExifTool diretto per compatibilità Lightroom
            import subprocess
        
            # Determina path XMP in base alle opzioni
            if options['path']['original']:
                # Path originale: XMP accanto all'immagine
                sidecar_path = image_file.with_suffix('.xmp')
            else:
                # Directory unica: XMP nella directory specificata
                single_dir = options['path']['single_dir']
                if not single_dir:
                    print(f"❌ Directory unica non specificata per {image_file.name}")
                    return False
                    
                output_dir = Path(single_dir)
                if not output_dir.exists():
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                sidecar_path = output_dir / f"{image_file.stem}.xmp"
        
            # KEYWORDS — Merge intelligente (union, non concatenazione)
            final_keywords = []
            
            if options['advanced']['xmp_preserve_existing'] and sidecar_path.exists():
                # Leggi keywords esistenti dal file XMP (possibili modifiche manuali utente)
                existing_keywords = self._read_existing_keywords_from_xmp(sidecar_path)
                existing_keywords = list(dict.fromkeys(existing_keywords))  # Dedup esistenti
                
                # UNION intelligente: esistenti + nuovi dal DB, senza duplicati
                all_keywords = existing_keywords[:]  # Copia esistenti
                
                for kw in keywords:
                    if kw not in all_keywords:  # Aggiungi solo se non esiste già
                        all_keywords.append(kw)
                
                final_keywords = all_keywords
                
                added_count = len(final_keywords) - len(existing_keywords)
                print(f"📋 PRESERVE MODE: {len(existing_keywords)} esistenti + {added_count} nuovi dal DB = {len(final_keywords)} totali")
            else:
                # OVERWRITE: solo keywords dal DB
                final_keywords = list(dict.fromkeys(keywords))
                print(f"📋 OVERWRITE MODE: {len(final_keywords)} keywords dal DB")

            # FORZA RISCRITTURA PULITA: usa ExifTool per cancellare completamente tutti i Subject
            if sidecar_path.exists():
                print(f"🔄 File XMP esistente trovato: {sidecar_path.name}")
                
                # Usa ExifTool per cancellare completamente tutti i Subject esistenti
                try:
                    clear_cmd = ["exiftool", "-overwrite_original", "-XMP-dc:Subject=", str(sidecar_path)]
                    clear_result = subprocess.run(clear_cmd, capture_output=True, text=True, timeout=10)
                    
                    if clear_result.returncode == 0:
                        print("✅ Keywords esistenti cancellati con ExifTool")
                    else:
                        print(f"⚠️ Errore cancellazione keywords esistenti: {clear_result.stderr}")
                        
                        # Fallback: elimina fisicamente il file
                        try:
                            sidecar_path.unlink()
                            print(f"🗑️ File XMP eliminato fisicamente come fallback")
                        except Exception as delete_error:
                            print(f"❌ Impossibile eliminare XMP: {delete_error}")
                            return False
                except Exception as clear_error:
                    print(f"❌ Errore comando clear ExifTool: {clear_error}")
                    return False

            cmd = ["exiftool", "-overwrite_original"]
            
            # Scrivi keywords finali (ogni keyword come comando separato)           
            if final_keywords:
                for kw in final_keywords:
                    cmd.append(f"-XMP-dc:Subject+={kw}")
                print(f"🔧 Scrittura: {len(final_keywords)} keywords separati")
            else:
                print("🔧 Nessun keyword da scrivere")
            
            if not keywords:
                print(f"ℹ️ Nessun keyword per {image_file.name}, esporto metadati base")
        
            # TITLE (usa campo title dal DB, fallback al filename senza estensione)
            title = image_item.image_data.get('title', '') or ''
            if not title:
                title = image_item.image_data.get('filename', '').split('.')[0]
            if title:
                cmd.append(f"-XMP-dc:Title={title}")

            # DESCRIPTION (correggi prefisso x-default)
            description = image_item.image_data.get('description', '')
            if description:
                # Rimuovi prefisso "x-default " se presente nel contenuto
                description = description.replace("x-default ", "").strip()
                cmd.append(f"-XMP-dc:Description={description}")
        
            # RATING (prova lr_rating poi rating - solo XMP universale, no namespace proprietari)
            rating = image_item.image_data.get('lr_rating') or image_item.image_data.get('rating')
            if rating is not None and 1 <= int(rating) <= 5:
                cmd.append(f"-XMP-xmp:Rating={int(rating)}")

            # Verifica che ci sia almeno qualcosa da scrivere
            metadata_count = len(cmd) - 2  # Sottrai "exiftool" e "-overwrite_original"
            if metadata_count == 1:  # Solo il filepath
                print(f"ℹ️ Scrivo XMP base per {image_file.name} (filename: {title})")
            elif metadata_count > 1:
                content_types = []
                if keywords: content_types.append(f"{len(keywords)} keywords")
                if description: content_types.append("descrizione")
                if rating: content_types.append(f"rating {rating}")
                print(f"📝 Scrivo XMP per {image_file.name}: {', '.join(content_types)}")
        
            cmd.append(str(sidecar_path))
        
            print(f"🔧 ExifTool command: {' '.join(cmd[:5])}... (+{len(cmd)-5} args)")
        
            # Esegui ExifTool
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
            if result.returncode == 0:
                print(f"✅ XMP scritto: {sidecar_path.name}")
                if keywords:
                    print(f"   🏷️ Keywords: {', '.join(keywords[:3])}{'...' if len(keywords) > 3 else ''}")
                if description:
                    print(f"   📖 Descrizione: {description[:50]}{'...' if len(description) > 50 else ''}")
                if rating:
                    print(f"   ⭐ Rating: {rating}/5")
                self._debug_database_sync(image_file)
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
            print(f"✅ Database sync_state aggiornato: {new_state}")
        
        except Exception as e:
            print(f"❌ Errore aggiornamento sync_state: {e}")

    def _debug_database_sync(self, image_file: Path):
        """Debug: verifica stato nel database"""
        try:
            config = self._load_config()
            if not config:
                return
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])
        
            # Cerca per filepath
            cursor = db_manager.cursor.execute(
                "SELECT id, filename, filepath, sync_state FROM images WHERE filepath = ? OR filename = ?",
                (str(image_file), image_file.name)
            )
            results = cursor.fetchall()
        
            print(f"🔍 Debug database per {image_file.name}:")
            for row in results:
                print(f"   ID: {row[0]}, Filename: {row[1]}")
                print(f"   Filepath: {row[2]}")
                print(f"   Sync_state: {row[3]}")
            
            db_manager.close()
        
        except Exception as e:
            print(f"❌ Errore debug database: {e}")

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
            
            print(f"📖 Keywords esistenti validi: {len(clean_keywords)} (scartati {len(subjects) - len(clean_keywords)} malformati)")
            return clean_keywords
            
        except Exception as e:
            print(f"❌ Errore lettura keywords XMP esistenti: {e}")
            return []

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
            },
            "path": {
                "original": self.path_original.isChecked(),
                "single": self.path_single.isChecked(),
                "single_dir": self.output_dir_input.text().strip(),
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
