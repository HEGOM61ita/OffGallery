# -*- coding: utf-8 -*-
"""
Misura quanto gli embedding in archivio si discostano da quelli generati oggi.

Perché serve
------------
Il 2026-08-25 è stato corretto un difetto per cui i file RAW venivano descritti
partendo dalla preview JPEG della fotocamera invece che dall'immagine sviluppata
dal sensore (rawpy falliva sempre, in silenzio). L'immagine data ai modelli è
ora migliore, ma diversa: gli embedding calcolati prima e dopo non coincidono.

Questo strumento NON modifica niente: prende un campione di immagini, ricalcola
l'embedding e lo confronta con quello in archivio. Serve a decidere se valga la
pena rigenerare, e per quali file.

Come si legge il risultato
--------------------------
La somiglianza va da 0 a 1. Sopra 0,95 la differenza è trascurabile per la
ricerca; sotto 0,90 le due immagini sono abbastanza diverse da spostare i
risultati.

Uso
---
    python misura_scarto_embedding.py                 100 immagini a campione
    python misura_scarto_embedding.py --quante 300    campione più ampio
    python misura_scarto_embedding.py --elenco        elenca i file più discordanti
"""
import argparse
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ap = argparse.ArgumentParser(add_help=True)
ap.add_argument('--quante', type=int, default=100, help="immagini da controllare (default 100)")
ap.add_argument('--elenco', action='store_true', help="elenca i file più discordanti")
args = ap.parse_args()

SEP = "=" * 74
print(SEP)
print("  Quanto sono cambiati gli embedding dopo la correzione dei RAW")
print(SEP)

import warnings
warnings.filterwarnings('ignore')
import numpy as np
import yaml
from utils.paths import get_app_dir

cfg = yaml.safe_load((get_app_dir() / 'config_new.yaml').read_text(encoding='utf-8'))
db_path = cfg['paths']['database']

# Solo CLIP: gli altri modelli non servono e costerebbero tempo e memoria
for k in ('dinov2', 'aesthetic', 'technical', 'bioclip', 'llm_vision'):
    if k in cfg['embedding']['models']:
        cfg['embedding']['models'][k]['enabled'] = False

conn = sqlite3.connect(db_path)
rows = conn.execute(
    "SELECT filepath, filename, clip_embedding FROM images WHERE clip_embedding IS NOT NULL"
).fetchall()
conn.close()

RAW_EXT = {'.orf','.cr2','.nef','.arw','.dng','.raf','.cr3','.nrw','.srf','.sr2',
           '.rw2','.raw','.pef','.ptx','.rwl','.3fr','.iiq','.x3f'}

def e_raw(p): return Path(p).suffix.lower() in RAW_EXT

raw_rows = [r for r in rows if e_raw(r[0])]
altri_rows = [r for r in rows if not e_raw(r[0])]

print(f"\n  In archivio con embedding : {len(rows)}")
print(f"    di cui RAW              : {len(raw_rows)}   <- toccati dalla correzione")
print(f"    altri formati           : {len(altri_rows)}")

