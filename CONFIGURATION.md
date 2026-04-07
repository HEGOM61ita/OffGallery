# Configurazione OffGallery

OffGallery offre ampie possibilità di personalizzazione tramite il file `config_new.yaml` o direttamente dall'interfaccia grafica (tab **Configurazione**).

---

## File di Configurazione

Il file principale di configurazione è `config_new.yaml` nella root del progetto.

### Struttura Generale

```yaml
embedding:
  enabled: true
  models:
    clip:
      enabled: true
      device: gpu              # gpu | cpu (per-modello)
      model_name: "openai/clip-vit-large-patch14"
    dinov2:
      enabled: true
      model_name: "facebook/dinov2-base"
      dimension: 768
      similarity_threshold: 0.25
    bioclip:
      enabled: true
      threshold: 0.05
      max_tags: 3
    aesthetic:
      enabled: true
      model_name: "aesthetic-predictor"
    technical:
      enabled: true
      model_name: "musiq"
    llm_vision:
      enabled: true
      model: "qwen3-vl:8b-instruct-q4_K_M"
      endpoint: "http://localhost:11434"
      timeout: 240
      generation:
        temperature: 0.1
        top_k: 40
        top_p: 0.8
        num_ctx: 4096
        num_batch: 512
        keep_alive: -1
      auto_import:
        tags:
          enabled: true
          max_tags: 5
          overwrite: true
        description:
          enabled: true
          max_words: 30
          overwrite: true
        title:
          enabled: true
          max_words: 5
          overwrite: true

search:
  semantic_threshold: 0.2
  fuzzy_enabled: true
  max_results: 100

similarity:
  max_results: 50

external_editors:
  editor_1:
    name: "Lightroom"
    path: "C:/Program Files/Adobe/Adobe Lightroom Classic/Lightroom.exe"
    command_args: ""
    enabled: true
  editor_2:
    name: "PhotoLab"
    path: "C:/Program Files/DxO/DxO PhotoLab 8/DxO.PhotoLab.exe"
    command_args: "nosplash"
    enabled: true
  editor_3:
    name: ""
    path: ""
    command_args: ""
    enabled: false

paths:
  database: "database/offgallery.sqlite"
  input_dir: "INPUT"
  log_dir: "logs"

models_repository:
  huggingface_repo: HEGOM/OffGallery-models
  models_dir: Models          # relativo ad APP_DIR, oppure percorso assoluto es. E:\MyModels
  auto_download: true

image_optimization:
  enabled: true
  profiles:
    clip_embedding:
      target_size: 224
      method: preview_optimized
      quality: 85
      resampling: LANCZOS
    dinov2_embedding:
      target_size: 518
      method: high_quality
      quality: 90
      resampling: LANCZOS
    bioclip_classification:
      target_size: 224
      method: preview_optimized
      quality: 85
      resampling: LANCZOS
    aesthetic_score:
      target_size: 224
      method: preview_optimized
      quality: 85
      resampling: BILINEAR
    llm_vision:
      target_size: 512
      method: preview_optimized
      quality: 85
      resampling: LANCZOS
    gallery_display:
      target_size: 256
      method: fast_thumbnail
      quality: 75
      resampling: BILINEAR

logging:
  show_debug: true
```

---

## Sezioni Principali

### Embedding Models

Configura i modelli AI per l'analisi delle immagini. Tutti i modelli girano localmente.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `<model>.device` | string | Device per-modello: `gpu` (usa backend rilevato) o `cpu`. Configurabile individualmente per ogni modello |
| `clip.enabled` | bool | Abilita embedding CLIP per ricerca semantica |
| `clip.model_name` | string | Modello CLIP (default: `openai/clip-vit-large-patch14`) |
| `dinov2.enabled` | bool | Abilita embedding DINOv2 per similarità visiva |
| `dinov2.model_name` | string | Modello DINOv2 (default: `facebook/dinov2-base`) |
| `dinov2.dimension` | int | Dimensione embedding DINOv2 (768) |
| `dinov2.similarity_threshold` | float | Soglia minima similarità visiva (0.0-1.0) |
| `bioclip.enabled` | bool | Abilita classificazione flora/fauna (~450k specie) |
| `bioclip.threshold` | float | Soglia minima confidenza BioCLIP (0.0-1.0, default: 0.05) |
| `bioclip.max_tags` | int | Numero massimo di tag specie (default: 3) |
| `aesthetic.enabled` | bool | Abilita valutazione estetica (score 0-10) |
| `technical.enabled` | bool | Abilita valutazione qualità tecnica MUSIQ (solo non-RAW) |

