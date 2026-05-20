# OffGallery Manager — Design Document

> Documento di progetto per il nuovo installer/manager GUI di OffGallery.
> Aggiornare man mano che il progetto avanza.
> **Questa directory NON va mai pushata su repo pubblica o beta finché il manager non è perfettamente funzionante.**

---

## Obiettivo

Rendere OffGallery installabile da un utente non-IT con un singolo doppio clic,
senza terminali, senza conoscenze tecniche, senza leggere guide.

Il problema attuale: la guida INSTALL_GUIDE_IT.md è ben scritta ma descrive un
processo troppo complesso per utenti non tecnici (12 step solo per Miniconda,
finestre nere, PATH, conda da terminale, ecc.).

---

## Concetto: OffGallery Manager

Non un installer one-shot, ma uno strumento persistente con due modalità:

- **Prima esecuzione**: wizard guidato con profili utente
- **Esecuzioni successive**: dashboard di manutenzione

L'utente può tornare al manager in qualsiasi momento per:
- Aggiungere componenti non installati inizialmente (es. Ollama)
- Aggiornare componenti esistenti (Ollama, LM Studio cambiano spesso)
- Reinstallare componenti rotti
- Scaricare modelli mancanti
- Aggiornare OffGallery Core

---

## Distribuzione

### File che l'utente scarica

`OffGallerySetup.exe` — singolo eseguibile, niente ZIP, niente cartelle da estrarre.

### Tecnologia di build: Strada B (PyInstaller)

`installer.py` viene compilato con PyInstaller in un exe standalone (~50MB).
Include Python embeddable minimale (solo per far girare il manager stesso).
L'ambiente conda che crea per l'app è separato e indipendente.

Strada A (C++ bootstrap) è valutabile quando il progetto è maturo e si ha
un certificato di firma digitale EV. Per ora Strada B è sufficiente.

### Firma digitale

Senza firma, Windows SmartScreen mostra un avviso rosso.
Da affrontare prima del rilascio pubblico (~80€/anno certificato EV).

---

## Sorgenti e risorse esterne

| Componente | Sorgente | Note |
|---|---|---|
| OffGallery Core | GitHub pubblico, branch main | ZIP: `github.com/HEGOM61ita/OffGallery/archive/refs/heads/main.zip` |
| Modelli AI | HuggingFace `HEGOM/OffGallery-models` | Repo frozen, versioni garantite |
| Miniconda | `repo.anaconda.com` | Ufficiale |
| Ollama | `ollama.com` | Versione rilevata dinamicamente |
| LM Studio | `lmstudio.ai` | Versione rilevata dinamicamente |
| Librerie Python | PyPI via pip | Da `requirements_offgallery.txt` |

### Versioning

Introdurre `version.txt` nel repo core con solo il numero di versione (es. `1.0.0`).
Il manager lo legge dopo l'installazione e lo salva localmente per confronti futuri.
Permette all'app di avvisare l'utente quando è disponibile un aggiornamento.

---

## Profili utente (wizard — prima esecuzione)

```
┌─────────────────────────────────────────────┐
│  Cosa vuoi fare con OffGallery?             │
│                                             │
│  ◉ Organizzare e cercare le mie foto        │
│    (consigliato — ~14 GB)                   │
│                                             │
│  ○ Anche generare descrizioni e tag         │
│    automatici con AI                        │
│    (richiede PC potente — ~20 GB)           │
│                                             │
│  ○ Personalizzato...                        │
└─────────────────────────────────────────────┘
```

### Profilo Leggero (~14 GB)
- Miniconda + env Python
- OffGallery Core
- Librerie Python (PyTorch CPU o CUDA auto-rilevato)
- Modelli AI: CLIP, DINOv2, Aesthetic, BioCLIP, Argos
- NO Ollama, NO LM Studio

### Profilo Completo (~20 GB)
- Tutto il Profilo Leggero
- Ollama + modello `qwen3-vl:8b-instruct-q4_K_M` (~5.2 GB)
- Richiede 16GB+ RAM, GPU consigliata

### Profilo Personalizzato
- Checkbox per ogni componente
- Mostra dimensioni e requisiti per ciascuno
- Per utenti che sanno cosa vogliono

