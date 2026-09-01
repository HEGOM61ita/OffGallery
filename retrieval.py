# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024-2026 Michele Mulè <hegomm@gmail.com>
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
        # Motivo dell'ultimo risultato vuoto: permette alla UI di spiegare il
        # perché invece di mostrare solo "0 risultati".
        #   'no_candidates'  — i filtri escludono ogni foto (colpa dei filtri)
        #   'no_embeddings'  — foto presenti, ma senza impronta visiva (SigLIP)
        #   'old_embeddings' — impronte presenti ma di un modello precedente
        #                      (768 valori del vecchio CLIP contro i 1152 di
        #                      SigLIP): vanno rielaborate, NON riscaricato SigLIP
        #   None             — nessun esito vuoto da spiegare
        self.last_empty_reason = None

    def _plugin_columns(self) -> str:
        """Ritorna le colonne plugin che esistono nel DB, lette dai manifest installati.
        Gestisce DB creati prima dell'installazione dei plugin (colonne assenti)."""
        try:
            plugins_dir = Path(__file__).parent / 'plugins'
            candidates = []
            if plugins_dir.is_dir():
                for mpath in plugins_dir.rglob('manifest.json'):
                    try:
                        m = json.loads(mpath.read_text(encoding='utf-8'))
                        if m.get('type') == 'standalone':
                            candidates.extend(m.get('output_fields', []))
                    except Exception:
                        pass
            if not candidates:
                return ""
            self.db.cursor.execute("PRAGMA table_info(images)")
            existing = {row[1] for row in self.db.cursor.fetchall()}
            found = [c for c in dict.fromkeys(candidates) if c in existing]
            return (", " + ", ".join(found)) if found else ""
        except Exception:
            return ""

    def _cosine_similarity(self, v1, v2):
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0: return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))

    def _normalize(self, text):
        if not text: return ""
        return "".join(c for c in unicodedata.normalize('NFD', str(text).lower()) if unicodedata.category(c) != 'Mn')

    def search(self, query_text, mode="semantic", filters_sql=None, filter_params=None,
               deep_search=False, signal_callback=None, min_threshold=None, fuzzy=True, strictness=0.4, include_description=True, include_title=True, max_results=None, cancel_flag=None, query_emb=None):
        """
        Punto di ingresso della ricerca. 
        Ritorna una tupla: (lista_risultati, numero_candidati_totali_reali)
        """
        
        # Usa max_results passato come parametro, altrimenti default dalla config
        effective_limit = max_results if max_results is not None else self.max_results

        # Azzerato a ogni ricerca: vale solo per l'esito corrente
        self.last_empty_reason = None
        
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

        # 0-bis. NESSUN CANDIDATO
        # Vale per ogni modalità, campo vuoto compreso: se i filtri non lasciano
        # passare nemmeno una foto non c'è niente da confrontare, né embedding
        # né tag, e la causa è nei filtri — non nei modelli. Senza questa
        # distinzione l'utente vedeva accusare SigLIP per un filtro directory
        # rimasto attivo, e reinstallava l'ambiente Python per niente
        # (segnalato il 18/08/2026).
        if total_found_in_db == 0:
            self.last_empty_reason = 'no_candidates'
            logger.warning(
                "Ricerca senza risultati: i filtri attivi non lasciano passare "
                "nessuna foto (0 candidati). Non è un problema dei modelli: "
                "controllare i filtri, in particolare 'Ambito ricerca — Directory'."
            )
            return [], 0

        # 1. CONTROLLO QUERY VUOTA
        if not query_text.strip():
            # Solo filtri - restituiamo tutti i risultati filtrati senza processing AI
            plugin_cols = self._plugin_columns()
            base_sql = f"""
            SELECT id, filepath, filename, clip_embedding, tags, llm_tags, description, title,
                   camera_make, camera_model, lens_model, focal_length, aperture,
                   iso, shutter_speed, width, height, datetime_original,
                   datetime_digitized, datetime_modified, processed_date,
                   aesthetic_score, technical_score, lr_rating, color_label,
                   bioclip_taxonomy, geo_hierarchy, is_raw, orientation{plugin_cols}
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
        
        # 2. QUERY LANGUAGE
        # SigLIP è multilingua: la query viene passata direttamente senza traduzione IT→EN.
        # Per il matching tag/keyword si cerca con PIÙ varianti della query.
        #
        # _translate_to_tag_language presume che il testo in ingresso sia inglese
        # (nasce dalla vecchia pipeline CLIP, dove la query veniva prima tradotta
        # IT→EN). Con SigLIP quel passaggio non c'è più: la query arriva nella
        # lingua dell'utente. Passare "folaga" a un traduttore EN→IT restituisce
        # testo arbitrario, e il tag "Folaga" — presente nel database — non veniva
        # più trovato. Da qui la ricerca per tag muta in italiano.
        #
        # Soluzione: la query ORIGINALE è sempre una variante di ricerca; la
        # traduzione si aggiunge (utile a chi cerca in inglese contenuti italiani)
        # ma non sostituisce mai l'originale.
        query_en = query_text  # SigLIP non richiede EN: passata così com'è

        query_variants = [query_text]
        translated = self.embedding_gen._translate_to_tag_language(query_text)
        if translated and self._normalize(translated) != self._normalize(query_text):
            query_variants.append(translated)

        # Il deep search semantico riceve tutte le varianti unite: qui il match
        # è un bonus di punteggio parola-per-parola, non un filtro, quindi
        # l'unione non falsa i risultati e recupera anche il termine tradotto.
        query_tag = " ".join(query_variants)
        logger.info(f"🔤 Query: '{query_text}' | Varianti tag: {query_variants}")

        # 3. SQL FETCH — due passaggi per supportare cancel e minimizzare memoria:
        # Passaggio A: solo id + clip_embedding (blob pesanti, nessun metadato)
        #
        # Solo per la ricerca semantica: _tag_pipeline confronta esclusivamente
        # testo (tags, llm_tags, title, description, vernacular_name) e non tocca
        # mai gli embedding. Caricarli in modalità tag era inutile e — peggio —
        # il "if not emb_list: return" più sotto azzerava la ricerca per tag su
        # database senza embedding, dove invece i tag ci sono eccome.
        id_list  = []
        emb_list = []
        if mode == "semantic":
            emb_sql = "SELECT id, clip_embedding FROM images WHERE clip_embedding IS NOT NULL"
            if filters_sql:
                emb_sql += f" AND {filters_sql}"

            try:
                self.db.cursor.execute(emb_sql, filter_params or [])
            except Exception as e:
                logger.error(f"Errore SQL embedding fetch: {e}")
                return [], 0

            # Deserializzazione in batch con check cancel ogni 500 righe
            BATCH = 500
            while True:
                if cancel_flag is not None and cancel_flag():
                    logger.info("Ricerca annullata durante fetch embedding")
                    return [], 0
                rows = self.db.cursor.fetchmany(BATCH)
                if not rows:
                    break
                for row_id, raw_data in rows:
                    try:
                        if isinstance(raw_data, bytes):
                            if len(raw_data) >= 2 and raw_data[0] == 0x80 and raw_data[1] in (2, 3, 4, 5):
                                import pickle as _pk
                                emb_raw = _pk.loads(raw_data)
                                emb = np.array(emb_raw.get('image_embedding') if isinstance(emb_raw, dict) else emb_raw, dtype=np.float32)
                            elif len(raw_data) >= 4 and len(raw_data) % 4 == 0:
                                emb = np.frombuffer(raw_data, dtype=np.float32).copy()
                            else:
                                continue
                        else:
                            emb = np.array(raw_data, dtype=np.float32)
                        id_list.append(row_id)
                        emb_list.append(emb)
                    except Exception:
                        pass

            # Senza embedding la ricerca semantica non ha nulla da confrontare.
            # Vale solo qui: la pipeline tag lavora su testo e prosegue comunque.
            if not emb_list:
                # Qui le foto ci sono di sicuro (il caso "0 candidati" è già
                # uscito più su): mancano solo le impronte visive. Distinguere i
                # due casi conta — accusare SigLIP quando il colpevole era un
                # filtro directory ha mandato un utente a reinstallare protobuf
                # per niente (18/08/2026).
                self.last_empty_reason = 'no_embeddings'
                logger.warning(
                    f"Ricerca semantica senza risultati: nessuna delle "
                    f"{total_found_in_db} foto ha l'impronta visiva (SigLIP). "
                    f"Se SigLIP risulta già installato il problema è nel suo "
                    f"caricamento, non nel modello: cercare 'SigLIP' più su nel "
                    f"log. Altrimenti installarlo e rielaborare. In alternativa "
                    f"usare la ricerca per tag."
                )
                return [], 0

            logger.info(f"Embedding caricati: {len(emb_list)} su {total_found_in_db} totali")

        # 4. LOGICA DI SOGLIA
        threshold = min_threshold if min_threshold is not None else self.default_threshold

        # 5. DISPATCH PIPELINE
        if mode == "semantic":
            results = self._semantic_pipeline(
                query_tag, query_en, id_list, emb_list,
                deep_search, signal_callback, threshold, strictness,
                include_description, cancel_flag=cancel_flag,
                filters_sql=filters_sql, filter_params=filter_params,
                plugin_cols=self._plugin_columns(),
                precomputed_query_emb=query_emb,
            )
        else:
            # Tag pipeline: serve il fetch completo con metadati
            plugin_cols = self._plugin_columns()
            full_sql = f"""
            SELECT id, filepath, filename, clip_embedding, tags, llm_tags, description, title,
                   camera_make, camera_model, lens_model, focal_length, aperture,
                   iso, shutter_speed, width, height, datetime_original,
                   datetime_digitized, datetime_modified, processed_date,
                   aesthetic_score, technical_score, lr_rating, color_label,
                   bioclip_taxonomy, geo_hierarchy, is_raw, orientation{plugin_cols}
            FROM images
            """
            # Nessun vincolo su clip_embedding: la ricerca per tag confronta
            # testo, e una foto con i tag ma senza embedding va trovata lo stesso.
            if filters_sql:
                full_sql += f" WHERE {filters_sql}"
            self.db.cursor.execute(full_sql, filter_params or [])
            cols = [d[0] for d in self.db.cursor.description]
            tag_candidates = [dict(zip(cols, r)) for r in self.db.cursor.fetchall()]
            results = self._tag_pipeline(query_variants, tag_candidates, fuzzy=fuzzy, include_description=include_description, include_title=include_title)

        # 6. APPLICAZIONE LIMITE FINALE
        # Applichiamo il limite richiesto dall'utente sulla lista finale elaborata
        final_results = results[:effective_limit]

        return final_results, total_found_in_db
    
    def _semantic_pipeline(self, query_tag, query_en, id_list, emb_list,
                           deep_search, signal_callback, threshold, strictness,
                           include_description, cancel_flag=None,
                           filters_sql=None, filter_params=None, plugin_cols="",
                           precomputed_query_emb=None):
        """Pipeline semantica SigLIP + deep search testuale.

        Riceve id_list e emb_list già deserializzati dal fetch leggero.
        Carica i metadati solo per i candidati che superano la soglia.
        """
        import re
        import logging
        logger = logging.getLogger('root')
        results = []

        # 1. SigLIP EMBEDDING — usa quello pre-calcolato sul thread UI se disponibile
        if precomputed_query_emb is not None:
            query_emb = np.array(precomputed_query_emb, dtype=np.float32)
        else:
            res_query = self.embedding_gen.generate_embeddings(query_en)
            if not res_query:
                return []
            query_emb = np.array(res_query.get('text_embedding') if isinstance(res_query, dict) else res_query)
        expected_dim = query_emb.shape[0]

        # Filtra embedding con dimensione incompatibile
        valid_ids  = []
        valid_embs = []
        skipped = 0
        for img_id, emb in zip(id_list, emb_list):
            if emb.shape[0] != expected_dim:
                skipped += 1
                continue
            valid_ids.append(img_id)
            valid_embs.append(emb)

        if skipped:
            logger.warning(
                f"⚠️ {skipped} embedding ignorati (dimensione {emb_list[0].shape[0] if emb_list else '?'} "
                f"!= attesa {expected_dim}). Rielaborare le foto per rigenerare gli embedding SigLIP."
            )
        # Le impronte ci sono, ma di un modello precedente. Va segnalato anche
        # quando qualcuna compatibile sopravvive: con 21.000 foto escluse su
        # 21.500 la ricerca e' di fatto cieca, e senza spiegazione la UI
        # manderebbe a riscaricare SigLIP, che invece funziona benissimo.
        if skipped and skipped > len(valid_embs):
            self.last_empty_reason = 'old_embeddings'
            self._old_embeddings_count = skipped

        if not valid_embs:
            return []

        if cancel_flag is not None and cancel_flag():
            return []

        # 2. Similarità coseno vettorizzata — una sola operazione numpy
        emb_matrix   = np.stack(valid_embs)                         # (N, D)
        query_norm   = query_emb / (np.linalg.norm(query_emb) + 1e-8)
        row_norms    = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
        emb_norm     = emb_matrix / (row_norms + 1e-8)
        similarities = (emb_norm @ query_norm).astype(float)        # (N,)

        pre_threshold = (threshold - 0.40) if deep_search else threshold
        passing_indices = np.where(similarities >= pre_threshold)[0]
        logger.info(f"Pre-filtro SigLIP: {len(passing_indices)} candidati su {len(similarities)}")

        if cancel_flag is not None and cancel_flag():
            return []

        if not passing_indices.size:
            return []

        # 3. Fetch metadati solo per i candidati che superano la soglia
        passing_ids = [valid_ids[i] for i in passing_indices]
        placeholders = ",".join("?" * len(passing_ids))
        meta_sql = f"""
        SELECT id, filepath, filename, tags, llm_tags, description, title,
               camera_make, camera_model, lens_model, focal_length, aperture,
               iso, shutter_speed, width, height, datetime_original,
               datetime_digitized, datetime_modified, processed_date,
               aesthetic_score, technical_score, lr_rating, color_label,
               bioclip_taxonomy, geo_hierarchy, is_raw, orientation{plugin_cols}
        FROM images WHERE id IN ({placeholders})
        """
        try:
            self.db.cursor.execute(meta_sql, passing_ids)
            cols = [d[0] for d in self.db.cursor.description]
            meta_by_id = {row[0]: dict(zip(cols, row)) for row in self.db.cursor.fetchall()}
        except Exception as e:
            logger.error(f"Errore fetch metadati candidati: {e}")
            return []

        # 4. Deep search + scoring finale
        query_words  = [w.strip(",.?!").lower() for w in query_tag.split() if len(w) >= 3]
        match_length = max(4, min(9, 4 + int(strictness * 5)))

        for idx in passing_indices:
            img_id = valid_ids[idx]
            img = meta_by_id.get(img_id)
            if img is None:
                continue
            visual_score = float(similarities[idx])
            final_score  = visual_score
            debug_info   = "Solo SigLIP"

            if deep_search and query_words:
                desc      = str(img.get('description', '')).lower() if include_description else ""
                title     = str(img.get('title', '')).lower()
                tags      = str(img.get('tags', '[]')).lower()
                llm_tags  = str(img.get('llm_tags', '[]')).lower()
                vernacular = str(img.get('vernacular_name', '') or '').lower()
                full_text = f" {title} {desc} {tags} {llm_tags} {vernacular} ".replace('"', ' ').replace("'", " ").replace(",", " ").replace(".", " ")

                matches = 0
                match_details = []
                for word in query_words:
                    root = word[:min(match_length, len(word))]
                    if re.search(r'\b' + re.escape(root), full_text):
                        matches += 1
                        match_details.append(f"{word}→{root}✓")
                    else:
                        match_details.append(f"{word}→{root}✗")

                match_ratio = matches / len(query_words)
                if match_ratio == 1.0:
                    bonus = 0.15 + (0.25 * strictness)
                    final_score = visual_score + bonus
                    debug_info  = f"MATCH COMPLETO (+{bonus:.2f}) [{', '.join(match_details)}]"
                elif match_ratio >= 0.5:
                    partial_bonus = (0.08 + 0.12 * strictness) * match_ratio
                    final_score   = visual_score + partial_bonus
                    debug_info    = f"MATCH PARZIALE (+{partial_bonus:.2f}) [{', '.join(match_details)}]"
                else:
                    penalty     = 0.05 + (0.15 * strictness)
                    final_score = visual_score - penalty
                    debug_info  = f"MATCH SCARSO (-{penalty:.2f}) [{', '.join(match_details)}]"

            filename = img.get('filename', str(img_id))
            if final_score >= threshold:
                logger.info(f"[AMMESSO]  FILE: {filename[:25]:<25} | SigLIP: {visual_score:.3f} | FINAL: {final_score:.3f} | {debug_info}")
                results.append((final_score, img))
            else:
                logger.debug(f"[SCARTATO] {filename} score={final_score:.3f}")

        results.sort(key=lambda x: x[0], reverse=True)

        # Rilevamento spazio embedding incompatibile: se il miglior score è molto
        # basso, gli image embedding nel DB sono probabilmente generati con una
        # versione diversa di transformers → spazi non allineati → rielaborare foto
        if results:
            best_score = results[0][0]
            if best_score < 0.20 and len(valid_embs) > 5:
                logger.warning(
                    f"⚠️ Score CLIP massimo molto basso ({best_score:.3f}). "
                    f"Gli embedding nel database potrebbero essere incompatibili con il modello attuale. "
                    f"Rielaborare le foto dal tab Elaborazione per rigenerare gli embedding."
                )

        # Preserva final_score negli oggetti immagine
        final_results = []
        for score, img in results:
            img['final_score'] = score
            final_results.append(img)

        return final_results

    def _tag_pipeline(self, query_text, candidates, fuzzy=True, include_description=True, include_title=True):
        """Pipeline Tag unica e definitiva: gestisce sia ricerca ESATTA che FUZZY.

        query_text accetta una stringa oppure una lista di varianti della query
        (es. originale + traduzione). Con più varianti un'immagine è un risultato
        se corrisponde ad almeno una: così "folaga" trova i tag italiani anche
        quando la traduzione automatica produce un termine diverso.
        """
        results = []

        # 1. Preparazione Query — normalizza l'ingresso a lista di varianti
        variants = [query_text] if isinstance(query_text, str) else list(query_text)
        variants = [v for v in variants if v and str(v).strip()]
        if not variants:
            return []

        if fuzzy:
            # Un set di stems per variante: il match richiede che UNA variante
            # sia soddisfatta, non l'unione indiscriminata di tutte (che
            # gonfierebbe il denominatore di match_ratio falsando lo score).
            variant_stems = [self._get_stems(v) for v in variants]
            variant_stems = [s for s in variant_stems if s]
            if not variant_stems:
                return []
            logger.info(f"🏷️ Tag Search [FUZZY] - Radici per variante: {[sorted(s) for s in variant_stems]}")
        else:
            variant_terms = []
            for v in variants:
                terms = [self._normalize(t.strip()) for t in str(v).split() if t.strip()]
                if terms:
                    variant_terms.append(terms)
            if not variant_terms:
                return []
            logger.info(f"🏷️ Tag Search [EXACT] - Termini per variante: {variant_terms}")

        # 2. Ciclo di filtraggio con scoring
        for img in candidates:
            # Recupero e pulizia Tag — unisce tag umani e tag LLM
            def _parse_tags_field(raw):
                try:
                    if isinstance(raw, str) and raw.startswith('['):
                        return json.loads(raw)
                    elif isinstance(raw, list):
                        return raw
                    elif raw:
                        return [str(raw)]
                except Exception:
                    pass
                return []

            all_tags = _parse_tags_field(img.get('tags', '[]')) + _parse_tags_field(img.get('llm_tags', '[]'))
            processed_tags = " ".join(all_tags)

            title_text = str(img.get('title', '')) if include_title else ""
            desc_text = str(img.get('description', '')) if include_description else ""
            vernacular_text = str(img.get('vernacular_name', '') or '')
            content_text = self._normalize(f"{title_text} {desc_text} {processed_tags} {vernacular_text}")
            
            # 3. Logica di Match con scoring
            if fuzzy:
                # Conta quanti stems matchano per calcolare score
                img_id = img.get('id')
                if img_id not in self.stems_cache:
                    self.stems_cache[img_id] = self._get_stems(content_text)
                img_stems = self.stems_cache[img_id]

                # Ogni variante è valutata a sé: vince il rapporto di match
                # migliore, così una traduzione infelice non penalizza la query
                # originale (e viceversa).
                best_ratio = 0.0
                for q_stems in variant_stems:
                    matched_stems = sum(1 for q_s in q_stems if q_s in img_stems)
                    if matched_stems:
                        best_ratio = max(best_ratio, matched_stems / len(q_stems))

                if best_ratio > 0:
                    content_bonus = min(0.1, len(content_text) / 1000)  # Bonus per contenuto ricco
                    final_score = best_ratio + content_bonus

                    img['final_score'] = round(final_score, 3)
                    results.append(img)
            else:
                # Verifica che ogni termine esatto sia presente
                best_ratio = 0.0
                for q_terms in variant_terms:
                    matched_terms = sum(1 for q_t in q_terms if q_t in content_text)
                    if matched_terms:
                        best_ratio = max(best_ratio, matched_terms / len(q_terms))

                if best_ratio > 0:
                    final_score = best_ratio + 0.1  # Base bonus per exact match

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
