"""
Lettore catalogo Lightroom Classic (.lrcat)
Il file .lrcat è un database SQLite standard.
Aperto in modalità read-only per non interferire con Lightroom aperto.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LightroomCatalogReader:
    """Legge un catalogo Lightroom Classic e restituisce la lista dei file registrati."""

    # Query per ricavare tutti i percorsi assoluti dei file
    _QUERY_PATHS = """
        SELECT
            root.absolutePath || folder.pathFromRoot || file.idx_filename AS full_path
        FROM AgLibraryFile file
        JOIN AgLibraryFolder folder ON file.folder = folder.id_local
        JOIN AgLibraryRootFolder root ON folder.rootFolder = root.id_local
        WHERE file.idx_filename IS NOT NULL
          AND file.idx_filename != ''
    """

    # Query per ricavare il nome del catalogo (tabella Adobe_variablesTable)
    _QUERY_CATALOG_NAME = """
        SELECT value FROM Adobe_variablesTable
        WHERE name = 'Adobe_catalogTitle'
        LIMIT 1
    """

    def read_catalog(self, lrcat_path: Path, supported_formats: list) -> dict:
        """
        Legge il catalogo Lightroom e restituisce la lista dei file compatibili.

        Args:
            lrcat_path: percorso al file .lrcat
            supported_formats: lista estensioni supportate (es. ['.jpg', '.cr2', ...])

        Returns:
            {
                'files': [Path, ...],      # percorsi assoluti presenti su disco
                'missing': [Path, ...],    # percorsi non trovati su disco
                'stats': {
                    'total_in_catalog': int,   # tutti i file nel catalogo
                    'supported': int,           # filtrati per formato
                    'found_on_disk': int,
                    'missing_on_disk': int,
                    'catalog_name': str,
                }
            }
        """
        lrcat_path = Path(lrcat_path)
        if not lrcat_path.exists():
            raise FileNotFoundError(f"Catalogo non trovato: {lrcat_path}")

        # Normalizza formati supportati: tutti minuscoli con punto iniziale
        supported_exts = {
            (ext if ext.startswith('.') else f'.{ext}').lower()
            for ext in supported_formats
        }

        catalog_name = lrcat_path.stem
        all_paths = []
        files_found = []
        files_missing = []

        # Apre in read-only tramite URI per non bloccare Lightroom
        uri = f"file:{lrcat_path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError:
            # Fallback: connessione normale (read-only di fatto se LR ha il lock)
            conn = sqlite3.connect(str(lrcat_path))

        try:
            cursor = conn.cursor()

            # Prova a leggere il nome del catalogo
            try:
                cursor.execute(self._QUERY_CATALOG_NAME)
                row = cursor.fetchone()
                if row and row[0]:
                    catalog_name = row[0]
            except sqlite3.OperationalError:
                pass  # Tabella non presente in versioni vecchie

            # Legge tutti i percorsi
            cursor.execute(self._QUERY_PATHS)
            rows = cursor.fetchall()

        finally:
            conn.close()

        logger.info(f"Catalogo '{catalog_name}': {len(rows)} file totali letti")

        total_in_catalog = len(rows)

        for (raw_path,) in rows:
            if not raw_path:
                continue
            # Normalizza separatori (LR usa / su tutte le piattaforme)
            file_path = Path(raw_path.replace('/', '\\') if '\\' not in raw_path else raw_path)

            # Filtra per formato supportato
            if file_path.suffix.lower() not in supported_exts:
                continue

            all_paths.append(file_path)
            if file_path.exists():
                files_found.append(file_path)
            else:
                files_missing.append(file_path)

        supported_count = len(all_paths)
        logger.info(
            f"Formati supportati: {supported_count} | "
            f"Trovati su disco: {len(files_found)} | "
            f"Mancanti: {len(files_missing)}"
        )

        return {
            'files': files_found,
            'missing': files_missing,
            'stats': {
                'total_in_catalog': total_in_catalog,
                'supported': supported_count,
                'found_on_disk': len(files_found),
                'missing_on_disk': len(files_missing),
                'catalog_name': catalog_name,
            }
        }