---

## Dashboard di manutenzione (esecuzioni successive)

```
┌──────────────────────────────────────────────────────┐
│  🦉 OffGallery Manager                               │
├──────────────────────────────────────────────────────┤
│  AMBIENTE                                            │
│  ✅ Miniconda          v24.1     ──────────          │
│  ✅ Python env         3.12      ──────────          │
│  ✅ Librerie           OK        [ Reinstalla ]      │
│  ✅ OffGallery Core    v1.0.0    [ Aggiorna ]        │
│                                                      │
│  MODELLI AI                                          │
│  ✅ SigLIP            1800 MB    ──────────          │
│  ✅ DINOv2             330 MB    ──────────          │
│  ✅ Aesthetic          1.6 GB    ──────────          │
│  ✅ BioCLIP            4.2 GB    ──────────          │
│  ✅ Argos Translate    92 MB     ──────────          │
│                                                      │
│  LLM (opzionale)                                     │
│  ❌ Ollama             —         [ Installa ]        │
│  ❌ LM Studio          —         [ Installa ]        │
│                                                      │
│  [ ▶ Avvia OffGallery ]                             │
└──────────────────────────────────────────────────────┘
```

Ogni riga mostra stato (✅/❌/⚠️), versione installata, azione disponibile.
Ollama e LM Studio mostrano `[ Aggiorna a vX.Y ]` quando disponibile una nuova versione.

---

## Fasi di installazione (interne, invisibili all'utente)

Ogni fase completata scrive il proprio stato in `installer_state.json`.
Se l'installazione viene interrotta, alla riapertura riparte dall'ultimo checkpoint.

### FASE 0 — Preflight (~30 sec)

Schermata dedicata che mostra i risultati prima di iniziare qualsiasi download.

```
┌─────────────────────────────────────────────────────┐
│  Controllo del tuo computer                         │
├─────────────────────────────────────────────────────┤
│  Sistema operativo   Windows 11 64-bit      ✅      │
│  RAM disponibile     16 GB                  ✅      │
│  Spazio disco        234 GB liberi su C:\   ✅      │
│  Connessione         45 Mb/s (stimati)      ✅      │
│  GPU                 NVIDIA RTX 3060 12GB   ✅      │
│                      CUDA 12.1 compatibile          │
│                                                     │
│  Tempo stimato installazione:  ~35 minuti           │
│  Spazio che verrà usato:       ~18 GB               │
│                                                     │
│                          [ CONTINUA ]               │
└─────────────────────────────────────────────────────┘
```

Se qualcosa non va, la riga diventa rossa o gialla con consiglio leggibile:

```
│  RAM disponibile     6 GB                   ⚠️      │
│  → Funziona ma sarà più lento.                      │
│    Considera di non installare Ollama.              │
│                                                     │
│  Spazio disco        8 GB liberi su C:\     ❌      │
│  → Servono almeno 15 GB. Libera spazio o            │
│    scegli un altro disco.  [ Cambia disco ]         │
```

Livelli di severità:
- ✅ OK — tutto bene, si procede
- ⚠️ Avviso — si può procedere, ma con aspettative ridimensionate
- ❌ Bloccante — non si può procedere finché non risolto

Check eseguiti:
- **OS**: Windows 10+/macOS 12+/Linux 64-bit — ❌ se non soddisfatto
- **RAM**: minimo 8 GB — ⚠️ sotto 8 GB, ❌ sotto 4 GB
- **Disco**: minimo 15 GB liberi — ⚠️ tra 15-20 GB, ❌ sotto 15 GB
- **Connessione**: ping + download file piccolo per stimare velocità — ⚠️ sotto 5 Mb/s (avvisa sui tempi lunghi)
- **GPU**: rileva NVIDIA + versione CUDA driver — ✅ con GPU, ℹ️ senza GPU (CPU-only, nessun problema)

### FASE 1 — Miniconda (~5 min)
- Se già presente nel PATH o in percorsi standard: rileva e usa silenziosamente
- Se non trovato automaticamente: mostra dialog
  ```
  ┌─────────────────────────────────────────────────────┐
  │  Hai già Anaconda o Miniconda installato?           │
  │                                                     │
  │  ◉ No, installa automaticamente                     │
  │  ○ Sì, indicami dove si trova  [ Sfoglia... ]       │
  └─────────────────────────────────────────────────────┘
  ```
