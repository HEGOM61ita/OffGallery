"""
Generazione contenuti AI in un thread separato, per la Gallery.

Perché esiste
-------------
La chiamata al modello dura 40-50 secondi per immagine. Fatta nel thread della
finestra, la blocca per tutto quel tempo: Windows la dichiara "non risponde" e
l'utente crede che il programma sia morto. Qui la parte lenta — preparazione
dell'immagine e chiamata al modello — avviene in disparte, e i risultati
tornano al thread principale uno per volta.

Divisione dei compiti
---------------------
In questo thread:      preparazione immagine, lettura dei contesti, chiamata al modello
Nel thread principale: scritture sul database, aggiornamento della finestra

Le scritture restano nel thread principale come richiesto dall'architettura del
progetto: il worker non tocca il database in scrittura, si limita a leggere.

Limite noto
-----------
Annullando, l'immagine in corso viene comunque portata a termine: la chiamata al
modello non si interrompe a metà. L'attesa può arrivare a una cinquantina di
secondi, ma la finestra resta viva e può dirlo.
"""

import json
import logging
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class LLMWorkerThread(QThread):
    """Genera titolo, tag e descrizione per una lista di immagini, in disparte."""

    # i, totale, nome file — prima di iniziare l'immagine
    progress = pyqtSignal(int, int, str)
    # i, nome file, informazione sul contesto (specie riconosciuta, o assenza)
    context_ready = pyqtSignal(int, str, str)
    # indice nella lista, risultato del modello: il thread principale salva
    result_ready = pyqtSignal(int, dict)
    # indice, motivo — immagine saltata (file mancante, estrazione fallita)
    item_skipped = pyqtSignal(int, str)
    # annullato dall'utente?
    finished_all = pyqtSignal(bool)
    # errore che ha interrotto tutto
    error = pyqtSignal(str)

    def __init__(self, items, embedding_gen, config, db_path, gen_options, parent=None):
        """
        Args:
            items:         lista di ImageCard da elaborare
            embedding_gen: EmbeddingGenerator già inizializzato
            config:        configurazione completa
            db_path:       percorso del database (per le sole letture del worker)
            gen_options:   scelte del dialogo (quali campi, quanti tag, ecc.)
        """
        super().__init__(parent)
        self.items = list(items)
        self.embedding_gen = embedding_gen
        self.config = config
        self.db_path = db_path
        self.gen_options = gen_options or {}
        self._canceled = False
        # Conteggi per il riepilogo finale
        self.bio_found = 0
        self.bio_not_found = 0
        self._preset_nome_cache = None

    # ------------------------------------------------------------------
    # Comandi dal thread principale
    # ------------------------------------------------------------------

    def cancel(self):
        """Chiede di fermarsi. L'immagine in corso viene comunque completata."""
        self._canceled = True

    @property
    def is_canceled(self) -> bool:
        return self._canceled

    # ------------------------------------------------------------------
    # Esecuzione
    # ------------------------------------------------------------------

    def run(self):
        conn = None
        try:
            # Connessione di sola lettura, propria di questo thread: SQLite non
            # consente di riusare fra thread diversi quella del thread principale.
            conn = self._open_readonly_db()

            modes = self._modes()
            if not modes:
                self.finished_all.emit(False)
                return

            total = len(self.items)
            for i, item in enumerate(self.items):
                if self._canceled:
                    self.finished_all.emit(True)
                    return

                filename = item.image_data.get('filename', '')
                self.progress.emit(i, total, filename)

                filepath = Path(item.image_data.get('filepath', ''))
                if not filepath.exists():
                    self.item_skipped.emit(i, "file non trovato")
                    continue

                llm_input = self._prepare_image(filepath)
                if llm_input is None:
                    self.item_skipped.emit(i, "nessuna immagine estraibile")
                    continue

                ctx = self._gather_context(item, conn)
                self.context_ready.emit(i, filename, ctx['info'])

                # La parte lenta: qui si sta 40-50 secondi, ma la finestra e' viva
                try:
                    result = self.embedding_gen.generate_llm_combined(
                        llm_input, modes=modes,
                        max_tags=self.gen_options.get('max_tags', 10),
                        max_description_words=self.gen_options.get('max_words_desc', 100),
                        max_title_words=self.gen_options.get('max_title_words', 5),
                        bioclip_context=ctx['bioclip_context'],
                        category_hint=ctx['category_hint'],
                        location_hint=ctx['location_hint'],
                        vernacular_name=ctx['vernacular_name'],
                    ) or {}
                except Exception as e:
                    logger.warning("Generazione fallita per %s: %s", filename, e, exc_info=True)
                    self.item_skipped.emit(i, f"generazione non riuscita: {e}")
                    continue

                if not result:
                    self.item_skipped.emit(i, "il modello non ha prodotto nulla")
                    continue

                # Il salvataggio avviene nel thread principale, immagine per
                # immagine: annullando, quelle gia' fatte restano salvate.
                result['_bioclip_context'] = ctx['bioclip_context']
                self.result_ready.emit(i, result)

            self.finished_all.emit(self._canceled)

        except Exception as e:
            logger.error("Errore nel worker LLM: %s", e, exc_info=True)
            self.error.emit(str(e))
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception as e:
                    logger.debug("Chiusura connessione worker fallita: %s", e)

    # ------------------------------------------------------------------
    # Preparazione
    # ------------------------------------------------------------------

    def _modes(self) -> list:
        """Campi da generare, secondo le scelte del dialogo."""
        modes = []
        if self.gen_options.get('title'):
            modes.append('title')
        if self.gen_options.get('tags'):
            modes.append('tags')
        if self.gen_options.get('description'):
            modes.append('description')
        return modes

    def _open_readonly_db(self):
        """Connessione di sola lettura al database, per i dati di contesto."""
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
            return conn
        except Exception as e:
            logger.warning("Database non apribile dal worker: %s", e, exc_info=True)
            return None

    def _prepare_image(self, filepath: Path):
        """Estrae l'immagine da dare al modello, raddrizzata secondo l'orientamento.

        Tutto passa da extract_thumbnail, RAW e JPEG allo stesso modo: e' il punto
        unico dove avviene il raddrizzamento. Prima i JPEG seguivano una strada
        propria e arrivavano coricati al modello.
        """
        try:
            from raw_processor import RAWProcessor
            processor = RAWProcessor(self.config)
            return processor.extract_thumbnail(filepath, profile_name='llm_vision')
        except Exception as e:
            logger.warning("Preparazione immagine fallita per %s: %s",
                           filepath.name, e, exc_info=True)
            return None

    def _gather_context(self, item, conn) -> dict:
        """Raccoglie i dati che arricchiscono il prompt per questa immagine."""
        ctx = {
            'bioclip_context': None,
            'category_hint': None,
            'location_hint': None,
            'vernacular_name': None,
            'info': '',
        }

        # Località, dalla gerarchia geografica
        geo_hierarchy = item.image_data.get('geo_hierarchy')
        if geo_hierarchy:
            try:
                from geo_enricher import get_location_hint
                ctx['location_hint'] = get_location_hint(geo_hierarchy)
            except Exception as e:
                logger.debug("Località non ricavata: %s", e)

        # Nome comune, se BioNomen l'ha già trovato
        if conn is not None:
            try:
                row = conn.execute(
                    "SELECT vernacular_name FROM images WHERE filename = ?",
                    (item.image_data.get('filename', ''),)
                ).fetchone()
                if row and row[0]:
                    ctx['vernacular_name'] = row[0]
            except Exception as e:
                logger.debug("Nome comune non letto: %s", e)

        # Specie e categoria, dalla tassonomia BioCLIP
        taxonomy_raw = item.image_data.get('bioclip_taxonomy')
        if taxonomy_raw:
            try:
                taxonomy = (json.loads(taxonomy_raw)
                            if isinstance(taxonomy_raw, str) else taxonomy_raw)
                if isinstance(taxonomy, list) and len(taxonomy) >= 6:
                    genus = taxonomy[5] if len(taxonomy) > 5 else ''
                    species_ep = taxonomy[6] if len(taxonomy) > 6 else ''
                    species = f"{genus} {species_ep}".strip() if genus else ''
                    if species:
                        ctx['bioclip_context'] = species
                from embedding_generator import EmbeddingGenerator
                ctx['category_hint'] = EmbeddingGenerator.extract_category_hint(taxonomy)
            except Exception as e:
                logger.debug("Tassonomia non interpretata: %s", e)

        # Testo da mostrare nella finestra di avanzamento
        if ctx['bioclip_context']:
            self.bio_found += 1
            ctx['info'] = ctx['bioclip_context']
            if ctx['category_hint']:
                ctx['info'] += f" ({ctx['category_hint']})"
        else:
            self.bio_not_found += 1
            ctx['info'] = ctx['category_hint'] or ''

        # Il contesto scelto nel dialogo (es. "Boudoir e nudo") va mostrato:
        # veniva applicato al prompt ma la finestra diceva comunque
        # "Contesto: nessuno" (segnalazione 2026-09-01).
        preset = self._nome_preset_attivo()
        if preset:
            ctx['info'] = f"{preset} - {ctx['info']}" if ctx['info'] else preset

        return ctx

    def _nome_preset_attivo(self) -> str:
        """Nome leggibile del contesto scelto nel dialogo, '' se nessuno.

        Il dialogo passa il solo identificativo: il nome da mostrare si
        recupera dall'elenco dei preset del plugin, una volta sola.
        """
        preset_id = (self.gen_options or {}).get('preset_id', '')
        if not preset_id:
            return ''
        if self._preset_nome_cache is not None:
            return self._preset_nome_cache

        nome = preset_id  # se il plugin non risponde, meglio l'id di niente
        try:
            import sys
            from utils.paths import get_app_dir
            cartella = str(get_app_dir() / 'plugins')
            if cartella not in sys.path:
                sys.path.insert(0, cartella)
            from plugins.prompt_context.plugin import load_all_presets
            for voce in load_all_presets():
                if voce.get('id') == preset_id:
                    nome = voce.get('name') or preset_id
                    break
        except Exception as e:
            logger.debug("Nome del contesto non recuperato: %s", e)

        self._preset_nome_cache = nome
        return nome
