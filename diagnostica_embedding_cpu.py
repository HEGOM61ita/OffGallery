# -*- coding: utf-8 -*-
"""
DIAGNOSTICA — embedding mancanti su CPU (segnalazione: 6 su 13)

A cosa serve
------------
Una volta e' successo che, elaborando 13 immagini con i modelli su CPU, solo 6
avessero l'embedding nel database. Nessun errore nei log. Questo script NON
corregge niente: conta. Serve a stabilire se il difetto esiste davvero e con
quale frequenza, prima di toccare il codice.

Come si usa
-----------
    conda activate OffGallery
    python diagnostica_embedding_cpu.py <cartella_con_immagini>

Facoltativi:
    --ripetizioni 5     quante volte ripetere la prova  (default 5)
    --device cpu|cuda   dove far girare i modelli       (default cpu)

La prova viene ripetuta piu' volte perche' il difetto e' comparso una volta
sola: una singola esecuzione andata bene non dimostra nulla.

Alla fine: copiare TUTTO il testo e inviarlo.
"""
import argparse
import json
import os
import platform
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

SEP = "=" * 74

def riga(k, v):
    print(f"  {k:<34} {v}")

def titolo(n, testo):
    print(f"\n[{n}] {testo}")


# ─────────────────────────────────────────────────────────────────────────
# Argomenti
# ─────────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(add_help=True)
ap.add_argument('cartella', nargs='?', help="cartella con le immagini di prova")
ap.add_argument('--ripetizioni', type=int, default=5)
ap.add_argument('--device', default='cpu', choices=['cpu', 'cuda'])
ap.add_argument('--max-immagini', type=int, default=13,
                help="quante immagini usare per ogni giro (default 13, come la segnalazione)")
args = ap.parse_args()

print(SEP)
print("  DIAGNOSTICA — embedding mancanti su CPU — OffGallery")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(SEP)

if not args.cartella:
    print("\n  Manca la cartella delle immagini.")
    print("  Uso:  python diagnostica_embedding_cpu.py <cartella_con_immagini>")
    sys.exit(1)

cartella = Path(args.cartella)
if not cartella.is_dir():
    print(f"\n  Cartella non trovata: {cartella}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────
# [1] Ambiente
# ─────────────────────────────────────────────────────────────────────────
titolo(1, "Ambiente")
riga("Sistema", f"{platform.system()} {platform.release()}")
riga("Python", sys.version.split()[0])
riga("Interprete", sys.executable)
riga("Processori logici", os.cpu_count())
try:
    import torch
    riga("torch", torch.__version__)
    riga("CUDA disponibile", torch.cuda.is_available())
    if torch.cuda.is_available():
        riga("GPU", torch.cuda.get_device_name(0))
    riga("thread torch (get_num_threads)", torch.get_num_threads())
    riga("thread interop", torch.get_num_interop_threads())
except Exception as e:
    riga("torch", f"NON IMPORTABILE: {e}")

for nome in ('transformers', 'PIL', 'numpy', 'pyiqa', 'open_clip_torch'):
    try:
        mod = __import__(nome)
        riga(nome, getattr(mod, '__version__', '(versione non esposta)'))
    except Exception:
        riga(nome, "non installato")

try:
    import psutil
    vm = psutil.virtual_memory()
    riga("RAM totale", f"{vm.total / 1e9:.1f} GB")
    riga("RAM libera all'avvio", f"{vm.available / 1e9:.1f} GB")
    _psutil = psutil
except Exception:
    riga("RAM", "psutil non installato (memoria non misurata)")
    _psutil = None


# ─────────────────────────────────────────────────────────────────────────
# [2] Immagini di prova
# ─────────────────────────────────────────────────────────────────────────
titolo(2, "Immagini di prova")
ESTENSIONI = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.orf', '.cr2', '.cr3',
              '.nef', '.arw', '.dng', '.raf', '.rw2', '.pef', '.nrw'}