# Campione: in prevalenza RAW, con alcuni non-RAW come termine di paragone
n_raw = min(int(args.quante * 0.8), len(raw_rows))
n_alt = min(args.quante - n_raw, len(altri_rows))
def campiona(lista, n):
    if not lista or n <= 0: return []
    passo = max(1, len(lista) // n)
    return lista[::passo][:n]
campione = [(r, True) for r in campiona(raw_rows, n_raw)] + \
           [(r, False) for r in campiona(altri_rows, n_alt)]

print(f"  Campione da controllare   : {len(campione)} ({n_raw} RAW, {n_alt} altri)")
print("\n  Caricamento del modello…")

import io, contextlib
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from embedding_generator import EmbeddingGenerator
    gen = EmbeddingGenerator(cfg)

def leggi_embedding(blob):
    """Deserializza l'embedding dal database (raw float32, o pickle nei formati vecchi)."""
    if not isinstance(blob, bytes):
        return None
    if len(blob) > 1 and blob[0] == 0x80 and blob[1] in (2, 3, 4, 5):
        import pickle
        return np.asarray(pickle.loads(blob), dtype=np.float32).flatten()
    if len(blob) % 4 == 0:
        return np.frombuffer(blob, dtype=np.float32).copy()
    return None

print("  Confronto in corso (ogni immagine viene rielaborata)…\n")
risultati = []
saltate = Counter()
t0 = time.time()

for i, ((filepath, filename, blob), raw) in enumerate(campione, 1):
    if i % 10 == 0 or i == len(campione):
        trascorso = time.time() - t0
        rimanenti = (trascorso / i) * (len(campione) - i)
        print(f"    {i}/{len(campione)}  (circa {rimanenti/60:.0f} min rimanenti)", end='\r')
    if not Path(filepath).exists():
        saltate['file non raggiungibile'] += 1
        continue
    vecchio = leggi_embedding(blob)
    if vecchio is None or vecchio.size == 0:
        saltate['embedding illeggibile'] += 1
        continue
    try:
        out = gen.generate_embeddings(filepath)
        nuovo = out.get('clip_embedding') if isinstance(out, dict) else out
        nuovo = np.asarray(nuovo, dtype=np.float32).flatten()
    except Exception:
        saltate['rielaborazione fallita'] += 1
        continue
    if nuovo.size != vecchio.size:
        saltate['dimensioni diverse'] += 1
        continue
    a = vecchio / (np.linalg.norm(vecchio) or 1)
    b = nuovo / (np.linalg.norm(nuovo) or 1)
    risultati.append((float(np.dot(a, b)), filename, raw))

print(" " * 60, end='\r')

if not risultati:
    print("\n  Nessun confronto riuscito.")
    for m, n in saltate.items(): print(f"    {m}: {n}")
    sys.exit(1)

print(f"\n  Confronti riusciti: {len(risultati)} in {(time.time()-t0)/60:.1f} minuti")
if saltate:
    for m, n in saltate.items(): print(f"    saltate — {m}: {n}")

def riepiloga(titolo, dati):
    if not dati: return
    v = sorted(s for s, _, _ in dati)
    n = len(v)
    print(f"\n  {titolo}  ({n} immagini)")
    print(f"    somiglianza media    : {sum(v)/n:.4f}")
    print(f"    mediana              : {v[n//2]:.4f}")
    print(f"    peggiore             : {v[0]:.4f}")
    print(f"    migliore             : {v[-1]:.4f}")
    fasce = [
        ("praticamente identici (>0,99)", sum(1 for s in v if s > 0.99)),
        ("differenza trascurabile (0,95-0,99)", sum(1 for s in v if 0.95 < s <= 0.99)),
        ("differenza percepibile (0,90-0,95)", sum(1 for s in v if 0.90 < s <= 0.95)),
        ("immagini diverse (<0,90)", sum(1 for s in v if s <= 0.90)),
    ]
    for etichetta, quanti in fasce:
        if quanti:
            print(f"      {etichetta:<38} {quanti:>4}  ({100*quanti/n:.0f}%)")

riepiloga("RAW — toccati dalla correzione", [r for r in risultati if r[2]])
riepiloga("Altri formati — termine di paragone", [r for r in risultati if not r[2]])

raw_v = [s for s, _, r in risultati if r]
print("\n" + SEP)
if raw_v:
    sotto = sum(1 for s in raw_v if s <= 0.95)
    quota = 100 * sotto / len(raw_v)
    print(f"  CONCLUSIONE: {sotto} RAW su {len(raw_v)} ({quota:.0f}%) hanno un embedding")
    print(f"  abbastanza diverso da spostare i risultati di ricerca.")
    print()
    if quota < 10:
        print("  Rigenerare non sembra necessario: la grande maggioranza combacia.")
    elif quota < 40:
        print("  Conviene rigenerare i RAW, ma non c'e' urgenza: la ricerca")
        print("  funziona, con qualche imprecisione sull'archivio misto.")
    else:
        print("  Conviene rigenerare gli embedding dei RAW: una parte")
        print("  consistente dell'archivio non e' piu' confrontabile.")
print(SEP)

if args.elenco:
    print("\n  I venti file piu' discordanti:")
    for s, nome, raw in sorted(risultati)[:20]:
        print(f"    {s:.4f}  {'RAW ' if raw else '    '} {nome}")