### LLM Vision (Ollama)

Configura la generazione di tag, descrizioni e titoli tramite modello LLM Vision locale via Ollama.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `llm_vision.enabled` | bool | Abilita generazione LLM |
| `llm_vision.model` | string | Modello Ollama da usare. Consigliato per 8 GB VRAM: `qwen3-vl:8b-instruct-q4_K_M` |
| `llm_vision.endpoint` | string | Indirizzo endpoint Ollama (default: `http://localhost:11434`) |
| `llm_vision.timeout` | int | Timeout in secondi per risposta LLM (default: 240) |

#### Parametri di Generazione

Parametri avanzati che controllano il comportamento del modello LLM. Accessibili dalla UI nel pannello avanzato (collassabile).

| Parametro | Tipo | Range | Default | Descrizione |
|-----------|------|-------|---------|-------------|
| `temperature` | float | 0.0–2.0 | 0.1 | Creatività LLM. Bassi (0.1-0.3): preciso e deterministico. Alti (0.7+): creativo e vario |
| `top_k` | int | 1–100 | 40 | Numero token candidati per step di generazione |
| `top_p` | float | 0.0–1.0 | 0.8 | Nucleus sampling: probabilità cumulativa dei token considerati |
| `num_ctx` | int | 512–32768 | 4096 | Dimensione finestra di contesto in token. Valori più alti usano più VRAM |
| `num_batch` | int | 128–4096 | 512 | Dimensione batch per prompt evaluation. Influisce su velocità e uso VRAM |
| `keep_alive` | int | -1, 0+ | -1 | Tempo in minuti per mantenere il modello in VRAM. `-1` = permanente (consigliato) |

> **Nota VRAM**: Con `keep_alive: -1` il modello Ollama resta caricato in VRAM dopo il primo utilizzo, eliminando il tempo di caricamento (~2-3s) per le chiamate successive. Consigliato per GPU con almeno 4 GB liberi. Il modello `qwen3-vl:8b-instruct-q4_K_M` (consigliato per 8 GB VRAM) occupa circa 5 GB di VRAM.

#### Auto Import

Controlla cosa viene generato automaticamente durante l'elaborazione delle immagini.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `auto_import.tags.enabled` | bool | Genera tag automatici da LLM |
| `auto_import.tags.max_tags` | int | Numero massimo di tag LLM per immagine (default: 5) |
| `auto_import.tags.overwrite` | bool | Sovrascrive tag LLM esistenti alla rielaborazione |
| `auto_import.description.enabled` | bool | Genera descrizione automatica |
| `auto_import.description.max_words` | int | Lunghezza massima descrizione in parole (default: 30) |
| `auto_import.description.overwrite` | bool | Sovrascrive descrizione esistente alla rielaborazione |
| `auto_import.title.enabled` | bool | Genera titolo automatico |
| `auto_import.title.max_words` | int | Lunghezza massima titolo in parole (default: 5) |
| `auto_import.title.overwrite` | bool | Sovrascrive titolo esistente alla rielaborazione |

> **Nota**: I tag BioCLIP sono gestiti in un campo DB dedicato (`bioclip_taxonomy`) separato dai tag LLM/utente. La tassonomia BioCLIP (7 livelli: Kingdom, Phylum, Class, Order, Family, Genus, Species) è visibile nell'hover della gallery e modificabile dal menu contestuale "Edita tag BioCLIP". In export XMP, viene scritta in `HierarchicalSubject` con prefisso `AI|Taxonomy|...`. I dati BioCLIP NON vengono importati da XMP — sono gestiti esclusivamente dentro OffGallery.

### Search

Configura i parametri di ricerca.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `semantic_threshold` | float | Soglia minima similarità CLIP (0.0-1.0, default: 0.2) |
| `fuzzy_enabled` | bool | Abilita ricerca fuzzy per tag |
| `max_results` | int | Numero massimo risultati di ricerca (default: 100) |

### Similarity

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `max_results` | int | Numero massimo risultati similarità visiva (default: 50) |