- Se l'utente indica un percorso manuale: verifica che conda sia lì dentro
- Se assente e nessun percorso indicato: scarica e installa silenziosamente
- NON modifica il PATH globale del sistema — usa il conda locale
- Se esiste già un env 'OffGallery' con Python corretto: lo usa senza ricreare
- Se esiste env 'OffGallery' con Python sbagliato: lo ricrea
- Checkpoint dopo completamento

### FASE 2 — Ambiente Python (~2 min)
- `conda create -n OffGallery python=3.12`
- Se già esiste: verifica versione Python, ricrea se necessario
- Checkpoint dopo completamento

### FASE 3 — OffGallery Core (~1 min + download)
- Scarica ZIP da GitHub main
- Estrae nella cartella scelta dall'utente
- Salva versione installata in file locale
- Checkpoint dopo completamento

### FASE 4 — Librerie Python (~15-20 min, ~3 GB)
- Auto-rileva GPU: installa PyTorch CUDA (versione matching driver) o CPU-only
- Installa tutto da `requirements_offgallery.txt`
- Versioni pinnate per compatibilità: `transformers==4.57.3`, `huggingface-hub==0.36.0`, `open-clip-torch==3.2.0`
- Progress reale per ogni pacchetto
- Checkpoint dopo completamento

### FASE 5 — Modelli AI (~15-20 min, ~6.7 GB)
- Scaricati QUI nell'installer, non al primo avvio dell'app
- Download chunked con resume nativo
- Verifica hash dopo ogni modello
- Progress individuale per ogni modello:

| Modello | Cartella HF | File principali | Dimensione |
|---|---|---|---|
| SigLIP so400m | `clip/` | model.safetensors + sentencepiece.bpe.model | ~1.80 GB |
| DINOv2 | `dinov2/` | model.safetensors | ~330 MB |
| Aesthetic Scorer | `aesthetic/` | model.safetensors + tokenizer | ~1.63 GB |
| BioCLIP v2 | `bioclip/` | open_clip_model.safetensors | ~1.63 GB |
| TreeOfLife Embeddings | `treeoflife/` | txt_emb_species.npy + .json | ~2.63 GB |
| MUSIQ | `musiq/` | musiq_koniq_ckpt-e95806b9.pth | ~104 MB |
| Argos Translate IT→EN | `argos-it-en/` | model.bin + stanza + sentencepiece | ~92 MB |
| **TOTALE** | | | **~8.1 GB** |

Nota: dimensioni verificate su disco il 2026-05-06 (file reali, non stime LFS).
CLIP, Aesthetic e BioCLIP usano tutti ViT-L/14 come backbone — stesso peso 1631 MB.

- Checkpoint per ogni modello singolo

### FASE 6 — Ollama (opzionale, ~10 min + ~5.2 GB)
- Solo se profilo Completo o scelta manuale
- Download installer Ollama, installazione silenziosa
- `ollama pull qwen3-vl:8b-instruct-q4_K_M`
- Configurazione come servizio Windows
- Checkpoint dopo completamento

### FASE 7 — Collegamento desktop + test
- Crea `OffGallery.lnk` sul desktop
- Avvia l'app in background per smoke test
- Conferma che risponda correttamente
- Messaggio finale: "Installazione completata! [ Avvia OffGallery ]"

---

## Stato persistente (installer_state.json)

```json
{
  "version": "1.0",
  "install_path": "C:\\Users\\Nome\\OffGallery",
  "profile": "leggero",
  "miniconda": { "status": "done", "path": "C:\\miniconda3", "version": "24.1" },
  "conda_env": { "status": "done", "python_version": "3.12" },
  "core": { "status": "done", "version": "1.0.0" },
  "packages": { "status": "done", "torch_variant": "cuda118" },
  "models": {
    "clip":      { "status": "done",        "size_mb": 1800 },
    "dinov2":    { "status": "done",        "size_mb": 330  },
    "aesthetic": { "status": "in_progress", "size_mb": 1600 },
    "bioclip":   { "status": "pending",     "size_mb": 4200 },
    "argos":     { "status": "pending",     "size_mb": 92   }
  },
  "ollama": { "status": "skipped" },
  "lmstudio": { "status": "not_installed" }
}
```

