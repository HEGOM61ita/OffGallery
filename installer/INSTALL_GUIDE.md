# Guida Installazione OffGallery

## Requisiti di Sistema

| Componente | Minimo | Consigliato |
|------------|--------|-------------|
| **Sistema Operativo** | Windows 10 64-bit / Linux 64-bit / macOS 12+ | Windows 11 / Ubuntu 22.04+ / macOS 13+ |
| **RAM** | 8 GB | 16 GB |
| **Spazio Disco** | 15 GB | 25 GB |
| **GPU (opzionale)** | - | NVIDIA con 4+ GB VRAM (Windows/Linux) · Apple Silicon M1+ (macOS) |
| **Connessione Internet** | Richiesta solo al primo avvio | - |

> **Nota GPU Windows/Linux**: OffGallery funziona anche senza GPU NVIDIA, ma l'elaborazione sarà più lenta. Puoi scegliere CPU/GPU nelle impostazioni.
>
> **Nota GPU macOS**: Su Apple Silicon (M1/M2/M3/M4) PyTorch usa automaticamente Metal/MPS per l'accelerazione GPU. Su Intel Mac funziona in modalità CPU.
>
> **Nota Linux**: Testato su Ubuntu, Fedora e Arch Linux. Altre distribuzioni con supporto conda dovrebbero funzionare.
>
> **Nota macOS**: Supportato su Apple Silicon (arm64) e Intel (x86_64). Richiede macOS 12 Monterey o successivo.

---

## Passo 0: Scaricare ed Estrarre OffGallery

> **Questo passo è necessario solo se hai scaricato lo ZIP da GitHub.**
> Se hai usato `git clone`, salta direttamente a "Installazione Rapida".

Lo ZIP di GitHub contiene una cartella `OffGallery-main` al suo interno — quella **è** la root dell'applicazione.

**Errore comune:** fare "Estrai tutto" in una cartella già chiamata `OffGallery` crea una doppia cartella:
```
OffGallery\
  OffGallery-main\   ← la vera root (dentro c'è installer\, gui\, ecc.)
```
In questo caso l'installer non trova i file che si aspetta.

**Come estrarre correttamente:**

