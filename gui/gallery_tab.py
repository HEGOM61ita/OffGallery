"""
Gallery Tab v3 - Visualizzazione risultati a griglia + XMP Sync handlers
Logica principale: ricerca, BioCLIP, gestione tag, XMP Sync
"""

from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QPushButton, QMessageBox,
    QApplication, QProgressDialog, QSizePolicy, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
import json
import yaml
from queue import Queue

from xmp_badge_manager import refresh_xmp_badges

# Import componenti UI dal modulo widgets
from gui.gallery_widgets import (
    ImageCard, FlowLayout, UserTagDialog, RemoveTagDialog, LLMTagDialog, COLORS,
    apply_popup_style
)

# Import XMP Manager condiviso
try:
    from xmp_manager_extended import XMPManagerExtended
    XMP_SUPPORT_AVAILABLE = True
except ImportError:
    XMP_SUPPORT_AVAILABLE = False


class LightweightXMPChecker(QThread):
    """Threading Qt-compatible per XMP sync check"""
    
    card_processed = pyqtSignal(object)  # Segnale per aggiornare UI
    
    def __init__(self, gallery_tab):
        super().__init__()
        self.gallery = gallery_tab
        self.xmp_queue = Queue()
        self.checked_cards = set()
        self.running = True
        
    def request_xmp_check(self, cards):
        """Richiede XMP check su carte non ancora controllate"""
        new_cards = [c for c in cards if id(c) not in self.checked_cards]  # Tutte
        if not new_cards:
            return
            
        for card in new_cards:
            self.checked_cards.add(id(card))
            self.xmp_queue.put(card)
            
        if not self.isRunning():
            self.start()
    
    def run(self):
        """Thread Qt principale - processing sequenziale"""
        while self.running:
            try:
                card = self.xmp_queue.get(timeout=2)
                if card and hasattr(card, 'filepath') and card.filepath:
                    if hasattr(card, '_xmp_processing'):
                        continue
                    card._xmp_processing = True
                
                    # Emetti segnale e aspetta che venga processato
                    self.card_processed.emit(card)
                
                    # Aspetta che il main thread completi prima di continuare
                    self.msleep(300)  # 300ms per permettere refresh completo
                
            except:
                break

    def stop(self):
        self.running = False
        self.quit()
        self.wait()

class ViewportXMPManager:
    """Gestisce XMP check solo per card visibili"""
    def enable_viewport_checking(self):
        """Abilita controllo viewport + check automatico post-display"""
        if hasattr(self.gallery, 'scroll_area'):
            scroll_bar = self.gallery.scroll_area.verticalScrollBar()
            scroll_bar.valueChanged.connect(self._on_scroll)
        
            # CHECK AUTOMATICO dopo che display_results è completato
            QTimer.singleShot(500, self._force_initial_check)  # 1 secondo dopo apertura
        else:
            pass
    
    def __init__(self, gallery_tab):
        self.gallery = gallery_tab
        self.xmp_checker = LightweightXMPChecker(gallery_tab)
        # Collega segnale per aggiornare UI
        self.xmp_checker.card_processed.connect(self._process_card_ui)
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self._check_viewport_xmp)
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.setSingleShot(True)
        
    def _process_card_ui(self, card):
        """Aggiorna UI nel main thread"""
        try:
            card.refresh_xmp_state()      #ATTENZIONE DA QUI DIPENDE IL RICALCOLO BADGE
        finally:
            if hasattr(card, '_xmp_processing'):
                delattr(card, '_xmp_processing')

    def _force_initial_check(self):
        """Check iniziale XMP per le prime card visibili"""
        try:
            if hasattr(self.gallery, 'cards') and self.gallery.cards:
                test_cards = self.gallery.cards[:3]
                self.xmp_checker.request_xmp_check(test_cards)
        except Exception as e:
            print(f"Errore force check XMP: {e}")
    
    def _on_scroll(self):
        """Debounced scroll handler"""
        self.scroll_timer.start(800)  # 800ms di pausa
    
    def _check_viewport_xmp(self):
        """Trova card visibili e richiede XMP check"""
        try:
            visible_cards = self._get_visible_cards()
            if visible_cards:
                self.xmp_checker.request_xmp_check(visible_cards)
        except Exception as e:
            print(f"Error viewport XMP check: {e}")
    
    def _get_visible_cards(self):
        """Calcola card attualmente visibili - versione semplificata"""
        if not hasattr(self.gallery, 'cards'):
            return []
    
        # Strategia semplice: restituisce TUTTE le cards visibili
        # Il FlowLayout rende difficile calcolare viewport preciso
        visible_cards = []
        for card in self.gallery.cards:
            try:
                if card.isVisible():
                    visible_cards.append(card)
            except:
                continue
    
        return visible_cards
#----------------------------------------------------------------


