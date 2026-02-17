"""
Test standalone per le 3 chiamate Ollama Vision (title, tags, description).
Replica esattamente i parametri e i prompt di embedding_generator.py.
Usa la prima immagine trovata in /INPUT.

Uso: python test_ollama_calls.py
"""

import os
import sys
import time
import base64
import glob
import requests
import re
import yaml

# --- Carica config ---
config_path = os.path.join(os.path.dirname(__file__), "config_new.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

llm_config = config["embedding"]["models"]["llm_vision"]
generation = llm_config.get("generation", {})

ENDPOINT = llm_config.get("endpoint", "http://localhost:11434")
MODEL = llm_config.get("model", "qwen3-vl:4b-instruct")
TIMEOUT = llm_config.get("timeout", 180)
KEEP_ALIVE = generation.get("keep_alive", -1)
TEMPERATURE = generation.get("temperature", 0.2)
TOP_P = generation.get("top_p", 0.8)
TOP_K = generation.get("top_k", 20)
NUM_CTX = generation.get("num_ctx", 2048)
NUM_BATCH = generation.get("num_batch", 1024)
MIN_P = generation.get("min_p", 0.0)

MAX_TAGS = 10
MAX_TITLE_WORDS = 5
MAX_DESC_WORDS = 50
THINK_MARGIN_SMALL = 10  # per title e tags (come embedding_generator)
THINK_MARGIN_DESC = 20   # per description (come embedding_generator)

# --- Immagine da processare ---
input_dir = os.path.join(os.path.dirname(__file__), "INPUT")
# Specifica il file da testare (None = cerca la prima immagine)
TARGET_FILE = "_OMX0627.ORF"

if TARGET_FILE:
    image_path = os.path.join(input_dir, TARGET_FILE)
    if not os.path.exists(image_path):
        print(f"❌ File non trovato: {image_path}")
        sys.exit(1)
else:
    extensions = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff", "*.webp",
                  "*.cr2", "*.cr3", "*.nef", "*.arw", "*.orf", "*.raf", "*.rw2", "*.dng")
    image_path = None
    for ext in extensions:
        found = glob.glob(os.path.join(input_dir, ext))
        if found:
            image_path = found[0]
            break
    if not image_path:
        print(f"❌ Nessuna immagine trovata in {input_dir}")
        sys.exit(1)

print(f"📷 Immagine: {os.path.basename(image_path)}")
print(f"🤖 Modello: {MODEL}")
print(f"⚙️  Params: temp={TEMPERATURE}, top_k={TOP_K}, top_p={TOP_P}, num_ctx={NUM_CTX}, num_batch={NUM_BATCH}, keep_alive={KEEP_ALIVE}")
print(f"{'='*70}")

# --- Ridimensiona immagine come fa l'app (profilo llm_vision) ---
from PIL import Image
LLM_TARGET_SIZE = config.get("image_optimization", {}).get("profiles", {}).get("llm_vision", {}).get("target_size", 512)

# Estrai immagine (supporta RAW via RAWProcessor)
RAW_EXTENSIONS = {'.cr2', '.cr3', '.crw', '.nef', '.nrw', '.arw', '.srf', '.sr2',
                  '.raf', '.orf', '.rw2', '.raw', '.pef', '.ptx', '.dng', '.rwl',
                  '.3fr', '.iiq', '.x3f'}
ext = os.path.splitext(image_path)[1].lower()

if ext in RAW_EXTENSIONS:
    from pathlib import Path
    from raw_processor import RAWProcessor
    raw_proc = RAWProcessor(config)
    img = raw_proc.extract_thumbnail(Path(image_path), target_size=LLM_TARGET_SIZE)
    if not img:
        print(f"❌ Impossibile estrarre thumbnail da {image_path}")
        sys.exit(1)
    orig_size = img.size
else:
    img = Image.open(image_path)
    orig_size = img.size
    max_side = max(img.size)
    if max_side > LLM_TARGET_SIZE:
        scale = LLM_TARGET_SIZE / max_side
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

# Converti in JPEG base64
import io
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=85)
image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
print(f"📐 Immagine: {orig_size[0]}x{orig_size[1]} → {img.size[0]}x{img.size[1]} (target: {LLM_TARGET_SIZE}px)")


def strip_think_blocks(text):
    """Rimuovi blocchi <think>...</think> dalla risposta LLM (qwen3)."""
    if "<think>" in text:
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if cleaned:
            return cleaned
        if "</think>" not in text:
            return ""
    return text