immagini = sorted(p for p in cartella.iterdir()
                  if p.is_file() and p.suffix.lower() in ESTENSIONI)[:args.max_immagini]
riga("Cartella", cartella)
riga("Immagini trovate", len(immagini))
if not immagini:
    print("\n  Nessuna immagine utilizzabile nella cartella. Interrotto.")
    sys.exit(1)
for p in immagini:
    riga(f"  {p.name}", f"{p.stat().st_size / 1e6:.1f} MB")


# ─────────────────────────────────────────────────────────────────────────
# [3] Configurazione: quali modelli sono accesi e su che scheda
# ─────────────────────────────────────────────────────────────────────────
titolo(3, "Configurazione dei modelli")
try:
    import yaml
    from utils.paths import get_app_dir
    cfg_path = get_app_dir() / 'config_new.yaml'
    config = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
except Exception as e:
    print(f"  Configurazione non leggibile: {e}")
    sys.exit(1)

modelli_cfg = config.get('embedding', {}).get('models', {})
attesi = []          # modelli che DOVREBBERO produrre un risultato
for chiave in ('clip', 'dinov2', 'aesthetic', 'technical', 'bioclip'):
    m = modelli_cfg.get(chiave, {})
    acceso = m.get('enabled', False)
    dev    = m.get('device', '(non indicato)')
    riga(chiave, f"acceso={acceso}  scheda={dev}")
    if acceso:
        attesi.append(chiave)
llm = modelli_cfg.get('llm_vision', {})
riga("llm_vision", f"acceso={llm.get('enabled', False)}  backend={llm.get('backend', '?')}")

# La prova forza il device richiesto, senza toccare il file di configurazione
for chiave in ('clip', 'dinov2', 'aesthetic', 'technical', 'bioclip'):
    if chiave in modelli_cfg:
        modelli_cfg[chiave]['device'] = args.device
# L'LLM resta spento: qui si misurano gli embedding, non la generazione testi
if 'llm_vision' in modelli_cfg:
    modelli_cfg['llm_vision']['enabled'] = False
riga("scheda forzata per questa prova", args.device)
riga("modelli attesi per immagine", ', '.join(attesi) or '(nessuno!)')

if not attesi:
    print("\n  Nessun modello embedding e' acceso: non c'e' niente da contare.")
    print("  Accendere almeno CLIP in Configurazione e ripetere.")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────
# [4] I giri di prova
# ─────────────────────────────────────────────────────────────────────────
titolo(4, f"Prova ripetuta {args.ripetizioni} volte su {len(immagini)} immagini")
print("  Per ogni immagine si conta quali modelli hanno prodotto un risultato.")
print("  Attenzione: si conta il RISULTATO, non l'assenza di errori.\n")

CAMPI = {
    'clip':      'clip_embedding',
    'dinov2':    'dinov2_embedding',
    'aesthetic': 'aesthetic_score',
    'technical': 'technical_score',
    'bioclip':   'bioclip_taxonomy',
}

# BioCLIP ha una soglia di confidenza: su un soggetto che non e' un essere
# vivente riconoscibile non restituisce nulla, e questo e' il comportamento
# giusto, non un dato perduto. Contarlo come "mancante" manderebbe a cercare
# un difetto dove non c'e'. Viene quindi contato a parte.
FACOLTATIVI = {'bioclip'}
soglia_bioclip = modelli_cfg.get('bioclip', {}).get('threshold', '(non indicata)')

def vuoto(valore):
    """Un risultato manca se e' None, stringa vuota o blob vuoto."""
    if valore is None:
        return True
    if isinstance(valore, (bytes, str)) and len(valore) == 0:
        return True
    if isinstance(valore, (list, tuple)) and len(valore) == 0:
        return True
    return False

riepilogo = []      # un elemento per giro
eccezioni_viste = []

