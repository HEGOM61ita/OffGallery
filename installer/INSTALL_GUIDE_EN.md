# OffGallery Installation Guide

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **Operating System** | Windows 10 64-bit / Linux 64-bit / macOS 12+ | Windows 11 / Ubuntu 22.04+ / macOS 13+ |
| **RAM** | 8 GB | 16 GB |
| **Disk Space** | 15 GB | 25 GB |
| **GPU (optional)** | — | NVIDIA with 4+ GB VRAM (Windows/Linux) · Apple Silicon M1+ (macOS) |
| **Internet** | Required on first launch only | — |

> **GPU note — Windows/Linux**: OffGallery works without an NVIDIA GPU, but processing will be slower.
>
> **GPU note — macOS**: On Apple Silicon (M1/M2/M3/M4) PyTorch automatically uses Metal/MPS for GPU acceleration. On Intel Macs it runs in CPU mode.
>
> **Linux note**: Tested on Ubuntu, Fedora and Arch Linux. Other distributions with conda support should work.
>
> **macOS note**: Supported on Apple Silicon (arm64) and Intel (x86_64). Requires macOS 12 Monterey or later.

---

## Step 0: Download and Extract OffGallery

> **This step is only needed if you downloaded the ZIP from GitHub.**
> If you used `git clone`, skip directly to "Quick Installation".

The GitHub ZIP contains an `OffGallery-main` folder inside it — that folder **is** the application root.

**Common mistake:** clicking "Extract all" into a folder already named `OffGallery` creates a double folder:
```
OffGallery\
  OffGallery-main\   ← the real root (contains installer\, gui\, etc.)
```
In this case the installer will not find the files it expects.

**How to extract correctly:**

1. Choose the **parent folder** where you want OffGallery to live — e.g. `C:\Programs\` or `C:\Users\YourName\`
2. Open the ZIP and click **"Extract all"**, setting that parent folder as the destination
3. `C:\Programs\OffGallery-main\` is created automatically
4. (Optional) Rename the folder as you like, e.g. `OffGallery`

The folder that contains `installer\`, `gui\`, `gui_launcher.py` is the correct root. Navigate there before continuing.

---

## Quick Installation (Recommended)

The easiest way to install OffGallery is the **installation wizard**:

### Windows

1. Open the `installer` folder
2. **Double-click** **`INSTALLA_OffGallery.bat`**
3. Follow the on-screen instructions (answer Y/N to the prompts)

### Linux

1. Open a terminal in the OffGallery folder
2. Run:
   ```bash
   bash installer/install_offgallery_linux_en.sh
   ```
3. Follow the on-screen instructions

### macOS

1. Open a **Terminal** in the OffGallery folder
2. Run:
   ```bash
   bash installer/install_offgallery_mac_en.sh
   ```
3. Follow the on-screen instructions

> **Apple Silicon**: the wizard automatically detects your architecture (arm64 or x86_64) and downloads the correct version of Miniconda.
>
> **Gatekeeper**: on first launch of `OffGallery.app` or `OffGallery.command`, macOS may show a security warning. Use **right-click → Open** to confirm. The installer already removes the quarantine attribute, so the warning normally does not appear.

### What the wizard does

| | Windows | Linux | macOS |
|---|---------|-------|-------|
| Miniconda | Downloads and installs (default `C:\miniconda3`) | Downloads and installs (`~/miniconda3`) | Downloads and installs (`~/miniconda3`), detects arm64/x86_64 |
| Python environment | Creates `OffGallery` with Python 3.12 | Creates `OffGallery` with Python 3.12 | Creates `OffGallery` with Python 3.12 |
| Python libraries | Installs everything from requirements | Installs everything from requirements | Installs everything from requirements |
| ExifTool | Bundled in `exiftool_files/` | Via apt/dnf/pacman/zypper or local tar.gz | Via Homebrew or local tar.gz |
| Ollama | Optional | Optional | Optional (via Homebrew or official script) |
| Shortcut | `OffGallery.lnk` on Desktop | Application menu entry | `OffGallery.app` in `~/Applications` (Spotlight + Launchpad) + `OffGallery.command` on Desktop |

**Estimated time**: 20–40 minutes. On first launch, OffGallery will automatically download ~6.7 GB of AI models. All subsequent launches are completely offline.

> **Re-runnable**: If the wizard is interrupted, you can run it again. Steps already completed are detected and skipped.

---

## Manual Installation (Alternative)

If you prefer to install components individually, follow the steps below.

### Windows — Separate scripts

| Step | Script | What it does | Time |
|------|--------|--------------|------|
| 1 | `01_install_miniconda.bat` | Verify/install Miniconda | 5 min |
| 2 | `02_create_env.bat` | Create Python environment | 2 min |
| 3 | `03_install_packages.bat` | Install Python libraries | 15–20 min |
| 4 | `06_setup_ollama.bat` | Install local LLM (optional) | 5–10 min |
| — | **First app launch** | Automatic AI model download | 10–20 min |

### Linux — Manual installation

If you prefer not to use the `install_offgallery_linux_en.sh` wizard:

```bash
# 1. Install Miniconda (if not already present)
curl -fSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p $HOME/miniconda3
$HOME/miniconda3/bin/conda init bash
# Reopen the terminal after this command

