# OffGallery Manager — Design Document Linux

> Documento specifico per il porting Linux dell'installer.
> Il documento principale per l'architettura generale è `A_INSTALLER/DESIGN.md`.
> **Questa directory NON va mai pushata su repo pubblica o beta.**

---

## Origine

`B_INSTALLER/` è il porting Linux di `A_INSTALLER/`.
Il codice Python di A_INSTALLER era già in larga parte cross-platform;
le modifiche rispetto alla versione Windows sono documentate qui.

**Regola assoluta: non modificare mai A_INSTALLER per adattarlo a Linux.**
Le due directory sono indipendenti.

---

## Differenze rispetto ad A_INSTALLER (Windows)

### File identici — copiati senza modifiche

| File | Motivo |
|------|--------|
| `utils/download.py` | Puro urllib, nessuna dipendenza OS |
| `utils/logger.py` | Puro stdlib |
| `utils/preflight.py` | Già gestisce Linux (RAM da /proc/meminfo, rocminfo, ecc.) |
| `state/state_manager.py` | Puro stdlib, scrittura atomica con os.replace() |
| `components/miniconda.py` | Già supporta Linux x86_64/aarch64 con .sh installer |
| `components/conda_env.py` | Già cross-platform (path /bin/conda su Linux) |
| `components/core.py` | Puro Python/zipfile, nessuna dipendenza OS |
| `components/packages.py` | Già gestisce ROCm/CUDA/CPU; CREATE_NO_WINDOW=0 su Linux |
| `components/models.py` | Puro download urllib |
| `components/ollama.py` | _install_linux() già implementato (script ufficiale) |
| `components/lmstudio.py` | _install_linux() già implementato (AppImage in ~/.local/bin/) |
| `ui/progress.py` | Widget tkinter puri, nessuna dipendenza OS |
| `requirements_offgallery.txt` | Identico |

### File modificati

| File | Modifiche |
|------|-----------|
| `installer.py` | Fix Tcl/Tk per Linux nel bundle PyInstaller (cerca tcl8.6/tk8.6 in `_MEIPASS`). Rimosso il fix specifico Windows (TCL_LIBRARY su percorso Windows). |
| `ui/__init__.py` | Font di fallback `sans-serif` invece di `Segoe UI` nel logo testuale. |
| `ui/wizard.py` | Font cross-platform (`sans-serif`/`monospace` invece di `Segoe UI`/`Consolas`). Aggiunta fase ExifTool come primo step dell'installazione. `_shortcut_linux()` scrive il `.desktop` sia in `~/.local/share/applications/` che in `~/Desktop/`. `_update_disk_label()` usa il mount point `/` come fallback invece della drive letter Windows. |
| `ui/dashboard.py` | Font cross-platform. Aggiunta sezione SISTEMA con riga ExifTool. Tooltip Ollama/LM Studio aggiornati con note Linux-specifiche. |

### File nuovi

| File | Descrizione |
|------|-------------|
| `components/exiftool_linux.py` | Installazione ExifTool tramite apt/dnf/pacman/zypper via sudo. Rilevamento automatico del package manager. |
| `OffGallerySetup_linux.spec` | Spec PyInstaller per Linux: ricerca Tcl/Tk in CONDA_PREFIX/lib e /usr/lib. Nessuna sezione binaries (non servono DLL). |
| `build_linux.sh` | Script di build: attiva conda, verifica pyinstaller, lancia lo spec. |
| `DESIGN_LINUX.md` | Questo file. |

---

## Criticità Linux risolte

### 1. Font `Segoe UI`
**Problema**: Segoe UI non è disponibile su Linux, tkinter usa un fallback generico.
**Soluzione scelta**: `sans-serif` e `monospace` — tkinter li mappa automaticamente
al font di sistema (Liberation Sans, DejaVu Sans, ecc. a seconda della distro).
Non viene specificato un font esplicito per evitare dipendenze da pacchetti font.

### 2. ExifTool bundled vs. system
**Problema**: Su Windows `exiftool_files/` è bundled con l'app.
Su Linux ExifTool è un pacchetto di sistema (`libimage-exiftool-perl` / `perl-Image-ExifTool`).
**Soluzione**: Nuovo step nell'installer che rileva il package manager (`apt-get`,
`dnf`, `yum`, `pacman`, `zypper`) e installa il pacchetto corretto via `sudo`.
La password sudo viene gestita dal sistema operativo (PAM/keyring), non dall'installer.
Se l'installazione fallisce, l'utente riceve le istruzioni manuali e può procedere
comunque (ExifTool è necessario per leggere EXIF ma non blocca l'avvio dell'app).