1. Scegli la **cartella padre** dove vuoi che viva OffGallery — per esempio `C:\Programs\` o `C:\Users\TuoNome\`
2. Apri lo ZIP e clicca **"Estrai tutto"**, impostando come destinazione quella cartella padre
3. Si crea automaticamente `C:\Programs\OffGallery-main\`
4. (Facoltativo) Rinomina la cartella come preferisci, es. `OffGallery`

La cartella che contiene `installer\`, `gui\`, `gui_launcher.py` è la root corretta. Entra lì prima di procedere.

---

## Installazione Rapida (Consigliata)

Il modo piu' semplice per installare OffGallery e' usare il **wizard di installazione**:

### Windows

1. Apri la cartella `installer`
2. **Doppio click** su **`INSTALLA_OffGallery.bat`**
3. Segui le istruzioni a schermo (rispondi S/N alle domande)

### Linux

1. Apri un terminale nella cartella OffGallery
2. Esegui:
   ```bash
   bash installer/install_offgallery.sh
   ```
3. Segui le istruzioni a schermo (rispondi s/n alle domande)

### macOS

1. Apri un **Terminale** nella cartella OffGallery
2. Esegui:
   ```bash
   bash installer/install_offgallery_mac.sh
   ```
3. Segui le istruzioni a schermo (rispondi s/n alle domande)

> **Apple Silicon**: il wizard rileva automaticamente l'architettura (arm64 o x86_64) e scarica la versione corretta di Miniconda.
>
> **Gatekeeper**: al primo avvio di `OffGallery.app` o `OffGallery.command`, macOS potrebbe mostrare un avviso di sicurezza. Usa **tasto destro → Apri** per confermarlo. L'installer rimuove già l'attributo quarantine, quindi l'avviso normalmente non compare.

### Cosa fa il wizard

| | Windows | Linux | macOS |
|---|---------|-------|-------|
| Miniconda | Scarica e installa (default `C:\miniconda3`) | Scarica e installa (`~/miniconda3`) | Scarica e installa (`~/miniconda3`), rileva arm64/x86_64 |
| Ambiente Python | Crea `OffGallery` con Python 3.12 | Crea `OffGallery` con Python 3.12 | Crea `OffGallery` con Python 3.12 |
| Librerie Python | Installa tutto da requirements | Installa tutto da requirements | Installa tutto da requirements |
| ExifTool | Bundled in `exiftool_files/` | Via apt/dnf/pacman/zypper o tar.gz locale | Via Homebrew o tar.gz locale |
| Ollama | Opzionale | Opzionale | Opzionale (via Homebrew o script ufficiale) |
| Collegamento | `OffGallery.lnk` sul Desktop | Voce nel menu applicazioni | `OffGallery.app` in `~/Applications` (Spotlight + Launchpad) + `OffGallery.command` sul Desktop |

**Tempo stimato**: 20-40 minuti. Al primo avvio, OffGallery scarichera' automaticamente ~7 GB di modelli AI. Gli avvii successivi saranno completamente offline.

> **Rieseguibile**: Se il wizard viene interrotto, puoi rieseguirlo. Gli step gia' completati verranno rilevati e saltati automaticamente.

---

## Installazione Manuale (Alternativa)

Se preferisci installare i componenti singolarmente, segui gli step qui sotto.

### Windows - Script separati

| Step | Script | Cosa fa | Tempo |
|------|--------|---------|-------|
| 1 | `01_install_miniconda.bat` | Verifica/installa Miniconda | 5 min |
| 2 | `02_create_env.bat` | Crea ambiente Python | 2 min |
| 3 | `03_install_packages.bat` | Installa librerie Python | 15-20 min |
| 4 | `06_setup_ollama.bat` | Installa LLM locale (opzionale) | 5-10 min |
| - | **Primo avvio app** | Download automatico modelli AI | 10-20 min |

### Linux - Installazione manuale

Se preferisci non usare il wizard `install_offgallery.sh`, puoi eseguire ogni step manualmente:

```bash
# 1. Installa Miniconda (se non presente)
curl -fSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p $HOME/miniconda3
$HOME/miniconda3/bin/conda init bash
# Riapri il terminale dopo questo comando

# 2. Crea ambiente Python
conda create -n OffGallery python=3.12 --override-channels -c conda-forge -y

# 3. Installa librerie Python
conda run -n OffGallery pip install -r installer/requirements_offgallery.txt

# 4. Installa ExifTool
# Ubuntu/Debian:
sudo apt install libimage-exiftool-perl
# Fedora/RHEL:
sudo dnf install perl-Image-ExifTool
# Arch Linux:
sudo pacman -S perl-image-exiftool

# 5. Ollama (opzionale)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-vl:4b-instruct
```

### macOS - Installazione manuale

```bash
# 1. Installa Miniconda (se non presente)
#    Scegli arm64 per Apple Silicon, x86_64 per Intel
# Apple Silicon:
curl -fSL https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh -o /tmp/miniconda.sh
# Intel:
# curl -fSL https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh -o /tmp/miniconda.sh

bash /tmp/miniconda.sh -b -p $HOME/miniconda3
$HOME/miniconda3/bin/conda init zsh    # zsh è la shell default su macOS
$HOME/miniconda3/bin/conda init bash
# Riapri il terminale dopo questo comando

# 2. Crea ambiente Python
conda create -n OffGallery python=3.12 --override-channels -c conda-forge -y

# 3. Installa librerie Python
conda run -n OffGallery pip install -r installer/requirements_offgallery.txt

# 4. Installa ExifTool
brew install exiftool
# Se non hai Homebrew: https://brew.sh — oppure scarica il .pkg da https://exiftool.org

# 5. Ollama (opzionale)
brew install ollama
# oppure: curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-vl:4b-instruct