# 2. Create Python environment
conda create -n OffGallery python=3.12 --override-channels -c conda-forge -y

# 3. Install Python libraries
conda run -n OffGallery pip install -r installer/requirements_offgallery.txt

# 4. Install ExifTool
# Ubuntu/Debian:
sudo apt install libimage-exiftool-perl
# Fedora/RHEL:
sudo dnf install perl-Image-ExifTool
# Arch Linux:
sudo pacman -S perl-image-exiftool

# 5. Ollama (optional)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-vl:8b-instruct-q4_K_M
```

### macOS — Manual installation

```bash
# 1. Install Miniconda (if not already present)
#    Choose arm64 for Apple Silicon, x86_64 for Intel
# Apple Silicon:
curl -fSL https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh -o /tmp/miniconda.sh
# Intel:
# curl -fSL https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh -o /tmp/miniconda.sh

bash /tmp/miniconda.sh -b -p $HOME/miniconda3
$HOME/miniconda3/bin/conda init zsh    # zsh is the default shell on macOS
$HOME/miniconda3/bin/conda init bash
# Reopen the terminal after this command

# 2. Create Python environment
conda create -n OffGallery python=3.12 --override-channels -c conda-forge -y

# 3. Install Python libraries
conda run -n OffGallery pip install -r installer/requirements_offgallery.txt

# 4. Install ExifTool
brew install exiftool
# If you don't have Homebrew: https://brew.sh — or download the .pkg from https://exiftool.org

# 5. Ollama (optional)
brew install ollama
# or: curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-vl:8b-instruct-q4_K_M

