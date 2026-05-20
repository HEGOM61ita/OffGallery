
<p align="center">
  <a href="#italiano">🇮🇹 Italiano</a> &nbsp;|&nbsp; <a href="#english">🇬🇧 English</a>
</p>

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
  <img src="https://img.shields.io/badge/macOS-12%2B-lightgrey?logo=apple" alt="macOS"/>
</p>

<p align="center">
  <em>Analisi semantica ed estetica delle tue foto con AI locale. Zero cloud. Zero compromessi.</em>
</p>

<a id="italiano"></a>

---

> [!NOTE]
> **🌍 Supporto multilingua completo**
>
> OffGallery supporta ora 6 lingue (**IT, EN, FR, DE, ES, PT**) a tutti i livelli, in modo indipendente:
>
> - **Interfaccia grafica**: seleziona la lingua dal tab Configurazione → Lingua interfaccia
> - **Contenuti generati da LLM** (tag, descrizioni, titoli): scegli la lingua di output LLM indipendentemente dalla GUI. I tag vengono generati nella lingua configurata e salvati così nel database
> - **Ricerca semantica SigLIP**: multilingua nativo (Google SigLIP so400m) — la query viene passata direttamente senza traduzione, in qualsiasi lingua
> - **Ricerca per tag/keyword**: la query viene automaticamente tradotta nella lingua dei tag (la stessa `llm_output_language`) prima del matching, garantendo risultati corretti anche con tag in francese, tedesco, ecc.
>
> Le traduzioni avvengono tramite **Argostranslate** completamente offline. I pacchetti di traduzione vengono scaricati al primo avvio se necessari; un messaggio nel pannello Log informa l'utente sullo stato.

---

## Ultime Novità

| Data | Cosa | Note |
|------|------|------|
| 8 mag 2026 | **Installer guidato Windows — [`OffGallerySetup.exe`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup.exe)** | Wizard in 5 schermate: rileva la GPU (NVIDIA/AMD/CPU), installa Miniconda, Python, librerie, modelli AI (~8 GB) e opzionalmente Ollama. Nessun terminale, nessuna configurazione manuale. Crea collegamento sul Desktop. |
| 8 mag 2026 | **Installer guidato Linux — [`OffGallerySetup`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup)** | Wizard grafico nativo per Linux (Ubuntu, Fedora, Arch e compatibili). `chmod +x OffGallerySetup && ./OffGallerySetup` — installa tutto e crea la voce nel menu applicazioni. Nessun terminale necessario. |
| 3 mag 2026 | **Plugin Contesto Prompt** | Inietta un blocco CONTEXT personalizzato nel prompt LLM Vision per adattare tag, descrizioni e titoli al dominio fotografico specifico dell'archivio. 8 preset built-in (naturalistico, paesaggio, astrofotografia, macro scientifico, subacqueo, reportage, commerciale, street) + generazione preset personalizzati via LLM locale. Preset selezionabile dal tab Plugin o dal menu contestuale in Gallery |
| 22 apr 2026 | **Compatibilità Darktable e altri editor** | Supporto completo al workflow Darktable: lettura sidecar `.NEF.xmp` / `.ARW.xmp` (convenzione `nomefile.EXT.xmp`), preservazione namespace proprietari nella creazione di nuovi sidecar, import XMP→DB e sync badge dalla Gallery, opzione **Output format: Lightroom / Darktable** nel tab Export. Compatibile con Lightroom, Darktable, Capture One, digiKam, ACDSee, FastRawViewer |
| 5 apr 2026 | **Plugin GeoNames** | Geolocalizzazione avanzata: gerarchia geografica completa (continente → nazione → regione → città), filtro Luogo con autocompletamento dal DB, filtro GPS a 4 stati (tutti / solo GPS / GPS modificato / senza GPS) |