---

## Gestione errori intelligente

| Problema | Comportamento |
|---|---|
| Spazio disco insufficiente | Avviso prima di iniziare, suggerisce disco alternativo |
| Connessione assente | Rileva offline, avvisa, riprova automaticamente |
| Proxy aziendale | Prova pip normale → `--trusted-host` → chiede credenziali |
| Antivirus blocca download | Suggerisce whitelist temporanea, fallback mirror locale |
| CUDA version mismatch | Auto-fallback a CPU-only con spiegazione chiara |
| Conda non risponde | Kill e retry, poi suggerisce reinstallazione Miniconda |
| Download modello corrotto | Verifica hash, riscarica automaticamente |
| Porta 11434 occupata (Ollama) | Rileva conflitto e propone porta alternativa |
| Permessi insufficienti | Prova `--user` install, altrimenti chiede elevazione UAC |

---

## Struttura moduli Python (da implementare)

```
A_INSTALLER/
├── DESIGN.md                  ← questo file
├── installer.py               ← entry point, GUI principale (tkinter)
├── components/
│   ├── __init__.py
│   ├── miniconda.py           ← download, install, detect
│   ├── conda_env.py           ← create, verify, recreate
│   ├── core.py                ← download da GitHub, extract, versioning
│   ├── packages.py            ← pip install, cuda detection, pinned versions
│   ├── models.py              ← download HF, chunked, resume, hash verify
│   ├── ollama.py              ← install, pull model, service, version check
│   └── lmstudio.py            ← install, version check
├── state/
│   └── state_manager.py       ← read/write installer_state.json
├── ui/
│   ├── wizard.py              ← schermata profili (prima installazione)
│   ├── dashboard.py           ← schermata manutenzione (esecuzioni successive)
│   ├── preflight_ui.py        ← schermata check sistema (FASE 0)
│   ├── progress.py            ← widget progress bar con speed/ETA
│   └── styles.py              ← colori, font, costanti UI
└── utils/
    ├── download.py            ← download chunked con resume
    ├── gpu_detect.py          ← rileva GPU NVIDIA e versione CUDA driver
    ├── preflight.py           ← check sistema completo (OS, RAM, disco, rete, GPU)
    └── net_check.py           ← verifica connessione e stima velocità
```

---

## Differenze per piattaforma

### Rilevamento piattaforma
```python
import platform
system = platform.system()  # "Windows" | "Darwin" | "Linux"
machine = platform.machine() # "x86_64" | "arm64" (Apple Silicon)
```

### Miniconda — URL di download per piattaforma

| Piattaforma | URL |
|---|---|
| Windows x86_64 | `Miniconda3-latest-Windows-x86_64.exe` |
| macOS Apple Silicon | `Miniconda3-latest-MacOSX-arm64.sh` |
| macOS Intel | `Miniconda3-latest-MacOSX-x86_64.sh` |
| Linux x86_64 | `Miniconda3-latest-Linux-x86_64.sh` |

Base URL: `https://repo.anaconda.com/miniconda/`

### Miniconda — installazione silenziosa

| Piattaforma | Comando |
|---|---|
| Windows | `miniconda.exe /S /D=C:\miniconda3` |
| macOS / Linux | `bash miniconda.sh -b -p ~/miniconda3` |

### Percorsi Miniconda di default

| Piattaforma | Percorso default |
|---|---|
| Windows | `C:\miniconda3` |
| macOS / Linux | `~/miniconda3` |

### Percorso conda executable

| Piattaforma | Percorso |
|---|---|
| Windows | `{miniconda_path}\Scripts\conda.exe` |
| macOS / Linux | `{miniconda_path}/bin/conda` |

### Percorso Python nell'env

| Piattaforma | Percorso |
|---|---|
| Windows | `{miniconda_path}\envs\OffGallery\python.exe` |
| macOS / Linux | `{miniconda_path}/envs/OffGallery/bin/python` |

### Collegamento desktop

