"""
XMP Badge Manager - Gestore centralizzato per refresh badge XMP
Gestisce il ricalcolo e aggiornamento dei badge XMP in background
preservando la logica esistente in refresh_xmp_state()
"""

import logging
from pathlib import Path
from typing import List, Optional, Set
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer, QMutex, QMutexLocker
from PyQt6.QtWidgets import QApplication
import time

logger = logging.getLogger(__name__)


class XMPBadgeWorker(QObject):
    """Worker per calcolo badge XMP in background thread"""
    badge_computed = pyqtSignal(object, str)  # (ImageCard, reason)
    batch_completed = pyqtSignal(int, str)    # (processed_count, reason)
    
    def __init__(self):
        super().__init__()
        self.queue = []
        self.processing = False
        self.mutex = QMutex()
        
    def queue_refresh(self, image_cards: List, reason: str):
        """Accoda cards per refresh (thread-safe)"""
        with QMutexLocker(self.mutex):
            # Aggiungi alla coda evitando duplicati
            for card in image_cards:
                if card not in [item[0] for item in self.queue]:
                    self.queue.append((card, reason))
            
            logger.info(f"🔄 XMP Worker: accodate {len(image_cards)} cards - coda totale: {len(self.queue)}")
        
        # Avvia processing se non già attivo
        if not self.processing:
            QTimer.singleShot(0, self.process_queue)
    
    def process_queue(self):
        """Processa coda in background"""
        self.processing = True
        processed = 0
        current_reason = ""
        
        try:
            while True:
                # Prendi prossimo item (thread-safe)
                with QMutexLocker(self.mutex):
                    if not self.queue:
                        break
                    card, reason = self.queue.pop(0)
                    current_reason = reason
                
                # Processa card (fuori dal mutex)
                try:
                    logger.debug(f"🔄 Processing badge per {getattr(card, 'image_data', {}).get('filename', 'unknown')}")
                    
                    # Usa la logica esistente (preservata)
                    card.refresh_xmp_state()
                    
                    # Emetti signal per UI update
                    self.badge_computed.emit(card, reason)
                    processed += 1
                    
                    # Small delay per non bloccare UI
                    time.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"❌ Errore processing badge: {e}")
                    continue
        
        finally:
            self.processing = False
            
        if processed > 0:
            self.batch_completed.emit(processed, current_reason)
            logger.info(f"✅ XMP Worker: completato batch {processed} badges - reason: {current_reason}")


class XMPBadgeManager(QObject):
    """Gestore centralizzato per refresh badge XMP"""
    refresh_started = pyqtSignal(int, str)    # (count, reason)  
    refresh_completed = pyqtSignal(int, str)  # (processed, reason)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Setup worker thread
        self.worker_thread = QThread()
        self.worker = XMPBadgeWorker()
        self.worker.moveToThread(self.worker_thread)
        
        # Connect signals
        self.worker.badge_computed.connect(self._on_badge_computed)
        self.worker.batch_completed.connect(self._on_batch_completed)
        
        # Start thread
        self.worker_thread.start()
        
        logger.info("✅ XMP Badge Manager inizializzato")
    
    def refresh_badges(self, image_cards: List, reason: str):
        """
        Entry point UNICO per tutti i refresh badge XMP
        
        Args:
            image_cards: Lista di ImageCard da aggiornare
            reason: Motivo del refresh per logging/debug
        """
        if not image_cards:
            logger.warning(f"⚠️ XMP Badge refresh chiamato senza cards - reason: {reason}")
            return
        
        # Filtra cards valide
        valid_cards = []
        for card in image_cards:
            if hasattr(card, 'refresh_xmp_state') and hasattr(card, 'image_data'):
                valid_cards.append(card)
            else:
                logger.warning(f"⚠️ Card non valida per refresh XMP: {card}")
        
        if not valid_cards:
            logger.warning(f"⚠️ Nessuna card valida per refresh - reason: {reason}")
            return
        
        logger.info(f"🔄 XMP Badge Manager: refresh {len(valid_cards)} cards - reason: {reason}")
        
        # Invalida cache su tutte le cards (UI thread)
        for card in valid_cards:
            try:
                # Reset cache XMP per forzare ricalcolo
                if hasattr(card, '_xmp_state_cache'):
                    card._xmp_state_cache = None
                if hasattr(card, '_xmp_info_cache'): 
                    card._xmp_info_cache = None
                
                logger.debug(f"🗑️ Cache invalidata per {card.image_data.get('filename', 'unknown')}")
            except Exception as e:
                logger.error(f"❌ Errore invalidazione cache: {e}")
        
        # Emetti signal inizio
        self.refresh_started.emit(len(valid_cards), reason)
        
        # Invia al worker per processing background
        self.worker.queue_refresh(valid_cards, reason)
    
    def _on_badge_computed(self, card, reason):
        """Callback quando singolo badge è pronto"""
        try:
            # Forza update UI se necessario
            if hasattr(card, 'update'):
                card.update()
            
            logger.debug(f"✅ Badge aggiornato: {card.image_data.get('filename', 'unknown')}")
        except Exception as e:
            logger.error(f"❌ Errore update badge UI: {e}")
    
    def _on_batch_completed(self, processed_count, reason):
        """Callback quando batch è completato"""
        self.refresh_completed.emit(processed_count, reason)
        logger.info(f"🎯 Batch XMP completato: {processed_count} badges - reason: {reason}")
        
        # Force refresh UI globale se necessario
        QApplication.processEvents()
    
    def shutdown(self):
        """Cleanup per shutdown applicazione"""
        logger.info("🔄 XMP Badge Manager shutdown...")
        
        if self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(5000)  # 5 sec timeout
        
        logger.info("✅ XMP Badge Manager shutdown completato")