for giro in range(1, args.ripetizioni + 1):
    print(f"  ── giro {giro} di {args.ripetizioni} " + "─" * 40)
    t_giro = time.time()
    if _psutil:
        ram_prima = _psutil.virtual_memory().available / 1e9

    # Un generatore nuovo ad ogni giro: se il difetto dipende dallo stato
    # accumulato, ripartire da zero lo fa sparire e questo e' un dato utile.
    try:
        from embedding_generator import EmbeddingGenerator
        gen = EmbeddingGenerator(config)
    except Exception as e:
        print(f"    Impossibile creare il generatore: {e}")
        traceback.print_exc()
        break

    presenze = {k: 0 for k in attesi}
    per_immagine = []
    errori_giro = 0

    for idx, img in enumerate(immagini, 1):
        t0 = time.time()
        risultato, errore = None, None
        try:
            risultato = gen.generate_embeddings(str(img))
        except Exception as e:
            errore = f"{type(e).__name__}: {e}"
            errori_giro += 1
            eccezioni_viste.append((giro, img.name, traceback.format_exc()))
        dt = time.time() - t0

        ottenuti = []
        mancanti = []       # solo modelli che DEVONO dare un risultato
        senza_esito = []    # modelli con soglia: nessun risultato puo' essere corretto
        if isinstance(risultato, dict):
            for chiave in attesi:
                campo = CAMPI[chiave]
                if not vuoto(risultato.get(campo)):
                    ottenuti.append(chiave)
                    presenze[chiave] += 1
                elif chiave in FACOLTATIVI:
                    senza_esito.append(chiave)
                else:
                    mancanti.append(chiave)
        else:
            mancanti = [c for c in attesi if c not in FACOLTATIVI]
            senza_esito = [c for c in attesi if c in FACOLTATIVI]

        per_immagine.append({
            'file': img.name, 'secondi': round(dt, 2),
            'ottenuti': ottenuti, 'mancanti': mancanti,
            'senza_esito': senza_esito, 'errore': errore,
        })
        if mancanti:
            stato = f"MANCA: {', '.join(mancanti)}"
        elif senza_esito:
            stato = f"completa (nessuna specie riconosciuta: {', '.join(senza_esito)})"
        else:
            stato = "completa"
        extra = f"  [eccezione: {errore}]" if errore else ""
        print(f"    {idx:>2}/{len(immagini)} {img.name:<30} {dt:>6.1f}s  {stato}{extra}")

    durata = time.time() - t_giro
    # "completa" = nessun modello obbligatorio senza risultato. I modelli con
    # soglia (BioCLIP) non contano: il loro silenzio puo' essere corretto.
    complete = sum(1 for r in per_immagine if not r['mancanti'])
    riepilogo.append({
        'giro': giro, 'secondi': round(durata, 1),
        'immagini': len(immagini), 'complete': complete,
        'presenze': dict(presenze), 'errori': errori_giro,
        'per_immagine': per_immagine,
        'thread_vivi': threading.active_count(),
        'ram_libera_prima_gb': round(ram_prima, 1) if _psutil else None,
        'ram_libera_dopo_gb': round(_psutil.virtual_memory().available / 1e9, 1) if _psutil else None,
    })
    print(f"    → {complete}/{len(immagini)} immagini complete in {durata:.0f}s"
          f" | thread vivi: {threading.active_count()}")
    for chiave in attesi:
        print(f"      {chiave:<12} {presenze[chiave]}/{len(immagini)}")

    # Liberare il generatore fra un giro e l'altro
    try:
        del gen
        import gc; gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# [5] Il conto che risponde alla domanda
# ─────────────────────────────────────────────────────────────────────────
titolo(5, "Conteggio complessivo  <-- il dato decisivo")
tot_img = sum(r['immagini'] for r in riepilogo)
tot_ok  = sum(r['complete'] for r in riepilogo)
riga("Immagini elaborate in tutto", tot_img)
riga("Immagini con tutti i risultati attesi", f"{tot_ok}/{tot_img}")
riga("Immagini incomplete", tot_img - tot_ok)
riga("Eccezioni sollevate", sum(r['errori'] for r in riepilogo))

