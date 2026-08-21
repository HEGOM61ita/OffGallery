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

QUANDO INTERVIENE — E QUANDO NO
Solo dove la stessa radice compare con DUE scritture diverse. Un archivio
scritto tutto come 'I:\\...' è già coerente e non viene toccato: abbassarlo a
'i:\\...' riscriverebbe ogni riga senza risolvere niente (verificato sul DB
reale di Mike, dove sarebbero stati riscritti 22.307 record su 22.307).
Le righe vengono allineate alla scrittura più frequente — la stessa scelta
fatta dall'albero directory, così il percorso resta quello che l'utente
riconosce.

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
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _radici_da_allineare(conn: sqlite3.Connection) -> dict:
    """Radici presenti nel DB in più di una scrittura, con la forma a cui allinearle.

    Il criterio NON è "diverso dalla forma canonica": un archivio scritto tutto
    come 'I:\\...' è perfettamente coerente e abbassarlo a 'i:\\...' sarebbe
    riscrivere ogni riga senza risolvere nulla (verificato sul DB reale di Mike:
    22.307 record su 22.307 sarebbero stati toccati inutilmente).

    Si interviene solo dove convivono DAVVERO due scritture della stessa radice
    — il caso di Raul, '\\\\MYCLOUD-180438\\...' accanto a
    '\\\\mycloud-180438\\...'. Come forma di destinazione si tiene la più
    frequente, la stessa scelta fatta dall'albero directory: l'utente continua a
    leggere il percorso come lo conosce invece di vederselo cambiare sotto.

    Returns:
        dict: {radice_da_sostituire: radice_di_destinazione}, vuoto se non c'è
              nessuna ambiguità
    """
    conteggi = defaultdict(Counter)
    try:
        for (fp,) in conn.execute(
                "SELECT filepath FROM images WHERE filepath IS NOT NULL"):
            if not fp:
                continue
            radice = Path(fp).anchor
            if radice:
                conteggi[radice.lower()][radice] += 1
    except sqlite3.Error as e:
        # Database assente, tabella non ancora creata, file corrotto: non è
        # compito di questo modulo diagnosticarlo, si tira indietro.
        logger.warning("Verifica migrazione percorsi non riuscita: %s", e, exc_info=True)
        return {}

    da_allineare = {}
    for varianti in conteggi.values():
        if len(varianti) < 2:
            continue  # radice già scritta in un modo solo: niente da fare
        # Più immagini = forma prevalente; a parità, ordine alfabetico per un
        # risultato stabile fra un avvio e l'altro.
        destinazione = max(varianti.items(), key=lambda v: (v[1], v[0]))[0]
        for variante in varianti:
            if variante != destinazione:
                da_allineare[variante] = destinazione
    return da_allineare


def needs_migration(conn: sqlite3.Connection) -> bool:
    """True se la stessa radice compare nel DB con scritture diverse.

    Su un archivio coerente — anche se scritto tutto in maiuscolo — restituisce
    False e non viene riscritto nulla.
    """
    return bool(_radici_da_allineare(conn))


def dimensione_mb(db_path: str) -> float:
    """Dimensione del database in MB, per dire all'utente quanto peserà la copia."""
    try:
        from pathlib import Path as _Path
        return _Path(db_path).stat().st_size / (1024 * 1024)
    except Exception:
        logger.warning("Dimensione database non leggibile: %s", db_path, exc_info=True)
        return 0.0


def _backup_database(db_path: str) -> Optional[Path]:
    """Copia di sicurezza accanto al database, prima di riscrivere i percorsi.

    Nessuna soglia di dimensione: la copia la chiede l'utente sapendo quanto
    pesa l'archivio, quindi saltarla di nascosto sarebbe peggio che farla
    aspettare. Restituisce il path del backup, o None se non è stato possibile
    crearlo (spazio esaurito, permessi).
    """
    try:
        # Path importato qui e non dal modulo: il backup lavora sul filesystem
        # locale, dove serve sempre la classe concreta del sistema in uso.
        from pathlib import Path as _Path
        src = _Path(db_path)
        if not src.exists():
            return None

        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = src.with_name(f"{src.stem}_pre_migrazione_percorsi_{stamp}{src.suffix}")
        shutil.copy2(src, dest)
        logger.info("Backup pre-migrazione creato: %s", dest.name)
        return dest
    except Exception as e:
        logger.warning("Backup pre-migrazione non riuscito: %s", e, exc_info=True)
        return None


