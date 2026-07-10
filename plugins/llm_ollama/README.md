# Ollama LLM Vision Plugin

Backend **Ollama** per la generazione di tag, descrizioni e titoli tramite modelli Vision-Language (VLM) locali in OffGallery.

---

## Come funziona

Il plugin si connette al server Ollama in esecuzione localmente e invia le immagini (ridimensionate a 512px) al modello VLM configurato. Il modello genera tag, descrizione e/o titolo in italiano (o nella lingua selezionata) direttamente offline.

---

## Requisiti

- **Ollama** installato e in esecuzione: [ollama.com](https://ollama.com)
- Un modello Vision-Language scaricato in Ollama
- Modello consigliato per 8 GB VRAM: `qwen3-vl:8b-instruct-q4_K_M`

### Installazione modello consigliato

```bash
ollama pull qwen3-vl:8b-instruct-q4_K_M
```

---

## Configurazione

In **Config Tab → Connessione LLM**:

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| Endpoint | `http://localhost:11434` | Indirizzo server Ollama |
| Modello | `qwen3-vl:8b-instruct-q4_K_M` | Nome modello Ollama |
| Timeout | 240 s | Timeout risposta (aumentare per modelli grandi) |

### Parametri di generazione consigliati (8B Q4)

| Parametro | Valore | Descrizione |
|-----------|--------|-------------|
| `temperature` | 0.1 | Output deterministico e preciso |
| `top_k` | 40 | Token candidati per step |
| `top_p` | 0.8 | Nucleus sampling |
| `num_ctx` | 4096 | Finestra di contesto |
| `num_batch` | 512 | Batch prefill |
| `keep_alive` | -1 | Modello sempre in VRAM |

---

## Licenza / License

OffGallery Plugins License v1.0 — Proprietario, nessuna redistribuzione.
Ollama è un software separato distribuito con licenza propria.

---

---

# Ollama LLM Vision Plugin (EN)

**Ollama** backend for generating tags, descriptions and titles using local Vision-Language Models (VLM) in OffGallery.

---

## How it works

The plugin connects to the locally running Ollama server and sends images (resized to 512px) to the configured VLM model. The model generates tags, description and/or title in Italian (or the selected language) entirely offline.

---

## Requirements

- **Ollama** installed and running: [ollama.com](https://ollama.com)
- A Vision-Language model downloaded in Ollama
- Recommended model for 8 GB VRAM: `qwen3-vl:8b-instruct-q4_K_M`

### Install recommended model

```bash
ollama pull qwen3-vl:8b-instruct-q4_K_M
```

---

## Configuration

In **Config Tab → LLM Connection**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Endpoint | `http://localhost:11434` | Ollama server address |
| Model | `qwen3-vl:8b-instruct-q4_K_M` | Ollama model name |
| Timeout | 240 s | Response timeout (increase for large models) |

### Recommended generation parameters (8B Q4)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `temperature` | 0.1 | Deterministic, precise output |
| `top_k` | 40 | Candidate tokens per step |
| `top_p` | 0.8 | Nucleus sampling |
| `num_ctx` | 4096 | Context window |
| `num_batch` | 512 | Prefill batch size |
| `keep_alive` | -1 | Model always in VRAM |

---

## License

OffGallery Plugins License v1.0 — Proprietary, no redistribution.
Ollama is a separate software distributed under its own license.
