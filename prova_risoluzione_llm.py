#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prova quale risoluzione conviene dare al modello LLM Vision.

Genera la descrizione della STESSA foto a piu' risoluzioni (512, 768, 1024)
e stampa i risultati affiancati, con i tempi. Serve a decidere se il valore
'target_size' del profilo llm_vision, oggi 512, e' adatto al modello in uso.

Il 512 attuale porta un commento che cita un modello diverso da quello
configurato oggi: va rimisurato, non dato per buono.

USO (dal terminale Anaconda su Windows, con Ollama acceso):

    conda activate OffGallery
    python prova_risoluzione_llm.py "D:\\DOWLOAD\\20200116-9610.CR2"

Opzioni:
    --misure 512,768,1024   risoluzioni da provare (default: 512,768,1024)
    --giri 2                ripeti per vedere quanto varia a parita' di misura
"""
import argparse
import sys
import time
from pathlib import Path

# La root del progetto e' la cartella di questo script
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def principale():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('foto', help='percorso della foto (RAW o JPEG)')
    ap.add_argument('--misure', default='512,768,1024',
                    help='risoluzioni da provare, separate da virgola')
    ap.add_argument('--giri', type=int, default=1,
                    help='quante volte ripetere ogni misura')
    args = ap.parse_args()

    foto = Path(args.foto)
    if not foto.exists():
        print(f"ERRORE: file non trovato: {foto}")
        return 1

    try:
        misure = [int(x) for x in args.misure.split(',')]
    except ValueError:
        print(f"ERRORE: --misure vuole numeri separati da virgola, ricevuto: {args.misure}")
        return 1

    # --- Config e generatore, gli stessi che usa l'applicazione -------------
    import yaml
    cfg_path = ROOT / 'config_new.yaml'
    if not cfg_path.exists():
        print(f"ERRORE: config non trovato: {cfg_path}")
        return 1
    with open(cfg_path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    llm_cfg = cfg.get('embedding', {}).get('models', {}).get('llm_vision', {})
    modello = llm_cfg.get('model', '(non indicato)')
    endpoint = llm_cfg.get('endpoint', 'http://localhost:11434')

    print("=" * 78)
    print(f"Foto      : {foto.name}")
    print(f"Modello   : {modello}")
    print(f"Endpoint  : {endpoint}")
    print(f"Misure    : {', '.join(str(m) for m in misure)} px (lato lungo)")
    print(f"Giri      : {args.giri}")
    print("=" * 78)

    # Ollama risponde?
    try:
        import requests
        r = requests.get(f"{endpoint}/api/tags", timeout=5)
        nomi = [m.get('name', '') for m in r.json().get('models', [])]
        if modello not in nomi:
            print(f"\nATTENZIONE: '{modello}' non risulta fra i modelli scaricati.")
            print(f"Disponibili: {', '.join(nomi) if nomi else '(nessuno)'}")
            print("La prova andra' avanti, ma probabilmente fallira'.\n")
    except Exception as e:
        print(f"\nERRORE: Ollama non risponde su {endpoint} ({e})")
        print("Avvia Ollama e riprova.\n")
        return 1

    from embedding_generator import EmbeddingGenerator
    gen = EmbeddingGenerator(cfg)

    risultati = []
    for misura in misure:
        for giro in range(1, args.giri + 1):
            etichetta = f"{misura}px" + (f" (giro {giro})" if args.giri > 1 else "")
            print(f"\n--- {etichetta} " + "-" * (74 - len(etichetta)))

            # L'unica cosa che cambia fra una prova e l'altra: la risoluzione.
            # Si scrive nel profilo che _prepare_llm_image legge davvero.
            gen.optimization_profiles.setdefault('llm_vision', {})['target_size'] = misura
            gen._cleanup_llm_image_cache()   # senza questo riuserebbe l'immagine di prima

            t0 = time.monotonic()
            try:
                out = gen.generate_llm_combined(
                    str(foto),
                    modes=['title', 'tags', 'description'],
                    max_tags=10,
                    max_description_words=100,
                    max_title_words=5,
                ) or {}
            except Exception as e:
                print(f"  FALLITA: {e}")
                risultati.append((etichetta, None, 0))
                continue
            durata = time.monotonic() - t0

            if not out:
                print("  Il modello non ha prodotto nulla.")
                risultati.append((etichetta, None, durata))
                continue

            print(f"  Tempo      : {durata:.1f}s")
            print(f"  Titolo     : {out.get('title', '-')}")
            tags = out.get('tags') or []
            print(f"  Tag        : {', '.join(tags) if tags else '-'}")
            desc = out.get('description', '') or ''
            print(f"  Descrizione: {desc}")
            risultati.append((etichetta, out, durata))

    # --- Riepilogo ---------------------------------------------------------
    print("\n" + "=" * 78)
    print("RIEPILOGO — confronta le descrizioni e scegli a occhio")
    print("=" * 78)
    for etichetta, out, durata in risultati:
        if out is None:
            print(f"{etichetta:16s} FALLITA ({durata:.1f}s)")
            continue
        desc = (out.get('description') or '').replace('\n', ' ')
        n_parole = len(desc.split())
        print(f"{etichetta:16s} {durata:5.1f}s  {n_parole:3d} parole  "
              f"{len(out.get('tags') or []):2d} tag  | {desc[:60]}...")

    print("\nCosa guardare:")
    print("  - la descrizione piu' grande nota dettagli che le altre perdono?")
    print("  - se 768 e 1024 dicono le stesse cose di 512, tenere 512: e' piu' rapido")
    print("  - se le piu' grandi aggiungono dettagli veri, alzare target_size")
    print("\nDove si cambia il valore, se decidi di alzarlo:")
    print("  config_new.yaml -> image_optimization -> profiles -> llm_vision -> target_size")
    print("  (occhio: c'e' un secondo valore in embedding_generator.py:253, usato come")
    print("   ripiego quando il config non ha la voce. Meglio allinearli.)")
    return 0


if __name__ == '__main__':
    sys.exit(principale())