def _backup_non_necessario(db_path: str) -> bool:
    """True se non c'era proprio niente da salvare (database inesistente).

    Distingue il caso innocuo dal guasto vero: se il file non c'è, l'assenza di
    backup non è un motivo per rinunciare alla migrazione.
    """
    try:
        from pathlib import Path as _Path
        return not _Path(db_path).exists()
    except Exception:
        logger.warning("Controllo esistenza database non riuscito", exc_info=True)
        return False


def anteprima(conn: sqlite3.Connection) -> Optional[dict]:
    """Cosa farebbe la migrazione, senza toccare niente. None se non serve.

    Pensata per popolare la finestra che chiede conferma all'utente: dice
    quante immagini verrebbero allineate e fra quali scritture, così la
    decisione si prende su dati concreti invece che su un messaggio generico.

    Returns:
        dict con 'record' (int) e 'radici' (lista di coppie da→a), oppure None
    """
    da_allineare = _radici_da_allineare(conn)
    if not da_allineare:
        return None
    try:
        record = 0
        for (fp,) in conn.execute(
                "SELECT filepath FROM images WHERE filepath IS NOT NULL"):
            if fp and Path(fp).anchor in da_allineare:
                record += 1
    except sqlite3.Error as e:
        logger.warning("Anteprima migrazione non riuscita: %s", e, exc_info=True)
        return None
    return {
        'record': record,
        'radici': [(v, n) for v, n in da_allineare.items()],
    }


def migrate_database(conn: sqlite3.Connection, db_path: str = None,
                     backup: bool = True) -> int:
    """Uniforma la radice dei percorsi già registrati. Restituisce quanti ne ha corretti.

    Args:
        conn: connessione SQLite aperta sul database da migrare
        db_path: percorso del file database, necessario per la copia di sicurezza
        backup: se True (predefinito) copia il database prima di scrivere, e in
                caso di guasto rinuncia a migrare. Passare False solo quando è
                l'utente a dichiarare di avere già un backup proprio: la
                migrazione procede comunque, sotto la sua responsabilità.

    Returns:
        int: numero di record corretti (0 se non c'era nulla da fare)
    """
    try:
        da_allineare = _radici_da_allineare(conn)
        if not da_allineare:
            return 0

        for vecchia, nuova in da_allineare.items():
            logger.info("Migrazione percorsi: %r → %r", vecchia, nuova)

        # Raccoglie prima e scrive dopo: modificare mentre si scorre un cursore
        # SQLite dà risultati imprevedibili.
        da_correggere = []
        for (img_id, fp) in conn.execute(
                "SELECT id, filepath FROM images WHERE filepath IS NOT NULL"):
            if not fp:
                continue
            radice = Path(fp).anchor
            destinazione = da_allineare.get(radice)
            if destinazione:
                da_correggere.append((destinazione + fp[len(radice):], img_id))

        if not da_correggere:
            return 0

        if backup and db_path:
            # Se la copia non riesce per un guasto — permessi, disco pieno — si
            # rinuncia a migrare invece di riscrivere senza rete. Il DB resta
            # nello stato misto, comunque utilizzabile grazie alla fusione
            # delle radici nell'albero directory.
            if _backup_database(db_path) is None and not _backup_non_necessario(db_path):
                logger.warning(
                    "Migrazione percorsi rinviata: backup non riuscito, "
                    "il database non viene modificato")
                return 0
        elif not backup:
            logger.info("Migrazione percorsi: backup saltato su richiesta dell'utente")

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
