"""
Database Manager - Schema definitivo con campi separati
Versione pulita senza migrazioni - richiede database ricreato da zero
UNIFIED: Campo tags per user/ai tags, bioclip_taxonomy separato per tassonomia BioCLIP
"""

import sqlite3
import logging
import json
import pickle
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Gestore database con schema completo XMP Lightroom e tags unificati"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.init_database()
    
    def init_database(self):
        """Inizializza database con schema completo"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            self.create_tables()
            
        except Exception as e:
            logger.error(f"Errore inizializzazione database: {e}")
            raise
    
    def create_tables(self):
        """Crea schema tabelle con supporto completo XMP Lightroom"""
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                filepath TEXT NOT NULL,
                file_size INTEGER,
                file_format TEXT,
                file_hash TEXT UNIQUE,
                
                -- ===== RAW INFO =====
                is_raw BOOLEAN,                -- True se file RAW
                raw_format TEXT,               -- Estensione RAW: orf, cr2, nef, arw
                raw_info TEXT,                 -- JSON con info RAW processing
                
                -- ===== DIMENSIONI =====
                width INTEGER,
                height INTEGER,
                aspect_ratio REAL,
                megapixels REAL,
                
                -- ===== EXIF FOTOGRAFICI BASE =====
                camera_make TEXT,
                camera_model TEXT,
                lens_model TEXT,
                focal_length REAL,
                focal_length_35mm REAL,
                aperture REAL,
                shutter_speed TEXT,
                shutter_speed_decimal REAL,
                iso INTEGER,
                
                -- ===== EXIF AVANZATI =====
                exposure_mode TEXT,
                exposure_bias REAL,
                metering_mode TEXT,
                white_balance TEXT,
                flash_used BOOLEAN,
                flash_mode TEXT,
                color_space TEXT,
                orientation INTEGER,
                
                -- ===== DATE =====
                datetime_original TEXT,
                datetime_digitized TEXT,
                datetime_modified TEXT,
                
                -- ===== GPS BASE =====
                gps_latitude REAL,
                gps_longitude REAL,
                gps_altitude REAL,
                gps_direction REAL,
                
                -- ===== METADATA AUTORE =====
                artist TEXT,
                copyright TEXT,
                software TEXT,
                
                -- ===== XMP LIGHTROOM COMPLETI =====
                title TEXT,                    -- Lightroom Title
                description TEXT,              -- Unified description field
                lr_rating INTEGER,             -- Rating stelle (1-5) 
                color_label TEXT,              -- Color Label Lightroom
                lr_instructions TEXT,          -- Instructions speciali
                
                -- ===== GPS ESTESO =====
                gps_city TEXT,                 -- Città GPS
                gps_state TEXT,                -- Stato/Provincia GPS  
                gps_country TEXT,              -- Paese GPS
                gps_location TEXT,             -- Location/SubLocation GPS
                
                -- ===== EXIF COMPLETO GREZZO =====
                exif_json TEXT,
                
                -- ===== EMBEDDING =====
                clip_embedding BLOB,
                dinov2_embedding BLOB,
                aesthetic_score REAL,
                technical_score REAL,
                is_monochrome BOOLEAN DEFAULT 0,  -- Rilevamento automatico B/N
                
                -- ===== TAGGING =====
                tags TEXT,                     -- Tags LLM + user (JSON array, NO bioclip)
                bioclip_taxonomy TEXT,          -- Tassonomia BioCLIP completa JSON [kingdom,phylum,class,order,family,genus,species]
                geo_hierarchy TEXT,             -- Gerarchia geografica 'Geo|Continent|Country|Region|City'
                
                -- ===== LLM VISION =====
                ai_description_hash TEXT,
                model_used TEXT,
                
                -- ===== PROCESSING INFO =====
                processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processing_time REAL,
                embedding_generated BOOLEAN DEFAULT 0,
                llm_generated BOOLEAN DEFAULT 0,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                app_version TEXT,
                
                -- ===== SYNC STATE =====
                sync_state TEXT DEFAULT 'pending',
                last_xmp_mtime DATETIME,
                last_sync_at DATETIME,
                last_sync_check_at DATETIME,
                last_import_mtime DATETIME
            )
        """)
        
        # Indici per performance
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_filename ON images(filename)",
            "CREATE INDEX IF NOT EXISTS idx_file_hash ON images(file_hash)",
            "CREATE INDEX IF NOT EXISTS idx_camera_model ON images(camera_model)",
            "CREATE INDEX IF NOT EXISTS idx_datetime_original ON images(datetime_original)",
            "CREATE INDEX IF NOT EXISTS idx_focal_length ON images(focal_length)",
            "CREATE INDEX IF NOT EXISTS idx_iso ON images(iso)",
            "CREATE INDEX IF NOT EXISTS idx_gps_lat ON images(gps_latitude)",
            "CREATE INDEX IF NOT EXISTS idx_gps_lon ON images(gps_longitude)",
            "CREATE INDEX IF NOT EXISTS idx_aesthetic_score ON images(aesthetic_score)",
            "CREATE INDEX IF NOT EXISTS idx_technical_score ON images(technical_score)",
            "CREATE INDEX IF NOT EXISTS idx_is_monochrome ON images(is_monochrome)",
            "CREATE INDEX IF NOT EXISTS idx_embedding_generated ON images(embedding_generated)",
            "CREATE INDEX IF NOT EXISTS idx_processed_date ON images(processed_date)",
            "CREATE INDEX IF NOT EXISTS idx_tags ON images(tags)",
            "CREATE INDEX IF NOT EXISTS idx_lr_rating ON images(lr_rating)",
        ]
        
        for index_sql in indices:
            self.cursor.execute(index_sql)
        
        self.conn.commit()
        logger.info(f"Database schema completo inizializzato: {self.db_path}")
    
    def insert_image(self, image_data: Dict[str, Any]) -> Optional[int]:
        """
        Inserisci nuova immagine con supporto completo XMP Lightroom
        
        Returns:
            int: ID del record inserito o None se errore
        """
        try:
            # Prepara embedding per storage
            clip_blob = self._serialize_embedding(image_data.get('clip_embedding'))
            dinov2_blob = self._serialize_embedding(image_data.get('dinov2_embedding'))
            
            self.cursor.execute("""
                INSERT INTO images (
                    filename, filepath, file_size, file_format, file_hash,
                    is_raw, raw_format, raw_info,
                    width, height, aspect_ratio, megapixels,
                    camera_make, camera_model, lens_model,
                    focal_length, focal_length_35mm, aperture,
                    shutter_speed, shutter_speed_decimal, iso,
                    exposure_mode, exposure_bias, metering_mode,
                    white_balance, flash_used, flash_mode,
                    color_space, orientation,
                    datetime_original, datetime_digitized, datetime_modified,
                    gps_latitude, gps_longitude, gps_altitude, gps_direction,
                    artist, copyright, software,
                    title, description, lr_rating, color_label, lr_instructions,
                    gps_city, gps_state, gps_country, gps_location,
                    exif_json,
                    clip_embedding, dinov2_embedding, aesthetic_score, technical_score, is_monochrome,
                    tags, bioclip_taxonomy, geo_hierarchy,
                    ai_description_hash, model_used,
                    processing_time, embedding_generated, llm_generated, success, error_message, app_version,
                    sync_state, last_xmp_mtime, last_sync_at, last_sync_check_at, last_import_mtime, processed_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                # File base
                image_data.get('filename'),
                image_data.get('filepath'),
                image_data.get('file_size'),
                image_data.get('file_format'),
                image_data.get('file_hash'),
                
                
                image_data.get('is_raw', False),
                image_data.get('raw_format'),
                image_data.get('raw_info'),
                
                # Dimensioni
                image_data.get('width'),
                image_data.get('height'),
                image_data.get('aspect_ratio'),
                image_data.get('megapixels'),
                
                # EXIF base - CORRETTO: prende i dati dal dizionario principale
                image_data.get('camera_make'),
                image_data.get('camera_model'),
                image_data.get('lens_model'),
                image_data.get('focal_length'),
                image_data.get('focal_length_35mm'),
                image_data.get('aperture'),
                image_data.get('shutter_speed'),
                image_data.get('shutter_speed_decimal'),
                image_data.get('iso'),
                
                # EXIF avanzati - CORRETTO
                image_data.get('exposure_mode'),
                image_data.get('exposure_bias'),
                image_data.get('metering_mode'),
                image_data.get('white_balance'),
                image_data.get('flash_used'),
                image_data.get('flash_mode'),
                image_data.get('color_space'),
                image_data.get('orientation'),
                
                # Date - CORRETTO
                image_data.get('datetime_original'),
                image_data.get('datetime_digitized'),
                image_data.get('datetime_modified'),
                
                # GPS base - CORRETTO  
                image_data.get('gps_latitude'),
                image_data.get('gps_longitude'),
                image_data.get('gps_altitude'),
                image_data.get('gps_direction'),
                
                # Metadata autore - CORRETTO
                image_data.get('artist'),
                image_data.get('copyright'),
                image_data.get('software'),
                
                # ===== XMP LIGHTROOM COMPLETI =====
                image_data.get('title'),                    # Lightroom Title
                image_data.get('description'),              # Unified description
                image_data.get('lr_rating'),                # Rating stelle
                image_data.get('color_label'),              # Color Label
                image_data.get('lr_instructions'),          # Instructions
                
                # GPS esteso
                image_data.get('gps_city'),
                image_data.get('gps_state'),
                image_data.get('gps_country'),
                image_data.get('gps_location'),
                
                # EXIF completo
                image_data.get('exif_json'),
                
                # Embedding
                clip_blob,
                dinov2_blob,
                image_data.get('aesthetic_score'),
                image_data.get('technical_score'),
                image_data.get('is_monochrome', 0),  # Campo aggiunto
                
                # Tags LLM + user (JSON)
                image_data.get('tags'),
                # Tassonomia BioCLIP completa (JSON)
                image_data.get('bioclip_taxonomy'),
                # Gerarchia geografica
                image_data.get('geo_hierarchy'),

                # LLM
                image_data.get('ai_description_hash'),
                image_data.get('model_used'),
                image_data.get('processing_time'),
                
                # Processing info
                image_data.get('embedding_generated', False),
                image_data.get('llm_generated', False),
                image_data.get('success', True),
                image_data.get('error_message'),
                image_data.get('app_version', '1.0'),
                
                # Sync state  
                'pending',
                None,  # last_xmp_mtime
                None,  # last_sync_at
                None,  # last_sync_check_at
                None,  # last_import_mtime
                datetime.now().isoformat()
            ))
            
            image_id = self.cursor.lastrowid
            self.conn.commit()
            
            logger.debug(f"Immagine inserita: {image_data.get('filename')} (ID: {image_id})")
            return image_id
            
        except Exception as e:
            logger.error(f"Errore insert_image: {e}")
            return None
    
    def _serialize_embedding(self, embedding) -> Optional[bytes]:
        """Serializza embedding numpy come raw float32 bytes per storage database"""
        if embedding is None:
            return None
        if isinstance(embedding, np.ndarray):
            return embedding.astype(np.float32).tobytes()
        return None
    
    def _deserialize_embedding(self, embedding_blob) -> Optional[np.ndarray]:
        """Deserializza embedding dal database (raw float32 bytes o pickle legacy)"""
        if embedding_blob is None:
            return None
        try:
            if isinstance(embedding_blob, bytes):
                # Pickle protocol 2-5: header \x80 + byte protocollo (0x02-0x05)
                if len(embedding_blob) >= 2 and embedding_blob[0] == 0x80 and embedding_blob[1] in (2, 3, 4, 5):
                    return pickle.loads(embedding_blob)
                # Raw float32 bytes: qualsiasi dimensione multipla di 4
                if len(embedding_blob) >= 4 and len(embedding_blob) % 4 == 0:
                    return np.frombuffer(embedding_blob, dtype=np.float32).copy()
            return None
        except Exception as e:
            logger.debug(f"Errore deserializzazione embedding: {e}")
            return None
    
    def get_image_by_filepath(self, filepath):
        """Recupera record immagine per filepath completo"""
        try:
            self.cursor.execute("SELECT * FROM images WHERE filepath = ?", (str(filepath),))
            result = self.cursor.fetchone()
            
            if result:
                columns = [description[0] for description in self.cursor.description]
                return dict(zip(columns, result))
            return None
            
        except Exception as e:
            logger.error(f"Errore get_image_by_filepath: {e}")
            return None
    
    def image_exists(self, filename):
        """Verifica se immagine è già stata processata"""
        try:
            self.cursor.execute("SELECT id FROM images WHERE filename = ?", (filename,))
            return self.cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Errore image_exists: {e}")
            return False
    
    def hash_exists(self, file_hash):
        """Verifica se hash file già presente (deduplicazione)"""
        if not file_hash:
            return False
        try:
            self.cursor.execute("SELECT id, filename FROM images WHERE file_hash = ?", (file_hash,))
            result = self.cursor.fetchone()
            if result:
                logger.info(f"File duplicato rilevato: hash={file_hash[:8]}... (originale: {result[1]})")
            return result is not None
        except Exception as e:
            logger.error(f"Errore hash_exists: {e}")
            return False
    
    def get_all_images(self):
        """Recupera tutte le immagini dal database"""
        try:
            self.cursor.execute("SELECT * FROM images ORDER BY processed_date DESC")
            results = self.cursor.fetchall()
            
            if results:
                columns = [description[0] for description in self.cursor.description]
                return [dict(zip(columns, row)) for row in results]
            return []
            
        except Exception as e:
            logger.error(f"Errore get_all_images: {e}")
            return []
    
    def get_stats(self):
        """Recupera statistiche database"""
        try:
            stats = {}
            
            # Conteggi base
            self.cursor.execute("SELECT COUNT(*) FROM images")
            stats['total_images'] = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM images WHERE embedding_generated = 1")
            stats['with_embeddings'] = self.cursor.fetchone()[0]
            
            self.cursor.execute("SELECT COUNT(*) FROM images WHERE tags IS NOT NULL")
            stats['with_tags'] = self.cursor.fetchone()[0]
            
            return stats
            
        except Exception as e:
            logger.error(f"Errore get_stats: {e}")
            return {}
    
    
    def update_image_tags(self, image_id: int, tags: List[str]) -> bool:
        """Aggiorna tags per un'immagine specifica"""
        try:
            tags_json = json.dumps(tags) if tags else None
            self.cursor.execute(
                "UPDATE images SET tags = ? WHERE id = ?",
                (tags_json, image_id)
            )
            self.conn.commit()
            
            rows_affected = self.cursor.rowcount
            if rows_affected > 0:
                logger.info(f"Tags aggiornati per image_id {image_id}: {tags}")
                return True
            else:
                logger.warning(f"Nessuna immagine trovata con id {image_id}")
                return False
                
        except Exception as e:
            logger.error(f"Errore update_image_tags: {e}")
            self.conn.rollback()
            return False
    
    def update_bioclip_taxonomy(self, image_id: int, taxonomy: List[str]) -> bool:
        """Aggiorna tassonomia BioCLIP per un'immagine"""
        try:
            taxonomy_json = json.dumps(taxonomy) if taxonomy else None
            self.cursor.execute(
                "UPDATE images SET bioclip_taxonomy = ? WHERE id = ?",
                (taxonomy_json, image_id)
            )
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logger.info(f"BioCLIP taxonomy aggiornata per image_id {image_id}")
                return True
            else:
                logger.warning(f"Nessuna immagine trovata con id {image_id}")
                return False
        except Exception as e:
            logger.error(f"Errore update_bioclip_taxonomy: {e}")
            self.conn.rollback()
            return False

    def get_bioclip_taxonomy(self, image_id: int) -> Optional[List[str]]:
        """Ottieni tassonomia BioCLIP per un'immagine"""
        try:
            self.cursor.execute(
                "SELECT bioclip_taxonomy FROM images WHERE id = ?",
                (image_id,)
            )
            result = self.cursor.fetchone()
            if result and result[0]:
                return json.loads(result[0])
            return None
        except Exception as e:
            logger.error(f"Errore get_bioclip_taxonomy: {e}")
            return None

    def update_geo_hierarchy(self, image_id: int, geo_hierarchy: str) -> bool:
        """Aggiorna gerarchia geografica per un'immagine"""
        try:
            self.cursor.execute(
                "UPDATE images SET geo_hierarchy = ? WHERE id = ?",
                (geo_hierarchy, image_id)
            )
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logger.info(f"Geo hierarchy aggiornata per image_id {image_id}: {geo_hierarchy}")
                return True
            else:
                logger.warning(f"Nessuna immagine trovata con id {image_id}")
                return False
        except Exception as e:
            logger.error(f"Errore update_geo_hierarchy: {e}")
            self.conn.rollback()
            return False

    def get_geo_hierarchy(self, image_id: int) -> Optional[str]:
        """Ottieni gerarchia geografica per un'immagine"""
        try:
            self.cursor.execute(
                "SELECT geo_hierarchy FROM images WHERE id = ?",
                (image_id,)
            )
            result = self.cursor.fetchone()
            return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Errore get_geo_hierarchy: {e}")
            return None

    def update_image_description(self, image_id: int, description: str) -> bool:
        """Aggiorna descrizione per un'immagine specifica"""
        try:
            self.cursor.execute(
                "UPDATE images SET description = ? WHERE id = ?",
                (description, image_id)
            )
            self.conn.commit()
            
            rows_affected = self.cursor.rowcount
            if rows_affected > 0:
                logger.info(f"Descrizione aggiornata per image_id {image_id}: {description[:50]}...")
                return True
            else:
                logger.warning(f"Nessuna immagine trovata con id {image_id}")
                return False
                
        except Exception as e:
            logger.error(f"Errore update_image_description: {e}")
            self.conn.rollback()
            return False
    
    def update_image_title(self, image_id: int, title: str) -> bool:
        """Aggiorna title per un'immagine specifica"""
        try:
            self.cursor.execute(
                "UPDATE images SET title = ? WHERE id = ?",
                (title, image_id)
            )
        
            if self.cursor.rowcount > 0:
                self.conn.commit()
                logger.info(f"Title aggiornato per image_id {image_id}: {title}")
                return True
            else:
                logger.warning(f"Nessuna immagine trovata con id {image_id}")
                return False
            
        except Exception as e:
            logger.error(f"Errore update_image_title: {e}")
            self.conn.rollback()
            return False

    def update_image_title(self, image_id: int, title: str) -> bool:
        """Aggiorna title per un'immagine specifica"""
        try:
            self.cursor.execute(
                "UPDATE images SET title = ? WHERE id = ?",
                (title, image_id)
            )
        
            if self.cursor.rowcount > 0:
                self.conn.commit()
                logger.info(f"Title aggiornato per image_id {image_id}: {title}")
                return True
            else:
                logger.warning(f"Nessuna immagine trovata con id {image_id}")
                return False
            
        except Exception as e:
            logger.error(f"Errore update_image_title: {e}")
            self.conn.rollback()
            return False

    def update_title(self, image_id: int, title: str) -> bool:
        """Alias per update_image_title"""
        return self.update_image_title(image_id, title)

    def update_title(self, image_id: int, title: str) -> bool:
        """Alias per update_image_title"""
        return self.update_image_title(image_id, title)
    
    def update_image_metadata(self, image_id: int, **kwargs) -> bool:
        """Aggiorna metadata multipli per un'immagine specifica"""
        try:
            if not kwargs:
                logger.warning("Nessun campo da aggiornare specificato")
                return False
            
            # Costruisci query dinamicamente
            fields = []
            values = []
            
            for field, value in kwargs.items():
                if field == 'tags' and isinstance(value, list):
                    fields.append("tags = ?")
                    values.append(json.dumps(value))
                elif field in ('clip_embedding', 'dinov2_embedding'):
                    fields.append(f"{field} = ?")
                    values.append(self._serialize_embedding(value))
                else:
                    fields.append(f"{field} = ?")
                    values.append(value)
            
            values.append(image_id)  # Per la WHERE clause
            
            query = f"UPDATE images SET {', '.join(fields)} WHERE id = ?"
            self.cursor.execute(query, values)
            self.conn.commit()
            
            rows_affected = self.cursor.rowcount
            if rows_affected > 0:
                logger.info(f"Metadata aggiornati per image_id {image_id}: {list(kwargs.keys())}")
                return True
            else:
                logger.warning(f"Nessuna immagine trovata con id {image_id}")
                return False
                
        except Exception as e:
            logger.error(f"Errore update_image_metadata: {e}")
            self.conn.rollback()
            return False

    def delete_image(self, image_id: int) -> bool:
        """
        Elimina un'immagine dal database.
        NON elimina il file fisico, solo il record nel DB.

        Args:
            image_id: ID dell'immagine da eliminare

        Returns:
            True se eliminata con successo, False altrimenti
        """
        try:
            # Verifica che l'immagine esista
            self.cursor.execute("SELECT filename FROM images WHERE id = ?", (image_id,))
            result = self.cursor.fetchone()

            if not result:
                logger.warning(f"Nessuna immagine trovata con id {image_id}")
                return False

            filename = result[0]

            # Elimina il record
            self.cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))
            self.conn.commit()

            rows_affected = self.cursor.rowcount
            if rows_affected > 0:
                logger.info(f"🗑️ Immagine eliminata dal DB: {filename} (id={image_id})")
                return True
            else:
                logger.warning(f"Eliminazione fallita per id {image_id}")
                return False

        except Exception as e:
            logger.error(f"Errore delete_image: {e}")
            self.conn.rollback()
            return False

    def delete_images(self, image_ids: List[int]) -> int:
        """
        Elimina multiple immagini dal database.

        Args:
            image_ids: Lista di ID delle immagini da eliminare

        Returns:
            Numero di immagini eliminate con successo
        """
        deleted_count = 0
        try:
            for image_id in image_ids:
                if self.delete_image(image_id):
                    deleted_count += 1
            return deleted_count
        except Exception as e:
            logger.error(f"Errore delete_images: {e}")
            return deleted_count
    
    # ═══════════════════════════════════════════════════════════════
    #                       ALIAS PER COMPATIBILITÀ
    # ═══════════════════════════════════════════════════════════════
    
    def update_image(self, filename: str, image_data: Dict[str, Any]) -> bool:
        """
        Aggiorna un'immagine esistente con tutti i nuovi dati
        Metodo principale per riprocessing - usa filename invece di image_id
        """
        try:
            # Prova prima con filename esatto, poi con solo il nome del file
            self.cursor.execute("SELECT id FROM images WHERE filename = ?", (filename,))
            result = self.cursor.fetchone()
            
            if not result:
                # Fallback: cerca per nome file (parte finale del path)
                from pathlib import Path
                filename_only = Path(filename).name
                self.cursor.execute("SELECT id FROM images WHERE filename LIKE ?", (f'%{filename_only}',))
                result = self.cursor.fetchone()
            
            if not result:
                logger.warning(f"Immagine non trovata per update: {filename}")
                return False
            
            image_id = result[0]
            
            # Lista delle colonne valide nel database (dalla create_tables)
            valid_columns = {
                'filename', 'filepath', 'file_size', 'file_format', 'file_hash',
                'is_raw', 'raw_format', 'raw_info',  # RAW INFO
                'width', 'height', 'aspect_ratio', 'megapixels',
                'camera_make', 'camera_model', 'lens_model',
                'focal_length', 'focal_length_35mm', 'aperture',
                'shutter_speed', 'shutter_speed_decimal', 'iso',
                'exposure_mode', 'exposure_bias', 'metering_mode',
                'white_balance', 'flash_used', 'flash_mode',
                'color_space', 'orientation',
                'datetime_original', 'datetime_digitized', 'datetime_modified',
                'gps_latitude', 'gps_longitude', 'gps_altitude', 'gps_direction',
                'artist', 'copyright', 'software',
                'title', 'description', 'lr_rating', 'color_label', 'lr_instructions',
                'gps_city', 'gps_state', 'gps_country', 'gps_location',
                'exif_json',
                'clip_embedding', 'dinov2_embedding', 'aesthetic_score', 'technical_score', 'is_monochrome',
                'tags',
                'ai_description_hash', 'model_used',
                'processing_time', 'embedding_generated', 'llm_generated', 'success', 'error_message', 'app_version',
                'sync_state', 'last_xmp_mtime', 'last_sync_at', 'last_sync_check_at', 'last_import_mtime', 'processed_date'
            }
            
            # Filtra solo i campi validi dal database
            update_data = {}
            for key, value in image_data.items():
                if key in valid_columns and key not in {'id', 'filename', 'filepath', 'file_hash'}:
                    update_data[key] = value
            
            if not update_data:
                logger.warning(f"Nessun campo valido da aggiornare per {filename}")
                return False
            
            # Usa update_image_metadata esistente
            success = self.update_image_metadata(image_id, **update_data)
            
            if success:
                logger.info(f"✅ Aggiornata immagine: {filename} ({len(update_data)} campi)")
            else:
                logger.error(f"❌ Fallito aggiornamento per: {filename}")
            
            return success
            
        except Exception as e:
            logger.error(f"Errore update_image per {filename}: {e}")
            return False

    def update_tags(self, image_id: int, tags: List[str]) -> bool:
        """Alias per update_image_tags"""
        return self.update_image_tags(image_id, tags)
    
    def update_description(self, image_id: int, description: str) -> bool:
        """Alias per update_image_description"""
        return self.update_image_description(image_id, description)
    
    def set_tags(self, image_id: int, tags: List[str]) -> bool:
        """Alias per update_image_tags"""
        return self.update_image_tags(image_id, tags)
    
    def set_description(self, image_id: int, description: str) -> bool:
        """Alias per update_image_description"""
        return self.update_image_description(image_id, description)
    
    def update_metadata(self, image_id: int, **kwargs) -> bool:
        """Alias per update_image_metadata"""
        return self.update_image_metadata(image_id, **kwargs)
    
    def close(self):
        """Chiudi connessione database thread-safe"""
        try:
            if hasattr(self, 'conn') and self.conn:
                self.conn.close()
        except sqlite3.ProgrammingError:
            # Ignora errori thread se oggetto creato in thread diverso
            pass
        except Exception as e:
            logger.debug(f"Database close error: {e}")

    def __del__(self):
        """Destructor thread-safe"""
        try:
            self.close()
        except:
            # Ignora tutti gli errori nel destructor
            pass
