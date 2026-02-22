
<p align="center">
  <img src="assets/logo3.jpg" alt="OffGallery Logo" width="200"/>
</p>

<h1 align="center">OffGallery</h1>

<p align="center">
  <strong>Sistema di catalogazione intelligente per fotografi, che rispetta la tua privacy</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12.9-blue?logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/PyTorch-2.7.1-red?logo=pytorch" alt="PyTorch"/>
  <img src="https://img.shields.io/badge/CUDA-11.8-green?logo=nvidia" alt="CUDA"/>
  <img src="https://img.shields.io/badge/License-AGPLV3-yellow" alt="License"/>
  <img src="https://img.shields.io/badge/100%25-Offline-brightgreen" alt="Offline"/>
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows" alt="Windows"/>
  <img src="https://img.shields.io/badge/Linux-Ubuntu%20|%20Fedora%20|%20Arch-orange?logo=linux" alt="Linux"/>
</p>

<p align="center">
  <em>Analisi semantica ed estetica delle tue foto con AI locale. Zero cloud. Zero compromessi.</em>
</p>

---

> [!NOTE]
> **🔧 Installer Windows — Verifica Finale in Corso**
>
> Tutti i problemi noti dell'installer Windows sono stati identificati e risolti:
> `CondaToSNonInteractiveError`, mancato salvataggio dei modelli AI in `Models/`, crash silenzioso di `from_pretrained` dopo il 100% del caricamento.
>
> **È in attesa di una verifica finale su installazione fresh.** Per problemi durante l'installazione, apri una [Discussion](https://github.com/HEGOM61ita/OffGallery/discussions).

---

## Ultime Novità

