"""
path_migration — Uniforma la radice dei percorsi già registrati nel database.

PERCHÉ ESISTE
Windows consegna la radice di un percorso (nome del server UNC, condivisione,
lettera di unità) con maiuscole variabili a seconda di come l'utente arriva
alla cartella. La stessa cartella di rete finiva quindi nel campo `filepath`
in due scritture diverse — '\\\\MYCLOUD-180438\\...' e '\\\\mycloud-180438\\...'
— e il database le trattava come due posti distinti (segnalato da Raul il
21/08/2026: 1304 immagini sotto una forma, 11 sotto l'altra).

Dalla versione che introduce `canonical_filepath()` i nuovi record entrano già
in forma uniforme, ma i database creati prima contengono entrambe le scritture.
Questo modulo le riallinea una volta sola.

NON è solo cosmesi: i confronti esatti sul percorso — per esempio
`UPDATE images SET sync_state = ? WHERE filepath = ?` in export_tab — non
trovano la riga se il percorso in mano al codice ha un case diverso da quello
registrato. L'operazione fallisce senza sollevare errori: l'XMP viene scritto
su disco ma il database non lo registra. Con una sola forma nel database questa
classe di guasti silenziosi sparisce.

COSA TOCCA
Solo la colonna `filepath`. Tag, descrizioni, titoli, punteggi ed embedding non
vengono letti né riscritti, e i file su disco non vengono mai toccati.

COME SI SPEGNE
`migrate_database()` prima verifica se c'è davvero qualcosa da uniformare: su un
archivio già coerente esce senza scrivere nulla, al costo di una query. È lo
stesso schema delle migrazioni già presenti nel progetto (rimozione di UNIQUE su
filename in db_manager_new, percorsi relativi→assoluti in search_tab).
"""

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.paths import canonical_filepath

logger = logging.getLogger(__name__)

# Oltre questa soglia il backup viene saltato: su archivi molto grandi la copia
# costerebbe più della migrazione stessa e ritarderebbe l'avvio dell'app.
_MAX_BACKUP_MB = 500


def needs_migration(conn: sqlite3.Connection) -> bool:
    """True se nel database esiste almeno un percorso non in forma canonica.

    Controllo volutamente economico: si ferma al primo percorso che cambierebbe,
    così su un archivio già coerente il costo è una scansione della sola colonna
    `filepath` senza alcuna scrittura.
    """
    try:
        for (fp,) in conn.execute(
                "SELECT filepath FROM images WHERE filepath IS NOT NULL"):
            if fp and canonical_filepath(fp) != fp:
                return True
        return False
    except sqlite3.Error as e:
        # Database assente, tabella non ancora creata, file corrotto: non è
        # compito di questo modulo diagnosticarlo, si tira indietro.
        logger.warning("Verifica migrazione percorsi non riuscita: %s", e, exc_info=True)
        return False


def _backup_database(db_path: str) -> Optional[Path]:
    """Copia di sicurezza accanto al database, prima di riscrivere i percorsi.

    Restituisce il path del backup, o None se non è stato possibile crearlo
    (spazio esaurito, permessi, archivio troppo grande).
    """
    try:
        src = Path(db_path)
        if not src.exists():
            return None

        size_mb = src.stat().st_size / (1024 * 1024)
        if size_mb > _MAX_BACKUP_MB:
            logger.info(
                "Backup pre-migrazione saltato: database di %.0f MB oltre la soglia di %d MB",
                size_mb, _MAX_BACKUP_MB)
            return None

        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = src.with_name(f"{src.stem}_pre_migrazione_percorsi_{stamp}{src.suffix}")
        shutil.copy2(src, dest)
        logger.info("Backup pre-migrazione creato: %s", dest.name)
        return dest
    except Exception as e:
        logger.warning("Backup pre-migrazione non riuscito: %s", e, exc_info=True)
        return None


def migrate_database(conn: sqlite3.Connection, db_path: str = None) -> int:
    """Uniforma la radice dei percorsi già registrati. Restituisce quanti ne ha corretti.

    Args:
        conn: connessione SQLite aperta sul database da migrare
        db_path: percorso del file database; se fornito, viene creata una copia
                 di sicurezza prima di scrivere

    Returns:
        int: numero di record corretti (0 se non c'era nulla da fare)
    """
    try:
        if not needs_migration(conn):
            return 0

        # Raccoglie prima e scrive dopo: modificare mentre si scorre un cursore
        # SQLite dà risultati imprevedibili.
        da_correggere = []
        for (img_id, fp) in conn.execute(
                "SELECT id, filepath FROM images WHERE filepath IS NOT NULL"):
            if not fp:
                continue
            canonico = canonical_filepath(fp)
            if canonico != fp:
                da_correggere.append((canonico, img_id))

        if not da_correggere:
            return 0

        if db_path:
            _backup_database(db_path)

        logger.info("Migrazione percorsi: %d record da uniformare", len(da_correggere))
        conn.executemany("UPDATE images SET filepath=? WHERE id=?", da_correggere)
        conn.commit()
        logger.info("Migrazione percorsi completata: %d record uniformati", len(da_correggere))
        return len(da_correggere)

    except Exception as e:
        # Un fallimento qui non deve impedire l'avvio dell'app: senza migrazione
        # il database resta nello stato misto di prima, che è comunque
        # utilizzabile grazie alla fusione delle radici nell'albero directory.
        logger.error("Migrazione percorsi non riuscita: %s", e, exc_info=True)
        try:
            conn.rollback()
        except Exception:
            logger.warning("Rollback dopo migrazione fallita non riuscito", exc_info=True)
        return 0