| Piattaforma | Metodo |
|---|---|
| Windows | `.lnk` via `winshell` o `win32com` |
| macOS | `.app` bundle in `~/Applications` + `.command` sul Desktop |
| Linux | `.desktop` file in `~/.local/share/applications/` |

### GPU

| Piattaforma | Supporto |
|---|---|
| Windows | NVIDIA CUDA (rilevato via `nvidia-smi`) |
| Linux | NVIDIA CUDA (rilevato via `nvidia-smi`) |
| macOS Apple Silicon | Metal/MPS — incluso in PyTorch standard, nessun overhead |
| macOS Intel | CPU only |

### Ollama — installazione

| Piattaforma | Metodo |
|---|---|
| Windows | Scarica `.exe`, esegui silenzioso |
| macOS | `brew install ollama` oppure script ufficiale |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

### LM Studio — installazione

| Piattaforma | Metodo |
|---|---|
| Windows | Scarica `.exe` installer |
| macOS | Scarica `.dmg` |
| Linux | Scarica `.AppImage` |

### ExifTool (bundled su Windows, da package manager su Linux/macOS)

| Piattaforma | Metodo |
|---|---|
| Windows | Bundled in `exiftool_files/` — nessuna installazione |
| macOS | `brew install exiftool` oppure `.pkg` da exiftool.org |
| Linux Ubuntu/Debian | `sudo apt install libimage-exiftool-perl` |
| Linux Fedora | `sudo dnf install perl-Image-ExifTool` |
| Linux Arch | `sudo pacman -S perl-image-exiftool` |

### Argos Translate — percorso dati

| Piattaforma | Percorso |
|---|---|
| Windows | `%USERPROFILE%\.local\share\argos-translate` |
| macOS | `~/Library/Application Support/argos-translate` |
| Linux | `~/.local/share/argos-translate` |

### PyInstaller — build per piattaforma

L'exe va compilato **sulla piattaforma target** — non è possibile cross-compilare.
- Windows → `OffGallerySetup.exe` (compilato su Windows)
- macOS → `OffGallerySetup.app` o `.dmg` (compilato su macOS)
- Linux → `OffGallerySetup` binary (compilato su Linux)

**Strategia di build: GitHub Actions**
Non serve avere Mac o Linux fisici. Si configura una pipeline CI con tre runner
(windows-latest, macos-latest, ubuntu-latest) che compila automaticamente tutti
e tre gli eseguibili ad ogni push sul branch dell'installer.
File da creare: `.github/workflows/build_installer.yml`

Workflow di sviluppo consigliato:
1. Sviluppa e testa su Windows (macchina disponibile)
2. Quando stabile su Windows, abilita GitHub Actions per le altre piattaforme
3. Per macOS: eventualmente coinvolgere un beta tester Mac per test reali

---

## Note tecniche

### PyTorch — rilevamento GPU e variante
- **NVIDIA (Windows/Linux)**: legge versione driver da `nvidia-smi`, mappa driver → CUDA, installa con index-url corretto:
  - CUDA 11.8: `https://download.pytorch.org/whl/cu118`
  - CUDA 12.1: `https://download.pytorch.org/whl/cu121`
- **AMD su Linux**: rileva tramite `rocminfo`, installa variante ROCm:
  - `https://download.pytorch.org/whl/rocm6.0`
- **AMD su Windows**: ROCm non è supportato su Windows; si usa invece **DirectML** (backend Microsoft via DirectX 12). Richiede che la GPU e i driver supportino DirectX 12. Installa PyTorch CPU standard + `torch-directml` da PyPI.
- **Apple Silicon**: PyTorch standard da PyPI (MPS incluso), nessun index-url separato.
- **Nessuna GPU / fallback**: `https://download.pytorch.org/whl/cpu`

### Download con resume (modelli HuggingFace)
- HTTP Range requests per riprendere download interrotti
- File temporaneo `.part` durante il download
- Rinomina a nome finale solo dopo hash verificato
- HuggingFace fornisce SHA256 nel metadata del file

### Threading
- Ogni operazione lunga gira in thread separato
- UI sempre responsiva durante download e installazioni
- Pulsante "Pausa" per download modelli
- Pulsante "Annulla" con cleanup pulito