> Per approfondimenti su ogni versione, visita le [**Discussions**](https://github.com/HEGOM61ita/OffGallery/discussions) del progetto.

### Fix Installer Windows v3 — 22 febbraio 2026 🔧

Grazie ai test sistematici su profili Windows nuovi, sono stati individuati e risolti i problemi residui dell'installer:

- **`CondaToSNonInteractiveError` su Anaconda**: l'ambiente veniva creato con successo ma l'installer si fermava perché l'exit code non era zero. Fix: verifica via filesystem (`python.exe` nell'env path) invece di fidarsi dell'exit code
- **`conda env list` falliva con ToS**: aggiunta verifica filesystem anche nel check iniziale "ambiente già esistente"
- **CLIP e Aesthetic non salvati in `Models/`**: `save_pretrained()` crashava silenziosamente perché `LogCapture` non implementava `isatty()`. Fix in due parti: (1) `hf_hub_download + shutil.copy2` invece di `save_pretrained` per il repo congelato, (2) `isatty()` aggiunto a `LogCapture`
- **`from_pretrained` crashava dopo il 100% di caricamento**: `tqdm` e `safetensors` chiamano `sys.stdout.isatty()` al completamento della barra di progresso. Con `LogCapture` come stdout, questo causava un `AttributeError` che buttava via il modello appena caricato
- Dettagli: [Discussion #9](https://github.com/HEGOM61ita/OffGallery/discussions/9)

### Fix Installer v2 — 20 febbraio 2026
- **13 bug risolti** nell'installer Windows e Linux che impedivano il completamento dell'installazione
- **Windows (7 fix)**: error check dopo `pip install`, verifica estesa a 9 pacchetti (era 2), rilevamento Anaconda in 6 percorsi noti, error check su `conda env remove`
- **Linux (6 fix)**: `opencv-contrib-python-headless` (elimina dipendenza `libGL.so.1`), installazione automatica dipendenze Qt di sistema, errori `sudo` ora visibili, messaggi di errore con fix specifici per distro
- Dettagli: [Discussion #8](https://github.com/HEGOM61ita/OffGallery/discussions/8)

### v0.7 — 18 febbraio 2026
- **Supporto Linux**: installer bash completo (`install_offgallery.sh`) con detection distro, ExifTool automatico e desktop entry
- **Launcher Linux**: `offgallery_launcher.sh` con auto-detection conda
- **Config cross-platform**: validazione editor esterni adattata per Linux (`os.X_OK` invece di `.exe`)

### v0.5 — 16 febbraio 2025
- **BioCLIP tassonomia completa**: 7 livelli (Kingdom, Phylum, Class, Order, Family, Genus, Species) nel campo DB dedicato `bioclip_taxonomy`
- **Separazione BioCLIP dai tag**: campo `tags` contiene solo LLM + user tags, BioCLIP ha storage e UI dedicati
- **Export XMP gerarchico**: tassonomia BioCLIP scritta in `HierarchicalSubject` con prefisso `AI|Taxonomy|...`, compatibile Lightroom
- **Edit BioCLIP da gallery**: nuovo dialog nel menu contestuale per modificare i 7 livelli tassonomici
- **Tooltip BioCLIP separato**: sezione dedicata nell'hover con gerarchia compatta (Kingdom > ... > Species)
- **Protezione dati**: i dati BioCLIP non vengono importati da XMP (gestione solo interna a OffGallery)

### v0.4 — 15 febbraio 2025
- **Ottimizzazione LLM Ollama**: keep_alive permanente in VRAM, warmup allo startup, cache immagine tra chiamate multiple
- **Parametri LLM configurabili da UI**: num_ctx, num_batch, keep_alive, temperature, top_k, top_p
- **Profili immagine corretti**: dimensioni adattate ai modelli AI reali (CLIP 224px, BioCLIP 224px, LLM 512px)
- **Prompt LLM migliorati**: identificazione specie prudente senza BioCLIP, niente più allucinazioni

### v0.3 — 14 febbraio 2025
- **Serializzazione embedding**: migrazione da pickle a raw float32 per robustezza e performance
- **Ordinamento gallery**: 7 criteri con selettore UI (rilevanza, data, nome, rating, score)
- **Log tab**: filtri per livello e limite 500 entry
- **Fix traduzione LLM**: strip think blocks, prompt esplicito IT, rimozione nomi specie

### v0.2 — 13-14 febbraio 2025
- **BioCLIP → LLM feedback loop**: identificazione specie guida la generazione di tag e descrizioni
- **Parametri LLM avanzati** nella config tab (temperature, top_k, top_p)
- **Wizard di installazione** unificato (INSTALLA_OffGallery.bat)
- **Fix processing**: progress bar accurata, ordine tag BioCLIP preservato

---

## Perché OffGallery?

Sei un fotografo che vuole catalogare migliaia di immagini RAW senza affidarle a servizi cloud? Vuoi cercare le tue foto con linguaggio naturale ("tramonto con montagne") mantenendo tutto sul tuo PC? **OffGallery è la risposta.**

### Caratteristiche Principali

| Funzionalità | Descrizione |
|--------------|-------------|
| **100% Offline** | Nessun dato lascia mai il tuo computer. Tutti i modelli AI girano localmente |
| **Potente ricerca Semantica /tags/Exif/+vari** | Cerca in ITALIANO con linguaggio naturale e/o combo complesse con traduzione automatica |
| **Supporto RAW Nativo** | 25+ formati RAW supportati (Canon CR2/CR3, Nikon NEF, Sony ARW, Fuji RAF...) |
| **Ricerca similarità visiva** | Un semplice click per trovare immagini simili, doppioni, etc. |
| **Integrazione Lightroom** | Sincronizzazione/edit bidirezionale XMP con rating, tag e metadati. Nessun dato proprietario viene modificato |
| **Valutazione Estetica** | Score automatico della qualità artistica (0-10) |
| **Identificazione Specie** | BioCLIP2 riconosce ~450.000 specie con tassonomia completa a 7 livelli |
| **Statistiche** | Tipologia, Date, Metadati, Attributi, Strumentazione usata, Tempi di posa, Ratings etc. |

<p align="center">
  <img src="assets/screenshot.png" alt="OffGallery Screenshot" width="800"/>
</p>

---

## Stack AI Locale

OffGallery orchestra **6 modelli AI** che lavorano insieme, completamente offline:

```
┌─────────────────────────────────────────────────────────────────┐
│                        OFFGALLERY                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │   CLIP   │  │  DINOv2  │  │ BioCLIP  │  │ LLM Vision       │ │
│  │ Ricerca  │  │Similarità│  │  Flora   │  │ (Qwen3-VL/Ollama)│ │
│  │Semantica │  │  Visiva  │  │  Fauna   │  │ Tag & Descrizioni│ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
│  ┌──────────────────────┐  ┌────────────────────────────────┐   │
│  │  Aesthetic Predictor │  │  MUSIQ (Technical Quality)     │   │
│  │  Valutazione 0-10    │  │  Analisi nitidezza/rumore      │   │
│  └──────────────────────┘  └────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Argos Translate (IT→EN) per query multilingue           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Funzionalità

### Ricerca Intelligente

- **Semantica**: Scrivi quello che cerchi in italiano ("gatto nero sul divano") con esclusivo sistema di accuratezza con slide gui
- **Per Tag**: Ricerca fuzzy con deduplicazione intelligente
- **Filtri EXIF**: Camera, obiettivo, focale, ISO, tempo, diaframma, data, etc.
- **Colore**: Rilevamento automatico B/N con soglia configurabile
- **Rating**: Sistema compatibile Lightroom (0-5 stelle)

<p align="center">
  <img src="assets/search_panel.png" alt="OffGallery Search Panel" width="600"/>
</p>

### Analisi Immagini

- **Embedding CLIP**: 512 dimensioni per ricerca semantica
- **Embedding DINOv2**: 768 dimensioni per similarità visiva
- **Tassonomia BioCLIP**: Classificazione automatica specie con 7 livelli tassonomici (campo dedicato, separato dai tag)
- **Tag LLM**: Descrizioni e tag generati da modelli linguistici locali parametrizzabili
- **Score Estetico**: Valutazione artistica automatica
- **Score Tecnico**: Analisi qualità (nitidezza, rumore, esposizione, solo per non RAW)

### Workflow Fotografico

- **Import XMP**: Legge tag e rating da Lightroom/DxO/etc.
- **Export XMP**: Scrive modifiche compatibili con editor esterni, inclusa tassonomia BioCLIP in `HierarchicalSubject`
- **Export gerarchico**: BioCLIP esportato con prefisso `AI|Taxonomy|...` senza interferire con keyword utente
- **Sync State**: Traccia stato sincronizzazione (PERFECT_SYNC, DIRTY, etc.)
- **Badge Visivi**: Score, rating, ranking e stato colore nella gallery
- **Ordinamento Gallery**: 7 criteri (rilevanza, data, nome, rating, score estetico/tecnico/composito) con direzione ASC/DESC
- **Menu contestuale**: Per ogni immagine nella Gallery, basta un click per editarla su Lightroom o altro editor, gestire metadati, creare tags e descrizioni, etc.

---

## Requisiti di Sistema

| Componente | Minimo | Consigliato |
|------------|--------|-------------|
| **RAM** | 8 GB | 16 GB |
| **Disco** | 15 GB | 25 GB |
| **GPU** | - | NVIDIA con CUDA |
| **OS** | Windows 10/11 oppure Linux 64-bit | Windows 11 / Ubuntu 22.04+ |

> **Note**:
> - GPU NVIDIA raccomandata per prestazioni ottimali. Funziona anche su CPU (più lento)
> - Connessione internet richiesta solo al primo avvio per download modelli AI (~7 GB)
> - **Linux**: testato su Ubuntu, Fedora e Arch. Altre distribuzioni con supporto conda dovrebbero funzionare

---

## Installazione

### 1. Scarica OffGallery

**Opzione A - Download ZIP (consigliato):**
1. Clicca il pulsante verde **"<> Code"** in alto a destra
2. Seleziona **"Download ZIP"**
3. Estrai lo ZIP scegliendo la **cartella padre** dove vuoi che risieda OffGallery

> **Attenzione all'estrazione:** lo ZIP contiene già una cartella `OffGallery-main` al suo interno — quella **è** la root dell'app.
> Se fai "Estrai tutto" in una cartella già chiamata `OffGallery`, ottieni `OffGallery\OffGallery-main\` (doppia cartella inutile).
> **Corretto:** estrai in `C:\Programs\` → si crea `C:\Programs\OffGallery-main\`, che puoi rinominare come vuoi (es. `OffGallery`).
> Con **git clone** il problema non esiste: la cartella creata è già la root.

**Opzione B - Git clone:**
```bash
git clone https://github.com/HEGOM61ita/OffGallery.git
```

### 2. Installa con il Wizard

#### Windows

1. Apri la cartella `installer`
2. **Doppio click** su **`INSTALLA_OffGallery.bat`**
3. Segui le istruzioni a schermo

#### Linux

1. Apri un terminale nella cartella OffGallery
2. Esegui:
   ```bash
   bash installer/install_offgallery.sh
   ```
3. Segui le istruzioni a schermo

Il wizard installa automaticamente tutto il necessario: Miniconda, ambiente Python, librerie (+ ExifTool su Linux), e opzionalmente Ollama per le descrizioni AI. Al termine crea un collegamento (Desktop su Windows, menu applicazioni su Linux).

> **Tempo stimato**: 20-40 minuti. Al primo avvio, OffGallery scarica automaticamente i modelli AI (~7 GB). Gli avvii successivi saranno completamente offline.

### Installazione manuale (alternativa)

**Windows** - script batch separati:
1. `installer/01_install_miniconda.bat` - Verifica/installa Miniconda
2. `installer/02_create_env.bat` - Crea ambiente Python
3. `installer/03_install_packages.bat` - Installa librerie
4. `installer/06_setup_ollama.bat` - Ollama + LLM Vision (opzionale)

**Linux** - usa il wizard `install_offgallery.sh` che copre tutti gli step, oppure installa manualmente:
1. Installa [Miniconda](https://docs.anaconda.com/miniconda/install/) per Linux
2. `conda create -n OffGallery python=3.12 -y`
3. `conda run -n OffGallery pip install -r installer/requirements_offgallery.txt`
4. Installa ExifTool: `sudo apt install libimage-exiftool-perl` (Ubuntu/Debian) o equivalente
5. (Opzionale) Installa [Ollama](https://ollama.com/download) e `ollama pull qwen3-vl:4b-instruct`

### Istruzioni Dettagliate

Per una guida passo-passo completa, consulta **[installer/INSTALL_GUIDE.md](installer/INSTALL_GUIDE.md)**.

---

## Utilizzo

### Interfaccia Grafica

L'applicazione presenta 7 tab principali:

| Tab | Funzione |
|-----|----------|
| **Elaborazione** | Processa nuove immagini con tutti i modelli AI |
| **Ricerca** | Query semantica e filtri avanzati |
| **Galleria** | Visualizza risultati con badge, preview e ordinamento intelligente |
| **Statistiche** | Analisi del database e pattern di scatto |
| **Esportazione** | Export metadati su XMP e CSV |
| **Configurazione** | Impostazioni modelli, parametri ed editor esterni |
| **Log** | Monitoraggio elaborazioni in tempo reale |

### Esempio di Workflow

1. **Importa**: Scegli una cartella (`INPUT/` predefinita) e avvia il processo
2. **Cerca**: Usa "Ricerca" per trovare le foto ("ritratto controluce") dal database
3. **Visualizza**: Seleziona / edita / gestisci i risultati dalla Gallery
4. **Esporta**: Sincronizza i tag con Lightroom/altri via XMP

---

## Configurazione

Per la documentazione completa delle opzioni di configurazione, consulta **[CONFIGURATION.md](CONFIGURATION.md)**.

---

## Architettura

```
offgallery/
├── gui/                      # Moduli interfaccia PyQt6
│   ├── processing_tab.py     # Orchestrazione elaborazione
│   ├── search_tab.py         # Ricerca semantica + filtri
│   ├── gallery_tab.py        # Visualizzazione risultati
│   └── ...
├── embedding_generator.py    # Generazione embedding multi-modello
├── retrieval.py              # Motore di ricerca
├── db_manager_new.py         # Gestione database SQLite
├── raw_processor.py          # Estrazione RAW ottimizzata
├── xmp_manager_extended.py   # Lettura/scrittura XMP
├── aesthetic/                # Modelli valutazione estetica
├── brisque_models/           # Modelli qualità tecnica
├── exiftool_files/           # ExifTool per metadati EXIF
├── database/                 # Database SQLite
├── INPUT/                    # Cartella import immagini
└── config_new.yaml           # Configurazione
```

---

## Formati Supportati

### Immagini Standard
`JPG` `JPEG` `PNG` `TIFF` `TIF` `WEBP` `BMP`

### Formati RAW
| Produttore | Formati |
|------------|---------|
| **Canon** | CR2, CR3, CRW |
| **Nikon** | NEF, NRW |
| **Sony** | ARW, SRF, SR2 |
| **Fujifilm** | RAF |
| **Panasonic** | RW2 |
| **Olympus/OM** | ORF |
| **Pentax** | PEF, DNG |
| **Leica** | DNG, RWL |
| **Adobe** | DNG |
| **Altri** | 3FR, IIQ, RWL, X3F |

---

## Privacy e Sicurezza

OffGallery è progettato con la privacy come principio fondamentale:

- **Zero telemetria**: Nessun dato viene raccolto o inviato
- **Offline dopo primo avvio**: Al primo avvio i modelli AI vengono scaricati dal repository HuggingFace congelato. Dopo il download, l'app funziona completamente offline
- **Repository congelato**: I modelli sono hostati su un repository controllato (`HEGOM/OffGallery-models`) per garantire stabilità e compatibilità delle versioni
- **Storage locale**: Database SQLite + embedding in formato binario
- **Nessuna API key**: Non servono account o abbonamenti

---

## Roadmap

Questo progetto è in sviluppo attivo. Tutte le funzionalità e migliorie sono aggiunte gradualmente senza una roadmap pubblica.

---

## Contributi e Feedback

Questo progetto segue un modello di sviluppo centralizzato.
Attualmente, non sono accettati contributi di codice esterno (pull requests).

Segnalazioni di bug, idee e suggerimenti per nuove funzionalità sono benvenuti nelle [**Discussions**](https://github.com/HEGOM61ita/OffGallery/discussions) del progetto. In particolare, sono apprezzati feedback sulle prestazioni con la descrizione dell'hardware utilizzato (GPU, RAM, modello Ollama) per migliorare l'ottimizzazione su diverse configurazioni.

---

## Support Policy

Questo progetto è fornito "as-is".
Non ho la possibilità di provvedere per un supporto individuale, risoluzione di problemi o assistenza nell'installazione.
Si prega di far riferimento alla documentazione.
Segnalazioni che descrivono chiaramente errori riproducibili saranno esaminate appena possibile.

---

## Licenza e Note Legali

Distribuito sotto licenza **AGPL-3.0**. Vedi `LICENSE` per maggiori informazioni.

- **[TRADEMARK.md](TRADEMARK.md)** - Informazioni sui marchi registrati
- **[THIRD_PARTY.md](THIRD_PARTY.md)** - Licenze e attribuzioni software di terze parti

---

## Ringraziamenti

- [OpenAI CLIP](https://github.com/openai/CLIP) - Ricerca semantica
- [Meta DINOv2](https://github.com/facebookresearch/dinov2) - Embedding visivi
- [BioCLIP](https://github.com/Imageomics/bioclip) - Classificazione flora/fauna
- [Ollama](https://ollama.ai/) - LLM locali
- [ExifTool](https://exiftool.org/) - Metadati EXIF/XMP
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - Framework UI

---

<p align="center">
  <strong>Fatto con passione per i fotografi che tengono alla loro privacy</strong>
</p>

<p align="center">
  <a href="#offgallery">Torna su</a>
</p>