def call_ollama(prompt, max_tokens, label):
    """Chiama Ollama e misura il tempo."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "num_predict": max_tokens,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "top_k": TOP_K,
            "min_p": MIN_P,
            "num_ctx": NUM_CTX,
            "num_batch": NUM_BATCH,
        },
    }

    print(f"\n🔄 [{label}] num_predict={max_tokens} ...")
    t0 = time.time()
    response = requests.post(f"{ENDPOINT}/api/generate", json=payload, timeout=TIMEOUT)
    elapsed = time.time() - t0

    if response.status_code != 200:
        print(f"   ❌ HTTP {response.status_code}: {response.text[:200]}")
        return None, elapsed

    result = response.json()
    raw = result.get("response", "").strip()
    cleaned = strip_think_blocks(raw)

    # Info dal response
    total_duration = result.get("total_duration", 0) / 1e9  # nanosecondi -> secondi
    load_duration = result.get("load_duration", 0) / 1e9
    prompt_eval_duration = result.get("prompt_eval_duration", 0) / 1e9
    eval_duration = result.get("eval_duration", 0) / 1e9
    prompt_eval_count = result.get("prompt_eval_count", 0)
    eval_count = result.get("eval_count", 0)

    print(f"   ⏱️  Tempo totale: {elapsed:.1f}s (HTTP round-trip)")
    print(f"   📊 Ollama internals:")
    print(f"      load_duration:        {load_duration:.2f}s")
    print(f"      prompt_eval_duration: {prompt_eval_duration:.2f}s ({prompt_eval_count} token)")
    print(f"      eval_duration:        {eval_duration:.2f}s ({eval_count} token generati)")
    if eval_count > 0:
        print(f"      velocità generazione: {eval_count / eval_duration:.1f} tok/s")
    print(f"   📝 Raw ({len(raw)} chars): {raw[:150]}{'...' if len(raw) > 150 else ''}")
    print(f"   ✅ Cleaned: {cleaned[:150]}{'...' if len(cleaned) > 150 else ''}")

    return cleaned, elapsed


# === WARMUP (preload modello) ===
print("\n⏳ Warmup: preload modello in VRAM...")
t0 = time.time()
r = requests.post(f"{ENDPOINT}/api/generate", json={"model": MODEL, "keep_alive": KEEP_ALIVE}, timeout=120)
print(f"   Warmup completato in {time.time() - t0:.1f}s (HTTP {r.status_code})")
print(f"{'='*70}")

# === PROMPT: approccio intermedio (identifica se sicuro, altrimenti generico) ===
italian_rules = (
    "LANGUAGE: ALL output MUST be in ITALIAN. NEVER use English words.\n"
    "ANIMAL/PLANT IDENTIFICATION:\n"
    "- If you clearly recognize the species, use its common Italian name (e.g. cervo, delfino, girasole)\n"
    "- If you are NOT sure, use a generic Italian term (uccello, animale, fiore, albero, pesce)\n"
    "- NEVER guess a species name. A generic term is ALWAYS better than a wrong name\n"
    "- Do NOT use scientific/Latin names\n"
)

PROMPTS = {
    "title": {
        "prompt": (
            "You are a professional photo archiving system.\n"
            "Task: generate a factual, descriptive title for this photo.\n\n"
            f"{italian_rules}"
            "\nSTRICT RULES:\n"
            "- Output ONLY the title text, nothing else\n"
            "- NO quotes, NO punctuation at the end\n"
            f"- Maximum {MAX_TITLE_WORDS} words\n"
            "- Be DESCRIPTIVE, not poetic or creative\n"
            "- Focus on: main subject, location type, action (if any)\n"
            "- For animals/plants: prefer generic terms if unsure (e.g. 'Uccello bianco' not a wrong species)\n"
        ),
        "max_tokens": int(MAX_TITLE_WORDS * 2) + THINK_MARGIN_SMALL,
    },
    "tags": {
        "prompt": (
            "You are a professional photographic tagging system.\n"
            "Task: observe the scene and generate photo tags, in format \"tag1,tag2,tag3\".\n"
            "Priority: 1) subjects, 2) scene, 3) actions, 4) objects, 5) weather, 6) mood, 7) colors\n\n"
            f"{italian_rules}"
            "\nSTRICT RULES:\n"
            f"- Maximum {MAX_TAGS} tags\n"
            "- lowercase, singular form\n"
            "- Only tag what you clearly see in the image\n"
        ),
        "max_tokens": (MAX_TAGS * 3) + THINK_MARGIN_SMALL,
    },
    "description": {
        "prompt": (
            "You are a professional photography captioning system.\n"
            "Task: describe the image.\n\n"
            f"{italian_rules}"
            "\nSTRICT RULES:\n"
            "- Output ONLY the description text, nothing else\n"
            "- Include: subject, environment, colors, composition, atmosphere\n"
            f"- Concise, informative, max {MAX_DESC_WORDS} words\n"
        ),
        "max_tokens": int(MAX_DESC_WORDS * 1.5) + THINK_MARGIN_DESC,
    },
}

# === Esegui le 3 chiamate in sequenza ===
total_start = time.time()
results = {}

for mode in ["title", "tags", "description"]:
    p = PROMPTS[mode]
    result, elapsed = call_ollama(p["prompt"], p["max_tokens"], mode.upper())
    results[mode] = {"result": result, "time": elapsed}

total_elapsed = time.time() - total_start

# === Riepilogo ===
print(f"\n{'='*70}")
print(f"📊 RIEPILOGO")
print(f"{'='*70}")
for mode, data in results.items():
    print(f"   {mode:12s}: {data['time']:5.1f}s → {(data['result'] or 'ERRORE')[:80]}")
print(f"   {'─'*50}")
print(f"   {'TOTALE':12s}: {total_elapsed:.1f}s")
