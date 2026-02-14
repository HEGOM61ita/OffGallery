import pickle
import numpy as np
import logging
import re
import unicodedata
import json
from pathlib import Path
from PyQt6.QtCore import QCoreApplication

logger = logging.getLogger(__name__)

class ImageRetrieval:
    def __init__(self, db_manager, embedding_gen, config):
        self.db = db_manager
        self.embedding_gen = embedding_gen
        self.config = config
        self.max_results = config.get('search', {}).get('max_results', 100)
        self.default_threshold = 0.15 # Abbassiamo il default dato il rumore multilingua
        self.stems_cache = {}  # Cache per stems delle immagini

    def _cosine_similarity(self, v1, v2):
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0: return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))

    def _normalize(self, text):
        if not text: return ""
        return "".join(c for c in unicodedata.normalize('NFD', str(text).lower()) if unicodedata.category(c) != 'Mn')

    def search(self, query_text, mode="semantic", filters_sql=None, filter_params=None,
               deep_search=False, signal_callback=None, min_threshold=None, fuzzy=True, strictness=0.4, include_description=True, include_title=True, max_results=None):
        """
        Punto di ingresso della ricerca. 
        Ritorna una tupla: (lista_risultati, numero_candidati_totali_reali)
        """
        
        # Usa max_results passato come parametro, altrimenti default dalla config
        effective_limit = max_results if max_results is not None else self.max_results
        
        # --- 0. CONTEGGIO TOTALE REALE (Senza LIMIT) ---
        # Questa query serve per sapere quante immagini esistono in totale con questi filtri
        count_sql = "SELECT COUNT(*) FROM images"
        if filters_sql:
            count_sql += f" WHERE {filters_sql}"
        
        try:
            self.db.cursor.execute(count_sql, filter_params or [])
            total_found_in_db = self.db.cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Errore nel conteggio totale: {e}")
            total_found_in_db = 0

        # 1. CONTROLLO QUERY VUOTA
        if not query_text.strip():
            # Solo filtri - restituiamo tutti i risultati filtrati senza processing AI
            base_sql = """
            SELECT id, filepath, filename, clip_embedding, tags, description, title,
                   camera_make, camera_model, lens_model, focal_length, aperture,
                   iso, shutter_speed, width, height, datetime_original,
                   datetime_digitized, datetime_modified, processed_date,
                   aesthetic_score, technical_score, lr_rating, color_label
            FROM images
            """
            if filters_sql:
                base_sql += f" WHERE {filters_sql}"
            # Ordinamento intelligente: stelle > score composito AI > data scatto
            base_sql += """
            ORDER BY
              COALESCE(lr_rating, 0) DESC,
              (COALESCE(aesthetic_score, 0) * 0.7 + COALESCE(technical_score, 0) * 0.3) DESC,
              COALESCE(datetime_original, datetime_digitized, datetime_modified, processed_date) DESC
            """
            base_sql += f" LIMIT {effective_limit}"
            
            try:
                self.db.cursor.execute(base_sql, filter_params or [])
                columns = [d[0] for d in self.db.cursor.description]
                results = [dict(zip(columns, row)) for row in self.db.cursor.fetchall()]
                # Aggiungi score fittizio per compatibilità
                for img in results:
                    img['final_score'] = 1.0
                return results, total_found_in_db
            except Exception as e:
                logger.error(f"Errore SQL filtri: {e}")
                return [], 0
        
        # 2. TRADUZIONE (solo se c'è query)
        query_en = self.embedding_gen._translate_to_english(query_text)
        logger.info(f"🔤 Query: '{query_text}' → Traduzione: '{query_en}'")
        
        # 3. SQL FETCH - Prende TUTTE le immagini per ricerca semantica
        # La ricerca CLIP deve confrontare la query con OGNI immagine nel database
        base_sql = """
        SELECT id, filepath, filename, clip_embedding, tags, description, title,
               camera_make, camera_model, lens_model, focal_length, aperture,
               iso, shutter_speed, width, height, datetime_original,
               datetime_digitized, datetime_modified, processed_date,
               aesthetic_score, technical_score, lr_rating, color_label
        FROM images
        WHERE clip_embedding IS NOT NULL
        """
        if filters_sql:
            base_sql += f" AND {filters_sql}" 
        
        try:
            self.db.cursor.execute(base_sql, filter_params or [])
            columns = [d[0] for d in self.db.cursor.description]
            candidates = [dict(zip(columns, row)) for row in self.db.cursor.fetchall()]
        except Exception as e:
            logger.error(f"Errore SQL: {e}")
            return [], 0

        if not candidates:
            return [], 0

        # 4. LOGICA DI SOGLIA
        threshold = min_threshold if min_threshold is not None else self.default_threshold
        
        # 5. DISPATCH PIPELINE
        if mode == "semantic":
            results = self._semantic_pipeline(query_text, query_en, candidates, deep_search, signal_callback, threshold, strictness, include_description)
        else:
            results = self._tag_pipeline(query_text, candidates, fuzzy=fuzzy, include_description=include_description, include_title=include_title)

        # 6. APPLICAZIONE LIMITE FINALE
        # Applichiamo il limite richiesto dall'utente sulla lista finale elaborata
        final_results = results[:effective_limit]

        return final_results, total_found_in_db
    
    def _semantic_pipeline(self, query_it, query_en, candidates, deep_search, signal_callback, threshold, strictness, include_description):
        import numpy as np
        import json
        import pickle
        import logging
        import re

        logger = logging.getLogger('root')
        results = []
        
        # 1. Preparazione Query
        res_query = self.embedding_gen.generate_embeddings(query_en)
        if not res_query: return []
        query_emb = np.array(res_query.get('text_embedding') if isinstance(res_query, dict) else res_query)

        # 2. Estrazione parole query (minimo 3 caratteri)
        query_words = [w.strip(",.?!").lower() for w in query_it.split() if len(w) >= 3]
        
        # 3. Calcolo lunghezza matching basata su strictness (CORRETTO)
        # strictness 0.0 → 4 caratteri, strictness 1.0 → 9 caratteri
        match_length = max(4, min(9, 4 + int(strictness * 5)))
        
        for i, img in enumerate(candidates):
            filename = img.get('filename', 'Unknown')
            try:
                # Deserializza embedding: può essere raw bytes (float32) o pickle
                raw_data = img['clip_embedding']
                if isinstance(raw_data, bytes):
                    # Pickle protocol 2-5: header \x80 + byte protocollo (0x02-0x05)
                    if len(raw_data) >= 2 and raw_data[0] == 0x80 and raw_data[1] in (2, 3, 4, 5):
                        img_emb_raw = pickle.loads(raw_data)
                        img_emb = np.array(img_emb_raw.get('image_embedding') if isinstance(img_emb_raw, dict) else img_emb_raw)
                    # Raw float32 bytes: qualsiasi dimensione multipla di 4
                    elif len(raw_data) >= 4 and len(raw_data) % 4 == 0:
                        img_emb = np.frombuffer(raw_data, dtype=np.float32).copy()
                    else:
                        raise ValueError(f"Formato embedding non riconosciuto ({len(raw_data)} bytes)")
                else:
                    img_emb = np.array(raw_data)

                visual_score = float(self._cosine_similarity(query_emb, img_emb))
                
                final_score = visual_score
                debug_info = "Solo CLIP"

                if deep_search:
                    # Pulizia e normalizzazione testo
                    desc = str(img.get('description', '')).lower() if include_description else ""
                    tags = str(img.get('tags', '[]')).lower()
                    full_text = f" {desc} {tags} ".replace('"', ' ').replace("'", " ").replace(",", " ").replace(".", " ")
                    
                    # Conteggio match con word boundary
                    matches = 0
                    match_details = []
                    
                    for word in query_words:
                        # Estrai radice della lunghezza calcolata
                        root = word[:min(match_length, len(word))]
                        
                        # Verifica presenza radice con word boundary (evita match in "marroni")
                        pattern = r'\b' + re.escape(root)
                        if re.search(pattern, full_text):
                            matches += 1
                            match_details.append(f"{word}→{root}✓")
                        else:
                            match_details.append(f"{word}→{root}✗")
                    
                    # Calcolo score finale con bonus/penalty più incisivi
                    match_ratio = matches / len(query_words)
                    
                    if match_ratio == 1.0:
                        # Tutti i concetti presenti - bonus forte
                        bonus = 0.15 + (0.25 * strictness)
                        final_score = visual_score + bonus
                        debug_info = f"MATCH COMPLETO (+{bonus:.2f}) [{', '.join(match_details)}]"
                    elif match_ratio >= 0.5:
                        # Match parziale - boost moderato
                        partial_bonus = (0.08 + 0.12 * strictness) * match_ratio
                        final_score = visual_score + partial_bonus
                        debug_info = f"MATCH PARZIALE (+{partial_bonus:.2f}) [{', '.join(match_details)}]"
                    else:
                        # Match insufficiente - penalty significativa
                        penalty = 0.05 + (0.15 * strictness)
                        final_score = visual_score - penalty
                        debug_info = f"MATCH SCARSO (-{penalty:.2f}) [{', '.join(match_details)}]"

                # Log dettagliato
                log_line = f"FILE: {filename[:25]:<25} | CLIP: {visual_score:.3f} | FINAL: {final_score:.3f} | LEN: {match_length if deep_search else 'N/A'} | {debug_info}"
                
                if final_score >= threshold:
                    logger.info(f"[AMMESSO]  {log_line}")
                    results.append((final_score, img))
                else:
                    logger.debug(f"[SCARTATO] {log_line}")

            except Exception as e:
                logger.error(f"Errore su {filename}: {str(e)}")

        results.sort(key=lambda x: x[0], reverse=True)
        
        # Preserva final_score negli oggetti immagine
        final_results = []
        for score, img in results:
            img['final_score'] = score
            final_results.append(img)
        
        return final_results

    def _tag_pipeline(self, query_text, candidates, fuzzy=True, include_description=True, include_title=True):
        """Pipeline Tag unica e definitiva: gestisce sia ricerca ESATTA che FUZZY."""
        results = []

        # 1. Preparazione Query
        if fuzzy:
            query_stems = self._get_stems(query_text)
            logger.info(f"🏷️ Tag Search [FUZZY] - Radici query: {query_stems}")
        else:
            query_terms = [self._normalize(t.strip()) for t in query_text.split() if t.strip()]
            logger.info(f"🏷️ Tag Search [EXACT] - Termini: {query_terms}")

        # 2. Ciclo di filtraggio con scoring
        for img in candidates:
            # Recupero e pulizia Tag (gestione stringa JSON o lista)
            raw_tags = img.get('tags', '[]')
            processed_tags = ""
            try:
                if isinstance(raw_tags, str) and raw_tags.startswith('['):
                    processed_tags = " ".join(json.loads(raw_tags))
                elif isinstance(raw_tags, list):
                    processed_tags = " ".join(raw_tags)
                else:
                    processed_tags = str(raw_tags)
            except:
                processed_tags = str(raw_tags)

            # Uniamo titolo, descrizione e tag per la ricerca
            title_text = str(img.get('title', '')) if include_title else ""
            desc_text = str(img.get('description', '')) if include_description else ""
            content_text = self._normalize(f"{title_text} {desc_text} {processed_tags}")
            
            # 3. Logica di Match con scoring
            if fuzzy:
                # Conta quanti stems matchano per calcolare score
                img_id = img.get('id')
                if img_id not in self.stems_cache:
                    self.stems_cache[img_id] = self._get_stems(content_text)
                img_stems = self.stems_cache[img_id]
                
                matched_stems = sum(1 for q_s in query_stems if q_s in img_stems)
                if matched_stems > 0:
                    # Score basato su % di match + lunghezza contenuto
                    match_ratio = matched_stems / len(query_stems)
                    content_bonus = min(0.1, len(content_text) / 1000)  # Bonus per contenuto ricco
                    final_score = match_ratio + content_bonus
                    
                    img['final_score'] = round(final_score, 3)
                    results.append(img)
            else:
                # Verifica che ogni termine esatto sia presente
                matched_terms = sum(1 for q_t in query_terms if q_t in content_text)
                if matched_terms > 0:
                    # Score per exact match
                    match_ratio = matched_terms / len(query_terms)
                    final_score = match_ratio + 0.1  # Base bonus per exact match
                    
                    img['final_score'] = round(final_score, 3)
                    results.append(img)
        
        # Ordina per score decrescente
        results.sort(key=lambda x: x.get('final_score', 0), reverse=True)
        return results

    def _get_stems(self, text):
        """Estrae stems/radici dalle parole del testo"""
        if not text:
            return set()
        
        # Normalizza e pulisci
        normalized = self._normalize(text)
        words = re.findall(r'\b\w{3,}\b', normalized)
        
        stems = set()
        for word in words:
            # Stem semplificato: primi 4 caratteri per parole > 4
            if len(word) > 4:
                stems.add(word[:4])
            else:
                stems.add(word)
        
        return stems