# Singleton instance globale
_badge_manager_instance: Optional[XMPBadgeManager] = None

def get_badge_manager() -> XMPBadgeManager:
    """Ottieni istanza singleton del Badge Manager"""
    global _badge_manager_instance
    
    if _badge_manager_instance is None:
        _badge_manager_instance = XMPBadgeManager()
        logger.info("🆕 XMP Badge Manager singleton creato")
    
    return _badge_manager_instance

def refresh_xmp_badges(image_cards: List, reason: str):
    """
    Funzione di convenienza per refresh badge XMP
    
    Usage:
        from xmp_badge_manager import refresh_xmp_badges
        refresh_xmp_badges([card1, card2], "export_completed")
    """
    manager = get_badge_manager()
    manager.refresh_badges(image_cards, reason)

def shutdown_badge_manager():
    """Cleanup per shutdown applicazione"""
    global _badge_manager_instance
    
    if _badge_manager_instance:
        _badge_manager_instance.shutdown()
        _badge_manager_instance = None


# Integration helpers per backward compatibility
class XMPBadgeIntegration:
    """Helper methods per integrare nel codice esistente"""
    
    @staticmethod
    def replace_refresh_after_database_operation(items, operation_type):
        """
        Drop-in replacement per _refresh_after_database_operation
        Preserva la stessa interfaccia ma usa il manager centralizzato
        """
        logger.info(f"🔄 Legacy refresh redirect: {len(items)} items - operation: {operation_type}")
        refresh_xmp_badges(items, f"database_{operation_type}")
    
    @staticmethod  
    def replace_individual_refresh(card, reason="manual"):
        """
        Drop-in replacement per chiamate singole refresh_xmp_state
        """
        refresh_xmp_badges([card], reason)


# Esempi di integrazione:
"""
# 1. In export_tab.py - dopo export completato:
from xmp_badge_manager import refresh_xmp_badges
selected = self.main_window.get_selected_gallery_items() 
refresh_xmp_badges(selected, "export_completed")

# 2. In gallery_widgets.py - sostituisci _refresh_after_database_operation:
from xmp_badge_manager import XMPBadgeIntegration
def _refresh_after_database_operation(self, items, operation_type):
    XMPBadgeIntegration.replace_refresh_after_database_operation(items, operation_type)

# 3. In main_window.py - dopo import XMP:
from xmp_badge_manager import refresh_xmp_badges
refresh_xmp_badges(imported_items, "xmp_import")

# 4. In gallery_tab.py - dopo caricamento/ricerca:
from xmp_badge_manager import refresh_xmp_badges  
refresh_xmp_badges(visible_cards, "gallery_loaded")

# 5. Shutdown in main:
from xmp_badge_manager import shutdown_badge_manager
app.aboutToQuit.connect(shutdown_badge_manager)
"""
