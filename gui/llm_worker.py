"""
LLM Worker Thread - Elaborazione asincrona generazione contenuti AI
Supporta cancellazione e rollback risultati
"""

from PyQt6.QtCore import QThread, pyqtSignal
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


class LLMWorkerThread(QThread):
    """
    Worker thread per generazione contenuti AI (tag + descrizioni)
    Elabora batch di immagini in modo asincrono con supporto cancellazione
    """
    
    # Segnali
    progress = pyqtSignal(int, int)  # current, total
    result_ready = pyqtSignal(dict)  # {image_id, tags, description}
    completed = pyqtSignal(list)  # lista risultati finali
    error = pyqtSignal(str)  # messaggio errore
    canceled  = pyqtSignal()  # utente ha annullato
    
    def __init__(self, items, embedding_gen, config):
        """
        Args:
            items: lista ImageCard objects con image_data
            embedding_gen: istanza EmbeddingGenerator
            config: config dict
        """
        super().__init__()
        self.items = items
        self.embedding_gen = embedding_gen
        self.config = config
        
        # Flag di controllo
        self.is_canceled  = False
        
        # Parametri elaborazione (impostati dal caller)
        self.mode = 'tags'
        self.tag_categories = ''
        self.description_style = ''
        self.user_hints = []
        
        # Risultati accumulati in memoria (rollback-safe)
        self.results = []  # lista di {image_id, tags, description}
    
    def set_parameters(self, mode, tag_categories, description_style, user_hints):
        """Imposta parametri generazione prima di start()"""
        self.mode = mode
        self.tag_categories = tag_categories
        self.description_style = description_style
        self.user_hints = user_hints
    
    def run(self):
        """Esegue elaborazione (thread worker)"""
        try:
            total = len(self.items)
            self.results.clear()
            
            for i, item in enumerate(self.items):
                # Check cancellazione
                if self.is_canceled :
                    self.canceled .emit()
                    return
                
                # Emetti progresso
                self.progress.emit(i, total)
                
                # Estrai dati immagine
                image_id = item.image_id
                filepath = Path(item.image_data.get('filepath', ''))
                
                if not filepath.exists():
                    logger.warning(f"File non trovato: {filepath}")
                    continue
                
                # Genera contenuto con LLM
                result = self.embedding_gen.generate_llm_content(
                    filepath,
                    mode=self.mode,
                    tag_categories=self.tag_categories,
                    description_style=self.description_style,
                    user_hints=self.user_hints
                )
                
                if result:
                    # Accumula risultato in memoria (non salva ancora)
                    result_entry = {
                        'image_id': image_id,
                        'tags': result.get('tags', []),
                        'description': result.get('description', '')
                    }
                    self.results.append(result_entry)
                    
                    # Emetti segnale risultato pronto
                    self.result_ready.emit(result_entry)
            
            # Se arriviamo qui senza cancellazione, emetti completed con tutti i risultati
            if not self.is_canceled :
                self.completed.emit(self.results)
        
        except Exception as e:
            logger.error(f"Errore worker LLM: {e}")
            self.error.emit(str(e))
    
    def cancel(self):
        """Richiesta di cancellazione (chiamato dal main thread)"""
        self.is_canceled  = True
    
    def get_results(self):
        """Ritorna risultati accumulati (in memoria, non salvati)"""
        return self.results
    
    def clear_results(self):
        """Scarta risultati (rollback)"""
        self.results.clear()