print()
for chiave in attesi:
    ottenuti = sum(r['presenze'][chiave] for r in riepilogo)
    quota = 100.0 * ottenuti / tot_img if tot_img else 0
    if chiave in FACOLTATIVI:
        nota = f"   (modello con soglia {soglia_bioclip}: un risultato assente puo' essere corretto)"
    elif ottenuti < tot_img:
        nota = "   <-- INCOMPLETO"
    else:
        nota = ""
    riga(chiave, f"{ottenuti}/{tot_img}  ({quota:.0f}%){nota}")

print()
if tot_ok == tot_img:
    print("  ESITO: nessun risultato mancante in questa prova.")
    print("  NON significa che il difetto non esista: significa che qui non si e'")
    print("  ripresentato. Inviare comunque il testo: serve come termine di paragone.")
else:
    print("  ESITO: risultati mancanti RIPRODOTTI.")
    print("  Sotto, l'elenco esatto di cosa e' mancato e dove.")
    for r in riepilogo:
        for v in r['per_immagine']:
            if v['mancanti']:
                print(f"    giro {r['giro']}  {v['file']:<30} manca: {', '.join(v['mancanti'])}"
                      f"  ({v['secondi']}s)" + (f"  eccezione: {v['errore']}" if v['errore'] else ""))


# ─────────────────────────────────────────────────────────────────────────
# [6] Dati per le ipotesi non ancora formulate
# ─────────────────────────────────────────────────────────────────────────
titolo(6, "Dati aggiuntivi (per ipotesi non ancora formulate)")
print("  Giro | durata | complete | errori | thread | RAM libera prima→dopo")
for r in riepilogo:
    ram = (f"{r['ram_libera_prima_gb']}→{r['ram_libera_dopo_gb']} GB"
           if r['ram_libera_prima_gb'] is not None else "(non misurata)")
    print(f"   {r['giro']:>3} | {r['secondi']:>6}s | {r['complete']:>3}/{r['immagini']:<3} |"
          f" {r['errori']:>6} | {r['thread_vivi']:>6} | {ram}")

print("\n  Tempo per immagine, giro per giro (un rallentamento progressivo o un")
print("  tempo vicino a zero su un'immagine incompleta sono indizi diversi):")
for r in riepilogo:
    tempi = ', '.join(f"{v['secondi']}" for v in r['per_immagine'])
    print(f"    giro {r['giro']}: {tempi}")

if eccezioni_viste:
    titolo(7, "Eccezioni per esteso")
    for giro, nome, tb in eccezioni_viste:
        print(f"\n  --- giro {giro}, {nome} ---")
        print('  ' + tb.replace('\n', '\n  '))
else:
    titolo(7, "Eccezioni per esteso")
    print("  Nessuna eccezione sollevata durante la prova.")
    print("  (Nota: e' esattamente cio' che era stato segnalato — nessun errore,")
    print("   e i dati mancanti lo stesso.)")


# ─────────────────────────────────────────────────────────────────────────
# [8] Copia su file
# ─────────────────────────────────────────────────────────────────────────
titolo(8, "Riepilogo salvato su file")
try:
    out = Path(tempfile.gettempdir()) / f"diagnostica_embedding_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({
        'quando': datetime.now().isoformat(),
        'sistema': platform.platform(),
        'device_forzato': args.device,
        'modelli_attesi': attesi,
        'giri': riepilogo,
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    riga("File", out)
except Exception as e:
    riga("File", f"non salvato: {e}")

print("\n" + SEP)
print("  Fine. Copiare TUTTO il testo qui sopra e inviarlo.")
print(SEP)
