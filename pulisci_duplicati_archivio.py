# -*- coding: utf-8 -*-
"""
Trova ed elimina le schede doppie nell'archivio.

Perché servono
--------------
Fino al 2026-08-25 la modalità «rielabora tutte» non riconosceva «D:» e «d:»
come lo stesso disco: la scansione di Windows produce la lettera maiuscola,
mentre nell'archivio alcune foto erano registrate con la minuscola. La foto
sembrava nuova e veniva aggiunta una seconda volta. Il difetto è stato corretto,
ma le schede doppie già create restano.

Cosa fa
-------
Per ogni foto presente più volte tiene la scheda **più completa** (quella con
più informazioni: descrizione, titolo, tag, impronte visive) e rimuove le altre.
Non sempre la più recente è la più ricca, quindi il criterio è la completezza,
non la data.

⚠️ Tocca soltanto l'archivio: le fotografie sui dischi non vengono mai sfiorate.

Uso
---
    python pulisci_duplicati_archivio.py            mostra cosa farebbe
    python pulisci_duplicati_archivio.py --esegui   rimuove davvero
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ap = argparse.ArgumentParser(add_help=True)
ap.add_argument('--esegui', action='store_true', help="rimuove davvero (senza, mostra soltanto)")
ap.add_argument('--dettaglio', type=int, default=10, help="quante coppie mostrare (default 10)")
args = ap.parse_args()

SEP = "=" * 74
print(SEP)
print("  Schede doppie nell'archivio")
print(SEP)

import yaml
from utils.paths import get_app_dir
cfg = yaml.safe_load((get_app_dir() / 'config_new.yaml').read_text(encoding='utf-8'))
db_path = Path(cfg['paths']['database'])
if not db_path.is_absolute():
    db_path = get_app_dir() / db_path

print(f"\n  Archivio: {db_path}")
conn = sqlite3.connect(db_path)

# Campi che rendono una scheda "completa"
CAMPI = ['clip_embedding', 'dinov2_embedding', 'description', 'title',
         'llm_tags', 'tags', 'bioclip_taxonomy', 'aesthetic_score',
         'technical_score', 'geo_hierarchy', 'vernacular_name']
esistenti = {r[1] for r in conn.execute("PRAGMA table_info(images)")}
campi = [c for c in CAMPI if c in esistenti]

totale = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]

# Doppioni sul percorso, senza distinguere maiuscole e minuscole
gruppi = conn.execute("""
    SELECT LOWER(filepath) AS chiave, COUNT(*) AS quante
    FROM images GROUP BY chiave HAVING quante > 1
""").fetchall()

print(f"  Foto in archivio        : {totale}")
print(f"  Presenti più di una volta: {len(gruppi)}")

if not gruppi:
    print("\n  Nessuna scheda doppia: niente da fare.")
    sys.exit(0)

def completezza(riga):
    """Quante informazioni ha questa scheda."""
    return sum(1 for v in riga if v not in (None, '', '[]', b''))

da_rimuovere = []
mostrate = 0
print()
for chiave, quante in gruppi:
    righe = conn.execute(
        f"SELECT id, filepath, processed_date, {', '.join(campi)} FROM images "
        f"WHERE LOWER(filepath) = ? ORDER BY id", (chiave,)
    ).fetchall()
    # (punteggio, data, id) — a parità di completezza vince la più recente
    valutate = sorted(
        ((completezza(r[3:]), str(r[2] or ''), r[0]) for r in righe),
        reverse=True
    )
    tenuta = valutate[0]
    scartate = valutate[1:]
    da_rimuovere.extend(t[2] for t in scartate)

    if mostrate < args.dettaglio:
        mostrate += 1
        nome = Path(righe[0][1]).name
        print(f"  {nome}")
        for punti, data, id_ in valutate:
            segno = "TIENE " if id_ == tenuta[2] else "rimuove"
            print(f"      {segno}  id={id_:<6} {data[:16]:<17} {punti}/{len(campi)} informazioni")

if len(gruppi) > mostrate:
    print(f"\n  … e altre {len(gruppi) - mostrate} foto (usa --dettaglio per vederne di più)")

print()
print(SEP)
print(f"  Schede da rimuovere: {len(da_rimuovere)}")
print(f"  Foto in archivio dopo la pulizia: {totale - len(da_rimuovere)}")
print(SEP)

if not args.esegui:
    print("\n  Non è stato modificato nulla (prova a vuoto).")
    print("  Per rimuoverle davvero:  python pulisci_duplicati_archivio.py --esegui")
    sys.exit(0)

# Copia di sicurezza prima di toccare l'archivio
backup = db_path.with_name(f"{db_path.stem}_prima_pulizia_{datetime.now():%Y%m%d_%H%M%S}{db_path.suffix}")
print(f"\n  Copia di sicurezza: {backup.name}")
try:
    conn.close()
    shutil.copy2(db_path, backup)
    conn = sqlite3.connect(db_path)
except Exception as e:
    print(f"  Copia non riuscita: {e}")
    print("  Interrotto: senza copia di sicurezza non si procede.")
    sys.exit(1)

rimosse = 0
try:
    for i in range(0, len(da_rimuovere), 500):
        blocco = da_rimuovere[i:i + 500]
        conn.execute(
            f"DELETE FROM images WHERE id IN ({','.join('?' * len(blocco))})", blocco
        )
        rimosse += len(blocco)
    conn.commit()
except Exception as e:
    conn.rollback()
    print(f"  Errore durante la rimozione: {e}")
    print(f"  Nessuna modifica applicata. L'archivio è intatto.")
    sys.exit(1)

rimasti = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
conn.close()

print(f"  Schede rimosse : {rimosse}")
print(f"  Foto rimaste   : {rimasti}")
print(f"\n  Se qualcosa non torna, l'archivio precedente è in {backup.name}")