class GalleryTab(QWidget):
    """Tab gallery con layout a griglia + XMP Sync"""
    
    def __init__(self, parent=None, ai_models=None):
        super().__init__(parent)
        self.parent_window = parent
        self.ai_models = ai_models  # Modelli centralizzati
        self.current_results = []
        self.selected_items = []
        self.config_path = Path('config_new.yaml')
        self.cards = []
        # XMP Manager condiviso per tutte le card (AGGIUNGI QUESTA RIGA)
        self.shared_xmp_manager = XMPManagerExtended() if XMP_SUPPORT_AVAILABLE else None               
        # Imposta policy resize
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        
        # Inizializza viewport XMP manager
        self.viewport_xmp_manager = ViewportXMPManager(self)

        # Inizializza viewport XMP manager
        self.viewport_xmp_manager = ViewportXMPManager(self)
        
        self.init_ui()

    def _check_xmp_sync(self):
        """Avvia scansione XMP e collega aggiornamento automatico"""
        if not XMP_SUPPORT_AVAILABLE:
            return

        # Prendi solo le card attualmente a schermo
        visible_cards = [card for card in self.cards if card.isVisible()]
        if not visible_cards:
            return

        if not hasattr(self, 'xmp_checker') or not self.xmp_checker.isRunning():
            self.xmp_checker = LightweightXMPChecker(self)
            
            # Colleghiamo il segnale alla funzione di refresh della card
            # Usiamo un metodo diretto per evitare errori di riferimento
            self.xmp_checker.card_processed.connect(lambda card: card.refresh_xmp_state())
            
            self.xmp_checker.request_xmp_check(visible_cards)
            self.xmp_checker.start()
        else:
            self.xmp_checker.request_xmp_check(visible_cards)

    def _handle_card_xmp_updated(self, card):
        """Il pezzo mancante che aggiorna la card quando il thread finisce"""
        if card:
            # Chiama il metodo di refresh che abbiamo appena aggiornato in gallery_widgets
            card.refresh_xmp_state()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Stile generale
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS['grafite']};
            }}
            QPushButton {{
                background-color: {COLORS['blu_petrolio']};
                color: {COLORS['grigio_chiaro']};
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['blu_petrolio_light']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['grafite_light']};
                color: {COLORS['grigio_medio']};
            }}
        """)
        
        # Barra azioni
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(10, 8, 10, 8)
        
        self.count_label = QLabel("Nessun risultato")
        self.count_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {COLORS['grigio_chiaro']};")
        action_bar.addWidget(self.count_label)
        
        self.selection_label = QLabel("")
        self.selection_label.setStyleSheet(f"font-size: 11px; color: {COLORS['blu_petrolio_light']};")
        action_bar.addWidget(self.selection_label)
        
        action_bar.addStretch()

        # Ordinamento risultati
        sort_label = QLabel("Ordina:")
        sort_label.setStyleSheet(f"font-size: 11px; color: {COLORS['grigio_medio']};")
        action_bar.addWidget(sort_label)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems([
            "Rilevanza",
            "Data scatto",
            "Nome file",
            "Rating",
            "Score estetico",
            "Score tecnico",
            "Score composito"
        ])
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['grafite_light']};
                color: {COLORS['grigio_chiaro']};
                border: 1px solid {COLORS['grigio_medio']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                min-width: 120px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['grafite_light']};
                color: {COLORS['grigio_chiaro']};
                selection-background-color: {COLORS['blu_petrolio']};
            }}
        """)
        self.sort_combo.currentIndexChanged.connect(self._apply_sort)
        action_bar.addWidget(self.sort_combo)

        self.sort_dir_btn = QPushButton("↓")
        self.sort_dir_btn.setToolTip("Decrescente")
        self.sort_dir_btn.setFixedWidth(30)
        self.sort_dir_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['grafite_light']};
                color: {COLORS['grigio_chiaro']};
                border: 1px solid {COLORS['grigio_medio']};
                border-radius: 4px;
                padding: 4px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['blu_petrolio']};
            }}
        """)
        self.sort_dir_btn.clicked.connect(self._toggle_sort_direction)
        action_bar.addWidget(self.sort_dir_btn)

        self._sort_descending = True
        self._original_results = []

        self.select_all_btn = QPushButton("✓ Tutti")
        self.select_all_btn.clicked.connect(self.select_all)
        self.select_all_btn.setEnabled(False)
        action_bar.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("✗ Nessuno")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        self.deselect_all_btn.setEnabled(False)
        action_bar.addWidget(self.deselect_all_btn)
        
        layout.addLayout(action_bar)
        
        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {COLORS['grafite']};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['grafite']};
                width: 12px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['grafite_light']};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['blu_petrolio']};
            }}
        """)
        
        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet(f"background-color: {COLORS['grafite']};")
        self.scroll_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.flow_layout = FlowLayout()
        self.scroll_widget.setLayout(self.flow_layout)
        
        self.scroll_area.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll_area)
        # Abilita controllo viewport XMP dopo setup UI
        self.viewport_xmp_manager.enable_viewport_checking()
     
    def get_selected_images(self):
        """Recupera la lista delle immagini selezionate nella gallery"""
        return [card for card in self.cards if card.is_selected()]   
    
    def resizeEvent(self, event):
        """Ricalcola layout quando la finestra cambia dimensione"""
        super().resizeEvent(event)
        if self.cards:
            QTimer.singleShot(50, self._do_relayout)
    
    def _do_relayout(self):
        # Forza il ricalcolo del layout
        self.flow_layout.invalidate()
        self.flow_layout.activate()

    def _toggle_sort_direction(self):
        """Inverte la direzione di ordinamento"""
        self._sort_descending = not self._sort_descending
        if self._sort_descending:
            self.sort_dir_btn.setText("↓")
            self.sort_dir_btn.setToolTip("Decrescente")
        else:
            self.sort_dir_btn.setText("↑")
            self.sort_dir_btn.setToolTip("Crescente")
        self._apply_sort()

    def _apply_sort(self):
        """Riordina le card nel layout SENZA ricrearle (preserva badge XMP)"""
        if not self.cards:
            return

        idx = self.sort_combo.currentIndex()
        reverse = self._sort_descending

        # Costruisci lista card ordinata
        if idx == 0:
            # Rilevanza: ripristina ordine originale
            order_map = {id(img): i for i, img in enumerate(self._original_results)}
            sorted_cards = sorted(self.cards, key=lambda c: order_map.get(id(c.image_data), 0))
            if not reverse:
                sorted_cards = list(reversed(sorted_cards))
        else:
            # Funzioni di ordinamento per campo
            def _date_key(card):
                img = card.image_data
                return (img.get('datetime_original')
                        or img.get('datetime_digitized')
                        or img.get('datetime_modified')
                        or img.get('processed_date')
                        or '')

            def _composite_key(card):
                img = card.image_data
                ae = img.get('aesthetic_score') or 0
                te = img.get('technical_score') or 0
                return ae * 0.7 + te * 0.3

            sort_map = {
                1: _date_key,
                2: lambda c: (c.image_data.get('filename') or '').lower(),
                3: lambda c: c.image_data.get('lr_rating') or 0,
                4: lambda c: c.image_data.get('aesthetic_score') or 0,
                5: lambda c: c.image_data.get('technical_score') or 0,
                6: _composite_key,
            }

            key_fn = sort_map.get(idx)
            if key_fn is None:
                return
            sorted_cards = sorted(self.cards, key=key_fn, reverse=reverse)

        # Riordina _items nel FlowLayout senza distruggere i widget
        item_map = {}
        for item in self.flow_layout._items:
            w = item.widget()
            if w:
                item_map[id(w)] = item

        new_items = []
        for card in sorted_cards:
            item = item_map.get(id(card))
            if item:
                new_items.append(item)

        self.flow_layout._items = new_items
        self.cards = sorted_cards
        self.current_results = [c.image_data for c in sorted_cards]

        # Ricalcola geometria senza ricreare widget
        self.flow_layout.invalidate()
        self.flow_layout.activate()
        QTimer.singleShot(10, self._do_relayout)

        # Accoda al worker XMP le card senza badge (ora potrebbero essere visibili)
        uncached = [c for c in sorted_cards if getattr(c, '_xmp_state_cache', None) is None]
        if uncached:
            QTimer.singleShot(100, lambda: refresh_xmp_badges(uncached, "sort_reorder"))

    def display_results(self, results):
        """Mostra risultati come griglia di card"""
        self.flow_layout.clear_items()
        self.cards.clear()
        self.selected_items.clear()

        self.current_results = results
        self._original_results = list(results)
        # Reset ordinamento a "Rilevanza" senza triggerare _apply_sort
        self.sort_combo.blockSignals(True)
        self.sort_combo.setCurrentIndex(0)
        self.sort_combo.blockSignals(False)
        count = len(results)
        import time
        start_time = time.time()
        
        self.count_label.setText(f"{count} immagini" if count > 0 else "Nessun risultato")
        self.selection_label.setText("")
        
        has_results = count > 0
        self.select_all_btn.setEnabled(has_results)
        self.deselect_all_btn.setEnabled(False)
        
        if count == 0:
            no_results = QLabel("Nessun risultato trovato")
            no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_results.setStyleSheet(f"color: {COLORS['grigio_medio']}; font-size: 14px; padding: 50px;")
            self.flow_layout.addWidget(no_results)
            return
        
        for image_data in results:
            card = ImageCard(image_data, parent=self) 
            card.selection_changed.connect(self._on_item_selection_changed)
            card.find_similar_requested.connect(self.find_similar)
            card.bioclip_requested.connect(self.run_bioclip_batch)
            card.llm_tagging_requested.connect(self.run_llm_tagging_batch)
            # Connetti segnali XMP Sync
            
            self.cards.append(card)
            self.flow_layout.addWidget(card)
        
        QTimer.singleShot(10, self._do_relayout)
               
        # Refresh badge XMP per tutte le card caricate  
        QTimer.singleShot(100, lambda: refresh_xmp_badges(self.cards, "gallery_loaded"))

        # Mantieni il check viewport esistente
        QTimer.singleShot(1500, lambda: self.viewport_xmp_manager._check_viewport_xmp())
    
    def _on_item_selection_changed(self, item, selected):
        if selected:
            if item not in self.selected_items:
                self.selected_items.append(item)
        else:
            if item in self.selected_items:
                self.selected_items.remove(item)
        self._update_selection_ui()
    
    def _update_selection_ui(self):
        count = len(self.selected_items)
        if count > 0:
            self.selection_label.setText(f"({count} selez.)")
            self.deselect_all_btn.setEnabled(True)
        else:
            self.selection_label.setText("")
            self.deselect_all_btn.setEnabled(False)
    
    def select_all(self):
        for card in self.cards:
            card.set_selected(True)
    
    def deselect_all(self):
        # Crea copia della lista prima di iterare (evita mutation durante ciclo)
        for item in list(self.selected_items):
            item.set_selected(False)
    
    def _reload_sync_states_from_db(self):
        """Ricarica sync_state dal database per tutti i current_results"""
        try:
            config = self._load_config()
            if not config:
                return
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])
            
            # Ricarica sync_state per tutte le immagini
            for image_data in self.current_results:
                image_id = image_data.get('id')
                if image_id:
                    db_manager.cursor.execute(
                        "SELECT sync_state FROM images WHERE id = ?",
                        (image_id,)
                    )
                    row = db_manager.cursor.fetchone()
                    if row:
                        image_data['sync_state'] = row[0]
            
            db_manager.close()
        except Exception as e:
            print(f"Errore reload sync_states: {e}")
    
    def _update_sync_states_batch(self, updates_batch):
        """Aggiorna sync_state nel DB per batch di immagini"""
        try:
            config = self._load_config()
            if not config:
                return
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])
            
            # Aggiorna DB
            for image_id, new_state in updates_batch:
                db_manager.cursor.execute(
                    "UPDATE images SET sync_state = ? WHERE id = ?",
                    (new_state, image_id)
                )
            
            db_manager.conn.commit()
            db_manager.close()
            
        except Exception as e:
            print(f"Errore aggiornamento DB sync_states: {e}")
    
    def _refresh_gallery_sync_states(self):
        """Aggiorna indicatori sync state nelle card gallery"""
        try:
            # Aggiorna tutte le card con i nuovi sync_state
            for card in self.cards:
                # Trova i dati aggiornati in current_results
                for image_data in self.current_results:
                    if image_data['id'] == card.image_id:
                        # Aggiorna sync_state nella card
                        new_sync_state = image_data.get('sync_state', 'NO_XMP')
                        card.update_sync_state(new_sync_state)
                        break
            
        except Exception as e:
            print(f"Errore refresh gallery sync states: {e}")

   
    def find_similar(self, item):
        """Trova immagini simili con DINOv2"""
        try:
            config = self._load_config()
            if not config:
                return
        
            # FIXED: Usa percorso config corretto
            threshold = config.get('embedding', {}).get('models', {}).get('dinov2', {}).get('similarity_threshold', 0.3)
            max_results = config.get('similarity', {}).get('max_results', 20)
            
            progress = QProgressDialog(self)
            progress.setWindowTitle("🔍 Ricerca Immagini Simili")
            progress.setLabelText("Caricamento embedding di riferimento...")
            progress.setCancelButtonText("Annulla")
            progress.setMinimumWidth(400)
            progress.setMinimumDuration(0)
            progress.setRange(0, 0)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            apply_popup_style(progress)
            progress.show()
            QApplication.processEvents()
        
            from db_manager_new import DatabaseManager
            import numpy as np
            import pickle
        
            db_manager = DatabaseManager(config['paths']['database'])
        
            ref_id = item.image_id
            db_manager.cursor.execute(
                "SELECT dinov2_embedding FROM images WHERE id = ?", (ref_id,)
            )
            row = db_manager.cursor.fetchone()
        
            if not row or not row[0]:
                progress.close()
                QMessageBox.warning(self, "Errore", "Immagine senza embedding DINOv2")
                db_manager.close()
                return
        
            try:
                # Prova pickle prima
                ref_embedding = pickle.loads(row[0])
            except:
                try:
                    # Se pickle fallisce, prova frombuffer
                    ref_embedding = np.frombuffer(row[0], dtype=np.float32)
                except Exception as e:
                    print(f"Errore deserializzazione embedding: {e}")
                    progress.close()
                    db_manager.close()
                    return
        
            ref_norm = ref_embedding / np.linalg.norm(ref_embedding)
        
            progress.setLabelText("Confronto con database...")
            QApplication.processEvents()
        
            db_manager.cursor.execute(
                "SELECT * FROM images WHERE dinov2_embedding IS NOT NULL AND id != ?",
                (ref_id,)
            )
            columns = [desc[0] for desc in db_manager.cursor.description]
            all_rows = db_manager.cursor.fetchall()
            
            progress.setRange(0, len(all_rows))
            progress.setLabelText(f"Analisi {len(all_rows)} immagini...")
            
            results = []
            for i, row in enumerate(all_rows):
                if progress.wasCanceled():
                    db_manager.close()
                    return
                
                progress.setValue(i)
                QApplication.processEvents()
                
                image_data = dict(zip(columns, row))
                emb_blob = image_data.get('dinov2_embedding')
                
                if not emb_blob:
                    continue
                
                try:
                    img_embedding = pickle.loads(emb_blob)
                    img_norm = img_embedding / np.linalg.norm(img_embedding)
                    similarity = float(np.dot(ref_norm, img_norm))
                    
                    if similarity >= threshold:
                        image_data['similarity_score'] = similarity
                        results.append(image_data)
                except Exception as e:
                    print(f"Errore deserializzazione embedding: {e}")
                    continue
                
            
            progress.close()
            db_manager.close()
            
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            results = results[:max_results]
            
            if results:
                self.display_results(results)
                if self.parent_window:
                    self.parent_window.update_status(f"Trovate {len(results)} immagini simili")
            else:
                QMessageBox.information(self, "Risultato", f"Nessuna immagine simile trovata (soglia: {threshold:.2f})")
        
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore ricerca simili:\n{e}")
            import traceback
            traceback.print_exc()
    
    def run_bioclip_batch(self, items):
        """Esegui BioCLIP su batch di immagini"""
        try:
            config = self._load_config()
            if not config:
                return
            
            # NOTA: Rimuovo controllo flag enabled - gallery permette sempre BioCLIP
            
            progress = QProgressDialog(self)
            progress.setWindowTitle("🌿 Classificazione BioCLIP")
            progress.setLabelText("Caricamento modello BioCLIP TreeOfLife...\n\nIl primo avvio può richiedere alcuni secondi.")
            progress.setCancelButtonText("Annulla")
            progress.setMinimumWidth(450)
            progress.setMinimumDuration(0)
            progress.setRange(0, len(items) + 1)
            progress.setValue(0)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            apply_popup_style(progress)
            progress.show()
            
            for _ in range(5):
                QApplication.processEvents()
            
            from db_manager_new import DatabaseManager

            if self.ai_models and 'embedding_generator' in self.ai_models:
                embedding_gen = self.ai_models['embedding_generator']
            else:
                from embedding_generator import EmbeddingGenerator
                if self.ai_models and 'embedding_generator' in self.ai_models:
                    embedding_gen = self.ai_models['embedding_generator']
                else:
                    embedding_gen = EmbeddingGenerator(config, initialization_mode='bioclip_only')  
            db_manager = DatabaseManager(config['paths']['database'])
            
            progress.setValue(1)
            QApplication.processEvents()
            
            updated = 0
            for i, item in enumerate(items):
                if progress.wasCanceled():
                    break
                
                progress.setValue(i + 1)
                progress.setLabelText(f"Classificazione:\n{item.image_data.get('filename', '')}\n\n({i+1}/{len(items)})")
                QApplication.processEvents()
                
                filepath = Path(item.image_data.get('filepath', ''))
                if not filepath.exists():
                    continue
                
                flat_tags, taxonomy = embedding_gen.generate_bioclip_tags(filepath)

                if taxonomy:
                    # Salva tassonomia BioCLIP nel campo dedicato
                    taxonomy_json = json.dumps(taxonomy, ensure_ascii=False)
                    db_manager.cursor.execute(
                        "UPDATE images SET bioclip_taxonomy = ? WHERE id = ?",
                        (taxonomy_json, item.image_id)
                    )

                    # Rimuovi eventuali vecchi tag BioCLIP dal campo tags
                    bioclip_prefixes = ("Specie: ", "Genere: ", "Famiglia: ", "Confidenza: ", "Nome comune: ")
                    existing_tags = []
                    if 'tags' in item.image_data and item.image_data['tags']:
                        try:
                            existing_tags = json.loads(item.image_data['tags'])
                        except:
                            existing_tags = []

                    clean_tags = [t for t in existing_tags if not any(t.startswith(p) for p in bioclip_prefixes)]
                    if clean_tags != existing_tags:
                        clean_json = json.dumps(clean_tags, ensure_ascii=False) if clean_tags else None
                        db_manager.cursor.execute(
                            "UPDATE images SET tags = ? WHERE id = ?",
                            (clean_json, item.image_id)
                        )
                        item.image_data['tags'] = clean_json or '[]'

                    db_manager.conn.commit()
                    item.image_data['bioclip_taxonomy'] = taxonomy_json
                    updated += 1
            
            progress.setValue(len(items) + 1)
            db_manager.close()

            # Invalida cache tooltip prima del refresh
            for item in items:
                if hasattr(item, '_invalidate_tooltip_cache'):
                    item._invalidate_tooltip_cache()

            self._refresh_cards(items)

            if self.parent_window:
                self.parent_window.update_status(f"BioCLIP: {updated} immagini classificate")

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore BioCLIP:\n{e}")
            import traceback
            traceback.print_exc()
    
    def run_llm_tagging_batch(self, items):
        """Esegui generazione AI (tag e/o descrizione) su batch di immagini"""
        try:
            config = self._load_config()
            if not config:
                return
            
            llm_config = config.get('embedding', {}).get('models', {}).get('llm_vision', {})
            
            
            dialog = LLMTagDialog(items, parent=self, num_images=len(items), config=config)
            if not dialog.exec():
                return

            # Ottieni selezioni come dizionario
            gen_options = dialog.get_mode()
            if not dialog.has_selection():
                return  # Nessuna selezione

            # Costruisci testo per titolo progress
            selected = []
            if gen_options.get('title'): selected.append('Titolo')
            if gen_options.get('tags'): selected.append('Tag')
            if gen_options.get('description'): selected.append('Descrizione')
            mode_text = ' + '.join(selected)

            progress = QProgressDialog(self)
            progress.setWindowTitle(f"🤖 Generazione {mode_text}")
            progress.setLabelText(f"Connessione a Ollama ({llm_config.get('model', 'qwen3-vl:4b')})...")
            progress.setCancelButtonText("Annulla")
            progress.setMinimumWidth(450)
            progress.setMinimumDuration(0)
            progress.setRange(0, len(items) + 1)
            progress.setValue(0)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            apply_popup_style(progress)
            progress.show()

            for _ in range(5):
                QApplication.processEvents()
            
            from db_manager_new import DatabaseManager

            if self.ai_models and 'embedding_generator' in self.ai_models:
                embedding_gen = self.ai_models['embedding_generator']
            else:
                from embedding_generator import EmbeddingGenerator
                if self.ai_models and 'embedding_generator' in self.ai_models:
                    embedding_gen = self.ai_models['embedding_generator']
                else:
                    embedding_gen = EmbeddingGenerator(config, initialization_mode='llm_only')
            db_manager = DatabaseManager(config['paths']['database'])
            
            progress.setValue(1)
            QApplication.processEvents()
            
            updated_title = 0
            updated_tags = 0
            updated_desc = 0
            
            for i, item in enumerate(items):
                if progress.wasCanceled():
                    break
                
                progress.setValue(i + 1)
                progress.setLabelText(f"Analisi AI:\n{item.image_data.get('filename', '')}\n\n({i+1}/{len(items)})")
                QApplication.processEvents()
                
                filepath = Path(item.image_data.get('filepath', ''))
                if not filepath.exists():
                    continue
                #-------------------------------------------
                # Pre-processa immagine come nel Processing Tab
                from raw_processor import RAWProcessor
                raw_processor = RAWProcessor(config)
                is_raw = filepath.suffix.lower() in ['.orf', '.cr2', '.nef', '.arw', '.dng', '.raf', '.cr3', '.nrw', '.srf', '.sr2', '.rw2', '.raw', '.pef', '.ptx', '.rwl', '.3fr', '.iiq', '.x3f']

                if is_raw:
                    llm_input = raw_processor.extract_thumbnail(filepath, profile_name='llm_vision')
                else:
                    from PIL import Image
                    llm_profile = config.get('image_optimization', {}).get('profiles', {}).get('llm_vision', {})
                    llm_target = llm_profile.get('target_size', 768)
                    with Image.open(filepath) as img:
                        if max(img.size) > llm_target:
                            pil_image = img.copy().convert('RGB')
                            pil_image.thumbnail((llm_target, llm_target), Image.Resampling.LANCZOS)
                            llm_input = pil_image
                        else:
                            llm_input = filepath

                # Ottieni parametri dalla config (nuova struttura granulare)
                llm_config = config.get('embedding', {}).get('models', {}).get('llm_vision', {})
                auto_import = llm_config.get('auto_import', {})

                # Leggi parametri per ogni tipo
                tags_cfg = auto_import.get('tags', {})
                max_tags = tags_cfg.get('max_tags', tags_cfg.get('max', 10))

                desc_cfg = auto_import.get('description', {})
                max_words = desc_cfg.get('max_words', desc_cfg.get('max', 100))

                title_cfg = auto_import.get('title', {})
                max_title_words = title_cfg.get('max_words', title_cfg.get('max', 5))

                # Estrai contesto BioCLIP dal campo dedicato bioclip_taxonomy
                bioclip_context = None
                category_hint = None
                taxonomy_raw = item.image_data.get('bioclip_taxonomy')
                if taxonomy_raw:
                    try:
                        taxonomy = json.loads(taxonomy_raw) if isinstance(taxonomy_raw, str) else taxonomy_raw
                        if isinstance(taxonomy, list) and len(taxonomy) >= 6:
                            # taxonomy: [kingdom, phylum, class, order, family, genus, species_epithet]
                            genus = taxonomy[5] if len(taxonomy) > 5 else ''
                            species_ep = taxonomy[6] if len(taxonomy) > 6 else ''
                            species = f"{genus} {species_ep}".strip() if genus else ''
                            if species:
                                bioclip_context = species
                        # Estrai hint di categoria dalla classe tassonomica
                        from embedding_generator import EmbeddingGenerator
                        category_hint = EmbeddingGenerator.extract_category_hint(taxonomy)
                    except Exception:
                        pass

                # Genera contenuti in base alle selezioni
                result = {}

                if gen_options.get('title'):
                    title = embedding_gen.generate_llm_title(llm_input, max_title_words, bioclip_context=bioclip_context, category_hint=category_hint)
                    if title:
                        result['title'] = title

                if gen_options.get('tags'):
                    tags = embedding_gen.generate_llm_tags(llm_input, max_tags, bioclip_context=bioclip_context, category_hint=category_hint)
                    if tags:
                        result['tags'] = tags

                if gen_options.get('description'):
                    description = embedding_gen.generate_llm_description(llm_input, max_words, bioclip_context=bioclip_context, category_hint=category_hint)
                    if description:
                        result['description'] = description
                #-------------------------------------------
                if not result:
                    continue

                # Salva TITLE
                if result.get('title'):
                    db_manager.cursor.execute(
                        "UPDATE images SET title = ? WHERE id = ?",
                        (result['title'], item.image_id)
                    )
                    item.image_data['title'] = result['title']
                    updated_title += 1

                # Salva TAGS
                if result.get('tags'):
                    # Ottieni tag esistenti unificati
                    existing_tags = []
                    if 'tags' in item.image_data and item.image_data['tags']:
                        try:
                            existing_tags = json.loads(item.image_data['tags'])
                        except:
                            existing_tags = []

                    # BioCLIP SEMPRE prima, poi LLM nuovi, poi altri esistenti
                    bioclip_prefixes = ("Specie: ", "Genere: ", "Famiglia: ", "Confidenza: ", "Nome comune: ",
                                        "Species: ", "Genus: ", "Family: ", "Confidence: ", "Common name: ")
                    bioclip_existing = [t for t in existing_tags if any(t.startswith(p) for p in bioclip_prefixes)]
                    non_bioclip_existing = [t for t in existing_tags if not any(t.startswith(p) for p in bioclip_prefixes)]

                    existing_lower = {t.lower() for t in existing_tags}
                    new_llm = [t for t in result['tags'] if t.lower() not in existing_lower]
                    merged = bioclip_existing + new_llm + non_bioclip_existing
                    tags_json = json.dumps(merged, ensure_ascii=False)

                    db_manager.cursor.execute(
                        "UPDATE images SET tags = ? WHERE id = ?",
                        (tags_json, item.image_id)
                    )
                    item.image_data['tags'] = tags_json
                    updated_tags += 1

                # Salva DESCRIPTION
                if result.get('description'):
                    db_manager.cursor.execute(
                        "UPDATE images SET description = ? WHERE id = ?",
                        (result['description'], item.image_id)
                    )
                    item.image_data['description'] = result['description']
                    updated_desc += 1

                db_manager.conn.commit()
            
            progress.setValue(len(items) + 1)
            db_manager.close()
            
            # Force refresh tooltip delle card elaborate
            for item in items:
                for card in self.cards:
                    if hasattr(card, 'image_id') and card.image_id == item.image_id:
                        # Aggiorna i dati della card
                        card.image_data.update(item.image_data)
                        # Force rebuild del tooltip
                        if hasattr(card, '_invalidate_tooltip_cache'):
                            card._invalidate_tooltip_cache()
                        break

            # Refresh generale
            self._refresh_cards(items)

            # Refresh badge XMP per le card aggiornate
            updated_cards = [c for c in self.cards if any(c.image_id == item.image_id for item in items)]
            if updated_cards:
                QTimer.singleShot(100, lambda: refresh_xmp_badges(updated_cards, "llm_generation"))

            status_parts = []
            if updated_title > 0:
                status_parts.append(f"{updated_title} titoli")
            if updated_tags > 0:
                status_parts.append(f"{updated_tags} tag")
            if updated_desc > 0:
                status_parts.append(f"{updated_desc} descrizioni")

            if self.parent_window and status_parts:
                self.parent_window.update_status(f"AI: generati {', '.join(status_parts)}")
        
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore LLM tagging:\n{e}")
            import traceback
            traceback.print_exc()
    
    def add_user_tags_to_images(self, items, new_tags):
        try:
            config = self._load_config()
            if not config:
                return
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])
            
            for item in items:
                # Ottieni tag esistenti unificati
                existing_tags = []
                if 'tags' in item.image_data and item.image_data['tags']:
                    try:
                        existing_tags = json.loads(item.image_data['tags'])
                    except:
                        existing_tags = []
                
                merged = list(set(existing_tags + new_tags))
                tags_json = json.dumps(merged, ensure_ascii=False)
                
                db_manager.cursor.execute(
                    "UPDATE images SET tags = ? WHERE id = ?",
                    (tags_json, item.image_id)
                )
                item.image_data['tags'] = tags_json
            
            db_manager.conn.commit()
            db_manager.close()

            # Invalida cache tooltip prima del refresh
            for item in items:
                if hasattr(item, '_invalidate_tooltip_cache'):
                    item._invalidate_tooltip_cache()

            self._refresh_cards(items)

            if self.parent_window:
                self.parent_window.update_status(f"Tag aggiunti a {len(items)} immagini")

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore aggiunta tag:\n{e}")

    def remove_user_tags_from_images(self, items, tags_to_remove):
        try:
            config = self._load_config()
            if not config:
                return
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])
            
            for item in items:
                # Ottieni tag esistenti unificati
                existing_tags = []
                if 'tags' in item.image_data and item.image_data['tags']:
                    try:
                        existing_tags = json.loads(item.image_data['tags'])
                    except:
                        existing_tags = []
                
                filtered = [t for t in existing_tags if t not in tags_to_remove]
                tags_json = json.dumps(filtered, ensure_ascii=False) if filtered else None
                
                db_manager.cursor.execute(
                    "UPDATE images SET tags = ? WHERE id = ?",
                    (tags_json, item.image_id)
                )
                item.image_data['tags'] = tags_json
            
            db_manager.conn.commit()
            db_manager.close()

            # Invalida cache tooltip prima del refresh
            for item in items:
                if hasattr(item, '_invalidate_tooltip_cache'):
                    item._invalidate_tooltip_cache()

            self._refresh_cards(items)
            self._update_selection_ui()

            if self.parent_window:
                self.parent_window.update_status(f"Tag rimossi da {len(items)} immagini")

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore rimozione tag:\n{e}")

    def clear_ai_descriptions(self, items):
        """Rimuove descrizioni AI da immagini"""
        try:
            config = self._load_config()
            if not config:
                return

            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])

            for item in items:
                db_manager.cursor.execute(
                    "UPDATE images SET description = NULL WHERE id = ?",
                    (item.image_id,)
                )
                item.image_data['description'] = None

            db_manager.conn.commit()
            db_manager.close()

            # Invalida cache tooltip prima del refresh
            for item in items:
                if hasattr(item, '_invalidate_tooltip_cache'):
                    item._invalidate_tooltip_cache()

            self._refresh_cards(items)

            if self.parent_window:
                self.parent_window.update_status(f"Descrizioni AI rimosse da {len(items)} immagini")

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore rimozione descrizioni AI:\n{e}")

    def _refresh_cards(self, items):
        """Ricrea le card aggiornate - Fix: mantiene posizione nel layout"""
        updates = []
        for item in items:
            for i, card in enumerate(self.cards):
                if card.image_id == item.image_id:
                    # Trova posizione nel layout (può differire da self.cards)
                    layout_pos = -1
                    for li in range(self.flow_layout.count()):
                        layout_item = self.flow_layout.itemAt(li)
                        if layout_item and layout_item.widget() == card:
                            layout_pos = li
                            break
                    updates.append((i, layout_pos, item.image_data, card.is_selected()))
                    break

        # Ordina per layout_pos decrescente per evitare shift degli indici
        updates.sort(key=lambda x: x[1], reverse=True)

        # Approccio sicuro: aggiorna le card interessate
        for idx, layout_pos, image_data, was_selected in updates:
            old_card = self.cards[idx]
            if old_card in self.selected_items:
                self.selected_items.remove(old_card)

            # Rimuovi widget dal layout usando API corrette
            self.flow_layout.removeWidget(old_card)
            old_card.setParent(None)
            old_card.deleteLater()

            # Crea nuova card con parent=self per mantenere riferimento _gallery
            new_card = ImageCard(image_data, parent=self)
            new_card.selection_changed.connect(self._on_item_selection_changed)
            new_card.find_similar_requested.connect(self.find_similar)
            new_card.bioclip_requested.connect(self.run_bioclip_batch)
            new_card.llm_tagging_requested.connect(self.run_llm_tagging_batch)
            # Connetti segnali XMP Sync

            # Aggiorna riferimenti
            self.cards[idx] = new_card

            # FIXED: Inserisci alla stessa posizione nel layout invece di appendere
            if layout_pos >= 0:
                self.flow_layout.insertWidget(layout_pos, new_card)
            else:
                self.flow_layout.addWidget(new_card)

            if was_selected:
                new_card.set_selected(True)
                # NON aggiungere manualmente - set_selected emette segnale che lo fa

        self._do_relayout()
    
    def _load_config(self):
        try:
            # Forziamo il controllo: se config_path non è un path o stringa, resetta al default
            if not isinstance(self.config_path, (str, Path)):
                 self.config_path = Path('config_new.yaml')
             
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            # Il problema è qui: se 'self' è in uno stato inconsistente, QMessageBox fallisce
            print(f"DEBUG - Errore critico su path: {self.config_path} (Tipo: {type(self.config_path)})")
            print(f"Errore caricamento directory salvata: {e}")
            return None


    def on_activated(self):
        pass


    
    def add_unified_tags_to_images(self, items, new_tags):
        """Aggiunge tag alla lista unificata delle immagini"""
        if not items or not new_tags:
            return
            
        try:
            config = self._load_config()
            if not config:
                return
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])
            
            for item in items:
                # Ottieni tag esistenti unificati
                current_tags = item.get_unified_tags() if hasattr(item, 'get_unified_tags') else []
                
                # Aggiungi nuovi tag evitando duplicati
                updated_tags = list(set(current_tags + new_tags))
                
                # Aggiorna database
                tags_json = json.dumps(updated_tags, ensure_ascii=False)
                db_manager.cursor.execute(
                    "UPDATE images SET tags = ? WHERE id = ?",
                    (tags_json, item.image_id)
                )
                
                # Aggiorna dati item
                item.image_data['tags'] = tags_json
                
            db_manager.conn.commit()
            db_manager.close()

            # Invalida cache tooltip prima del refresh
            for item in items:
                if hasattr(item, '_invalidate_tooltip_cache'):
                    item._invalidate_tooltip_cache()

            self._refresh_cards(items)

            if self.parent_window:
                self.parent_window.update_status(f"Aggiunti {len(new_tags)} tag a {len(items)} immagini")

        except Exception as e:
            print(f"Errore aggiunta tag unificati: {e}")

    def remove_unified_tags_from_images(self, items, tags_to_remove):
        """Rimuove tag specifici dalla lista unificata delle immagini"""
        if not items or not tags_to_remove:
            return
            
        try:
            config = self._load_config()
            if not config:
                return
            
            from db_manager_new import DatabaseManager
            db_manager = DatabaseManager(config['paths']['database'])
            
            for item in items:
                # Ottieni tag esistenti unificati
                current_tags = item.get_unified_tags() if hasattr(item, 'get_unified_tags') else []
                
                # Rimuovi tag specificati
                updated_tags = [tag for tag in current_tags if tag not in tags_to_remove]
                
                # Aggiorna database
                tags_json = json.dumps(updated_tags, ensure_ascii=False) if updated_tags else None
                db_manager.cursor.execute(
                    "UPDATE images SET tags = ? WHERE id = ?",
                    (tags_json, item.image_id)
                )
                
                # Aggiorna dati item
                item.image_data['tags'] = tags_json
                
            db_manager.conn.commit()
            db_manager.close()

            # Invalida cache tooltip prima del refresh
            for item in items:
                if hasattr(item, '_invalidate_tooltip_cache'):
                    item._invalidate_tooltip_cache()

            self._refresh_cards(items)

            if self.parent_window:
                self.parent_window.update_status(f"Rimossi {len(tags_to_remove)} tag da {len(items)} immagini")

        except Exception as e:
            print(f"Errore rimozione tag unificati: {e}")

    def reimport_image_metadata(self, image_id, filepath):
        """Reimporta metadati di un'immagine dopo modifica esterna usando sistema XMP esistente"""
        try:
            # Trova la card corrispondente 
            target_card = None
            for card in self.cards:
                if hasattr(card, 'image_id') and card.image_id == image_id:
                    target_card = card
                    break
            
            if not target_card:
                print(f"Card per immagine ID {image_id} non trovata")
                return
            
            # Usa il sistema XMP esistente per rilevare e sincronizzare le modifiche
            
            # Refresh stato XMP (rilegge da disco)
            target_card.refresh_xmp_state()
            
            # Se ci sono differenze, usa il sync automatico esistente
            if hasattr(target_card, 'xmp_state') and target_card.xmp_state:
                if 'OUT' in str(target_card.xmp_state) or 'DIRTY' in str(target_card.xmp_state):
                    # Attiva sincronizzazione automatica da XMP
                    target_card._import_from_xmp_with_refresh([target_card])
                    
                    if self.parent_window:
                        self.parent_window.update_status(f"Sincronizzati metadati XMP per {filepath.name}")
                        self.parent_window.log_info(f"Reimportazione XMP completata: {filepath.name}")
                else:
                    if self.parent_window:
                        self.parent_window.log_info(f"Nessuna modifica XMP per {filepath.name}")
            
        except Exception as e:
            print(f"Errore reimport_image_metadata: {e}")
            if self.parent_window:
                self.parent_window.log_error(f"Errore reimport {filepath.name}: {e}")

    def _refresh_single_card(self, image_id):
        """Refresh di una singola card dopo reimport"""
        try:
            # Trova la card e refresh completo
            for card in self.cards:
                if hasattr(card, 'image_id') and card.image_id == image_id:
                    card.refresh_xmp_state()  # Aggiorna stato XMP
                    card.refresh_display()   # Aggiorna display
                    break
                        
        except Exception as e:
            print(f"Errore refresh single card: {e}")