### 3. Fix Tcl/Tk nel bundle PyInstaller
**Problema**: Su Windows le DLL Tcl/Tk vanno bundlate esplicitamente.
Su Linux sono condivise (.so) e tkinter le trova tramite `LD_LIBRARY_PATH`.
Nel bundle PyInstaller i dati (directory tcl8.6/tk8.6) vanno bundlati
perché il bundle ha il suo `sys._MEIPASS` isolato.
**Soluzione**: `installer.py` setta `TCL_LIBRARY`/`TK_LIBRARY` cercando
le directory `tcl8.6`/`tk8.6` dentro `sys._MEIPASS`. Lo `.spec` le include
cercandole in `CONDA_PREFIX/lib` e nei percorsi di sistema standard.

### 4. Desktop shortcut
**Problema**: Su Windows il `.lnk` va sul Desktop. Su Linux il meccanismo
è il file `.desktop` XDG.
**Soluzione**: `_shortcut_linux()` crea il `.desktop` in due posti:
- `~/.local/share/applications/offgallery.desktop` — menu di sistema (launcher, Gnome, KDE)
- `~/Desktop/OffGallery.desktop` — icona sul Desktop (se la cartella esiste)

### 5. `CREATE_NO_WINDOW`
**Non è un problema**: tutti i moduli usano il pattern
`subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0`
che ritorna 0 su Linux. I processi figli non aprono finestre nere su Linux.

---

## Build

### Prerequisiti

```bash
conda activate OffGallery   # o qualsiasi env con Python 3.12 + tkinter
pip install pyinstaller
# Opzionale per compressione:
sudo apt-get install upx-ucl
```

### Comando di build

```bash
cd B_INSTALLER/
bash build_linux.sh
```

Output: `B_INSTALLER/dist/OffGallerySetup` (binary ELF auto-contenuto)

### Test rapido

```bash
./dist/OffGallerySetup
```

### Dimensione attesa

~40–55 MB (dipende da Tcl/Tk bundlato e UPX).

---

## Distribuzione

Il binary è auto-contenuto ma richiede le seguenti librerie di sistema
(presenti su tutte le distro moderne):

- `libGL.so.1` (OpenGL — per tkinter su alcune distro)
- `libX11.so.6` (display X11)
- `libpthread.so.0` (threading)
- GTK/GLib (su Wayland tramite XWayland)

Per una distribuzione universale (distro agnosttica):
- **AppImage** — da considerare quando il progetto è maturo
- **Flatpak** — alternativa per distribuzione via Flathub

---

## Stato avanzamento

### Completato ✅

- [x] Analisi criticità cross-platform rispetto ad A_INSTALLER
- [x] `installer.py` — fix Tcl/Tk Linux nel bundle
- [x] `ui/__init__.py` — font fallback
- [x] `ui/wizard.py` — font cross-platform, ExifTool step, shortcut dual (menu + Desktop)
- [x] `ui/dashboard.py` — font cross-platform, sezione ExifTool
- [x] `components/exiftool_linux.py` — installazione via apt/dnf/pacman/zypper
- [x] `OffGallerySetup_linux.spec` — Tcl/Tk Linux, no DLL Windows
- [x] `build_linux.sh` — script di build
- [x] Tutti i moduli cross-platform copiati da A_INSTALLER

### Da fare

- [ ] **Test build su WSL2** — eseguire `bash build_linux.sh` e verificare che il binary si avvii
- [ ] **Test installazione su VM Linux pulita** — Ubuntu 22.04 LTS o Fedora 40
- [ ] **Verifica ExifTool sudo** — testare che la richiesta password sudo funzioni nella UI
- [ ] **Verifica shortcut .desktop** — testare che appaia nel launcher Gnome/KDE e sul Desktop
- [ ] **Dimensione binary** — verificare che UPX comprimia correttamente
- [ ] **AppImage** — da considerare per distribuzione universale (futura fase)
- [ ] **GitHub Actions** — `.github/workflows/build_linux.yml` per build automatica su ubuntu-latest
