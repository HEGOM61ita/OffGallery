
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
</p>

<p align="center">
  <em>Analisi semantica ed estetica delle tue foto con AI locale. Zero cloud. Zero compromessi.</em>
</p>

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
| **Identificazione Specie** | BioCLIP2 riconosce ~450.000 specie di flora e fauna |
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
- **Tag BioCLIP**: Identificazione automatica specie naturali
- **Tag LLM**: Descrizioni e tag generati da modelli linguistici locali parametrizzabili
- **Score Estetico**: Valutazione artistica automatica
- **Score Tecnico**: Analisi qualità (nitidezza, rumore, esposizione, solo per non RAW)

### Workflow Fotografico

- **Import XMP**: Legge tag e rating da Lightroom/DxO/etc.
- **Export XMP**: Scrive modifiche compatibili con editor esterni
- **Sync State**: Traccia stato sincronizzazione (PERFECT_SYNC, DIRTY, etc.)
- **Badge Visivi**: Score, rating, ranking e stato colore nella gallery
- **Menu contestuale**: Per ogni immagine nella Gallery, basta un click per editarla su Lightroom o altro editor, gestire metadati, creare tags e descrizioni, etc.

---

## Requisiti di Sistema

| Componente | Minimo | Consigliato |
|------------|--------|-------------|
| **RAM** | 8 GB | 16 GB |
| **Disco** | 15 GB | 25 GB |
| **GPU** | - | NVIDIA con CUDA |
| **OS** | Windows 10/11 | Windows 11 |

> **Note**:
> - GPU NVIDIA raccomandata per prestazioni ottimali. Funziona anche su CPU (più lento)
> - Connessione internet richiesta solo al primo avvio per download modelli AI (~7 GB)

---

## Installazione

### 1. Scarica OffGallery

**Opzione A - Download ZIP (consigliato):**
1. Clicca il pulsante verde **"<> Code"** in alto a destra
2. Seleziona **"Download ZIP"**
3. Estrai la cartella dove preferisci (es. `C:\OffGallery`)

**Opzione B - Git clone:**
```bash
git clone https://github.com/HEGOM61ita/OffGallery.git
```

### 2. Installa dipendenze

1. **Installa Miniconda** (se non presente)
   - Esegui `installer/01_install_miniconda.bat` per verificare/installare
   - Oppure scarica da [miniconda.io](https://docs.conda.io/en/latest/miniconda.html)

2. **Crea ambiente e installa pacchetti**
   - Esegui `installer/02_create_env.bat`
   - Esegui `installer/03_install_packages.bat`

### 3. Avvia l'applicazione

- Doppio click su `installer/OffGallery_Launcher.bat`
- (Consiglio: copia il launcher sul Desktop)

> **Download automatico**: Al primo avvio, OffGallery scarica automaticamente i modelli AI (~7 GB) dal repository HuggingFace congelato. Gli avvii successivi saranno completamente offline.

### Ollama (opzionale, per descrizioni AI)

Per generare descrizioni e tag automatici con LLM:
- Esegui `installer/06_setup_ollama.bat` per installare Ollama + modello Qwen3-VL

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
| **Galleria** | Visualizza risultati con badge e preview |
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

## Contributi

Questo progetto segue un modello di sviluppo centralizzato.
Attualmente, non sono accettati contributi di codice esterno (pull requests).
Anche se non posso garantire una risposta, tutte le segnalazioni di bug, idee e suggerimenti per nuove funzionalità sono benvenuti e apprezzati e saranno presi in considerazione per futuri sviluppi.

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