### Platform
- **Windows**: priorità assoluta (bat files attuali, utenza principale)
- **Linux / macOS**: architettura compatibile, da implementare in seconda fase

---

## Stato avanzamento

### Completato ✅

- [x] Design e architettura definiti
- [x] `state/state_manager.py` — lettura/scrittura stato con atomic write
- [x] `utils/preflight.py` — check OS, RAM (PowerShell), disco, rete (HTTP port 80), GPU
- [x] `utils/download.py` — download chunked con resume, hash, retry (3 tentativi)
- [x] `utils/logger.py` — log su disco con timestamp, livelli INFO/WARNING/ERROR, riepilogo finale
- [x] `components/miniconda.py` — install/detect, CREATE_NO_WINDOW, TOS accepted
- [x] `components/conda_env.py` — create/verify/repair, pip incluso, fix TOS conda 24+
- [x] `components/core.py` — download GitHub, extract, versioning, update, _PRESERVE_ON_UPDATE
- [x] `components/packages.py` — pip install, cuda detection, pinned versions, no \r nel log
- [x] `components/models.py` — download HF, manifest reale, resume, progress, force re-download
- [x] `components/ollama.py` — install/service/pull model/version
- [x] `components/lmstudio.py` — install/detect/api check
- [x] `ui/progress.py` — ProgressBar singola (spinner + download), DownloadPanel, StepIndicator
- [x] `ui/wizard.py` — 5 pagine, orchestrazione, log su disco, DonePage con riepilogo
- [x] `ui/dashboard.py` — lock anti-doppio-click, Riscarica modelli, Riscarica core
- [x] `ui/__init__.py` — _add_logo() condiviso tra wizard e dashboard
- [x] `installer.py` — unica AppWindow, fix Tcl/Tk, fix SSL (_create_unverified_context)
- [x] `OffGallerySetup.spec` — Tcl/Tk DLL+data, logo bundlato, email hiddenimport
- [x] `assets/logo_header.png` — logo 113x40px per header tkinter
- [x] `build.bat` / `build.sh` — script di build

### Testato su VM Windows pulita ✅

Build PyInstaller funzionante. Test eseguiti il 2026-05-06 su VirtualBox (Windows guest vergine):
- Miniconda scaricato e installato silenziosamente ✅
- Ambiente conda OffGallery creato con pip ✅
- Librerie Python installate (variante CPU) ✅
- Download modelli CLIP verificato con barra progresso ✅
- OffGallery Core scaricato e avviato ✅
- Dashboard operativa con lock anti-concorrenza ✅
- Log installazione scritto su disco ✅

### Problemi noti / da fare

- [x] **Percorso modelli / re-download al primo avvio**: risolto con due fix.
      1. **TreeOfLife path mismatch** (root cause ~2.5 GB ri-scaricati): il manifest
         installer salvava i file in `treeoflife/embeddings/` ma `embedding_generator`
         e `gui_launcher.check_models_cached()` si aspettavano il percorso flat
         `treeoflife/`. Fix in `A_INSTALLER/components/models.py`: `local_name` dei
         file treeoflife ora è flat (senza `embeddings/`). Conseguenza: con i file
         presenti al posto giusto, `check_models_cached()` torna True →
         `HF_HUB_OFFLINE=1` viene settato → nessuna chiamata di rete all'avvio.
      2. **Argos Translate** (vedi sopra): fix separato in `embedding_generator.py`.
- [ ] **Cross-platform**: il codice Python è cross-platform ma lo `.spec` ha percorsi
      Tcl/Tk hardcoded Windows (`C:\Users\HEGOM\anaconda3\...`).
      Per Mac/Linux serve riscrivere la sezione `datas` e `binaries` dello spec
      con i percorsi corretti per quella piattaforma (da fare su macchina target).
- [ ] **⚠️ CLIP = Aesthetic backbone — duplicato da eliminare (~1.6 GB sprecati)**
      Verificato il 2026-05-06: `clip/model.safetensors` e `aesthetic/model.safetensors`
      sono **identici** (1.710.537.716 byte esatti) — stesso backbone ViT-L/14.
      Azioni necessarie su entrambi i lati:
      - **Installer** (`components/models.py`): rimuovere il download separato di
        `aesthetic/model.safetensors`; al suo posto, il componente aesthetic usa i
        file già scaricati in `Models/clip/`.
      - **App** (`embedding_generator.py`, `_init_aesthetic()`): aggiornare il path
        per caricare `model.safetensors` da `Models/clip/` invece di `Models/aesthetic/`.
        I file accessori (tokenizer, config, ecc.) restano in `Models/aesthetic/`.
      Risparmio: ~1.6 GB sull'installazione e download. Da fare prima del rilascio pubblico.
