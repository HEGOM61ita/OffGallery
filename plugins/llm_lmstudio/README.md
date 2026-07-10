# LM Studio LLM Vision Plugin

Backend **LM Studio** per la generazione di tag, descrizioni e titoli tramite modelli Vision-Language (VLM) locali in OffGallery.

---

## Come funziona

Il plugin si connette al server locale di LM Studio tramite API compatibile OpenAI e invia le immagini (ridimensionate a 512px) al modello VLM caricato. Il modello genera tag, descrizione e/o titolo in italiano (o nella lingua selezionata) interamente offline.

---

## Requisiti

- **LM Studio** installato e il server locale avviato: [lmstudio.ai](https://lmstudio.ai)
- Un modello Vision-Language caricato in LM Studio
- Modello consigliato: `qwen3-vl` (8B o superiore per risultati ottimali)

---

## Configurazione

In **Config Tab → Connessione LLM**, selezionare il backend **LM Studio**:

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| Endpoint | `http://localhost:1234` | Indirizzo server LM Studio |
| Modello | (nome modello caricato) | Nome esatto del modello in LM Studio |
| Timeout | 240 s | Timeout risposta |

> **Nota**: il nome del modello deve corrispondere esattamente a quello mostrato in LM Studio.

---

## Differenze rispetto al plugin Ollama

| | Ollama | LM Studio |
|--|--------|-----------|
| API | `/api/generate` (nativa) | `/v1/chat/completions` (OpenAI-compat.) |
| Gestione modelli | `ollama pull` da terminale | Interfaccia grafica LM Studio |
| Avvio server | automatico | manuale dal pannello LM Studio |

---

## Licenza / License

OffGallery Plugins License v1.0 — Proprietario, nessuna redistribuzione.
LM Studio è un software separato distribuito con licenza propria.

---

---

# LM Studio LLM Vision Plugin (EN)

**LM Studio** backend for generating tags, descriptions and titles using local Vision-Language Models (VLM) in OffGallery.

---

## How it works

The plugin connects to the LM Studio local server via OpenAI-compatible API and sends images (resized to 512px) to the loaded VLM model. The model generates tags, description and/or title in Italian (or the selected language) entirely offline.

---

## Requirements

- **LM Studio** installed and local server started: [lmstudio.ai](https://lmstudio.ai)
- A Vision-Language model loaded in LM Studio
- Recommended model: `qwen3-vl` (8B or larger for best results)

---

## Configuration

In **Config Tab → LLM Connection**, select **LM Studio** backend:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Endpoint | `http://localhost:1234` | LM Studio server address |
| Model | (loaded model name) | Exact model name as shown in LM Studio |
| Timeout | 240 s | Response timeout |

> **Note**: the model name must match exactly what is shown in LM Studio.

---

## Differences from the Ollama plugin

| | Ollama | LM Studio |
|--|--------|-----------|
| API | `/api/generate` (native) | `/v1/chat/completions` (OpenAI-compat.) |
| Model management | `ollama pull` from terminal | LM Studio GUI |
| Server startup | automatic | manual from LM Studio panel |

---

## License

OffGallery Plugins License v1.0 — Proprietary, no redistribution.
LM Studio is a separate software distributed under its own license.
