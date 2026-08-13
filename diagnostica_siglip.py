#!/usr/bin/env python3
"""
Diagnostica SigLIP / protobuf — OffGallery
Da lanciare con l'ambiente OffGallery attivo:

    conda activate OffGallery
    python diagnostica_siglip.py

Non modifica nulla: legge soltanto e stampa un rapporto da incollare.
"""
import os
import subprocess
import sys

SEP = "=" * 62


def riga(k, v):
    print(f"  {k:<26} {v}")


print(SEP)
print("  DIAGNOSTICA SigLIP / protobuf — OffGallery")
print(SEP)

# --- 1. Ambiente -----------------------------------------------------------
print("\n[1] Ambiente")
riga("Python", sys.version.split()[0])
riga("eseguibile", sys.executable)
riga("piattaforma", sys.platform)
riga("env PROTOCOL_BUFFERS...", os.environ.get(
    'PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION', '(non impostata)'))

# --- 2. Versioni ------------------------------------------------------------
print("\n[2] Versioni dei pacchetti coinvolti")
for nome in ('google.protobuf', 'sentencepiece', 'transformers'):
    try:
        mod = __import__(nome, fromlist=['__version__'])
        riga(nome, getattr(mod, '__version__', '(sconosciuta)'))
    except Exception as e:
        riga(nome, f"NON IMPORTABILE: {type(e).__name__}: {e}")

# --- 3. Quale motore protobuf, e da dove -----------------------------------
# È il punto chiave: il modulo C ("upb") è il sospettato principale.
print("\n[3] Motore protobuf in uso  <-- il dato decisivo")
try:
    from google.protobuf.internal import api_implementation
    riga("implementazione", api_implementation.Type())
except Exception as e:
    riga("implementazione", f"non determinabile: {e}")

try:
    import google.protobuf as _p
    riga("percorso pacchetto", os.path.dirname(_p.__file__))
except Exception as e:
    riga("percorso pacchetto", f"errore: {e}")

try:
    from google._upb import _message as _u
    riga("binario upb", getattr(_u, '__file__', '(built-in)'))
except Exception as e:
    riga("binario upb", f"non caricabile: {type(e).__name__}: {e}")

# --- 4. Il test che fallisce, con i due motori -----------------------------
# Ogni prova gira in un processo separato: protobuf legge la variabile
# d'ambiente una sola volta, quindi non si possono confrontare a caldo.
print("\n[4] Caricamento dello schema sentencepiece, motore per motore")
PROVA = (
    "from sentencepiece import sentencepiece_model_pb2 as m;"
    "print('OK  default character_coverage =', "
    "m.ModelProto().trainer_spec.character_coverage)"
)
for impl in ('upb', 'python'):
    env = dict(os.environ, PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=impl)
    try:
        r = subprocess.run([sys.executable, '-c', PROVA], env=env,
                           capture_output=True, text=True, timeout=180)
        out = (r.stdout or '').strip()
        if r.returncode == 0 and out:
            riga(f"motore {impl}", out)
        else:
            err = [l for l in (r.stderr or '').strip().splitlines()
                   if 'Error' in l or 'error' in l]
            riga(f"motore {impl}", "FALLITO -> " +
                 (err[-1][:150] if err else 'errore sconosciuto'))
    except Exception as e:
        riga(f"motore {impl}", f"prova non eseguibile: {e}")

# --- 5. Il tokenizer vero di SigLIP ----------------------------------------
print("\n[5] Tokenizer SigLIP vero e proprio (via transformers)")
PROVA_TOK = (
    "from transformers.convert_slow_tokenizer import import_protobuf;"
    "import_protobuf(); print('OK  import_protobuf() riuscito')"
)
for impl in ('upb', 'python'):
    env = dict(os.environ, PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=impl)
    try:
        r = subprocess.run([sys.executable, '-c', PROVA_TOK], env=env,
                           capture_output=True, text=True, timeout=300)
        out = (r.stdout or '').strip().splitlines()
        ok = [l for l in out if 'OK' in l]
        if r.returncode == 0 and ok:
            riga(f"motore {impl}", ok[-1])
        else:
            err = [l for l in (r.stderr or '').strip().splitlines()
                   if 'Error' in l or 'error' in l]
            riga(f"motore {impl}", "FALLITO -> " +
                 (err[-1][:150] if err else 'errore sconosciuto'))
    except Exception as e:
        riga(f"motore {impl}", f"prova non eseguibile: {e}")

print("\n" + SEP)
print("  Fine. Copiare TUTTO il testo qui sopra e inviarlo.")
print(SEP)