- [ ] **GitHub Actions** per build automatico su tutte le piattaforme (`.github/workflows/build_installer.yml`)
      Da fare quando si vuole supportare Mac/Linux. Non urgente per la fase attuale (Windows-only).
- [ ] **Firma digitale** — Windows SmartScreen avvisa senza firma EV (~80€/anno)
- [x] **DonePage riepilogo dinamico** — `on_enter()` ora svuota e rigenera il frame
      con i risultati reali da `InstallPage._results`: icona ✅/❌ per ogni
      componente, colore verde/rosso. Aggiunti i `_results` mancanti per
      conda_env, Ollama/LM Studio e collegamento desktop. Fallback statico
      se i risultati non sono disponibili.
- [ ] **SHA256 modelli** — aggiungere hash reali nel manifest `models.py` quando disponibili
- [x] **bioclip size_mb** — verificato su disco: 1631 MB (non 2000). Corretti anche
      aesthetic (1710→1631) e la tabella DESIGN.md (totale 8.5→8.1 GB).
      Curiosità: CLIP, Aesthetic e BioCLIP condividono lo stesso backbone ViT-L/14
      (1,710,537,716 byte esatti).
- [x] **Argos Translate path**: risolto in `embedding_generator.py::_init_translator()`.
      Root cause: l'installer scaricava i file raw in `Models/argos-it-en/` ma non chiamava
      `install_from_path()`, quindi `get_installed_packages()` restituiva vuoto e Argos
      riscaricava tutto da HF. Fix: aggiunto step 0 che crea l'`.argosmodel` dai file locali
      e chiama `install_from_path()` prima di toccare la rete.
- [x] **Tooltip dashboard** — ogni riga del Manager (ambienti, modelli AI, LLM)
      mostra un tooltip formattato (ⓘ + hover 500 ms) con descrizione,
      dimensione, e nota "opzionale / installabile anche in seguito" dove
      pertinente. Classe `_Tooltip` e dict `TOOLTIP_TEXT` in `dashboard.py`.
- [x] **UX wizard** — WelcomePage: intro riscritta in linguaggio non tecnico, box
      informativo con tempi/spazio, descrizioni profili con elenco funzionalità reali.
      PathPage: sezione Miniconda rinominata "Gestione librerie software", testo
      spiega cos'è e perché serve, radio button con etichette più chiare, spazio
      aggiornato da "~7 GB" a "~8 GB / 15 GB minimi".
- [ ] **Firma digitale** per eliminare avviso SmartScreen

### Fix applicati durante i test (storia)

| Problema | Fix |
|---|---|
| `no module named 'email'` | Aggiunto `email.*` a hiddenimports spec |
| `init.tcl not found` | Bundle Tcl/Tk DLL+data + env var in installer.py |
| `_center_window not defined` | Spostati helper PRIMA della classe AppWindow |
| SSL certificate verify failed | `ssl._create_unverified_context` nel bundle |
| RAM non rilevata | `wmic` → PowerShell `Get-CimInstance` con CREATE_NO_WINDOW |
| Internet non rilevata | TCP port 53 → port 80 su più host |
| Finestre nere | `CREATE_NO_WINDOW` in tutti i subprocess |
| `\r` nel log pip/conda | `.replace("\r","")` prima di loggare |
| `no module named pip` | Aggiunto `pip` al `conda create` + check+install in `ensure_env` |
| TOS conda 24+ | `CONDA_TOS_ACCEPTED=true` in `_clean_env()` |
| Download simultanei / flickering barre | Lock `_set_busy()` in dashboard |
| Barra progress vuota pip | `update_step_progress()` in DownloadPanel |
| Path doppio `OffGallery\OffGallery` | Fix `_browse()` in PathPage |