# 6. Launch
conda run -n OffGallery python gui_launcher.py
```

### Step 1: Install Miniconda

#### What is Miniconda?

Miniconda is a program that lets you install Python and the libraries required by OffGallery in an isolated environment, without interfering with other software on your computer. It is free and safe.

#### Check if it is already installed

1. **Double-click** `01_install_miniconda.bat`
2. A black window (terminal) will open
3. Read the message:
   - If you see `[OK] Conda already installed` → **Go to Step 2**
   - If you see `[!!] Conda not found` → **Continue reading below**

#### If Miniconda is NOT installed

##### A) Download Miniconda

1. When the script asks `Do you want to open the download page now? (Y/N):`
2. Type `Y` and press **ENTER**
3. The browser will open on the download page
4. Find the **Windows** section and click **Miniconda3 Windows 64-bit**
5. Wait for the download (~80 MB)

##### B) Install Miniconda

1. Go to the **Downloads** folder and **double-click** the downloaded file
   (the name will be similar to `Miniconda3-latest-Windows-x86_64.exe`)

2. The installer starts. Follow these steps:

   | Screen | What to do |
   |--------|-----------|
   | Welcome | Click **Next** |
   | License Agreement | Click **I Agree** |
   | Select Installation Type | Select **Just Me (recommended)** → Click **Next** |
   | Choose Install Location | Leave the default path → Click **Next** |
   | **Advanced Options** | **IMPORTANT — Check BOTH boxes:** |
   | | **Add Miniconda3 to my PATH environment variable** |
   | | **Register Miniconda3 as my default Python 3.x** |
   | | Then click **Install** |
   | Installing | Wait for completion (1–2 minutes) |
   | Completed | Click **Next** then **Finish** |

   > **Warning**: If you do not check "Add to PATH", the subsequent scripts will not work!

##### C) Verify the installation

1. **Close** all open terminal windows
2. **Double-click** `01_install_miniconda.bat` again
3. You should now see:
   ```
   [OK] Conda already installed
   conda 24.x.x
   ```
4. If you see this message, **Step 1 complete!**

##### Common issues

| Issue | Solution |
|-------|---------|
| Still "Conda not found" after installation | Restart the computer and try again |
| "Add to PATH" was greyed out / disabled | Uninstall Miniconda, reinstall selecting "Just Me" |
| Error during installation | Temporarily disable your antivirus |

---

### Step 2: Create OffGallery Environment

1. **Double-click** `02_create_env.bat`
2. Wait for the message `[OK] "OffGallery" environment created successfully!`

---

### Step 3: Install Python Packages

This step downloads approximately **3 GB** of libraries.

1. **Double-click** `03_install_packages.bat`
2. Wait 15–20 minutes (depends on your connection)
3. You will see `[OK] All packages installed successfully!`

---

### Step 4: Install Ollama (Optional)

> **Ollama is completely optional.** OffGallery works fully without it for semantic search (CLIP), BioCLIP taxonomy, aesthetic/technical scoring, EXIF metadata and geo-enrichment. Install Ollama only if you want to generate **automatic descriptions, tags and titles** with an LLM.

**If the one-click installer fails on this step**, do not worry: finish the main installation anyway, then install Ollama separately with `06_setup_ollama.bat` whenever you like — you will have more control over the process.

**Low-RAM or slow PC?** Consider skipping Ollama altogether: OffGallery without LLM is still a complete tool for semantic indexing and visual-similarity search.

1. **Double-click** `06_setup_ollama.bat`
2. If Ollama is not installed:
   - Press `Y` to open the download page
   - Download and install **Ollama for Windows**
   - Re-run the script
3. Press `Y` to download the `qwen3-vl:8b-instruct-q4_K_M` model (~5.2 GB, requires 8 GB VRAM)

**Note:** Ollama installs independently (`%LOCALAPPDATA%\Programs\Ollama`) and stores models in `%USERPROFILE%\.ollama\models`. It does not depend on any OffGallery directories — you can install or remove it at any time without affecting the rest of the installation.

---

## Pinned Library Versions (Critical)

OffGallery requires specific versions of some libraries to guarantee compatibility with the CLIP ViT-L/14 model. If you experience issues with semantic search (scores always near zero) or see shape mismatch errors, run:

```bash
conda run -n OffGallery pip install transformers==4.57.3 huggingface-hub==0.36.0 open-clip-torch==3.2.0
```

Then reimport the affected photos (re-run Processing on the same folder).

> The wizard already installs the correct pinned versions. This step is only needed if you have manually updated these packages.

---

## Launching OffGallery

### Windows

**Method 1 — Double-click (Recommended):**

In the `installer` folder you will find `OffGallery_Launcher_EN.bat`:

1. **Copy** `OffGallery_Launcher_EN.bat` to the **Desktop**
2. **Double-click** to launch the app

**Method 2 — From terminal:**

1. Open the **Anaconda Prompt**
2. Type:
   ```
   conda activate OffGallery
   cd C:\path\to\OffGallery
   python gui_launcher.py
   ```

### Linux

**Method 1 — Application menu (Recommended):**

If you used the wizard, OffGallery appears in the application menu. Search for it by name.

**Method 2 — From terminal:**

```bash
bash installer/offgallery_launcher_linux_en.sh
```

**Method 3 — Manual:**

```bash
conda activate OffGallery
cd ~/path/to/OffGallery
python gui_launcher.py
```

### macOS

**Method 1 — Spotlight / Launchpad (Recommended):**

If you used the wizard, `OffGallery.app` is installed in `~/Applications` and is immediately searchable:
- **Spotlight**: `Cmd+Space` → type *OffGallery* → Enter
- **Launchpad**: search for *OffGallery* among apps
- **Dock**: drag `OffGallery.app` from `~/Applications`

**Method 2 — Double-click on Desktop:**

The wizard also creates `OffGallery.command` on the Desktop as a quick shortcut.

> On first launch macOS may ask for confirmation. Use **right-click → Open**.

**Method 3 — From terminal:**

```bash
bash installer/offgallery_launcher_mac_en.sh
```

---

## First Launch

On **first launch**, OffGallery automatically downloads the required AI models:

| Model | Use | Size |
|-------|-----|------|
| **CLIP** | Semantic search | ~580 MB |
| **DINOv2** | Visual similarity | ~330 MB |
| **Aesthetic** | Aesthetic scoring | ~1.6 GB |
| **BioCLIP v2 + TreeOfLife** | Flora/fauna classification | ~4.2 GB |
| **Argos Translate** | Query translation | ~92 MB |

**Estimated time**: 10–20 minutes (depends on your connection)

Models are downloaded from the frozen repository `HEGOM/OffGallery-models` and saved in the **`OffGallery/Models/`** folder (not in the system cache). All subsequent launches are **completely offline**.

> If the download is interrupted, restart the app: already-downloaded models are not re-downloaded.

---

## Saved Searches

The **Search** tab lets you save and recall complete search configurations, so you do not have to re-enter frequently used filters and parameters (e.g. "birds Sardinia, 4+ stars").

### Save a search

1. Configure the search normally: query, mode (semantic/tag), threshold, all EXIF, score, date filters, etc.
2. Click **💾 Save search** (below the RESET button).
3. Enter a descriptive name and confirm.
   - If the name already exists, you will be asked whether to overwrite or choose a different name.

### Recall a search

1. Click **📋 Saved searches**.
2. Select the desired entry from the list (shows name and creation date).
3. Click **Load** or double-click — all parameters are restored instantly.

> Searches are saved in `database/saved_searches.json` in the project folder. This file can be copied alongside the database to bring your saved searches to another machine.

---

## Troubleshooting

### "conda is not recognised as a command"
- **Windows**: Restart the terminal after installing Miniconda. Verify that "Add to PATH" was selected during installation
- **Linux**: Run `~/miniconda3/bin/conda init bash` and reopen the terminal
- **macOS**: Run `~/miniconda3/bin/conda init zsh` (or `init bash`) and reopen the terminal

### "CUDA not available" / Slow processing
- Normal if you do not have an NVIDIA GPU
- Go to **Settings > Device** and select "CPU"

### Model download fails on first launch
- Check your internet connection
- Restart the app (already-downloaded models are not re-downloaded)
- Alternatively, use `python gui_launcher.py --download-models` to force the download

### Ollama installation fails during the wizard
If the one-click installer fails on the Ollama step (network errors, timeouts, etc.):
1. **Dismiss the error and complete the installation** — OffGallery works without Ollama
2. When you want to add LLM support, run `06_setup_ollama.bat` manually: you will have more control and can choose the right moment

### Ollama not responding
- **Windows**: Make sure Ollama is running (icon in the system tray). Restart Ollama
- **Linux**: Check with `systemctl status ollama` or start with `ollama serve`
- **macOS**: Launch Ollama from the app or run `ollama serve` from the terminal
- **No Ollama installed?** No problem — semantic search and all other AI models work normally. Tag/description/title generation will simply be unavailable.

### Linux: ExifTool not found
- Install via the system package manager:
  - Ubuntu/Debian: `sudo apt install libimage-exiftool-perl`
  - Fedora: `sudo dnf install perl-Image-ExifTool`
  - Arch: `sudo pacman -S perl-image-exiftool`

### Linux: app does not launch from the application menu
- Try from terminal: `bash installer/offgallery_launcher_linux_en.sh`
- Check that conda is initialised: `conda --version`

### macOS: ExifTool not found
- Install via Homebrew: `brew install exiftool`
- Or download the `.pkg` from [exiftool.org](https://exiftool.org)

### macOS: "cannot be opened" warning (Gatekeeper)
- Use **right-click → Open** on `OffGallery.app` or `OffGallery.command`
- Or from terminal:
  ```bash
  xattr -cr ~/Applications/OffGallery.app
  xattr -c ~/Desktop/OffGallery.command
  ```

### macOS: PyQt6 does not start / black window
- Check that Xcode Command Line Tools are installed: `xcode-select --install`
- On macOS 11+, ensure `QT_MAC_WANTS_LAYER=1` is set (the launcher does this automatically)

### Semantic search scores always near zero
- Embeddings were likely generated with an incompatible library version
- Run: `conda run -n OffGallery pip install transformers==4.57.3 huggingface-hub==0.36.0 open-clip-torch==3.2.0`
- Then reprocess the affected photos with "Reprocess all" in the Processing tab

### Wrong geotagging (incorrect city for GPS coordinates)
- This was a bug in versions prior to 10 Mar 2026 affecting photos taken West or South of the Greenwich meridian
- Reprocess the affected photos after updating to the current version

---

## Disk Space Used

> **GPU note**: the Python environment size differs significantly depending on the GPU.
> PyTorch CPU is ~700 MB; PyTorch CUDA 11.8 is ~2.2 GB + ~1 GB of CUDA runtime libraries.

### Windows

| Component | Location | CPU only | NVIDIA GPU (CUDA) |
|-----------|----------|----------|-------------------|
| Miniconda base | `C:\miniconda3` | ~400 MB | ~400 MB |
| OffGallery environment | `C:\miniconda3\envs\OffGallery` | ~3.5 GB | ~7 GB |
| **AI Models** | **`OffGallery\Models\`** | **~6.7 GB** | **~6.7 GB** |
| Argos Translate | `%USERPROFILE%\.local\share\argos-translate` | ~92 MB | ~92 MB |
| Ollama + model | `%LOCALAPPDATA%\Ollama` | ~3.5 GB | ~3.5 GB |
| **Total** | | **~14 GB** | **~18 GB** |

### Linux

| Component | Location | CPU only | NVIDIA GPU (CUDA) |
|-----------|----------|----------|-------------------|
| Miniconda base | `~/miniconda3` | ~400 MB | ~400 MB |
| OffGallery environment | `~/miniconda3/envs/OffGallery` | ~3.5 GB | ~7 GB |
| **AI Models** | **`OffGallery/Models/`** | **~6.7 GB** | **~6.7 GB** |
| Argos Translate | `~/.local/share/argos-translate` | ~92 MB | ~92 MB |
| Ollama + model | `~/.ollama` | ~3.5 GB | ~3.5 GB |
| **Total** | | **~14 GB** | **~18 GB** |

### macOS

> CUDA is not available on macOS. Apple Silicon uses Metal/MPS (included in standard PyTorch, no additional overhead).

| Component | Location | Size |
|-----------|----------|------|
| Miniconda base | `~/miniconda3` | ~400 MB |
| OffGallery environment | `~/miniconda3/envs/OffGallery` | ~3.5 GB |
| **AI Models** | **`OffGallery/Models/`** | **~6.7 GB** |
| Argos Translate | `~/Library/Application Support/argos-translate` | ~92 MB |
| Ollama + model | `~/.ollama` | ~3.5 GB |
| **Total** | | **~14 GB** |

---

## Moving AI Models to Another Disk

If your main disk does not have enough space, you can move the `Models/` folder to another disk after installation.

1. **Move** the `OffGallery/Models/` folder to the desired destination (e.g. `E:\MyModels\OffGallery`)
2. **Launch OffGallery** and go to the **Configuration** tab
3. In the **Paths & Database** section, **AI Models** field, enter the absolute path of the new location (e.g. `E:\MyModels\OffGallery`)
4. Click **Save**
5. Restart the app

> **Warning**: change the path only after physically moving the folder. If the path does not exist, OffGallery will consider the models missing and attempt to re-download them.

---

## Support

For issues or questions, see the [documentation](../README.md) or open an issue on [GitHub](https://github.com/HEGOM61ita/OffGallery/issues).