### External Editors

Configura fino a 3 editor fotografici esterni. Ogni editor è accessibile dal menu contestuale nella gallery.

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `editor_N.name` | string | Nome visualizzato nel menu (es. "Lightroom") |
| `editor_N.path` | string | Percorso completo dell'eseguibile |
| `editor_N.command_args` | string | Argomenti aggiuntivi da riga di comando |
| `editor_N.enabled` | bool | Abilita/disabilita l'editor nel menu |

### Paths

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `database` | string | Percorso del database SQLite |
| `input_dir` | string | Cartella di default per l'importazione immagini |
| `log_dir` | string | Cartella per i file di log |

### Models Repository

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `huggingface_repo` | string | Repository HuggingFace congelato per il download dei modelli |
| `models_dir` | string | Directory dove vengono salvati i modelli AI. Percorso relativo (es. `Models`) = dentro la cartella OffGallery. Percorso assoluto (es. `E:\MyModels`) = cartella esterna. **Default**: `Models` |
| `auto_download` | bool | Scarica automaticamente i modelli al primo avvio |

> **Spostare i modelli su un altro disco**: modifica `models_dir` con il percorso assoluto desiderato **solo dopo** aver spostato manualmente la cartella `Models/`. La modifica è disponibile nel tab Configurazione → sezione Percorsi & Database.

---

## Profili di Ottimizzazione Immagini

OffGallery ridimensiona le immagini secondo profili ottimizzati per ogni modello AI. Le dimensioni corrispondono all'input nativo di ciascun modello per massimizzare qualità e velocità.

| Profilo | Target Size | Metodo | Uso |
|---------|-------------|--------|-----|
| `clip_embedding` | 224 px | preview_optimized | Embedding CLIP (ViT-B/32 input: 224×224) |
| `dinov2_embedding` | 518 px | high_quality | Embedding DINOv2 (input nativo: 518×518) |
| `bioclip_classification` | 224 px | preview_optimized | Classificazione BioCLIP (ViT-B/16 input: 224×224) |
| `aesthetic_score` | 224 px | preview_optimized | Score estetico (input: 224×224) |
| `llm_vision` | 512 px | preview_optimized | LLM Vision via Ollama |
| `gallery_display` | 256 px | fast_thumbnail | Anteprima nella gallery |
| `metadata_extraction` | 256 px | fast_thumbnail | Estrazione metadati veloce |

### Metodi di Estrazione

| Metodo | Descrizione |
|--------|-------------|
| `fast_thumbnail` | Veloce, usa thumbnail embedded nel file |
| `preview_optimized` | Bilanciato qualità/velocità, usa preview JPEG embedded |
| `high_quality` | Alta qualità, estrazione completa |
| `rawpy_full` | Massima qualità, decodifica RAW completa con rawpy |

### Metodi di Resampling

| Metodo | Descrizione |
|--------|-------------|
| `LANCZOS` | Migliore qualità (più lento) |
| `BILINEAR` | Buona qualità, veloce |
| `BICUBIC` | Qualità media |
| `NEAREST` | Velocissimo, qualità base |

---

## Configurazione via GUI

La maggior parte delle impostazioni è accessibile dal tab **Configurazione** dell'interfaccia grafica:

1. **Modelli AI**: Abilita/disabilita singoli modelli (CLIP, DINOv2, BioCLIP, Aesthetic, Technical, LLM Vision)
2. **Soglie**: Regola threshold per ricerca e classificazione
3. **Editor esterni**: Configura fino a 3 editor con percorso e argomenti
4. **Parametri LLM**: Modello, endpoint, timeout
5. **Parametri avanzati LLM** (sezione collassabile): temperature, top_k, top_p, num_ctx, num_batch, keep_alive
6. **Auto Import LLM**: Abilita/disabilita generazione di tags, descrizione e titolo con limiti configurabili
7. **Percorsi & Database**: Database, Logs, e **Directory Modelli AI** (`models_dir`) con warning per modifica accidentale

Le modifiche dalla GUI vengono salvate in `config_new.yaml` tramite il pulsante **Salva**.

---

## Gallery

La gallery supporta **7 criteri di ordinamento** selezionabili dalla UI:

| Criterio | Descrizione |
|----------|-------------|
| **Rilevanza** | Ordinamento per punteggio di ricerca semantica (default in ricerca) |
| **Data** | Per data di scatto EXIF |
| **Nome** | Per nome file alfabetico |
| **Rating** | Per rating Lightroom (0-5 stelle) |
| **Score Estetico** | Per punteggio valutazione artistica |
| **Score Tecnico** | Per punteggio qualità tecnica MUSIQ |
| **Score Composito** | Media pesata di score estetico e tecnico |

Ogni criterio supporta direzione ASC/DESC.

### Badge Visivi

Nella gallery ogni immagine mostra badge informativi:
- **Score estetico** (colore basato sul valore)
- **Score tecnico** (se disponibile)
- **Rating** (stelle Lightroom)
- **Etichetta colore** (sincronizzata da XMP)

---

## Log Tab

Il tab Log mostra le elaborazioni in tempo reale con:
- **Filtri per livello**: DEBUG, INFO, WARNING, ERROR (selezionabili)
- **Limite 500 entry**: Le entry più vecchie vengono rimosse automaticamente per mantenere le prestazioni
- **Opzione show_debug**: Configurabile in `logging.show_debug` per mostrare/nascondere i messaggi DEBUG

---

---

## Sorgente Immagini (Tab Elaborazione)

Il tab **Elaborazione** permette di scegliere da dove provengono le immagini da processare.

### Modalità Directory

Comportamento classico: OffGallery scansiona ricorsivamente una cartella e processa tutti i file immagine con formato supportato.

La cartella predefinita è configurabile in `config_new.yaml` → `paths.input_dir` (default: `INPUT/`).

### Modalità Catalogo Lightroom (.lrcat)

Permette di usare un catalogo **Adobe Lightroom Classic** come sorgente di input. OffGallery legge il file `.lrcat` (un database SQLite) ed estrae i percorsi assoluti di tutte le immagini indicizzate.

**Come si usa:**
1. Nel tab Elaborazione, seleziona il radio **"Catalogo .lrcat"**
2. Clicca 📂 e seleziona il file `.lrcat` del catalogo
3. OffGallery mostra il numero di file trovati
4. Avvia l'elaborazione normalmente con i modelli selezionati

**Note importanti:**
- Il file `.lrcat` viene aperto **in sola lettura** — il catalogo Lightroom non viene mai modificato
- Chiudere Lightroom prima di selezionare il catalogo, per evitare conflitti con il lock SQLite
- I file assenti su disco (offline, rimossi) vengono saltati automaticamente
- Compatibile con Lightroom Classic 6 e superiori (formato SQLite standard)
- Utile per ri-processare selettivamente file già catalogati in Lightroom senza dover specificare manualmente le cartelle

---

## Export (Tab Esportazione)

Il tab Export permette di esportare metadati e/o copiare fisicamente i file delle immagini selezionate nella Gallery. Le operazioni sono **combinabili** tra loro.

### Operazioni disponibili

| Operazione | Descrizione |
|---|---|
| **XMP sidecar (.xmp)** | Crea un file `.xmp` accanto all'immagine (o in directory di output) con tag, titolo, descrizione, rating, colore, tassonomia BioCLIP e gerarchia geografica |
| **XMP embedded** | Scrive i metadati nel file immagine (JPG / TIFF / DNG). Non supportato per RAW nativi |
| **Consenti DNG embedded** | Abilita la scrittura embedded nei file DNG (modifica il file originale) |
| **CSV completo** | Esporta tutti i campi DB + EXIF in formato tabellare, compatibile con Lightroom e Capture One |
| **Copia file originali** | Copia fisica dei file nella directory di output |

### Destinazione XMP

Il blocco "Destinazione XMP" è **visibile solo quando XMP sidecar o embedded è attivo**. Scompare automaticamente se si seleziona solo la copia file.

| Opzione | Descrizione |
|---|---|
| **Accanto ai file originali** *(default)* | XMP scritto nella stessa cartella del file sorgente — raccomandato per workflow Lightroom e Darktable |
| **In directory di output** | XMP scritto nella directory di output specificata |

### Copia file originali

La directory di output è sempre richiesta quando la copia è attiva.

| Opzione | Default | Descrizione |
|---|---|---|
| **Mantieni struttura directory** | Off | Ricrea nella destinazione la gerarchia di cartelle originale |
| **Sovrascrivi se esiste** | Off | Se disattivo, i file già presenti vengono saltati e conteggiati separatamente |

