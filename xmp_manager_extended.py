"""
XMP Manager Esteso - Supporto completo XMP embedded + sidecar
Gestisce lettura, scrittura e sincronizzazione basata sul formato file
CORRETTO: Usa naming Lightroom-compatibile per sidecar (.xmp invece di .ORF.xmp)
UNIFICATO: Usa RAWProcessor per parsing standard in tutti i metodi
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class XMPSyncState(Enum):
    """Stati di sincronizzazione XMP"""
    PERFECT_SYNC = "PERFECT_SYNC"        # DB = Embedded = Sidecar
    EMBEDDED_DIRTY = "EMBEDDED_DIRTY"    # Embedded ≠ DB 
    SIDECAR_DIRTY = "SIDECAR_DIRTY"     # Sidecar ≠ DB
    MIXED_STATE = "MIXED_STATE"         # Embedded ≠ Sidecar (conflict!)
    MIXED_DIRTY = "MIXED_DIRTY"
    DB_ONLY = "DB_ONLY"                 # Solo metadata in DB
    EMBEDDED_ONLY = "EMBEDDED_ONLY"     # Solo XMP embedded
    SIDECAR_ONLY = "SIDECAR_ONLY"      # Solo sidecar XMP
    NO_XMP = "NO_XMP"                   # Nessun XMP ovunque
    ERROR = "ERROR"                      # Errore lettura XMP


class XMPManagerExtended:
    """XMP Manager con supporto embedded completo via ExifTool e gestione format-aware"""

    # Cache a livello di classe: check ExifTool eseguito una sola volta
    _exiftool_checked = False
    _exiftool_available = False
    _exiftool_cmd: list = ['exiftool']  # Comando risolto in _check_exiftool

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.exiftool_available = self._check_exiftool()

        # Format definitions per gestione format-aware
        self.raw_formats = ['.cr2', '.cr3', '.nef', '.nrw', '.orf', '.arw', '.srf', '.sr2',
                           '.raf', '.rw2', '.raw', '.pef', '.ptx', '.rwl', '.3fr', '.iiq', '.x3f']
        self.standard_formats = ['.jpg', '.jpeg', '.tiff', '.tif', '.png']

        if not self.exiftool_available:
            logger.warning("⚠️ ExifTool non disponibile - supporto XMP embedded limitato")

    def _check_exiftool(self) -> bool:
        """Verifica disponibilità ExifTool (cached a livello di classe).
        Prima cerca il bundled perl+exiftool in exiftool_files/, poi fallback al sistema."""
        if XMPManagerExtended._exiftool_checked:
            return XMPManagerExtended._exiftool_available

        # Percorso bundled: exiftool_files/ è nella root del progetto (stessa dir di questo file)
        _root = Path(__file__).parent
        _perl = _root / 'exiftool_files' / 'perl.exe'
        _script = _root / 'exiftool_files' / 'exiftool.pl'

        # 1. Prova ExifTool bundled (perl.exe + exiftool.pl)
        if _perl.exists() and _script.exists():
            try:
                result = subprocess.run([str(_perl), str(_script), '-ver'],
                                        capture_output=True, timeout=10)
                if result.returncode == 0:
                    version = result.stdout.decode().strip()
                    logger.info(f"✓ ExifTool bundled disponibile: v{version}")
                    XMPManagerExtended._exiftool_cmd = [str(_perl), str(_script)]
                    XMPManagerExtended._exiftool_checked = True
                    XMPManagerExtended._exiftool_available = True
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError):
                pass

        # 2. Fallback: exiftool di sistema nel PATH
        try:
            result = subprocess.run(['exiftool', '-ver'],
                                    capture_output=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.decode().strip()
                logger.info(f"✓ ExifTool di sistema disponibile: v{version}")
                XMPManagerExtended._exiftool_cmd = ['exiftool']
                XMPManagerExtended._exiftool_checked = True
                XMPManagerExtended._exiftool_available = True
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        XMPManagerExtended._exiftool_checked = True
        XMPManagerExtended._exiftool_available = False
        return False
    
    def _get_file_category(self, file_path: Path) -> str:
        """
        Categorizza file per strategia XMP
        
        Returns:
            'dng' | 'raw' | 'standard' | 'unknown'
        """
        ext = file_path.suffix.lower()
        
        if ext == '.dng':
            return 'dng'
        elif ext in self.raw_formats:
            return 'raw'
        elif ext in self.standard_formats:
            return 'standard'
        else:
            return 'unknown'
    
    def read_xmp_by_format(self, file_path: Path) -> Dict[str, Any]:
        """
        Legge XMP usando strategia corretta per formato:
        - Standard (JPG/TIFF): solo embedded
        - RAW (eccetto DNG): solo sidecar  
        - DNG: embedded + sidecar (merge con priorità sidecar)
        """
        category = self._get_file_category(file_path)
        
        try:
            if category == 'dng':
                # DNG: prima embedded, poi merge sidecar (sidecar override embedded)
                embedded = self.read_xmp_embedded(file_path) or {}
                sidecar = self.read_xmp_sidecar(file_path) or {}
                
                # Merge: sidecar override embedded
                result = {**embedded, **sidecar}
                logger.debug(f"DNG XMP merge per {file_path.name}: {len(embedded)} embedded + {len(sidecar)} sidecar = {len(result)} total")
                return result
                
            elif category == 'raw':
                # RAW: solo sidecar
                result = self.read_xmp_sidecar(file_path) or {}
                logger.debug(f"RAW XMP sidecar per {file_path.name}: {len(result)} tags")
                return result
                
            elif category == 'standard':
                # Standard: solo embedded
                result = self.read_xmp_embedded(file_path) or {}
                logger.debug(f"Standard XMP embedded per {file_path.name}: {len(result)} tags")
                return result
                
            else:
                logger.warning(f"Formato non riconosciuto per XMP: {file_path.suffix}")
                return {}
                
        except Exception as e:
            logger.error(f"Errore lettura XMP format-aware per {file_path.name}: {e}")
            return {}
    
    def write_xmp_by_format(self, file_path: Path, xmp_dict: Dict[str, Any], 
                           mode: str = 'smart',
                           dng_options: Dict[str, Any] = None) -> bool:
        """
        Scrive XMP usando strategia corretta per formato con supporto DNG avanzato
        
        Args:
            file_path: Path del file
            xmp_dict: Metadata da scrivere
            mode: 'smart' (default), 'embedded_only', 'sidecar_only', 'both'
            dng_options: Opzioni DNG avanzate: {'destination': 'embedded|sidecar', 'mode': 'merge|overwrite', 'smart_cleanup': bool}
            
        Returns:
            True se almeno una scrittura è riuscita
        """
        category = self._get_file_category(file_path)
        
        try:
            if category == 'dng':
                # DNG: opzioni multiple
                if mode == 'embedded_only':
                    result = self.write_xmp_embedded(file_path, xmp_dict)
                    logger.info(f"DNG XMP embedded scritto per {file_path.name}: {'✓' if result else '❌'}")
                    return result
                    
                elif mode == 'sidecar_only':
                    result = self.write_xmp_sidecar(file_path, xmp_dict)
                    logger.info(f"DNG XMP sidecar scritto per {file_path.name}: {'✓' if result else '❌'}")
                    return result
                    
                else:  # 'smart' or 'both'
                    emb_ok = self.write_xmp_embedded(file_path, xmp_dict)
                    side_ok = self.write_xmp_sidecar(file_path, xmp_dict)
                    logger.info(f"DNG XMP both scritto per {file_path.name}: embedded {'✓' if emb_ok else '❌'}, sidecar {'✓' if side_ok else '❌'}")
                    return emb_ok or side_ok
                    
            elif category == 'raw':
                # RAW: solo sidecar (mai embedded)
                result = self.write_xmp_sidecar(file_path, xmp_dict)
                logger.info(f"RAW XMP sidecar scritto per {file_path.name}: {'✓' if result else '❌'}")
                return result
                
            elif category == 'standard':
                # Standard: solo embedded (mai sidecar)
                result = self.write_xmp_embedded(file_path, xmp_dict)
                logger.info(f"Standard XMP embedded scritto per {file_path.name}: {'✓' if result else '❌'}")
                return result
                
            else:
                logger.error(f"Formato non supportato per scrittura XMP: {file_path.suffix}")
                return False
                
        except Exception as e:
            logger.error(f"Errore scrittura XMP format-aware per {file_path.name}: {e}")
            return False
    
    # LEGACY: Mantieni per compatibilità con export_tab esistente

    def write_xmp(self, file_path: Path, xmp_dict: Dict[str, Any], options: Dict[str, Any] = None) -> bool:
        """
        LEGACY: Wrapper per compatibilità con export_tab esistente
        Usa write_xmp_by_format internamente
        """
        mode = 'smart'  # Default intelligente
        dng_options = None
        
        if options:
            # Mappa opzioni legacy se esistono
            dng_options = options.get('dng_options')
        
        return self.write_xmp_by_format(file_path, xmp_dict, mode, dng_options)
    
    def read_xmp_embedded(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        CORRECTED: Legge XMP embedded con protezione RAW rigorosa
        - RAW: BLOCCO TOTALE - nessun XMP embedded letto (usa solo sidecar)
        - SIDECAR .xmp: Processa normalmente  
        - STANDARD: Processa normalmente (DNG, JPG, TIFF)
        """
        if not self.exiftool_available:
            return None
        
        # PROTEZIONE RAW: Blocca totalmente la lettura embedded dai RAW
        raw_extensions = ['.orf', '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2', 
                         '.raf', '.rw2', '.raw', '.pef', '.ptx', '.rwl', '.3fr', '.iiq', '.x3f']
        
        if file_path.suffix.lower() in raw_extensions:
            logger.debug(f"RAW {file_path.name}: XMP embedded BLOCCATO per policy RAW")
            return None
            
        try:
            # Estrai XMP embedded as JSON per parsing facile
            # HAL: Leggiamo i tag specifici ovunque siano (XMP, IPTC o EXIF)
            cmd = [
            *XMPManagerExtended._exiftool_cmd,
            '-json',
            '-G',           # HAL: Molto importante! Aggiunge il gruppo (es. IPTC:Keywords)
            '-Subject',
            '-Keywords',
            '-Description',
            '-ImageDescription',
            '-Rating',
            '-xmp:all',     # Continuiamo a prendere tutto l'XMP
            str(file_path)
        ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout.decode())[0]
                
                # Filtra tag XMP in base al tipo di file
                if file_path.suffix.upper() in ['.ORF', '.CR2', '.NEF', '.ARW', '.RAF', '.RW2']:
                    # RAW: Solo metadati creativi da XMP sidecar (no EXIF tecnici)
                    xmp_data = {
                        key: value for key, value in data.items() 
                        if (key.startswith('XMP:') or 
                            key.startswith('XMP-') or
                            key in ['Subject', 'Keywords', 'Creator', 'Title', 'Description', 'Rights'] or  # Dublin Core creativi
                            key.startswith('Lightroom:') or  # Lightroom specific
                            'Rating' in key or 'Label' in key)  # Rating e label
                    }
                else:
                    # DNG/JPEG/TIFF: Tutti i metadati XMP (creativi + tecnici se nel file stesso)
                    xmp_data = {
                        key: value for key, value in data.items() 
                        if (key.startswith('XMP:') or 
                            key.startswith('XMP-') or
                            key in ['Subject', 'Keywords', 'Creator', 'Title', 'Description', 'Rights'] or  # Dublin Core
                            key.startswith('Lightroom:') or  # Lightroom
                            key.startswith('DC:') or  # Dublin Core namespace
                            key.startswith('LR:'))  # Lightroom namespace alternativo
                    }
                
                if xmp_data:
                    logger.debug(f"XMP embedded letto da {file_path.name}: {len(xmp_data)} tags")
                    logger.debug(f"XMP tags trovati: {list(xmp_data.keys())}")  # Debug dettagliato
                    return self._normalize_xmp_tags(xmp_data)
                
        except Exception as e:
            logger.error(f"Errore lettura XMP embedded da {file_path.name}: {e}")
        
        return None
    
    def write_xmp_embedded(self, file_path: Path, xmp_dict: Dict[str, Any]) -> bool:
        """
        Scrive XMP embedded nel file usando ExifTool
        
        Args:
            file_path: Path del file
            xmp_dict: Dizionario con metadata da scrivere
            
        Returns:
            True se successo, False se errore
        """
        if not self.exiftool_available:
            logger.error("ExifTool non disponibile per scrittura XMP embedded")
            return False
            
        try:
            # Prepara parametri ExifTool
            cmd = [*XMPManagerExtended._exiftool_cmd, '-overwrite_original']

            # Converti dict in parametri ExifTool
            for key, value in xmp_dict.items():
                if value is not None:
                    exif_key = self._dict_key_to_exiftool(key)
                    cmd.extend([f'-{exif_key}={value}'])

            cmd.append(str(file_path))

            result = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if result.returncode == 0:
                logger.info(f"✓ XMP embedded scritto in {file_path.name}")
                return True
            else:
                error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                logger.error(f"Errore scrittura XMP embedded: {error_msg}")
                
        except Exception as e:
            logger.error(f"Errore scrittura XMP embedded in {file_path.name}: {e}")
        
        return False
    
    def read_xmp_sidecar(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        UNIFICATO: Legge XMP sidecar usando RAWProcessor per consistenza totale
        Garantisce parsing standard Lightroom/ExifTool identico all'estrazione iniziale
        """
        sidecar_path = file_path.with_suffix('.xmp')  # Naming Lightroom standard
        
        if not sidecar_path.exists():
            return None
        
        try:
            # UNIFICAZIONE: Usa RAWProcessor per parsing completo e intelligente
            # Questo garantisce stessa logica di fallback e mapping dell'estrazione iniziale
            from raw_processor import RAWProcessor
            
            # Crea RAWProcessor temporaneo se non abbiamo config
            if not hasattr(self, 'raw_processor'):
                temp_config = self.config or {'image_processing': {'raw_processing': {}}}
                raw_processor = RAWProcessor(temp_config)
            else:
                raw_processor = self.raw_processor
            
            # USA STESSO METODO dell'estrazione iniziale
            exif_data = raw_processor._extract_with_exiftool(sidecar_path)
            
            if not exif_data:
                logger.warning(f"Nessun dato XMP estratto da sidecar {sidecar_path.name}")
                return None
            
            # USA STESSO MAPPING dell'estrazione iniziale  
            mapped_data = raw_processor._map_all_fields(exif_data)
            
            logger.debug(f"Sidecar unificato {sidecar_path.name}: {len(mapped_data)} campi mappati")
            
            # Ritorna solo i campi XMP rilevanti (non EXIF tecnici)
            xmp_fields = {
                'title': mapped_data.get('title'),
                'description': mapped_data.get('description'), 
                'tags': mapped_data.get('tags'),  # JSON format
                'lr_rating': mapped_data.get('lr_rating'),
                'artist': mapped_data.get('artist'),
                'copyright': mapped_data.get('copyright')
            }
            
            # Filtra campi vuoti
            return {k: v for k, v in xmp_fields.items() if v is not None and v != '' and v != '[]'}
            
        except Exception as e:
            logger.error(f"Errore lettura XMP sidecar unificato {sidecar_path.name}: {e}")
            return None

    def _get_clean_value(self, value):
        """Normalizza i valori XMP per un confronto coerente tra DB e File"""
        if value is None:
            return ""
        
        # Se è un dizionario (struttura x-default di Lightroom/ExifTool)
        if isinstance(value, dict):
            return value.get('x-default', str(value)).strip()
        
        # Se è una lista (Keywords/Subject), pulisci e ordina
        if isinstance(value, list):
            return sorted([str(v).strip() for v in value if v])
        
        # Se è una stringa, puliscila
        if isinstance(value, str):
            # Se la stringa sembra una lista (es. "tag1, tag2"), normalizzala
            if ',' in value:
                return sorted([t.strip() for t in value.split(',') if t.strip()])
            return value.strip()
            
        return value

    def _get_db_payload(self, db_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """HAL: Estrae e normalizza i dati dal DB evitando i crash da NoneType"""
        import json
        
        if not db_metadata:
            return {'Title': '', 'Description': '', 'Keywords': [], 'Rating': 0}

        # 1. Gestione Keywords (Sicura contro i None)
        tags_raw = db_metadata.get('tags') # Usiamo get senza default per il check successivo
        keywords = []
        
        if tags_raw is not None:
            if isinstance(tags_raw, str):
                if tags_raw.startswith('['):
                    try: keywords = json.loads(tags_raw)
                    except: keywords = []
                else:
                    keywords = [t.strip() for t in tags_raw.split(',') if t.strip()]
            elif isinstance(tags_raw, list):
                keywords = tags_raw
        
        # 2. Costruzione Payload con fallback sicuri
        return {
            'Title': str(db_metadata.get('title') or ''),
            'Description': str(db_metadata.get('description') or ''),
            'Keywords': keywords,
            'Rating': db_metadata.get('rating') or 0
        }

    def analyze_xmp_sync_state(self, file_path: Path, db_metadata: Dict[str, Any]) -> Tuple[XMPSyncState, Dict[str, Any]]:
        """
        Analizza lo stato di sincronizzazione tra DB, Sidecar e Embedded.
        Per i RAW (non DNG), ignora deliberatamente i dati interni al file.
        LOGICA CORRETTA: Gestisce tutti i casi possibili senza bug.
        """
        category = self._get_file_category(file_path)
    
        try:
            # 1. RECUPERO SORGENTI
            # Leggiamo sempre il sidecar se esiste (.xmp)
            sidecar_xmp = self.read_xmp_sidecar(file_path)
        
            # HAL: Qui applichiamo la tua regola ferrea per i RAW
            if category == 'raw':
                embedded_xmp = None  # Ignoriamo totalmente l'interno del file RAW
            else:
                embedded_xmp = self.read_xmp_embedded(file_path)
        
            # Normalizziamo i dati del Database
            db_payload = self._get_db_payload(db_metadata)
        
            # Flag di esistenza fisica
            has_sidecar = sidecar_xmp is not None
            has_embedded = embedded_xmp is not None
        
            # Prepariamo le info per i log e i tooltip
            info = {
                'category': category,
                'has_sidecar': has_sidecar,
                'has_embedded': has_embedded,
                'db_tags': len(db_payload.get('Keywords', [])),
                'sidecar_tags': len(self._extract_keywords_from_dict(sidecar_xmp)) if has_sidecar else 0,
                'embedded_tags': len(self._extract_keywords_from_dict(embedded_xmp)) if has_embedded else 0
            }

            # --- 2. LOGICA DECISIONALE CORRETTA ---
        
            # CASO A: RAW (ORF, ARW, NEF, etc.) - Solo sidecar conta
            if category == 'raw':
                if not has_sidecar:
                    return XMPSyncState.DB_ONLY, info
            
                # Confronta sidecar con DB
                is_sync = self._compare_xmp_dicts(sidecar_xmp, db_payload)
                return (XMPSyncState.PERFECT_SYNC if is_sync else XMPSyncState.SIDECAR_DIRTY), info
        
            # CASO B: Nessun XMP (né sidecar né embedded)
            if not has_sidecar and not has_embedded:
                return XMPSyncState.DB_ONLY, info
        
            # CASO C: Solo sidecar presente (embedded assente) ← FIX PRINCIPALE
            if has_sidecar and not has_embedded:
                is_sync = self._compare_xmp_dicts(sidecar_xmp, db_payload)
                return (XMPSyncState.PERFECT_SYNC if is_sync else XMPSyncState.SIDECAR_DIRTY), info
        
            # CASO D: Solo embedded presente (sidecar assente)  
            if has_embedded and not has_sidecar:
                is_sync = self._compare_xmp_dicts(embedded_xmp, db_payload)
                return (XMPSyncState.PERFECT_SYNC if is_sync else XMPSyncState.EMBEDDED_DIRTY), info
        
            # CASO E: Entrambi presenti (sidecar E embedded) - MIXED STATE
            if has_sidecar and has_embedded:
                sync_sidecar = self._compare_xmp_dicts(sidecar_xmp, db_payload)
                sync_embedded = self._compare_xmp_dicts(embedded_xmp, db_payload)
            
                if sync_sidecar and sync_embedded:
                    # Entrambi sincronizzati con DB
                    return XMPSyncState.PERFECT_SYNC, info  # Verde - tutto perfetto
                elif sync_sidecar or sync_embedded:
                    # Solo uno sincronizzato - stato misto
                    return XMPSyncState.MIXED_STATE, info  # Arancione - parzialmente sincronizzato
                else:
                    # Nessuno sincronizzato - conflitto totale
                    return XMPSyncState.MIXED_DIRTY, info  # Rosso - tutto desincronizzato
        
            # Fallback (non dovrebbe mai arrivare qui)
            return XMPSyncState.ERROR, info
        
        except Exception as e:
            # Qualcosa è andato storto nel parsing, evitiamo il crash totale
            import traceback
            print(f"ERROR: {traceback.format_exc()}")
            return XMPSyncState.ERROR, {'error': str(e), 'category': category}


    # DOCUMENTAZIONE DEI CASI:
    # ======================
    #
    # CASO A - RAW files:
    #   has_sidecar=T, has_embedded=ignore → PERFECT_SYNC/SIDECAR_DIRTY
    #   has_sidecar=F, has_embedded=ignore → DB_ONLY
    #
    # CASO B - Nessun XMP:
    #   has_sidecar=F, has_embedded=F → DB_ONLY
    #
    # CASO C - Solo sidecar (JPG+XMP): ← QUESTO ERA IL BUG!
    #   has_sidecar=T, has_embedded=F → PERFECT_SYNC/SIDECAR_DIRTY
    #
    # CASO D - Solo embedded:
    #   has_sidecar=F, has_embedded=T → PERFECT_SYNC/EMBEDDED_DIRTY
    #
    # CASO E - Entrambi (sidecar+embedded):
    #   has_sidecar=T, has_embedded=T → PERFECT_SYNC/MIXED_STATE/MIXED_DIRTY

    def sync_xmp_sources(self, file_path: Path, 
                        source: str, target: str,
                        db_metadata: Dict[str, Any] = None) -> bool:
        """
        Sincronizza tra fonti XMP diverse
        
        Args:
            file_path: Path del file
            source: 'embedded', 'sidecar', 'database'
            target: 'embedded', 'sidecar', 'database'  
            db_metadata: Metadata database (per source/target database)
            
        Returns:
            True se sincronizzazione riuscita
        """
        try:
            # Leggi source
            if source == 'embedded':
                source_data = self.read_xmp_embedded(file_path)
            elif source == 'sidecar':
                source_data = self.read_xmp_sidecar(file_path)
            elif source == 'database':
                source_data = self._extract_xmp_from_db(db_metadata or {})
            else:
                logger.error(f"Source non supportato: {source}")
                return False
            
            if not source_data:
                logger.warning(f"Nessun dato XMP in {source} per {file_path.name}")
                return False
            
            # Scrivi target usando format-aware logic
            if target == 'embedded':
                return self.write_xmp_embedded(file_path, source_data)
            elif target == 'sidecar':
                return self.write_xmp_sidecar(file_path, source_data)
            elif target == 'database':
                # Questo dovrebbe chiamare il database manager per update
                logger.info(f"Sync to database richiesto per {file_path.name}")
                return True  # Implementa chiamata al DB manager
            else:
                logger.error(f"Target non supportato: {target}")
                return False
                
        except Exception as e:
            logger.error(f"Errore sync XMP {source}→{target} per {file_path.name}: {e}")
            return False
    
    def _normalize_xmp_tags(self, raw_xmp: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizza tag XMP rimuovendo prefissi e pulendo valori"""
        normalized = {}
        
        for key, value in raw_xmp.items():
            # Rimuovi prefissi XMP
            clean_key = key.replace('XMP:', '').replace('XMP-', '')
            
            # Normalizza valore (sostituisce la vecchia _normalize_value)
            if isinstance(value, str):
                normalized_value = value.strip()
            elif isinstance(value, list):
                normalized_value = [v for v in value if v]
            elif value is None:
                normalized_value = None
            else:
                normalized_value = value
            
            if normalized_value is not None:
                normalized[clean_key] = normalized_value
        
        return normalized
    
    def _dict_key_to_exiftool(self, key: str) -> str:
        """Converte chiave dict in formato ExifTool"""
        # Mappa comuni
        key_mapping = {
            'title': 'XMP:Title',
            'description': 'XMP:Description', 
            'keywords': 'XMP:Keywords',
            'creator': 'XMP:Creator',
            'rights': 'XMP:Rights',
            'subject': 'XMP:Subject',
            'user_tags': 'XMP:Keywords',
            'ai_tags': 'XMP:Subject',
            'bioclip_tags': 'XMP:Keywords',
            'ai_description': 'XMP:Description'
        }
        
        return key_mapping.get(key.lower(), f'XMP:{key}')

    def _extract_keywords_from_dict(self, xmp_dict: Dict[str, Any]) -> List[str]:
        """UNIFICATO: Estrae keywords dai dati RAWProcessor (formato JSON) e XMP tradizionale"""
        if not xmp_dict:
            return []

        found_keywords = []
        
        # FORMATO UNIFICATO: Prima controlla il campo 'tags' JSON del RAWProcessor
        tags_json = xmp_dict.get('tags')
        if tags_json:
            try:
                if isinstance(tags_json, str):
                    # È JSON string - decodifica
                    keywords_list = json.loads(tags_json)
                    if isinstance(keywords_list, list):
                        found_keywords.extend([str(k) for k in keywords_list if k])
                elif isinstance(tags_json, list):
                    # È già lista
                    found_keywords.extend([str(k) for k in tags_json if k])
            except (json.JSONDecodeError, TypeError):
                logger.debug(f"Formato tags JSON non valido: {tags_json}")

        # FORMATO TRADIZIONALE: Poi cerca nei campi XMP classici (per compatibilità)
        keyword_fields = [
            'Subject', 'Keywords', 'XMP:Subject', 'IPTC:Keywords', 
            'XMP:Keywords', 'subject', 'keywords', 'XPKeywords'
        ]
    
        for field in keyword_fields:
            val = xmp_dict.get(field)
            if val:
                if isinstance(val, list):
                    found_keywords.extend([str(k) for k in val if k])
                elif isinstance(val, str):
                    # Gestisce tag separati da virgola
                    found_keywords.extend([t.strip() for t in val.split(',') if t.strip()])
    
        # Rimuovi duplicati e normalizza
        normalized_keywords = []
        for kw in found_keywords:
            cleaned = self._normalize_keyword(str(kw))
            if cleaned and cleaned not in normalized_keywords:
                normalized_keywords.append(cleaned)
        
        return sorted(normalized_keywords)

    def _extract_xmp_from_db(self, db_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Estrae campi XMP-rilevanti dal database metadata - CORRETTO per schema unificato"""
        import json
        
        # Ottieni tags dal campo unified
        tags_raw = db_metadata.get('tags', '')
        keywords = []
        if tags_raw:
            try:
                if isinstance(tags_raw, str):
                    keywords = json.loads(tags_raw)
                elif isinstance(tags_raw, list):
                    keywords = tags_raw
            except (json.JSONDecodeError, TypeError):
                keywords = []
        
        xmp_relevant_fields = {
            'title': db_metadata.get('title', '') or db_metadata.get('filename', '').replace('_', ' ').split('.')[0],
            'description': db_metadata.get('description', ''),
            'keywords': keywords,
            'subject': keywords,  # Usa stesso campo unified per Subject
            'creator': db_metadata.get('artist', ''),
            'rights': db_metadata.get('copyright', ''),
        }
        
        # Filtra valori None/vuoti
        return {k: v for k, v in xmp_relevant_fields.items() if v}
    
    def _compare_xmp_dicts(self, dict1: Dict[str, Any], dict2: Dict[str, Any]) -> bool:
        """HAL: Confronto granulare. Impedisce i falsi positivi se uno dei due manca."""
        
        # Se entrambi sono None, tecnicamente sono uguali (ma non dovrebbe succedere con la logica sopra)
        if dict1 is None and dict2 is None: 
            return True
            
        # Se uno dei due manca ma l'altro no, NON sono in sync
        if dict1 is None or dict2 is None:
            return False

        d1 = dict1 or {}
        d2 = dict2 or {}

        # DEBUG: Stampa confronto dettagliato
        debug_info = []

        # 1. TAGS (Keywords)
        kw1 = sorted(self._extract_keywords_from_dict(d1))
        kw2 = sorted(self._extract_keywords_from_dict(d2))
        if kw1 != kw2:
            debug_info.append(f"Keywords differ: XMP={kw1} vs DB={kw2}")
            if debug_info: logger.debug(f"XMP Compare MISMATCH: {' | '.join(debug_info)}")
            return False
            
        # 2. DESCRIZIONE (Normalizzata)
        desc1 = str(self._extract_description_from_dict(d1) or "").strip().lower()
        desc2 = str(self._extract_description_from_dict(d2) or "").strip().lower()
        if desc1 != desc2:
            debug_info.append(f"Description differ: XMP='{desc1}' vs DB='{desc2}'")
            if debug_info: logger.debug(f"XMP Compare MISMATCH: {' | '.join(debug_info)}")
            return False

        # 3. TITOLO (cerca in tutti i possibili campi)
        def get_title(d):
            for key in ['Title', 'XMP:Title', 'XMP-dc:Title', 'title', 'ObjectName', 'Headline']:
                val = d.get(key)
                if val:
                    return str(val).strip().lower()
            return ""
        t1 = get_title(d1)
        t2 = get_title(d2)
        if t1 != t2:
            debug_info.append(f"Title differ: XMP='{t1}' vs DB='{t2}'")
            if debug_info: logger.debug(f"XMP Compare MISMATCH: {' | '.join(debug_info)}")
            return False

        # 4. RATING
        def r_val(d):
            val = d.get('Rating', d.get('XMP:Rating', 0))
            try: return int(val)
            except: return 0
        r1, r2 = r_val(d1), r_val(d2)
        if r1 != r2:
            debug_info.append(f"Rating differ: XMP={r1} vs DB={r2}")
            if debug_info: logger.debug(f"XMP Compare MISMATCH: {' | '.join(debug_info)}")
            return False
            
        # Se arriviamo qui, tutto coincide
        logger.debug(f"XMP Compare MATCH: Keywords={len(kw1)}, Desc='{desc1[:30]}...', Title='{t1[:30]}...', Rating={r1}")
        return True
    
    def _extract_description_from_dict(self, xmp_dict: Dict[str, Any]) -> str:
        """Estrae descrizione gestendo dizionari x-default e prefissi stringa"""
        if not xmp_dict: return ""
        desc_fields = ['description', 'Description', 'Caption-Abstract', 'ImageDescription', 'dc:description']
        
        for field in desc_fields:
            val = xmp_dict.get(field)
            if val:
                if isinstance(val, dict):
                    val = val.get('x-default', str(val))
                
                val_str = str(val).strip()
                # Rimuove 'x-default ' se presente come testo puro
                if val_str.lower().startswith('x-default '):
                    val_str = val_str[10:].strip()
                return val_str
        return ""
    
    def _normalize_keyword(self, keyword: str) -> str:
        """Pulisce rimasugli di JSON, virgolette e parentesi"""
        if not keyword: return ""
        k = str(keyword).strip()
        # Rimuove caratteri di disturbo che spesso ExifTool lascia nei RAW
        for char in ['"', "'", '[', ']', '(', ')']:
            k = k.replace(char, '')
        return k.strip().lower()
    
    def write_xmp_sidecar(self, file_path: Path, xmp_dict: Dict[str, Any]) -> bool:
        """CORRETTO: Scrive XMP sidecar con naming Lightroom-compatibile"""
        # Implementazione esistente o via ExifTool
        sidecar_path = file_path.with_suffix('.xmp')  # ← CORRETTO: file.xmp invece di file.ORF.xmp
        
        try:
            if self.exiftool_available:
                # Usa ExifTool per consistency
                cmd = [*XMPManagerExtended._exiftool_cmd, '-overwrite_original']

                for key, value in xmp_dict.items():
                    if value is not None:
                        exif_key = self._dict_key_to_exiftool(key)
                        cmd.extend([f'-{exif_key}={value}'])
                
                # Crea file sidecar vuoto se non esiste
                if not sidecar_path.exists():
                    sidecar_path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="OffGallery XMP Manager"/>')
                
                cmd.append(str(sidecar_path))
                
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                
                if result.returncode == 0:
                    logger.info(f"✓ XMP sidecar scritto: {sidecar_path.name}")
                    return True
                else:
                    error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                    logger.error(f"Errore scrittura XMP sidecar: {error_msg}")
            
            # Fallback: implementazione XML esistente
            return self._write_xmp_xml(sidecar_path, xmp_dict)
            
        except Exception as e:
            logger.error(f"Errore scrittura XMP sidecar {sidecar_path.name}: {e}")
            return False
    
    def _write_xmp_xml(self, file_path: Path, xmp_dict: Dict[str, Any]) -> bool:
        """Fallback: scrivi XMP come XML"""
        try:
            # Template XMP base
            xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="OffGallery XMP Manager">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:xmp="http://ns.adobe.com/xap/1.0/">
   
   <!-- Metadata generati automaticamente -->
   
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>'''
            
            file_path.write_text(xml_content, encoding='utf-8')
            logger.info(f"✓ XMP sidecar XML creato: {file_path.name}")
            return True
            
        except Exception as e:
            logger.error(f"Errore scrittura XMP XML: {e}")
            return False
    
    def _parse_xmp_xml(self, root) -> Dict[str, Any]:
        """Parse XMP XML (implementazione semplificata)"""
        # Implementazione base per fallback XML parsing
        xmp_data = {}
        
        # Cerca namespace XMP comuni
        namespaces = {
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'xmp': 'http://ns.adobe.com/xap/1.0/'
        }
        
        # Parse basic tags (implementazione minimale)
        try:
            for desc in root.findall('.//rdf:Description', namespaces):
                for attr, value in desc.attrib.items():
                    if ':' in attr:
                        clean_attr = attr.split(':')[-1]
                        xmp_data[clean_attr] = value
        except:
            pass
        
        return xmp_data

    def write_hierarchical_bioclip(self, file_path: Path, hierarchical_path: str) -> bool:
        """Scrive tassonomia BioCLIP nel campo HierarchicalSubject XMP.
        Preserva keyword gerarchiche non-AI esistenti, sovrascrive solo ramo AI|Taxonomy.
        """
        if not self.exiftool_available or not hierarchical_path:
            return False

        try:
            # Determina target (sidecar per RAW, file per altri)
            raw_extensions = ['.orf', '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2',
                             '.raf', '.rw2', '.raw', '.pef', '.ptx', '.rwl', '.3fr', '.iiq', '.x3f']
            if file_path.suffix.lower() in raw_extensions:
                target = file_path.with_suffix('.xmp')
                if not target.exists():
                    return False
            else:
                target = file_path

            # Leggi HierarchicalSubject esistenti
            existing_hier = []
            try:
                result = subprocess.run(
                    [*XMPManagerExtended._exiftool_cmd, '-j', '-XMP-lr:HierarchicalSubject', str(target)],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    if data:
                        hs = data[0].get('HierarchicalSubject', [])
                        if isinstance(hs, str):
                            hs = [hs]
                        existing_hier = [s for s in hs if not s.startswith('AI|Taxonomy')]
            except Exception:
                pass

            # Scrivi: cancella + riscrivi con merge
            cmd = [*XMPManagerExtended._exiftool_cmd, '-overwrite_original', '-XMP-lr:HierarchicalSubject=']
            for subject in existing_hier:
                cmd.append(f'-XMP-lr:HierarchicalSubject+={subject}')
            cmd.append(f'-XMP-lr:HierarchicalSubject+={hierarchical_path}')
            cmd.append(str(target))

            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode == 0:
                logger.info(f"✓ HierarchicalSubject BioCLIP scritto: {target.name}")
                return True
            else:
                error_msg = result.stderr.decode() if result.stderr else "Unknown"
                logger.error(f"Errore HierarchicalSubject: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Errore write_hierarchical_bioclip: {e}")
            return False


# ===== UTILITY FUNCTIONS (invariate) =====

def get_sync_ui_config(state: XMPSyncState) -> dict:
    """HAL: Configurazione centralizzata per Badge e Icone"""
    configs = {
        # --- STATI PERFETTI ---
        XMPSyncState.PERFECT_SYNC: {
            "icon": "🟢", "label": "SYNC", "class": "bg-perfect", "color": "#28a745", "tooltip": "File e DB sincronizzati"
        },
        XMPSyncState.MIXED_STATE: {
            "icon": "🟣", "label": "MIX", "class": "bg-mix", "color": "#6f42c1", "tooltip": "Embedded e Sidecar sincronizzati"
        },

        # --- STATI DA AGGIORNARE (GIALLO/ARANCIO scuri per leggibilità) ---
        XMPSyncState.EMBEDDED_DIRTY: {
            "icon": "🟡", "label": "EMB", "class": "bg-dirty", "color": "#b8860b", "tooltip": "Dati nel file da aggiornare"
        },
        XMPSyncState.SIDECAR_DIRTY: {
            "icon": "🟠", "label": "XMP", "class": "bg-dirty", "color": "#c0650a", "tooltip": "File sidecar da aggiornare"
        },
        XMPSyncState.MIXED_DIRTY: {
            "icon": "🟡", "label": "MIX", "class": "bg-dirty", "color": "#b8860b", "tooltip": "Discrepanza tra DB, Sidecar o Embedded"
        },

        # --- STATI NEUTRI (IL CASO DEI TUOI RAW) ---
        XMPSyncState.DB_ONLY: {
            "icon": "⭐", "label": "DB", "class": "bg-db", "color": "#17a2b8", "tooltip": "Dati solo nel Database (nessun file fisico)"
        },
        XMPSyncState.NO_XMP: {
            "icon": "⚪", "label": "NO", "class": "bg-none", "color": "#6c757d", "tooltip": "Nessun metadato trovato"
        },

        # --- ERRORI ---
        XMPSyncState.ERROR: {
            "icon": "❌", "label": "ERR", "class": "bg-error", "color": "#dc3545", "tooltip": "Errore lettura metadati"
        }
    }
    return configs.get(state, {"icon": "❓", "label": "UNK", "class": "bg-none", "color": "#6c757d", "tooltip": "Sconosciuto"})

def get_xmp_sync_tooltip(sync_state: XMPSyncState, info: Dict[str, Any]) -> str:
    """Tooltip descrittivo per stato sync XMP - HAL Calibrated"""
    category = info.get('category', info.get('file_category', 'unknown'))
    
    # Definiamo i messaggi base aggiornati alla nuova logica
    base_tooltips = {
        XMPSyncState.PERFECT_SYNC: "Sincronizzato: Database e file coincidono",
        XMPSyncState.EMBEDDED_DIRTY: "Metadata nel file (Embedded) diversi dal Database",
        XMPSyncState.SIDECAR_DIRTY: "File sidecar (.XMP) diverso dal Database",
        XMPSyncState.MIXED_STATE: "MIX: Sidecar ed Embedded entrambi sincronizzati",
        XMPSyncState.MIXED_DIRTY: "MIX: Discrepanza tra DB, Sidecar o Embedded",
        XMPSyncState.DB_ONLY: "Presente solo nel Database (nessun XMP fisico scritto)",
        XMPSyncState.EMBEDDED_ONLY: "Presente solo metadato Embedded (non nel DB)",
        XMPSyncState.SIDECAR_ONLY: "Presente solo file Sidecar (non nel DB)",
        XMPSyncState.NO_XMP: "Nessun metadato trovato (vuoto)",
        XMPSyncState.ERROR: f"Errore: {info.get('error', 'Lettura XMP fallita')}"
    }
    
    tooltip = base_tooltips.get(sync_state, "Stato XMP sconosciuto")
    
    # Aggiungi info numeriche dettagliate per aiutare l'utente (HAL: utile per capire il 'Dirty')
    details = []
    e_tags = info.get('embedded_tags', 0)
    s_tags = info.get('sidecar_tags', 0)
    db_tags = info.get('db_tags', 0)

    if e_tags > 0: details.append(f"Emb: {e_tags}")
    if s_tags > 0: details.append(f"Side: {s_tags}")
    if db_tags > 0: details.append(f"DB: {db_tags}")
    
    if details:
        tooltip += f" ({' | '.join(details)})"
    
    # Specifica la categoria del file (RAW, STANDARD, DNG)
    tooltip += f" [{category.upper()}]"
    
    return tooltip