Storico completo nelle [**Discussions**](https://github.com/HEGOM61ita/OffGallery/discussions).

---

## Perché OffGallery?

Sei un fotografo che vuole catalogare migliaia di immagini RAW senza affidarle a servizi cloud? Vuoi cercare le tue foto con linguaggio naturale ("tramonto con montagne") mantenendo tutto sul tuo PC? **OffGallery è la risposta.**

### Caratteristiche Principali

| Funzionalità | Descrizione |
|--------------|-------------|
| **Installazione one-click (Windows e Linux)** | [`OffGallerySetup.exe`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup.exe) (Windows) e [`OffGallerySetup`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup) (Linux) installano tutto in automatico: Miniconda, Python, librerie, modelli AI (~8 GB) e Ollama. Nessun terminale. macOS: script guidato incluso nella cartella `installer/` |
| **100% Offline** | Nessun dato lascia mai il tuo computer. Tutti i modelli AI girano localmente |
| **Supporto multilingua** | GUI, output LLM e ricerca tag indipendenti: 6 lingue (IT, EN, FR, DE, ES, PT). Tag e descrizioni nella lingua che preferisci, anche diversa dalla lingua dell'interfaccia |
| **Potente ricerca Semantica /tags/Exif/+vari** | Cerca con linguaggio naturale e/o combo complesse; SigLIP multilingua nativo (nessuna traduzione); traduzione automatica query per tag (lingua contenuti); salva e richiama ricerche preferite in un click |
| **Supporto RAW Nativo** | 25+ formati RAW supportati (Canon CR2/CR3, Nikon NEF, Sony ARW, Fuji RAF...) |
| **Ricerca similarità visiva** | Un semplice click per trovare immagini simili, doppioni, etc. |
| **Import da catalogo Lightroom** | Elabora direttamente i file indicizzati in un catalogo `.lrcat` come sorgente di input, senza dover specificare cartelle manualmente |
| **Integrazione con editor fotografici** | Sincronizzazione/export bidirezionale XMP con rating, tag e metadati. Compatibile con **Lightroom** (`.xmp`), **Darktable** (`.EXT.xmp`), **Capture One**, **digiKam**, **ACDSee**, **FastRawViewer** e qualsiasi software che rispetti lo standard XMP. Nessun dato proprietario viene modificato |
| **Plugin LLM** | Backend LLM alternativi: Ollama e LM Studio. Auto-discovery all'avvio, cambio backend senza riavvio |
| **Plugin Dati** | BioNomen (nomi comuni biologici da GBIF), GeoNames (gerarchia geografica), GeoSpecies (BioCLIP contestuale per GPS), NaturArea (aree protette WDPA + habitat ESA), Meteo (contesto meteo storico) |
| **Valutazione Estetica** | Score automatico della qualità artistica (0-10) |
| **Identificazione Specie** | BioCLIP2 riconosce ~450.000 specie con tassonomia completa a 7 livelli |
| **Geotag Offline** | Gerarchia geografica automatica da GPS: paese, regione, città — senza API esterne, dati GeoNames bundled |
| **Statistiche** | Tipologia, Date, Metadati, Attributi, Strumentazione usata, Tempi di posa, Ratings etc. |

<p align="center">
  <img src="assets/Int_gallery.png" alt="OffGallery Screenshot" width="800"/>
</p>

---

## Motori di Analisi

Tutti i componenti core girano localmente, completamente offline:

```
┌──────────────────────────────────────────────────────────────────────┐
│                           OFFGALLERY                                 │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │   CLIP   │  │  DINOv2  │  │ BioCLIP2 │  │ LLM Vision (Plugin)  │ │
│  │ Ricerca  │  │Similarità│  │ ~450k    │  │  Ollama · LM Studio  │ │
│  │Semantica │  │  Visiva  │  │ specie   │  │  tag · desc · titolo │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────────┘ │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐  │
│  │  Aesthetic Predictor │  │  MUSIQ (Technical Quality)           │  │
│  │  Score artistico 0-10│  │  Nitidezza · rumore · qualità ottica │  │
│  └──────────────────────┘  └──────────────────────────────────────┘  │
│  ┌───────────────────────┐  ┌─────────────────────────────────────┐  │
│  │  Argos Translate      │  │  GeoNames (Plugin)                  │  │
│  │  Query SigLIP (ML)    │  │  GPS → Continente/Paese/Regione/    │  │
│  │  + lingua tag offline │  │  Città  (dati GeoNames bundled)     │  │
│  └───────────────────────┘  └─────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│  Plugin opzionali                                                    │
│  ┌─────────────────┐  ┌────────────────────┐  ┌──────────────────┐  │
│  │   GeoSpecies    │  │    NaturArea        │  │  Meteo           │  │
│  │ BioCLIP locale  │  │ Aree protette WDPA │  │ Condizioni meteo │  │
│  │ per GPS (GBIF)  │  │ + habitat ESA      │  │ storiche al GPS  │  │
│  └─────────────────┘  └────────────────────┘  └──────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  BioNomen — nomi comuni biologici (GBIF, 6 lingue)              │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Funzionalità

OffGallery offre ricerca semantica, analisi immagini con più modelli AI, workflow completo con Lightroom e export XMP. Consulta il **[Manuale Utente completo →](HTML/USER_MANUAL_IT.html)** per la descrizione dettagliata di ogni funzione, tab e opzione.

| Funzione | Descrizione rapida |
|----------|--------------------|
| **Ricerca Semantica** | Linguaggio naturale, traduzione automatica offline, cursore di soglia |
| **Ricerca per Tag** | Fuzzy matching case-insensitive, ricerche salvate |
| **Filtri Avanzati** | Camera, obiettivo, ISO, diaframma, tempo, data, rating, score, colore |
| **Analisi AI** | CLIP · DINOv2 · BioCLIP2 · LLM Vision · Score Estetico · Score Tecnico · Geotag |
| **Device per-modello** | Ogni modello AI assegnabile a GPU o CPU individualmente; auto-ottimizzazione con budget VRAM e rilevamento LLM |
| **Workflow Lightroom** | Import `.lrcat` · Import XMP · Export XMP gerarchico · Copia con struttura |
| **Solo Gen. AI** | Rigenera solo tag/descrizione/titolo LLM su foto già nel DB, salta EXIF ed embedding |
| **Plugin LLM** | Seleziona backend LLM (Ollama o LM Studio) dal tab Configurazione; plugin rilevati automaticamente |
| **Plugin Dati** | BioNomen · GeoNames · GeoSpecies · NaturArea · Meteo — arricchimento contestuale su foto già nel DB, avviabile dalla Gallery o in batch |

---

## Requisiti di Sistema

| Componente | Minimo | Consigliato |
|------------|--------|-------------|
| **RAM** | 8 GB | 16 GB |
| **Disco** | 14 GB (CPU) / 18 GB (NVIDIA GPU) | 20 GB |
| **GPU** | - | NVIDIA con CUDA |
| **OS** | Windows 10/11, Linux 64-bit o macOS 12+ | Windows 11 / Ubuntu 22.04+ / macOS 13+ |

> **Note**:
> - GPU NVIDIA raccomandata per prestazioni ottimali. Funziona anche su CPU (più lento)
> - **Spazio disco**: l'ambiente Python occupa ~3.5 GB senza GPU, ~7 GB con NVIDIA (PyTorch CUDA + runtime libraries). I modelli AI pesano ~6.7 GB indipendentemente dalla GPU
> - Connessione internet richiesta solo al primo avvio per download modelli AI (~6.7 GB)
> - **Linux**: testato su Ubuntu, Fedora e Arch. Altre distribuzioni con supporto conda dovrebbero funzionare
> - **macOS**: supportato su Apple Silicon (M1/M2/M3/M4) e Intel (x86_64). Su Apple Silicon PyTorch usa Metal/MPS senza CUDA

### WSL2 (Windows Subsystem for Linux)

OffGallery funziona anche su WSL2 con interfaccia grafica tramite **WSLg** (incluso in Windows 11 e Windows 10 aggiornato).

**Requisiti:**
- WSLg attivo (Windows 11 o Windows 10 aggiornato)
- Installa nella home Linux (es. `~/OffGallery`)

Il wizard installa e configura tutto automaticamente.

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

**[Scarica OffGallerySetup.exe](https://github.com/HEGOM61ita/OffGallery/releases/latest)**, fai doppio click e segui il wizard.
Nessun terminale, nessuna configurazione manuale.

> **Nota SmartScreen**: al primo avvio Windows potrebbe mostrare un avviso di sicurezza. Clicca **"Ulteriori informazioni" → "Esegui comunque"**. L'avviso è dovuto all'assenza di firma digitale EV, non a problemi di sicurezza.

#### Linux

**[Scarica OffGallerySetup](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup)**, rendilo eseguibile e avvialo:
```bash
chmod +x OffGallerySetup && ./OffGallerySetup
```
Nessun terminale necessario dopo l'avvio — il wizard installa tutto graficamente.

#### macOS

1. Apri un terminale nella cartella OffGallery
2. Esegui:
   ```bash
   bash installer/install_offgallery_mac_it.sh
   ```
3. Segui le istruzioni a schermo

> **Apple Silicon (M1/M2/M3/M4)**: PyTorch utilizza automaticamente Metal/MPS per l'accelerazione GPU — nessuna configurazione aggiuntiva necessaria.
>
> **Nota Gatekeeper**: al primo avvio di `OffGallery.app` o `OffGallery.command`, macOS potrebbe mostrare un avviso di sicurezza. Usa **tasto destro → Apri** per confermarlo. L'installer rimuove già l'attributo quarantine automaticamente, quindi l'avviso normalmente non compare.

Il wizard installa automaticamente tutto il necessario: Miniconda, ambiente Python, librerie, ExifTool e opzionalmente Ollama per le descrizioni AI. Al termine crea un collegamento per avviare l'app (su Windows il wizard crea un collegamento sul Desktop, voce nel menu applicazioni su Linux, `OffGallery.app` in `~/Applications` cercabile via Spotlight e Launchpad su macOS).

> **Tempo stimato**: 20-40 minuti. Al primo avvio, OffGallery scarica automaticamente i modelli AI (~6.7 GB). Gli avvii successivi saranno completamente offline.

### Installazione manuale (alternativa)

**Linux** - usa [`OffGallerySetup`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup) (wizard one-click) oppure installa manualmente:
1. Installa [Miniconda](https://docs.anaconda.com/miniconda/install/) per Linux
2. `conda create -n OffGallery python=3.12 --override-channels -c conda-forge -y`
3. `conda run -n OffGallery pip install -r installer/requirements_offgallery.txt`
4. Installa ExifTool: `sudo apt install libimage-exiftool-perl` (Ubuntu/Debian) o equivalente
5. (Opzionale) Installa [Ollama](https://ollama.com/download) e `ollama pull qwen3-vl:8b-instruct-q4_K_M`

**macOS** - usa il wizard `install_offgallery_mac_it.sh` che copre tutti gli step, oppure installa manualmente:
1. Installa [Miniconda](https://docs.anaconda.com/miniconda/install/) per macOS (scegli la versione arm64 per Apple Silicon, x86_64 per Intel)
2. `conda create -n OffGallery python=3.12 --override-channels -c conda-forge -y`
3. `conda run -n OffGallery pip install -r installer/requirements_offgallery.txt`
4. Installa ExifTool: `brew install exiftool` (richiede [Homebrew](https://brew.sh)) o scarica il `.pkg` da [exiftool.org](https://exiftool.org)
5. (Opzionale) Installa [Ollama](https://ollama.com/download) e `ollama pull qwen3-vl:8b-instruct-q4_K_M`
6. Avvia: `conda run -n OffGallery python gui_launcher.py`

### Istruzioni Dettagliate

- **Windows**: il wizard `OffGallerySetup.exe` guida l'intera installazione — non è necessaria una guida separata.
- **Linux/macOS**: guida passo-passo completa in **[installer/INSTALL_GUIDE_IT.md](installer/INSTALL_GUIDE_IT.md)**.

---

## Utilizzo

L'interfaccia ha 7 tab: **Elaborazione · Ricerca · Galleria · Statistiche · Esportazione · Configurazione · Log**.

Workflow tipico: importa una cartella o un catalogo `.lrcat` → elabora con AI → cerca con linguaggio naturale → esporta XMP verso Lightroom.

### Avviare OffGallery

| Sistema | Metodo consigliato |
|---------|-------------------|
| **Windows** | Doppio click sul collegamento **OffGallery** creato sul Desktop dal wizard `OffGallerySetup.exe` |
| **macOS** | Apri **OffGallery.app** da `~/Applications` o cerca con Spotlight |
| **Linux** | Usa la voce nel menu applicazioni, oppure `bash installer/offgallery_launcher_linux.sh` dalla cartella dell'app |

> **Manuale Utente completo (IT):** **[HTML/USER_MANUAL_IT.html](HTML/USER_MANUAL_IT.html)**
> — Descrizione dettagliata di ogni tab, opzione, badge, concetti avanzati (BioCLIP, geotag, sync state) e troubleshooting.

---

## Configurazione

Per la documentazione completa delle opzioni di configurazione, consulta **[CONFIGURATION.md](CONFIGURATION.md)**.

---

## Sistema Plugin

OffGallery include un sistema di plugin auto-discovery: i plugin vengono rilevati automaticamente dalla cartella `plugins/` all'avvio, senza configurazione manuale. Tutti i plugin elencati sono inclusi nel pacchetto principale.

I plugin si dividono in due categorie:

### Plugin LLM — generazione testo

Abilitano la generazione automatica di tag, descrizioni e titoli tramite modelli LLM Vision locali. **La generazione LLM è opzionale**: senza un plugin LLM attivo, OffGallery funziona normalmente per tutte le altre funzioni (CLIP, DINOv2, BioCLIP, score, ricerca, geo, EXIF).

| Plugin | Backend | Endpoint default | Note |
|--------|---------|------------------|------|
| **Ollama** | Ollama locale | `http://localhost:11434` | Ottimizzato per qwen3-VL, llava, gemma3. Supporto `think=false`, diagnostica timing, warmup/unload VRAM |
| **LM Studio** | LM Studio server | `http://localhost:1234` | API OpenAI-compatible. Supporto AMD/DirectML, unload via CLI `lms`. Consigliato: qwen3-VL. Plugin sviluppato da Riccardo Merlotti |

Il backend attivo si seleziona dal tab **Configurazione → Connessione LLM**. Il cambio non richiede riavvio; i dati già generati nel database restano invariati.

> **Accesso beta — Plugin LLM**: Durante il periodo di beta testing i plugin sono distribuiti gratuitamente. Per riceverli, scrivere a **offgallery.ai.info@gmail.com** indicando: sistema operativo, RAM di sistema, GPU (modello e VRAM), e se si preferisce Ollama o LM Studio. L'indirizzo sarà utilizzato esclusivamente per l'invio del plugin e per eventuali notifiche di aggiornamento, senza altri scopi né condivisione con terze parti.

### Plugin Dati — arricchimento contestuale

Arricchiscono le foto già nel database con informazioni aggiuntive derivate dai metadati (GPS, data, tassonomia BioCLIP). Si avviano dalla Gallery (menu contestuale sulla foto) o in batch dal tab Elaborazione.

| Plugin | Funzione | Richiede | Output |
|--------|----------|----------|--------|
| **GeoNames** | Gerarchia geografica completa da GPS | GPS nella foto | Continente → Paese → Regione → Città; filtro Luogo con autocompletamento |
| **GeoSpecies** | Restringe BioCLIP alle sole specie attese nella posizione GPS (da GBIF/eBird) | GPS + BioCLIP | Classificazione biologica più precisa in contesti geografici specifici |
| **NaturArea** | Area protetta (database WDPA) e tipo di habitat (ESA WorldCover) | GPS | Campo `area_protetta`, campo `habitat` (bosco, macchia, acqua, urbano, ecc.) |
| **Meteo** | Condizioni meteo storiche al momento dello scatto | GPS + data/ora + connessione internet | Temperatura, umidità, vento, precipitazioni, condizione (sereno/nuvoloso/pioggia…) |
| **BioNomen** | Nomi comuni biologici in 6 lingue (GBIF) | BioCLIP | Nomi comuni aggiunti accanto al nome scientifico nel tooltip e nei tag |

> **Accesso beta — Plugin Dati**: Durante il periodo di beta testing i plugin sono distribuiti gratuitamente. Per riceverli, scrivere a **offgallery.ai.info@gmail.com** indicando: sistema operativo, RAM di sistema, GPU (modello e VRAM), e quali plugin si desidera ricevere. L'indirizzo sarà utilizzato esclusivamente per l'invio e per eventuali notifiche di aggiornamento, senza altri scopi né condivisione con terze parti.

## Architettura

```
offgallery/
├── gui/                      # Moduli interfaccia PyQt6
│   ├── processing_tab.py     # Orchestrazione elaborazione + sorgente catalogo
│   ├── search_tab.py         # Ricerca semantica + filtri
│   ├── gallery_tab.py        # Visualizzazione risultati
│   ├── export_tab.py         # Export XMP/CSV + copia con struttura
│   └── ...
├── embedding_generator.py    # Generazione embedding multi-modello
├── retrieval.py              # Motore di ricerca
├── db_manager_new.py         # Gestione database SQLite
├── raw_processor.py          # Estrazione RAW ottimizzata
├── xmp_manager_extended.py   # Lettura/scrittura XMP
├── geo_enricher.py           # Geolocalizzazione offline GPS → GeOFF
├── catalog_readers/          # Lettori cataloghi esterni
│   └── lightroom_reader.py   # Legge .lrcat (SQLite) → lista file
├── plugins/                  # Plugin (auto-discovery all'avvio)
│   ├── base.py               # Interfaccia pubblica LLMVisionPlugin
│   ├── loader.py             # Auto-detection backend
│   ├── llm_ollama/           # Plugin LLM: Ollama
│   ├── llm_lmstudio/         # Plugin LLM: LM Studio
│   ├── geonames/             # Gerarchia geografica offline
│   ├── geospecies/           # BioCLIP contestuale per GPS
│   ├── naturarea/            # Aree protette WDPA + habitat ESA
│   ├── weather_context/      # Meteo storico (richiede internet)
│   └── bionomen/             # Nomi comuni biologici GBIF
├── utils/                    # Utility cross-platform
│   ├── paths.py              # Path resolver (script/EXE/WSL)
│   └── copy_helpers.py       # Copia con struttura multi-disco
├── aesthetic/                # Modelli valutazione estetica
├── device_allocator.py       # Rilevamento hardware e allocazione device per-modello
├── exiftool_files/           # ExifTool per metadati EXIF
├── database/                 # Database SQLite
├── INPUT/                    # Cartella import immagini
└── config_new.yaml           # Configurazione
```

---

## Formati Supportati

### Immagini Standard
`JPG` `JPEG` `PNG` `TIFF` `TIF` `WEBP` `BMP` `HEIC`

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
| **Altri** | 3FR, IIQ, X3F |

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

### Plugin Interface Exception

I file `plugins/base.py` e `plugins/loader.py` sono distribuiti con un'eccezione esplicita
che permette di sviluppare plugin con licenze diverse dall'AGPLv3 (inclusi plugin proprietari),
purché comunichino con OffGallery esclusivamente tramite l'interfaccia `LLMVisionPlugin`.

Vedi **[plugins/PLUGIN_LICENSE_EXCEPTION.md](plugins/PLUGIN_LICENSE_EXCEPTION.md)** per i dettagli e le condizioni.

- **[TRADEMARK.md](TRADEMARK.md)** - Informazioni sui marchi registrati
- **[THIRD_PARTY.md](THIRD_PARTY.md)** - Licenze e attribuzioni software di terze parti

---

## Ringraziamenti e Crediti

> Pagina completa con licenze e descrizioni: **[offgallery.app/credits.html](https://offgallery.app/credits.html)**

**Modelli AI**
- [Google SigLIP (so400m-patch14-384)](https://huggingface.co/google/siglip-so400m-patch14-384) — Ricerca semantica multilingua · Apache 2.0
- [Meta DINOv2](https://github.com/facebookresearch/dinov2) — Embedding visivi · Apache 2.0
- [BioCLIP v2](https://github.com/Imageomics/bioclip) — Classificazione flora/fauna · MIT
- [Aesthetic Predictor V2.5](https://github.com/christophschuhmann/improved-aesthetic-predictor) — Punteggio estetico · Apache 2.0
- [MUSIQ (Google Research)](https://github.com/google-research/google-research/tree/master/musiq) — Qualità tecnica · Apache 2.0
- [Ollama](https://ollama.com) + [Qwen-VL](https://github.com/QwenLM/Qwen-VL) — LLM locali · MIT / Apache 2.0

**Librerie Python**
- [PyTorch](https://pytorch.org/) — Framework deep learning · BSD-3-Clause
- [Hugging Face Transformers](https://huggingface.co/docs/transformers) — Caricamento modelli · Apache 2.0
- [OpenCLIP](https://github.com/mlfoundations/open_clip) — Base BioCLIP · MIT
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — Interfaccia grafica · GPL v3
- [rawpy](https://github.com/letmaik/rawpy) + [LibRaw](https://www.libraw.org/) — Decodifica RAW · MIT / LGPL v2.1
- [Pillow](https://python-pillow.org/) — Elaborazione immagini · HPND

**Metadati e dati geografici**
- [ExifTool](https://exiftool.org/) (Phil Harvey) — EXIF/IPTC/XMP · Perl Artistic License
- [reverse_geocoder](https://github.com/thampiman/reverse-geocoder) + [GeoNames](https://www.geonames.org/) — Geocodifica offline · MIT / CC BY 4.0
- [Argos Translate](https://github.com/argosopentech/argos-translate) — Traduzione offline · MIT
- [SQLite](https://sqlite.org/) — Database locale · Public Domain

**Assistenti AI usati nello sviluppo**
- [Claude / Claude Code](https://claude.ai/) (Anthropic) · [ChatGPT](https://chatgpt.com/) (OpenAI) · [Gemini](https://gemini.google.com/) (Google) · [Perplexity AI](https://www.perplexity.ai/) · [LM Studio](https://lmstudio.ai/)

Il testo completo di ogni licenza è disponibile nel file [`THIRD_PARTY.md`](THIRD_PARTY.md) e nei rispettivi repository ufficiali.

---

<p align="center">
  <strong>Fatto con passione per i fotografi che tengono alla loro privacy</strong>
</p>

<p align="center">
  <a href="#offgallery">Torna su</a> &nbsp;|&nbsp; <a href="#english">🇬🇧 English version below</a>
</p>

---

<a id="english"></a>

<p align="center">
  <img src="assets/logo3.jpg" alt="OffGallery Logo" width="200"/>
</p>

<h1 align="center">OffGallery</h1>

<p align="center">
  <strong>Intelligent AI photo cataloging for photographers who care about their privacy</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12.9-blue?logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/PyTorch-2.7.1-red?logo=pytorch" alt="PyTorch"/>
  <img src="https://img.shields.io/badge/CUDA-11.8-green?logo=nvidia" alt="CUDA"/>
  <img src="https://img.shields.io/badge/License-AGPLV3-yellow" alt="License"/>
  <img src="https://img.shields.io/badge/100%25-Offline-brightgreen" alt="Offline"/>
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows" alt="Windows"/>
  <img src="https://img.shields.io/badge/Linux-Ubuntu%20|%20Fedora%20|%20Arch-orange?logo=linux" alt="Linux"/>
  <img src="https://img.shields.io/badge/macOS-12%2B-lightgrey?logo=apple" alt="macOS"/>
</p>

<p align="center">
  <em>Semantic and aesthetic analysis of your photos with local AI. Zero cloud. Zero compromises.</em>
</p>

---

> [!NOTE]
> **🌍 Full Multilingual Support**
>
> OffGallery supports 6 languages (**IT, EN, FR, DE, ES, PT**) independently at every level:
>
> - **GUI language**: select your language in Configuration → Interface Language
> - **LLM output language** (tags, descriptions, titles): choose independently from the GUI language. Tags are generated and stored in the configured language
> - **SigLIP semantic search**: multilingual native (Google SigLIP so400m) — query is passed directly without translation, in any language
> - **Tag/keyword search**: query is automatically translated to the tag language (same as `llm_output_language`) before matching, ensuring correct results even with tags in French, German, etc.
>
> All translations use **Argostranslate** — completely offline. Translation packages are downloaded on first use; the Log panel notifies you of their status.

---

## What is OffGallery?

A photographer's tool to catalog thousands of RAW images without sending them to any cloud service. Search your photos with natural language ("sunset over mountains") while keeping everything on your own machine.

### Key Features

| Feature | Description |
|---------|-------------|
| **One-click installer (Windows & Linux)** | [`OffGallerySetup.exe`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup.exe) (Windows) and [`OffGallerySetup`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup) (Linux) install everything automatically: Miniconda, Python, libraries, AI models (~8 GB) and Ollama. No terminal needed. macOS: guided script included in the `installer/` folder |
| **100% Offline** | No data ever leaves your computer. All AI models run locally |
| **Multilingual** | GUI, LLM output and tag search are independent: 6 languages (IT, EN, FR, DE, ES, PT). Tags and descriptions in any language, different from the UI language if you prefer |
| **Powerful Search** | Natural language semantic search + tag/EXIF/score filters; SigLIP multilingual native (no translation needed); automatic query translation for tag matching (content language); save and recall favorite searches in one click |
| **Native RAW Support** | 25+ RAW formats (Canon CR2/CR3, Nikon NEF, Sony ARW, Fuji RAF…) |
| **Visual Similarity** | One click to find similar images or near-duplicates |
| **Lightroom Catalog Import** | Process files directly from a `.lrcat` catalog — read-only, no catalog modification |
| **Integration with photo editors** | Bidirectional XMP sync: ratings, tags, metadata. Compatible with **Lightroom** (`.xmp`), **Darktable** (`.EXT.xmp`), **Capture One**, **digiKam**, **ACDSee**, **FastRawViewer** and any XMP-standard compliant software. No proprietary data is modified |
| **LLM Plugins** | Alternative LLM backends: Ollama and LM Studio. Auto-discovery at startup, switch backends without restart |
| **Data Plugins** | BioNomen (biological common names from GBIF), GeoNames (geographic hierarchy), GeoSpecies (GPS-contextual BioCLIP), NaturArea (WDPA protected areas + ESA habitat), Weather (historical weather context) |
| **Aesthetic Scoring** | Automatic artistic quality score (0–10) |
| **Species Identification** | BioCLIP2 recognizes ~450,000 species with full 7-level taxonomy |
| **Offline Geotagging** | Automatic geographic hierarchy from GPS: continent, country, region, city — no external API, bundled GeoNames data |
| **Statistics** | Camera, dates, metadata, gear, exposure, ratings and more |

---

## AI Engines

All core components run locally, completely offline:

```
┌──────────────────────────────────────────────────────────────────────┐
│                           OFFGALLERY                                 │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │   CLIP   │  │  DINOv2  │  │ BioCLIP2 │  │ LLM Vision (Plugin)  │ │
│  │ Semantic │  │  Visual  │  │  ~450k   │  │  Ollama · LM Studio  │ │
│  │  Search  │  │Similarity│  │  species │  │  tags · desc · title │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────────┘ │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐  │
│  │  Aesthetic Predictor │  │  MUSIQ (Technical Quality)           │  │
│  │  Artistic score 0-10 │  │  Sharpness · noise · optical quality │  │
│  └──────────────────────┘  └──────────────────────────────────────┘  │
│  ┌───────────────────────┐  ┌─────────────────────────────────────┐  │
│  │  Argos Translate      │  │  GeoNames (Plugin)                  │  │
│  │  SigLIP query (ML)    │  │  GPS → Continent/Country/Region/    │  │
│  │  + tag lang. offline  │  │  City  (bundled GeoNames data)      │  │
│  └───────────────────────┘  └─────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│  Optional plugins                                                    │
│  ┌─────────────────┐  ┌────────────────────┐  ┌──────────────────┐  │
│  │   GeoSpecies    │  │    NaturArea        │  │  Weather         │  │
│  │ GPS-contextual  │  │ WDPA protected areas│  │ Historical meteo │  │
│  │  BioCLIP (GBIF) │  │ + ESA habitat       │  │ at shoot GPS/time│  │
│  └─────────────────┘  └────────────────────┘  └──────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  BioNomen — common biological names (GBIF, 6 languages)         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Features

OffGallery provides semantic search, multi-model AI image analysis, full Lightroom workflow and XMP export. See the **[Full User Manual →](HTML/USER_MANUAL_EN.html)** for a detailed description of every feature, tab and option.

| Feature | Quick description |
|---------|-------------------|
| **Semantic Search** | Natural language, automatic offline translation, threshold slider |
| **Tag Search** | Case-insensitive fuzzy matching, saved searches |
| **Advanced Filters** | Camera, lens, ISO, aperture, shutter, date, rating, score, colour |
| **AI Analysis** | CLIP · DINOv2 · BioCLIP2 · LLM Vision · Aesthetic Score · Technical Score · Geotag |
| **Per-model device** | Each AI model individually assignable to GPU or CPU; auto-optimization with VRAM budget and LLM detection |
| **Lightroom Workflow** | `.lrcat` import · XMP import · Hierarchical XMP export · Structured copy |
| **AI Gen. Only** | Regenerate tags/description/title (LLM) on existing DB photos, skip EXIF and embeddings |
| **LLM Plugins** | Select LLM backend (Ollama or LM Studio) from the Configuration tab; plugins auto-detected |
| **Data Plugins** | BioNomen · GeoNames · GeoSpecies · NaturArea · Weather — contextual enrichment on existing DB photos, from Gallery or batch |

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **RAM** | 8 GB | 16 GB |
| **Disk** | 14 GB (CPU) / 18 GB (NVIDIA GPU) | 20 GB |
| **GPU** | — | NVIDIA with CUDA |
| **OS** | Windows 10/11, Linux 64-bit or macOS 12+ | Windows 11 / Ubuntu 22.04+ / macOS 13+ |

> **Notes**:
> - NVIDIA GPU recommended for best performance. CPU-only works but is slower
> - **Disk space**: Python environment ~3.5 GB without GPU, ~7 GB with NVIDIA (PyTorch CUDA + runtime). AI models ~6.7 GB regardless of GPU
> - Internet required only on first launch to download AI models (~6.7 GB); fully offline afterwards
> - **macOS**: Apple Silicon (M1/M2/M3/M4) and Intel supported. PyTorch uses Metal/MPS on Apple Silicon — no CUDA needed

---

## Installation

### 1. Download OffGallery

**Option A — Download ZIP (recommended):**
1. Click the green **"<> Code"** button at the top right
2. Select **"Download ZIP"**
3. Extract to the **parent folder** where you want OffGallery to live

> **Extraction note:** the ZIP already contains an `OffGallery-main` folder — that folder **is** the app root.
> Extract to e.g. `C:\Programs\` → you get `C:\Programs\OffGallery-main\`, which you can rename freely.

**Option B — Git clone:**
```bash
git clone https://github.com/HEGOM61ita/OffGallery.git
```

### 2. Install with the Wizard

#### Windows

**[Download OffGallerySetup.exe](https://github.com/HEGOM61ita/OffGallery/releases/latest)**, double-click it and follow the wizard.
No terminal, no manual configuration needed.

> **SmartScreen note**: on first launch Windows may show a security warning. Click **"More info" → "Run anyway"**. The warning is due to the absence of an EV code signing certificate, not a security issue.

#### Linux

**[Download OffGallerySetup](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup)**, make it executable and run it:
```bash
chmod +x OffGallerySetup && ./OffGallerySetup
```
No terminal needed after launch — the wizard installs everything graphically.

#### macOS
```bash
bash installer/install_offgallery_mac_en.sh
```

> **Apple Silicon (M1/M2/M3/M4)**: PyTorch automatically uses Metal/MPS for GPU acceleration — no extra configuration needed.

The wizard installs everything automatically: Miniconda, Python environment, libraries, ExifTool and optionally Ollama for AI descriptions. On completion it creates a launcher shortcut (Desktop shortcut on Windows, application menu entry on Linux, `OffGallery.app` in `~/Applications` on macOS).

> **Estimated time**: 20–40 minutes. On first launch OffGallery downloads AI models (~6.7 GB). All subsequent launches are fully offline.

### Manual installation

**Linux** — use [`OffGallerySetup`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup) (one-click wizard) or install manually:
1. Install [Miniconda](https://docs.anaconda.com/miniconda/install/) for Linux
2. `conda create -n OffGallery python=3.12 --override-channels -c conda-forge -y`
3. `conda run -n OffGallery pip install -r installer/requirements_offgallery.txt`
4. Install ExifTool: `sudo apt install libimage-exiftool-perl` (Ubuntu/Debian) or equivalent
5. (Optional) Install [Ollama](https://ollama.com/download) and `ollama pull qwen3-vl:8b-instruct-q4_K_M`

**macOS:**
1. Install [Miniconda](https://docs.anaconda.com/miniconda/install/) for macOS (arm64 for Apple Silicon, x86_64 for Intel)
2. `conda create -n OffGallery python=3.12 --override-channels -c conda-forge -y`
3. `conda run -n OffGallery pip install -r installer/requirements_offgallery.txt`
4. Install ExifTool: `brew install exiftool`
5. (Optional) Install [Ollama](https://ollama.com/download) and `ollama pull qwen3-vl:8b-instruct-q4_K_M`

- **Windows**: the `OffGallerySetup.exe` wizard handles the entire installation — no separate guide needed.
- **Linux/macOS**: full step-by-step guide in **[installer/INSTALL_GUIDE_EN.md](installer/INSTALL_GUIDE_EN.md)**.

---

## Latest News

| Date | What | Notes |
|------|------|-------|
| 8 May 2026 | **Guided installer for Windows — [`OffGallerySetup.exe`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup.exe)** | 5-step wizard: detects your GPU (NVIDIA/AMD/CPU), installs Miniconda, Python, libraries, AI models (~8 GB) and optionally Ollama. No terminal, no manual configuration. Creates a Desktop shortcut. |
| 8 May 2026 | **Guided installer for Linux — [`OffGallerySetup`](https://github.com/HEGOM61ita/OffGallery/releases/latest/download/OffGallerySetup)** | Native graphical wizard for Linux (Ubuntu, Fedora, Arch and compatible distros). `chmod +x OffGallerySetup && ./OffGallerySetup` — installs everything and creates an application menu entry. No terminal needed. |
| 3 May 2026 | **Prompt Context Plugin** | Injects a custom CONTEXT block into the LLM Vision prompt to tailor tags, descriptions and titles to the archive's specific photographic domain. 8 built-in presets (wildlife, landscape, astrophotography, scientific macro, underwater, reportage, commercial, street) + generate custom presets via local LLM. Preset selectable from the Plugin tab or the Gallery context menu |
| 22 Apr 2026 | **Darktable & multi-editor compatibility** | Full Darktable workflow support: reads `.NEF.xmp` / `.ARW.xmp` sidecars (Darktable `filename.EXT.xmp` convention), preserves proprietary namespaces when creating new sidecars, XMP→DB import and badge sync from Gallery, **Output format: Lightroom / Darktable** option in Export tab. Compatible with Lightroom, Darktable, Capture One, digiKam, ACDSee, FastRawViewer |
| 5 Apr 2026 | **GeoNames plugin** | Advanced geolocation: full geographic hierarchy (continent → country → region → city), Location filter with DB autocomplete, GPS filter with 4 states (all / GPS only / GPS modified / no GPS) |

Full history in [**Discussions**](https://github.com/HEGOM61ita/OffGallery/discussions).

---

## Usage

The interface has 7 tabs: **Processing · Search · Gallery · Statistics · Export · Configuration · Log**.

Typical workflow: import a folder or `.lrcat` catalog → process with AI → search with natural language → export XMP to Lightroom.

### Launching OffGallery

| OS | Recommended method |
|----|-------------------|
| **Windows** | Double-click the **OffGallery** shortcut created on the Desktop by the `OffGallerySetup.exe` wizard |
| **macOS** | Open **OffGallery.app** from `~/Applications` or search via Spotlight |
| **Linux** | Use the application menu entry, or run `bash installer/offgallery_launcher_linux_en.sh` from the app folder |

> **Full User Manual (EN):** **[HTML/USER_MANUAL_EN.html](HTML/USER_MANUAL_EN.html)**
> — Detailed description of every tab, option, badge, advanced concepts (BioCLIP, geotagging, sync state) and troubleshooting.

---

## Plugin System

OffGallery includes an auto-discovery plugin system: plugins are detected automatically from the `plugins/` folder at startup, with no manual configuration. All plugins listed below are included in the main package.

Plugins fall into two categories:

### LLM Plugins — text generation

Enable automatic generation of tags, descriptions and titles via local LLM Vision models. **LLM generation is optional**: without an active LLM plugin, OffGallery works normally for all other features (CLIP, DINOv2, BioCLIP, scores, search, geo, EXIF).

| Plugin | Backend | Default endpoint | Notes |
|--------|---------|-----------------|-------|
| **Ollama** | Local Ollama | `http://localhost:11434` | Optimized for qwen3-VL, llava, gemma3. `think=false` support, timing diagnostics, VRAM warmup/unload |
| **LM Studio** | LM Studio server | `http://localhost:1234` | OpenAI-compatible API. AMD/DirectML support, `lms` CLI unload. Recommended: qwen3-VL. Plugin developed by Riccardo Merlotti |

The active backend is selected from **Configuration → LLM Connection**. Switching does not require a restart; existing database data is not affected.

> **Beta access — LLM Plugins**: During the beta testing period, plugins are distributed free of charge. To receive them, write to **offgallery.ai.info@gmail.com** stating: operating system, system RAM, GPU (model and VRAM), and whether you prefer Ollama or LM Studio. The address will be used solely to send the plugin and for update notifications — never for any other purpose or shared with third parties.

### Data Plugins — contextual enrichment

Enrich photos already in the database with additional information derived from metadata (GPS, date/time, BioCLIP taxonomy). Run from the Gallery (context menu on a photo) or in batch from the Processing tab.

| Plugin | Function | Requires | Output |
|--------|----------|----------|--------|
| **GeoNames** | Full geographic hierarchy from GPS | GPS in photo | Continent → Country → Region → City; Location filter with autocomplete |
| **GeoSpecies** | Restricts BioCLIP to species expected at the GPS location (GBIF/eBird data) | GPS + BioCLIP | More precise biological classification in geographically specific contexts |
| **NaturArea** | Protected area (WDPA database) and habitat type (ESA WorldCover) | GPS | `protected_area` field, `habitat` field (forest, shrubland, water, urban, etc.) |
| **Weather** | Historical weather conditions at time of capture | GPS + date/time + internet | Temperature, humidity, wind, precipitation, condition (clear/cloudy/rain…) |
| **BioNomen** | Common biological names in 6 languages (GBIF) | BioCLIP | Common names added alongside scientific name in tooltip and tags |

> **Beta access — Data Plugins**: During the beta testing period, plugins are distributed free of charge. To receive them, write to **offgallery.ai.info@gmail.com** stating: operating system, system RAM, GPU (model and VRAM), and which plugins you wish to receive. The address will be used solely to send the plugin and for update notifications — never for any other purpose or shared with third parties.

## Supported Formats

**Standard:** `JPG` `JPEG` `PNG` `TIFF` `TIF` `WEBP` `BMP` `HEIC`

**RAW:**

| Manufacturer | Formats |
|-------------|---------|
| **Canon** | CR2, CR3, CRW |
| **Nikon** | NEF, NRW |
| **Sony** | ARW, SRF, SR2 |
| **Fujifilm** | RAF |
| **Panasonic** | RW2 |
| **Olympus/OM** | ORF |
| **Pentax** | PEF, DNG |
| **Leica** | DNG, RWL |
| **Adobe** | DNG |
| **Others** | 3FR, IIQ, X3F |

---

## Privacy & Security

OffGallery is built with privacy as a core principle:

- **Zero telemetry**: No data is collected or transmitted
- **Offline after first launch**: AI models are downloaded from a frozen HuggingFace repository on first launch. After that the app runs completely offline
- **Frozen repository**: Models are hosted on a controlled repository (`HEGOM/OffGallery-models`) to guarantee version stability and compatibility
- **Local storage**: SQLite database + binary embeddings on your disk
- **No API keys**: No accounts or subscriptions required

---

## License

Distributed under the **AGPL-3.0** license. See `LICENSE` for details.

### Plugin Interface Exception

`plugins/base.py` and `plugins/loader.py` carry an explicit exception that allows
developing plugins under licenses other than AGPLv3 (including proprietary ones),
provided they communicate with OffGallery exclusively through the `LLMVisionPlugin` interface.

See **[plugins/PLUGIN_LICENSE_EXCEPTION.md](plugins/PLUGIN_LICENSE_EXCEPTION.md)** for full terms and conditions.

- **[TRADEMARK.md](TRADEMARK.md)** — Trademark information
- **[THIRD_PARTY.md](THIRD_PARTY.md)** — Third-party software licenses and attributions

---

## Acknowledgements & Credits

> Full page with licenses and descriptions: **[offgallery.app/credits.html](https://offgallery.app/credits.html)**

**AI Models**
- [Google SigLIP (so400m-patch14-384)](https://huggingface.co/google/siglip-so400m-patch14-384) — Multilingual semantic search · Apache 2.0
- [Meta DINOv2](https://github.com/facebookresearch/dinov2) — Visual embeddings · Apache 2.0
- [BioCLIP v2](https://github.com/Imageomics/bioclip) — Flora/fauna classification · MIT
- [Aesthetic Predictor V2.5](https://github.com/christophschuhmann/improved-aesthetic-predictor) — Aesthetic scoring · Apache 2.0
- [MUSIQ (Google Research)](https://github.com/google-research/google-research/tree/master/musiq) — Technical quality · Apache 2.0
- [Ollama](https://ollama.com) + [Qwen-VL](https://github.com/QwenLM/Qwen-VL) — Local LLMs · MIT / Apache 2.0

**Python Libraries**
- [PyTorch](https://pytorch.org/) — Deep learning framework · BSD-3-Clause
- [Hugging Face Transformers](https://huggingface.co/docs/transformers) — Model loading · Apache 2.0
- [OpenCLIP](https://github.com/mlfoundations/open_clip) — BioCLIP backbone · MIT
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — Graphical UI · GPL v3
- [rawpy](https://github.com/letmaik/rawpy) + [LibRaw](https://www.libraw.org/) — RAW decoding · MIT / LGPL v2.1
- [Pillow](https://python-pillow.org/) — Image processing · HPND

**Metadata & Geographic Data**
- [ExifTool](https://exiftool.org/) (Phil Harvey) — EXIF/IPTC/XMP · Perl Artistic License
- [reverse_geocoder](https://github.com/thampiman/reverse-geocoder) + [GeoNames](https://www.geonames.org/) — Offline geocoding · MIT / CC BY 4.0
- [Argos Translate](https://github.com/argosopentech/argos-translate) — Offline translation · MIT
- [SQLite](https://sqlite.org/) — Local database · Public Domain

**AI Assistants used in development**
- [Claude / Claude Code](https://claude.ai/) (Anthropic) · [ChatGPT](https://chatgpt.com/) (OpenAI) · [Gemini](https://gemini.google.com/) (Google) · [Perplexity AI](https://www.perplexity.ai/) · [LM Studio](https://lmstudio.ai/)

Full license text for each component is available in [`THIRD_PARTY.md`](THIRD_PARTY.md) and in the respective official repositories.

---

<p align="center">
  <strong>Built with passion for photographers who value their privacy</strong>
</p>

<p align="center">
  <a href="#offgallery">Back to top</a> &nbsp;|&nbsp; <a href="#italiano">🇮🇹 Versione italiana</a>
</p>