**Gestione multi-disco con struttura attiva:**

Con foto da dischi o volumi diversi, OffGallery crea una sottocartella per ciascun dispositivo:

| Sistema | Prefisso sottocartella |
|---|---|
| Windows | `C_drive/`, `D_drive/`, ecc. |
| macOS | Nome volume da `/Volumes/` (es. `SSD/`, `ExternalDisk/`) |
| Linux | Nome mount point da `/mnt/` o `/media/` (es. `ssd/`, `usb/`) |

**XMP e copia sono indipendenti:** è possibile scrivere XMP accanto agli originali e contemporaneamente copiare i file su un disco esterno in directory di output separata.

### Comportamento XMP (campi già presenti)

| Opzione | Default | Descrizione |
|---|---|---|
| **Unisci keywords** | ✅ | Aggiunge i keyword OffGallery a quelli già presenti nel file |
| **Preserva Titolo** | ✅ | Non sovrascrive il titolo se già presente |
| **Preserva Descrizione** | ✅ | Non sovrascrive la descrizione se già presente |
| **Preserva Rating** | ✅ | Non sovrascrive il rating (stelle) se già presente |
| **Preserva Color Label** | ✅ | Non sovrascrive l'etichetta colore se già presente |

I namespace Lightroom (`crs:`, `lr:`, `xmpMM:`) sono sempre preservati automaticamente.

### Directory CSV

La directory CSV è opzionale e separata dalla directory di output principale. Se lasciata vuota, il CSV viene salvato nella directory di output; se anche quella è vuota, nella cartella della prima immagine selezionata.

---

## Lingua Interfaccia e Contenuti

OffGallery gestisce due impostazioni linguistiche **indipendenti**, entrambe configurabili dal tab Configurazione.

### `ui.user_language` — Lingua interfaccia grafica

Controlla la lingua di tutti i testi dell'interfaccia (etichette, tooltip, dialoghi, messaggi di stato).

| Valore | Lingua |
|--------|--------|
| `it` | Italiano (default) |
| `en` | English |
| `fr` | Français |
| `de` | Deutsch |
| `es` | Español |
| `pt` | Português |

> La modifica richiede il riavvio dell'applicazione.

### `ui.llm_output_language` — Lingua contenuti LLM

Controlla la lingua in cui il modello LLM Vision genera **tag, descrizioni e titoli**. È indipendente dalla lingua dell'interfaccia: è possibile avere la GUI in italiano e i tag in inglese, o la GUI in inglese e i tag in francese.

Stessi valori di `user_language`.

> **Esempio**: un fotografo italiano che vuole condividere i propri archivi con colleghi francofoni può impostare la GUI in italiano (`user_language: it`) e i contenuti LLM in francese (`llm_output_language: fr`).

### Come funziona la ricerca con lingue miste

La ricerca gestisce automaticamente la lingua a due livelli distinti:

| Fase | Query usata | Perché |
|------|-------------|--------|
| **Ricerca semantica CLIP** | Query tradotta in **inglese** | CLIP è addestrato su coppie immagine-testo in EN: la precisione semantica è massima in inglese |
| **Ricerca tag / deep search** | Query tradotta nella **lingua dei tag** (`llm_output_language`) | I tag nel DB sono nella lingua di generazione LLM; il matching deve operare nella stessa lingua |

Le traduzioni avvengono tramite **Argostranslate** (offline). I pacchetti necessari (es. `en→fr`, `en→de`) vengono scaricati automaticamente al primo avvio se non già presenti. Lo stato del download è visibile nel pannello **Log**.

> **Graceful degradation**: se il pacchetto di traduzione per una lingua non è disponibile, la ricerca tag usa la query originale (in inglese). La ricerca semantica CLIP non è mai compromessa.

---

## Note

- Le modifiche al file YAML richiedono il riavvio dell'applicazione
- Le modifiche dalla GUI sono applicate al salvataggio
- All'avvio, OffGallery esegue un warmup automatico del modello Ollama (se abilitato) per ridurre il tempo della prima chiamata LLM
- L'immagine viene estratta e codificata una sola volta per le 3 chiamate LLM (title, tags, description) della stessa immagine, grazie a un sistema di cache interno