# 6. Avvia
conda run -n OffGallery python gui_launcher.py
```

### Step 1: Installa Miniconda

#### Cos'è Miniconda?

Miniconda è un programma che permette di installare Python e le librerie necessarie per OffGallery in modo isolato, senza interferire con altri programmi sul tuo computer. È gratuito e sicuro.

#### Verifica se è già installato

1. **Doppio click** su `01_install_miniconda.bat`
2. Si aprirà una finestra nera (terminale)
3. Leggi il messaggio:
   - Se vedi `[OK] Conda già installato` → **Vai allo Step 2**
   - Se vedi `[!!] Conda non trovato` → **Continua a leggere sotto**

#### Se Miniconda NON è installato

##### A) Scarica Miniconda

1. Quando lo script chiede `Vuoi aprire la pagina di download ora? (S/N):`
2. Digita `S` e premi **INVIO**
3. Si aprirà il browser sulla pagina di download
4. Cerca la sezione **Windows** e clicca su **Miniconda3 Windows 64-bit**
5. Attendi il download del file (circa 80 MB)

##### B) Installa Miniconda

1. Vai nella cartella **Download** e fai **doppio click** sul file scaricato
   (il nome sarà simile a `Miniconda3-latest-Windows-x86_64.exe`)

2. Si avvia l'installer. Segui questi passaggi:

   | Schermata | Cosa fare |
   |-----------|-----------|
   | Welcome | Clicca **Next** |
   | License Agreement | Clicca **I Agree** |
   | Select Installation Type | Seleziona **Just Me (recommended)** → Clicca **Next** |
   | Choose Install Location | Lascia il percorso predefinito → Clicca **Next** |
   | **Advanced Options** | **IMPORTANTE - Spunta ENTRAMBE le caselle:** |
   | | **Add Miniconda3 to my PATH environment variable** |
   | | **Register Miniconda3 as my default Python 3.x** |
   | | Poi clicca **Install** |
   | Installing | Attendi il completamento (1-2 minuti) |
   | Completed | Clicca **Next** poi **Finish** |

   > **Attenzione**: Se non spunti "Add to PATH", gli script successivi non funzioneranno!

##### C) Verifica l'installazione

1. **Chiudi** tutte le finestre del terminale aperte
2. Fai **doppio click** di nuovo su `01_install_miniconda.bat`
3. Ora dovresti vedere:
   ```
   [OK] Conda già installato nel sistema
   conda 24.x.x
   ```
4. Se vedi questo messaggio, **Step 1 completato!**

##### Problemi comuni

| Problema | Soluzione |
|----------|-----------|
| Ancora "Conda non trovato" dopo l'installazione | Riavvia il computer e riprova |
| "Add to PATH" era grigio/disabilitato | Disinstalla Miniconda, reinstalla selezionando "Just Me" |
| Errore durante l'installazione | Disabilita temporaneamente l'antivirus |

---

### Step 2: Crea Ambiente OffGallery

1. **Doppio click** su `02_create_env.bat`
2. Attendi il messaggio `[OK] Ambiente "OffGallery" creato con successo!`

---

### Step 3: Installa Pacchetti Python

Questo step scarica circa **3 GB** di librerie.

1. **Doppio click** su `03_install_packages.bat`
2. Attendi 15-20 minuti (dipende dalla connessione)
3. Vedrai `[OK] Tutti i pacchetti installati con successo!`

---

### Step 4: Installa Ollama (Opzionale)

Ollama è necessario solo se vuoi generare **descrizioni e tag automatici** con LLM.
Se non ti interessa questa funzionalità, puoi saltare questo step.

1. **Doppio click** su `06_setup_ollama.bat`
2. Se Ollama non è installato:
   - Premi `S` per aprire la pagina di download
   - Scarica e installa **Ollama for Windows**
   - Riesegui lo script
3. Premi `S` per scaricare il modello `qwen3-vl:4b-instruct` (~3.3 GB)

---

## Avviare OffGallery

### Windows

**Metodo 1 - Doppio Click (Consigliato):**

Nella cartella `installer` trovi il file `OffGallery_Launcher.bat`:

1. **Copia** `OffGallery_Launcher.bat` sul **Desktop**
2. **Doppio click** per avviare l'app

**Metodo 2 - Da Terminale:**

1. Apri il **Prompt Anaconda**
2. Digita:
   ```
   conda activate OffGallery
   cd C:\percorso\di\OffGallery
   python gui_launcher.py
   ```

### Linux

**Metodo 1 - Menu applicazioni (Consigliato):**

Se hai usato il wizard, OffGallery appare nel menu applicazioni. Cercalo per nome.

**Metodo 2 - Da terminale:**

```bash
bash installer/offgallery_launcher.sh
```

**Metodo 3 - Manuale:**

```bash
conda activate OffGallery
cd ~/percorso/di/OffGallery
python gui_launcher.py
```

### macOS

**Metodo 1 - Spotlight / Launchpad (Consigliato):**

Se hai usato il wizard, `OffGallery.app` viene installata in `~/Applications` ed è immediatamente cercabile:
- **Spotlight**: `Cmd+Space` → digita *OffGallery* → Invio
- **Launchpad**: cerca *OffGallery* tra le app
- **Dock**: trascina `OffGallery.app` dalla cartella `~/Applications`

**Metodo 2 - Doppio click sul Desktop:**

Il wizard crea anche `OffGallery.command` sul Desktop come scorciatoia rapida.

> Al primo avvio macOS potrebbe chiedere conferma. Usa **tasto destro → Apri**.

**Metodo 2 - Da terminale:**

```bash
bash installer/offgallery_launcher_mac.sh
```

**Metodo 3 - Manuale:**

```bash
conda activate OffGallery
cd ~/percorso/di/OffGallery
python gui_launcher.py
```

---

## Primo Avvio

Al **primo avvio**, OffGallery scarica automaticamente i modelli AI necessari:

| Modello | Uso | Dimensione |
|---------|-----|------------|
| **CLIP** | Ricerca semantica | ~580 MB |
| **DINOv2** | Similarità visiva | ~330 MB |
| **Aesthetic** | Valutazione estetica | ~1.6 GB |
| **BioCLIP v2 + TreeOfLife** | Classificazione flora/fauna | ~4.2 GB |
| **Argos Translate** | Traduzione IT→EN | ~92 MB |

**Tempo stimato**: 10-20 minuti (dipende dalla connessione)

I modelli vengono scaricati dal repository congelato `HEGOM/OffGallery-models` e salvati nella cartella **`OffGallery/Models/`** (non nella cache di sistema). Gli avvii successivi saranno **completamente offline**.

> Se il download viene interrotto, riavvia l'app: i modelli già scaricati non vengono riscaricati.

---

## Risoluzione Problemi

### "conda non è riconosciuto come comando"
- **Windows**: Riavvia il terminale dopo aver installato Miniconda. Verifica che "Add to PATH" sia stato selezionato durante l'installazione
- **Linux**: Esegui `~/miniconda3/bin/conda init bash` e riapri il terminale
- **macOS**: Esegui `~/miniconda3/bin/conda init zsh` (o `init bash`) e riapri il terminale

### "CUDA not available" / Elaborazione lenta
- Normale se non hai una GPU NVIDIA
- Vai in **Impostazioni > Device** e seleziona "CPU"

### Download modelli fallisce al primo avvio
- Verifica la connessione internet
- Riavvia l'app (i modelli già scaricati non vengono riscaricati)
- In alternativa, usa `python gui_launcher.py --download-models` per forzare il download

### Ollama non risponde
- **Windows**: Assicurati che Ollama sia in esecuzione (icona nella system tray). Riavvia Ollama
- **Linux**: Verifica con `systemctl status ollama` oppure avvia con `ollama serve`
- **macOS**: Avvia Ollama dall'app o esegui `ollama serve` dal terminale

### Linux: ExifTool non trovato
- Installa tramite il gestore pacchetti del sistema:
  - Ubuntu/Debian: `sudo apt install libimage-exiftool-perl`
  - Fedora: `sudo dnf install perl-Image-ExifTool`
  - Arch: `sudo pacman -S perl-image-exiftool`

### Linux: l'app non si avvia dal menu applicazioni
- Prova da terminale: `bash installer/offgallery_launcher.sh`
- Verifica che conda sia inizializzato: `conda --version`

### macOS: ExifTool non trovato
- Installa tramite Homebrew: `brew install exiftool`
- Oppure scarica il `.pkg` da [exiftool.org](https://exiftool.org)

### macOS: avviso "non può essere aperto" (Gatekeeper)
- Usa **tasto destro → Apri** su `OffGallery.app` o `OffGallery.command`
- Oppure da terminale:
  ```bash
  xattr -cr ~/Applications/OffGallery.app
  xattr -c ~/Desktop/OffGallery.command
  ```

### macOS: PyQt6 non si avvia / finestra nera
- Verifica che Xcode Command Line Tools siano installati: `xcode-select --install`
- Se su macOS 11+, assicurati che `QT_MAC_WANTS_LAYER=1` sia impostato (il launcher lo fa automaticamente)

---

## Spazio Disco Utilizzato

### Windows

| Componente | Posizione | Dimensione |
|------------|-----------|------------|
| Miniconda | `C:\miniconda3` (default wizard) | ~400 MB |
| Ambiente OffGallery | `C:\miniconda3\envs\OffGallery` | ~6 GB |
| **Modelli AI** | **`OffGallery\Models\`** | **~6.7 GB** |
| Argos Translate | `%USERPROFILE%\.local\share\argos-translate` | ~92 MB |
| Ollama + modello | `%LOCALAPPDATA%\Ollama` | ~3.5 GB |
| **Totale** | | **~17 GB** |

### Linux

| Componente | Posizione | Dimensione |
|------------|-----------|------------|
| Miniconda | `~/miniconda3` | ~400 MB |
| Ambiente OffGallery | `~/miniconda3/envs/OffGallery` | ~6 GB |
| **Modelli AI** | **`OffGallery/Models/`** | **~6.7 GB** |
| Argos Translate | `~/.local/share/argos-translate` | ~92 MB |
| Ollama + modello | `~/.ollama` | ~3.5 GB |
| **Totale** | | **~17 GB** |

### macOS

| Componente | Posizione | Dimensione |
|------------|-----------|------------|
| Miniconda | `~/miniconda3` | ~400 MB |
| Ambiente OffGallery | `~/miniconda3/envs/OffGallery` | ~6 GB |
| **Modelli AI** | **`OffGallery/Models/`** | **~6.7 GB** |
| Argos Translate | `~/Library/Application Support/argos-translate` | ~92 MB |
| Ollama + modello | `~/.ollama` | ~3.5 GB |
| **Totale** | | **~17 GB** |

---

## Spostare i Modelli AI su un Altro Disco

Se il disco principale non ha spazio sufficiente, puoi spostare la cartella `Models/` su un altro disco dopo l'installazione.

1. **Sposta la cartella** `OffGallery/Models/` nella destinazione desiderata (es. `E:\MyModels\OffGallery`)
2. **Avvia OffGallery** e vai nel tab **Configurazione**
3. Nella sezione **Percorsi & Database**, campo **Modelli AI**, inserisci il percorso assoluto della nuova posizione (es. `E:\MyModels\OffGallery`)
4. Clicca **Salva**
5. Riavvia l'app

> **Attenzione**: modifica il percorso solo dopo aver spostato fisicamente la cartella. Se il percorso non esiste, OffGallery considererà i modelli mancanti e tenterà di riscaricарli.

---

## Supporto

Per problemi o domande, consulta la [documentazione](../README.md) o apri una issue su GitHub.
