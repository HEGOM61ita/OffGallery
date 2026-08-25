# -*- coding: utf-8 -*-
"""
Rimuove dalla cache le miniature delle foto ruotate, che erano state salvate coricate.

Perche' serve
-------------
Fino alla correzione dell'orientamento, le miniature delle foto verticali
(EXIF Orientation 5-8) finivano in cache coricate. La correzione vale per le
miniature nuove: quelle gia' in cache restano storte finche' non si rifanno.

Questo script cancella SOLO le miniature delle foto ruotate. Le altre non
vengono toccate, cosi' non si rigenera l'intera cache. Le miniature cancellate
si ricreano da sole quando la foto ricompare in gallery.

NON tocca le fotografie: agisce solo sulla cartella cache/thumbs.

Uso
---
    python pulisci_miniature_ruotate.py            mostra cosa farebbe, senza cancellare
    python pulisci_miniature_ruotate.py --esegui   cancella davvero
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ap = argparse.ArgumentParser(add_help=True)
ap.add_argument('--esegui', action='store_true',
                help="cancella davvero (senza questo, mostra soltanto)")
args = ap.parse_args()

print("=" * 70)
print("  Pulizia miniature delle foto ruotate")
print("=" * 70)

try:
    import yaml
    from utils.paths import get_app_dir
    from utils.thumb_cache import _cache_path, get_thumb_cache_dir
    cfg = yaml.safe_load((get_app_dir() / 'config_new.yaml').read_text(encoding='utf-8'))
    db_path = cfg['paths']['database']
except Exception as e:
    print(f"  Configurazione non leggibile: {e}")
    sys.exit(1)

cache_dir = get_thumb_cache_dir()
print(f"\n  Archivio : {db_path}")
print(f"  Cache    : {cache_dir}")

conn = sqlite3.connect(db_path)
ruotate = conn.execute(
    "SELECT filepath FROM images WHERE orientation IN (2,3,4,5,6,7,8)"
).fetchall()
totali = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
conn.close()

print(f"\n  Foto in archivio          : {totali}")
print(f"  Di cui dichiarate ruotate : {len(ruotate)}")

da_togliere = []
byte_liberati = 0
for (fp,) in ruotate:
    try:
        c = _cache_path(Path(fp))
        if c.exists():
            da_togliere.append(c)
            byte_liberati += c.stat().st_size
    except Exception:
        continue

in_cache = len(list(cache_dir.glob('*.jpg')))
print(f"  Miniature in cache        : {in_cache}")
print(f"  Da rifare (foto ruotate)  : {len(da_togliere)}")
print(f"  Spazio che si libera      : {byte_liberati / 1e6:.0f} MB")
print(f"  Miniature lasciate stare  : {in_cache - len(da_togliere)}")

if not da_togliere:
    print("\n  Niente da fare: nessuna miniatura di foto ruotate in cache.")
    sys.exit(0)

if not args.esegui:
    print("\n  Nessun file e' stato toccato (prova a vuoto).")
    print("  Per cancellare davvero:  python pulisci_miniature_ruotate.py --esegui")
    sys.exit(0)

print()
tolte = falliti = 0
for c in da_togliere:
    try:
        c.unlink()
        tolte += 1
    except Exception as e:
        falliti += 1
        print(f"  Non rimossa: {c.name} ({e})")

print(f"  Miniature rimosse : {tolte}")
if falliti:
    print(f"  Non rimosse       : {falliti}")
print(f"  Spazio liberato   : {byte_liberati / 1e6:.0f} MB")
print("\n  Si ricreeranno da sole, dritte, quando le foto torneranno in gallery.")
