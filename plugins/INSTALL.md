# Installazione Plugin OffGallery — Beta Tester

## Prerequisiti

- OffGallery già installato e funzionante
- Ambiente conda `OffGallery` attivo
- Accesso alla repo privata `OffGallery_BETA` (richiesto al maintainer)

---

## 1. Ottieni i plugin

Clona la repo beta in una cartella **temporanea** (non dentro OffGallery):

```bash
git clone https://github.com/HEGOM61ita/OffGallery_BETA.git offgallery-beta
cd offgallery-beta
```

---

## 2. Esegui l'installer

### Windows (Anaconda Prompt)

```bat
conda activate OffGallery
python install_plugins.py
```

Se OffGallery non viene trovato automaticamente:

```bat
python install_plugins.py --target "C:\percorso\a\OffGallery"
```

### macOS / Linux

```bash
conda activate OffGallery
python install_plugins.py
```

Se OffGallery non viene trovato automaticamente:

```bash
python install_plugins.py --target "/percorso/a/OffGallery"
```

---

## 3. Dipendenze Python

La maggior parte dei plugin usa esclusivamente librerie già presenti nell'ambiente `OffGallery`.
L'installer installa automaticamente le dipendenze aggiuntive dichiarate da ciascun plugin.

| Plugin | Dipendenza aggiuntiva | Installazione |
|--------|-----------------------|---------------|
| LLM Ollama / LM Studio | — | nessuna |
| BioNomen | — | nessuna |
| NaturArea | `rasterio` | automatica (installer) |
| Weather Context | — | nessuna |

> **Nota**: `rasterio` è richiesto da NaturArea per la lettura dei tile ESA WorldCover (habitat).
> Viene installato automaticamente dall'installer tramite `pip`. Se per qualsiasi motivo
> l'installazione automatica fallisse, eseguire manualmente:
> ```bash
> conda activate OffGallery
> pip install rasterio
> ```

---

## 4. Plugin LLM (Ollama e LM Studio)

I plugin LLM sono pronti all'uso dopo l'installazione.
Richiedono che Ollama o LM Studio siano **in esecuzione** al momento dell'avvio di OffGallery.

Configurazione in OffGallery: **Config → LLM Vision → Backend**

### Modelli consigliati

| Backend | Modello consigliato | VRAM minima |
|---------|--------------------|-----------:|
| Ollama | `qwen3.5:4b-q4_K_M` | 6 GB |
| LM Studio | `qwen/qwen3-vl-4b` (GGUF Q4) | 6 GB |

---

## 5. Plugin BioNomen — database specie

Il database delle specie **non è incluso** nella repo per ragioni di dimensione.
Va scaricato al primo avvio tramite l'interfaccia BioNomen stessa.

### Come scaricare il database

1. Avvia OffGallery
2. Vai in **Config → Plugin → BioNomen → Configura**
3. Seleziona i **taxa** di interesse:
   - Aves (Uccelli)
   - Mammalia (Mammiferi)
   - Reptilia (Rettili)
   - Amphibia (Anfibi)
   - Insecta (Insetti)
   - Plantae (Piante)
4. Clicca **Scarica database**

Il download avviene da **GBIF** e richiede connessione internet solo la prima volta.
L'uso successivo è completamente **offline**.

### Dimensioni indicative dei database

| Taxon | Dimensione DB |
|-------|-------------:|
| Aves | ~15 MB |
| Mammalia | ~5 MB |
| Insecta | ~40 MB |
| Plantae | ~60 MB |
| Reptilia | ~3 MB |
| Amphibia | ~2 MB |

---

## 9. Verifica installazione

Avvia OffGallery. Nel log di avvio (pannello Log) dovresti vedere:

```
Plugin LLM attivo: Ollama          ← se Ollama è in esecuzione
Plugin LLM attivo: LM Studio       ← se LM Studio è in esecuzione
BioNomen: plugin disponibile       ← sempre, se installato correttamente
```

Se un plugin LLM non viene riconosciuto, verifica che il backend sia in esecuzione
**prima** di avviare OffGallery.

---

## 6. Plugin NaturArea — prima configurazione

NaturArea arricchisce le foto con coordinate GPS con:
- **Area protetta** — nome dal database WDPA (UNEP-WCMC), consultato via API online con cache locale
- **Habitat** — classe di copertura del suolo da mappe satellitari ESA WorldCover 2021

Non è richiesta nessuna preparazione: basta avere connessione internet al momento della prima
elaborazione di ogni nuova area geografica. I risultati vengono poi memorizzati in cache locale.

Configurazione in OffGallery: **Config → Plugin → NaturArea → Configura**

---

## 7. Plugin Weather Context — prima configurazione

Weather Context recupera le condizioni meteo al momento dello scatto per ogni foto con GPS e data.
Richiede connessione internet per le nuove foto (risultati in cache dopo la prima elaborazione).

Configurazione in OffGallery: **Config → Plugin → Weather Context → Configura**

---

## 8. Installare un solo plugin

```bash
python install_plugins.py --plugin llm_ollama
python install_plugins.py --plugin llm_lmstudio
python install_plugins.py --plugin bionomen
python install_plugins.py --plugin naturarea
python install_plugins.py --plugin weather_context
```

---

## Licenza

I plugin sono distribuiti sotto **OffGallery Plugins License v1.0** — uso personale
e professionale su singolo computer. Nessuna redistribuzione consentita.
Vedere `LICENSE` nella cartella di ogni plugin.
