@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ═══════════════════════════════════════════════════════════════════
:: OffGallery - Unified Installation Wizard
:: Run with double click to install all components
:: Automatically detects GPU (NVIDIA/AMD) and allows choosing
:: the LLM backend (Ollama or LM Studio)
:: ═══════════════════════════════════════════════════════════════════

:: === GLOBAL VARIABLES ===
set "SCRIPT_DIR=%~dp0"
set "APP_ROOT=%~dp0.."
set "CONFIG_FILE=%APP_ROOT%\config_new.yaml"
set "REQUIREMENTS=%SCRIPT_DIR%requirements_offgallery.txt"
set "LAUNCHER=%SCRIPT_DIR%OffGallery_Launcher_EN.bat"
set "ENV_NAME=OffGallery"
set "PYTHON_VER=3.12"
set "MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
set "MINICONDA_INSTALLER=%TEMP%\miniconda_installer.exe"
set "MINICONDA_DIR=C:\miniconda3"
set "CONDA_BAT=%MINICONDA_DIR%\condabin\conda.bat"

:: Ollama
set "OLLAMA_URL=https://ollama.com/download/OllamaSetup.exe"
set "OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe"
set "OLLAMA_MODEL=qwen3.5:4b-q4_K_M"

:: LM Studio
set "LMSTUDIO_URL=https://lmstudio.ai/download/latest/win32/x64"
set "LMSTUDIO_PATH=%LOCALAPPDATA%\Programs\LM Studio"
set "LMSTUDIO_EXE=%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe"
set "LMSTUDIO_INSTALLER=%TEMP%\lmstudio.exe"
set "LMSTUDIO_CONFIG_SOURCE=%SCRIPT_DIR%lmstudio_settings.json"
set "LMSTUDIO_SERVER_SOURCE=%SCRIPT_DIR%lmstudio_http-server-config.json"
set "LMSTUDIO_CONFIG_DEST=%USERPROFILE%\.lmstudio\config.json"
set "LMSTUDIO_SERVER_DEST=%USERPROFILE%\.lmstudio\.internal\http-server-config.json"
set "LMSTUDIO_MODEL=qwen/qwen3-vl-4b"

set "STEP_TOTAL=5"

:: Status flags for summary
set "STATUS_MINICONDA=-"
set "STATUS_ENV=-"
set "STATUS_PACKAGES=-"
set "STATUS_LLM=-"
set "STATUS_LLM_MODEL=-"
set "STATUS_SHORTCUT=-"
set "GPU_TYPE=None"
set "PYTORCH_VARIANT=cpu"
set "LLM_BACKEND=none"

:: ═══════════════════════════════════════════════════════════════════
:: HEADER
:: ═══════════════════════════════════════════════════════════════════
cls
echo.
echo  ================================================================
echo.
echo             OffGallery - Installation Wizard
echo.
echo    Automatic photo cataloguing with AI - 100%% Offline
echo.
echo  ================================================================
echo.
echo   This wizard will install all required components.
echo   Estimated time: 20-40 minutes (depends on connection speed).
echo.
echo   Components:
echo     [1] Miniconda (Python environment manager)
echo     [2] OffGallery Python environment
echo     [3] Python libraries (PyTorch, CLIP, BioCLIP, etc.)
echo     [4] LLM Vision backend: Ollama or LM Studio (optional)
echo     [5] Desktop shortcut
echo.
echo  ----------------------------------------------------------------
echo.
echo   SYSTEM REQUIREMENTS:
echo     Operating System:   Windows 10/11 64-bit
echo     RAM:                8 GB minimum, 16 GB recommended
echo     Disk Space:         15-25 GB free
echo     GPU (optional):     NVIDIA with 4+ GB VRAM or AMD
echo     Internet:           Required for installation
echo.
echo  ----------------------------------------------------------------
echo.
set /p "CONFIRM_START=  Do you want to proceed with the installation? (Y/N): "
if /i "!CONFIRM_START!" NEQ "Y" goto :END_CANCELLED

:: ═══════════════════════════════════════════════════════════════════
:: CHOOSE MINICONDA INSTALLATION PATH
:: ═══════════════════════════════════════════════════════════════════
echo.
echo  ----------------------------------------------------------------
echo.
echo   Where do you want to install Miniconda?
echo   Press ENTER to accept the default or type another path.
echo   WARNING: the path must NOT contain spaces!
echo   Valid examples: C:\miniconda3   D:\miniconda3   E:\tools\miniconda3
echo.
set /p "MINICONDA_DIR_INPUT=  Path [!MINICONDA_DIR!]: "
if not "!MINICONDA_DIR_INPUT!"=="" set "MINICONDA_DIR=!MINICONDA_DIR_INPUT!"

:: Check for spaces in the chosen path
echo !MINICONDA_DIR! | findstr " " >nul
if !ERRORLEVEL! EQU 0 (
    echo.
    echo   [ERROR] The path "!MINICONDA_DIR!" contains spaces.
    echo   Choose a path without spaces ^(e.g. D:\miniconda3^).
    echo.
    pause
    goto :END_ERROR
)

:: Update CONDA_BAT with the final path chosen by the user
set "CONDA_BAT=!MINICONDA_DIR!\condabin\conda.bat"
echo.

:: ═══════════════════════════════════════════════════════════════════
:: STEP 1/5: MINICONDA
:: ═══════════════════════════════════════════════════════════════════
:STEP1_MINICONDA
set "STEP_CURRENT=1"
echo.
echo  ================================================================
echo    STEP 1/%STEP_TOTAL%: Miniconda
echo  ================================================================
echo.

:: --- Scenario A: Conda in PATH ---
where conda >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "tokens=*" %%v in ('conda --version 2^>nul') do echo   [OK] %%v found in the system.
    set "STATUS_MINICONDA=Already present"
    set "CONDA_CMD=conda"
    goto :STEP2_ENV
)

:: --- Scenario B: Miniconda/Anaconda installed but not in PATH ---
if exist "!CONDA_BAT!" (
    echo   [OK] Miniconda found in !MINICONDA_DIR!
    set "STATUS_MINICONDA=Already present"
    set "CONDA_CMD=!CONDA_BAT!"
    goto :STEP2_ENV
)

:: Also check Anaconda paths
for %%P in (
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\Anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\miniconda3\condabin\conda.bat"
) do (
    if exist %%P (
        echo   [OK] Conda found in %%~P
        set "STATUS_MINICONDA=Already present"
        set "CONDA_CMD=%%~P"
        goto :STEP2_ENV
    )
)

:: --- Scenario C: Installation required ---
echo   Miniconda not found. Installing...
echo.
echo   Downloading Miniconda (~80 MB)...
echo.

powershell -NoProfile -Command "& { try { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '!MINICONDA_URL!' -OutFile '!MINICONDA_INSTALLER!' -UseBasicParsing; Write-Host '  [OK] Download complete.' } catch { Write-Host '  [ERROR] Download failed:' $_.Exception.Message; exit 1 } }"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERROR] Miniconda download failed.
    echo   Check your internet connection and try again.
    echo.
    echo   Alternatively, download manually from:
    echo   https://docs.anaconda.com/miniconda/install/
    echo   then re-run this wizard.
    goto :END_ERROR
)

:: Verify the file exists and is not corrupted
if not exist "!MINICONDA_INSTALLER!" (
    echo   [ERROR] Installer file not found after download.
    goto :END_ERROR
)

for %%A in ("!MINICONDA_INSTALLER!") do (
    if %%~zA LSS 50000000 (
        echo   [ERROR] Downloaded file is too small. Download is probably corrupted.
        echo   Delete the file and try again:
        echo   !MINICONDA_INSTALLER!
        goto :END_ERROR
    )
)

:: If a partial installation exists, ask whether to remove it
if exist "!MINICONDA_DIR!" (
    echo   [!!] Folder !MINICONDA_DIR! already exists
    echo       but conda does not appear to be working.
    echo       This may be an incomplete previous installation.
    echo.
    set /p "REMOVE_OLD=  Do you want to remove it and reinstall? (Y/N): "
    if /i "!REMOVE_OLD!"=="Y" (
        echo   Removing...
        rmdir /s /q "!MINICONDA_DIR!" 2>nul
        echo   Folder removed.
    ) else (
        echo.
        echo   Cannot proceed with the existing folder.
        echo   Remove it manually and re-run the wizard.
        goto :END_ERROR
    )
)

echo.
echo   Installing Miniconda...
echo   (May take 2-5 minutes, please wait...)
echo.

start /wait "" "!MINICONDA_INSTALLER!" /InstallationType=JustMe /RegisterPython=0 /AddToPath=1 /S /D=!MINICONDA_DIR!

:: Post-installation check (concrete check instead of ERRORLEVEL)
if not exist "!CONDA_BAT!" (
    echo   [ERROR] Installation completed but conda.bat not found.
    echo   Expected path: !CONDA_BAT!
    echo   Restart the computer and re-run the wizard.
    goto :END_ERROR
)

:: Cleanup installer
del /f /q "!MINICONDA_INSTALLER!" 2>nul

:: Initialize conda for this session
call "!CONDA_BAT!" init >nul 2>&1

echo   [OK] Miniconda installed successfully!
set "STATUS_MINICONDA=Installed"
set "CONDA_CMD=!CONDA_BAT!"

:: ═══════════════════════════════════════════════════════════════════
:: STEP 2/5: OFFGALLERY ENVIRONMENT
:: ═══════════════════════════════════════════════════════════════════
:STEP2_ENV
set "STEP_CURRENT=2"
echo.
echo  ================================================================
echo    STEP 2/%STEP_TOTAL%: Python Environment
echo  ================================================================
echo.

:: Check whether the environment already exists (conda env list + filesystem fallback)
call "!CONDA_CMD!" env list > "%TEMP%\og_envlist.tmp" 2>nul
findstr /C:"!ENV_NAME!" "%TEMP%\og_envlist.tmp" >nul 2>&1
set "ENV_EXISTS=!ERRORLEVEL!"
del /f /q "%TEMP%\og_envlist.tmp" 2>nul
:: Filesystem fallback: conda env list may fail with ToS on Anaconda
if !ENV_EXISTS! NEQ 0 (
    if "!CONDA_CMD!" NEQ "conda" (
        for %%C in ("!CONDA_CMD!") do (
            for %%D in ("%%~dpC..") do set "_CBASE_E=%%~fD"
        )
        if exist "!_CBASE_E!\envs\!ENV_NAME!\python.exe" set "ENV_EXISTS=0"
    )
    if !ENV_EXISTS! NEQ 0 (
        for %%B in ("%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%USERPROFILE%\Anaconda3" "%LOCALAPPDATA%\miniconda3" "%LOCALAPPDATA%\anaconda3") do (
            if exist "%%~B\envs\!ENV_NAME!\python.exe" set "ENV_EXISTS=0"
        )
    )
)
if !ENV_EXISTS! EQU 0 (
    echo   [OK] Environment "!ENV_NAME!" already present.
    echo.
    set /p "RECREATE_ENV=  Do you want to delete it and recreate from scratch? (Y/N): "
    if /i "!RECREATE_ENV!"=="Y" (
        echo.
        echo   Removing existing environment...
        call "!CONDA_CMD!" env remove -n !ENV_NAME! -y >nul 2>&1
        if !ERRORLEVEL! NEQ 0 (
            echo   [ERROR] Could not remove the environment.
            echo   Try manually: conda env remove -n !ENV_NAME! -y
            goto :END_ERROR
        )
        echo   Environment removed. Recreating...
        echo.
    ) else (
        set "STATUS_ENV=Already present"
        goto :STEP3_PACKAGES
    )
)

echo   Creating environment "!ENV_NAME!" with Python !PYTHON_VER!...
echo   (1-3 minutes)
echo.

call "!CONDA_CMD!" create -n !ENV_NAME! python=!PYTHON_VER! --override-channels -c conda-forge -y
set "ENV_CREATED=!ERRORLEVEL!"

:: Concrete filesystem check: Anaconda may exit with a non-zero code
:: even if the environment was created correctly (e.g. residual ToS warning).
set "ENV_VERIFIED=0"
if "!CONDA_CMD!" NEQ "conda" (
    for %%C in ("!CONDA_CMD!") do (
        for %%D in ("%%~dpC..") do set "_CBASE_C=%%~fD"
    )
    if exist "!_CBASE_C!\envs\!ENV_NAME!\python.exe" set "ENV_VERIFIED=1"
)
if !ENV_VERIFIED! EQU 0 (
    for %%B in ("%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%USERPROFILE%\Anaconda3" "%LOCALAPPDATA%\miniconda3" "%LOCALAPPDATA%\anaconda3") do (
        if exist "%%~B\envs\!ENV_NAME!\python.exe" set "ENV_VERIFIED=1"
    )
)

if !ENV_CREATED! NEQ 0 (
    if !ENV_VERIFIED! EQU 1 (
        echo   [OK] Environment verified in the filesystem ^(exit code !ENV_CREATED! ignored^).
    ) else (
        echo.
        echo   [ERROR] Environment creation failed.
        echo   Possible causes:
        echo     - Anaconda Terms of Service not accepted
        echo     - Insufficient disk space
        echo     - Missing permissions
        echo.
        echo   Open the Anaconda Prompt and type:
        echo     conda create -n !ENV_NAME! python=!PYTHON_VER! --override-channels -c conda-forge -y
        echo   then re-run this wizard.
        goto :END_ERROR
    )
)

echo.
echo   [OK] Environment "!ENV_NAME!" created!
set "STATUS_ENV=Created"

:: ═══════════════════════════════════════════════════════════════════
:: STEP 3/5: PYTHON DEPENDENCIES (with automatic GPU detection)
:: ═══════════════════════════════════════════════════════════════════
:STEP3_PACKAGES
set "STEP_CURRENT=3"
echo.
echo  ================================================================
echo    STEP 3/%STEP_TOTAL%: Python Dependencies
echo  ================================================================
echo.

:: Check requirements file
if not exist "!REQUIREMENTS!" (
    echo   [ERROR] Requirements file not found:
    echo   !REQUIREMENTS!
    echo   Make sure the installer folder is complete.
    goto :END_ERROR
)

echo   Installing Python libraries (PyTorch, CLIP, BioCLIP, etc.)
echo   Estimated download: ~3-4 GB
echo   Estimated time: 10-20 minutes
echo.
echo   Components:
echo     - PyTorch (automatic GPU if NVIDIA or AMD present)
echo     - Transformers (HuggingFace)
echo     - BioCLIP (nature classification)
echo     - PyQt6 (graphical interface)
echo     - OpenCV (image processing)
echo     - Argos Translate (IT-EN translation)
echo.
echo   NOTE: The PyTorch download may appear stuck for
echo   several minutes. This is normal, please wait patiently.
echo.
echo  ----------------------------------------------------------------
echo.

:: === GPU DETECTION ===
echo   Detecting graphics card...
set "PYTORCH_VARIANT=cpu"
set "PYTORCH_INDEX=https://download.pytorch.org/whl/cpu"
set "GPU_TYPE=None"
set "INSTALL_DIRECTML=0"

:: --- Try NVIDIA first ---
nvidia-smi >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo   [OK] NVIDIA card detected!
    for /f "tokens=*" %%G in ('nvidia-smi --query-gpu=name --format^=csv^,noheader 2^>nul') do echo        Model: %%G
    echo   PyTorch will be installed with GPU support ^(CUDA 11.8^)
    set "PYTORCH_VARIANT=cu118"
    set "PYTORCH_INDEX=https://download.pytorch.org/whl/cu118"
    set "GPU_TYPE=NVIDIA (CUDA)"
    goto :GPU_DETECTED
)

:: --- Try AMD ---
powershell -NoProfile -Command "Get-CimInstance -ClassName Win32_VideoController | Select-Object Name" 2>nul | findstr /I "AMD Radeon" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo   [OK] AMD card detected!
    for /f "tokens=*" %%G in ('powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'AMD|Radeon' } | Select-Object -ExpandProperty Name" 2^>nul') do echo        Model: %%G
    echo   PyTorch will be installed with GPU support ^(DirectML^)
    set "PYTORCH_VARIANT=DirectML"
    set "PYTORCH_INDEX=https://download.pytorch.org/whl/cpu"
    set "GPU_TYPE=AMD (DirectML)"
    set "INSTALL_DIRECTML=1"
    goto :GPU_DETECTED
)

:: --- No dedicated GPU ---
echo   [INFO] No dedicated graphics card detected.
echo          PyTorch will be installed in CPU-only mode.
echo          ^(If you have a GPU, install the drivers first and re-run^)

:GPU_DETECTED
echo.

:: Update pip
echo   [1/3] Updating pip...
call "!CONDA_CMD!" run -n !ENV_NAME! python -m pip install --upgrade pip -q 2>nul

:: Pre-install PyTorch with the correct variant
echo   [2/3] Installing PyTorch ^(!PYTORCH_VARIANT!^)...
echo         ^(download ~2 GB, please wait patiently^)
echo.
call "!CONDA_CMD!" run -n !ENV_NAME! pip install torch torchvision --index-url "!PYTORCH_INDEX!"
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [!!] PyTorch !PYTORCH_VARIANT! installation failed. Retrying with CPU...
    echo.
    set "PYTORCH_VARIANT=cpu"
    set "GPU_TYPE=None (CPU fallback)"
    set "INSTALL_DIRECTML=0"
    call "!CONDA_CMD!" run -n !ENV_NAME! pip install torch torchvision --index-url "https://download.pytorch.org/whl/cpu"
)

:: Install torch-directml if AMD GPU detected
if "!INSTALL_DIRECTML!"=="1" (
    echo.
    echo   Installing torch-directml for AMD GPU...
    call "!CONDA_CMD!" run -n !ENV_NAME! pip install torch-directml
    if !ERRORLEVEL! NEQ 0 (
        echo   [!!] torch-directml not installed. AMD GPU will not be used.
        set "GPU_TYPE=AMD (CPU fallback)"
    )
)

:: Install remaining dependencies
echo.
echo   [3/3] Installing dependencies...
echo.

call "!CONDA_CMD!" run -n !ENV_NAME! pip install -r "!REQUIREMENTS!"
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERROR] Dependency installation failed.
    echo.
    echo   Possible causes:
    echo     - No or unstable internet connection
    echo     - Insufficient disk space ^(~6 GB needed^)
    echo     - Antivirus blocking the download
    echo.
    echo   Tip: re-run this wizard. Already downloaded packages
    echo   will not be downloaded again.
    goto :END_ERROR
)

:: Concrete check: verify all critical packages
echo.
echo   Verifying installation...
set "INSTALL_OK=1"

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import torch; print('  [OK] PyTorch', torch.__version__, '- CUDA:', 'YES' if torch.cuda.is_available() else 'NO')" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] torch not found & set "INSTALL_OK=0" )

:: Verify DirectML if installed
if "!INSTALL_DIRECTML!"=="1" (
    call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import torch_directml; print('  [OK] torch-directml - AMD GPU:', 'YES' if torch_directml.device() else 'NO')" 2>nul
    if !ERRORLEVEL! NEQ 0 ( echo   [!!] torch-directml not verified )
)

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "from PyQt6.QtWidgets import QApplication; print('  [OK] PyQt6')" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] PyQt6 not found & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import cv2; print('  [OK] OpenCV', cv2.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] opencv not found & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import numpy; print('  [OK] NumPy', numpy.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] numpy not found & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import PIL; print('  [OK] Pillow', PIL.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] Pillow not found & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import transformers; print('  [OK] transformers', transformers.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] transformers not found & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import open_clip; print('  [OK] open-clip-torch')" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] open-clip-torch not found & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import rawpy; print('  [OK] rawpy', rawpy.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] rawpy not found & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import yaml; print('  [OK] PyYAML', yaml.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERROR] pyyaml not found & set "INSTALL_OK=0" )

if "!INSTALL_OK!"=="0" (
    echo.
    echo   [ERROR] Installation incomplete. One or more packages are missing.
    echo   Re-run this wizard: already downloaded packages will not be downloaded again.
    goto :END_ERROR
)

echo.
echo   [OK] Python dependencies installed!
set "STATUS_PACKAGES=Installed"

:: ═══════════════════════════════════════════════════════════════════
:: STEP 4/5: LLM VISION BACKEND (OPTIONAL)
:: ═══════════════════════════════════════════════════════════════════
:STEP4_LLM
set "STEP_CURRENT=4"
echo.
echo  ================================================================
echo    STEP 4/%STEP_TOTAL%: LLM Vision Backend (Optional)
echo  ================================================================
echo.
echo   An LLM backend is used to automatically generate descriptions,
echo   tags and titles with AI. You can choose between:
echo.
echo     [1] Ollama    - Most popular, supports many models
echo     [2] LM Studio - Graphical interface, good AMD support
echo     [3] None      - I will install it later, or I already have my own
echo.
echo   If you skip this now, you can install it later.
echo   Search and classification functions work without it.
echo.

set /p "LLM_CHOICE=  Choose [1/2/3]: "

if "!LLM_CHOICE!"=="1" goto :INSTALL_OLLAMA
if "!LLM_CHOICE!"=="2" goto :INSTALL_LMSTUDIO
:: Any other choice = none
echo.
echo   LLM backend skipped. You can install it later.
set "STATUS_LLM=Skipped"
set "STATUS_LLM_MODEL=-"
set "LLM_BACKEND=none"
goto :STEP5_SHORTCUT

:: -----------------------------------------------------------------
:: OLLAMA INSTALLATION
:: -----------------------------------------------------------------
:INSTALL_OLLAMA
set "LLM_BACKEND=ollama"

:: Check if Ollama is already installed
where ollama >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo.
    echo   [OK] Ollama already installed.
    goto :OLLAMA_MODEL
)

:: Download Ollama
echo.
echo   Downloading Ollama...
echo.

powershell -NoProfile -Command "& { try { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '!OLLAMA_URL!' -OutFile '!OLLAMA_INSTALLER!' -UseBasicParsing; Write-Host '  [OK] Download complete.' } catch { Write-Host '  [ERROR] Download failed:' $_.Exception.Message; exit 1 } }"

if not exist "!OLLAMA_INSTALLER!" (
    echo.
    echo   [!!] Ollama download failed. You can install it manually from:
    echo       https://ollama.com/download
    echo.
    echo   Continuing with the next steps...
    set "STATUS_LLM=Failed"
    set "STATUS_LLM_MODEL=-"
    pause
    goto :STEP5_SHORTCUT
)

:: Install Ollama
echo.
echo   Installing Ollama...
echo   (An installation window may appear)
echo.

:: Ollama uses NSIS installer: the standard silent flag is /S
start /wait "" "!OLLAMA_INSTALLER!" /S 2>nul
:: If silent install fails, try interactive installation
where ollama >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        echo   Starting interactive installation...
        start /wait "" "!OLLAMA_INSTALLER!"
    )
)

:: Cleanup
del /f /q "!OLLAMA_INSTALLER!" 2>nul

:: Update PATH for this session
set "PATH=!PATH!;%LOCALAPPDATA%\Programs\Ollama"

:: Post-install check
where ollama >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "PATH=!PATH!;%LOCALAPPDATA%\Programs\Ollama"
    ) else (
        echo   [!!] Ollama installed but not found in PATH.
        echo       Restart the computer and then run:
        echo       ollama pull !OLLAMA_MODEL!
        set "STATUS_LLM=Requires restart"
        set "STATUS_LLM_MODEL=-"
        goto :STEP5_SHORTCUT
    )
)

echo   [OK] Ollama installed!

:OLLAMA_MODEL
echo.
echo   Checking model !OLLAMA_MODEL!...

:: Wait for Ollama service to start (retry with increasing wait)
set "OLLAMA_READY=0"
for %%t in (8 5 5) do (
    if !OLLAMA_READY! EQU 0 (
        timeout /t %%t /nobreak >nul 2>&1
        ollama list >nul 2>&1 && set "OLLAMA_READY=1"
    )
)

ollama list 2>nul | findstr /C:"!OLLAMA_MODEL!" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo   [OK] Model !OLLAMA_MODEL! already installed.
    set "STATUS_LLM=Ollama"
    set "STATUS_LLM_MODEL=OK"
    goto :STEP5_SHORTCUT
)

echo.
echo   Model !OLLAMA_MODEL! is not installed.
echo   Download size: ~3.3 GB
echo.
set /p "PULL_MODEL=  Do you want to download the model now? (Y/N): "
if /i "!PULL_MODEL!" NEQ "Y" (
    echo.
    echo   You can download it later with:
    echo   ollama pull !OLLAMA_MODEL!
    set "STATUS_LLM=Ollama (no model)"
    set "STATUS_LLM_MODEL=Not downloaded"
    goto :STEP5_SHORTCUT
)

echo.
echo   Downloading model (5-15 minutes)...
echo.

ollama pull "!OLLAMA_MODEL!"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [!!] Model download failed.
    echo   You can retry with: ollama pull !OLLAMA_MODEL!
    set "STATUS_LLM=Ollama"
    set "STATUS_LLM_MODEL=Not downloaded"
    pause
    goto :STEP5_SHORTCUT
)

echo.
echo   [OK] Ollama + model installed!
set "STATUS_LLM=Ollama"
set "STATUS_LLM_MODEL=OK"
goto :STEP5_SHORTCUT

:: -----------------------------------------------------------------
:: LM STUDIO INSTALLATION
:: -----------------------------------------------------------------
:INSTALL_LMSTUDIO
set "LLM_BACKEND=lmstudio"

:: Check if LM Studio is already installed
if exist "!LMSTUDIO_EXE!" (
    echo.
    echo   [OK] LM Studio already installed.
    goto :LMSTUDIO_CONFIG
)

:: Download LM Studio
echo.
echo   Downloading LM Studio...
echo.

powershell -NoProfile -Command "& { try { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '!LMSTUDIO_URL!' -OutFile '!LMSTUDIO_INSTALLER!' -UseBasicParsing; Write-Host '  [OK] Download complete.' } catch { Write-Host '  [ERROR] Download failed:' $_.Exception.Message; exit 1 } }"

if not exist "!LMSTUDIO_INSTALLER!" (
    echo.
    echo   [!!] LM Studio download failed. You can install it manually from:
    echo       https://lmstudio.ai
    echo.
    echo   Continuing with the next steps...
    set "STATUS_LLM=Failed"
    set "STATUS_LLM_MODEL=-"
    pause
    goto :STEP5_SHORTCUT
)

:: Install LM Studio (interactive)
echo.
echo   ---------------------------------------------------
echo   ------------------  ATTENTION!  -------------------
echo   ---------------------------------------------------
echo.
echo           The interactive installer will open!
echo.
echo     Leave all options at DEFAULT, allowing
echo     LM Studio to start at the end of the installation
echo     (it will then be closed automatically
echo     for the subsequent configuration).
echo.
echo   ---------------------------------------------------
echo.
timeout /t 5 /nobreak >nul 2>&1
start /wait "" "!LMSTUDIO_INSTALLER!" 2>nul

if not exist "!LMSTUDIO_EXE!" (
    echo.
    echo   [!!] LM Studio installation failed.
    echo       You can install it manually from: https://lmstudio.ai
    echo.
    set "STATUS_LLM=Failed"
    set "STATUS_LLM_MODEL=-"
    pause
    goto :STEP5_SHORTCUT
)

:: Cleanup
del /f /q "!LMSTUDIO_INSTALLER!" 2>nul

:: Update PATH for this session
set "PATH=!PATH!;!LMSTUDIO_PATH!"

:LMSTUDIO_CONFIG
echo.
echo   Configuring LM Studio...

:: Check that LM Studio has been launched at least once
:: (required to create the .lmstudio folder)
if exist "%USERPROFILE%\.lmstudio" (
    goto :LMSTUDIO_COPY_CONFIG
)

:: First launch of LM Studio to create the folders
powershell -NoProfile -Command "Start-Process -FilePath '!LMSTUDIO_EXE!' -WindowStyle Hidden"
echo   Waiting for LM Studio first launch...
echo.
:WAIT_LM
tasklist /FI "IMAGENAME eq LM Studio.exe" | find /I "LM Studio.exe" >nul
if errorlevel 1 (
    timeout /t 10 /nobreak >nul
    goto :WAIT_LM
)
timeout /t 5 /nobreak >nul 2>&1
echo   Closing LM Studio to copy the configuration...
taskkill /IM "LM Studio.exe" /F >nul 2>&1

:LMSTUDIO_COPY_CONFIG
:: Copy configuration files for local server auto-start
if exist "!LMSTUDIO_CONFIG_SOURCE!" (
    copy /Y "!LMSTUDIO_CONFIG_SOURCE!" "!LMSTUDIO_CONFIG_DEST!" >nul 2>&1
)
if exist "!LMSTUDIO_SERVER_SOURCE!" (
    if not exist "%USERPROFILE%\.lmstudio\.internal" mkdir "%USERPROFILE%\.lmstudio\.internal" 2>nul
    copy /Y "!LMSTUDIO_SERVER_SOURCE!" "!LMSTUDIO_SERVER_DEST!" >nul 2>&1
)
echo   [OK] Configuration copied.

:: Download model
echo.
echo   Model !LMSTUDIO_MODEL! is not installed.
echo   Download size: ~3.3 GB (in two parts).
echo   This will take between 3 and 15 minutes.
echo.
echo   NOTE: if the model has already been downloaded previously,
echo         you can safely skip this step.
echo.
set /p "INSTALL_MODEL=  Do you want to download the model now? (Y/N): "
if /i "!INSTALL_MODEL!"=="Y" (
    lms get !LMSTUDIO_MODEL!
    echo   [OK] Model downloaded!
    set "STATUS_LLM_MODEL=OK"
) else (
    echo.
    echo   You can download it later by opening LM Studio
    echo   and searching for: !LMSTUDIO_MODEL!
    set "STATUS_LLM_MODEL=Not downloaded"
)

:: Verify LM Studio server
powershell -NoProfile -Command "Start-Process -FilePath '!LMSTUDIO_EXE!' -WindowStyle Hidden"
set "LMSTUDIO_READY=0"
for %%t in (8 5 5) do (
    if !LMSTUDIO_READY! EQU 0 (
        timeout /t %%t /nobreak >nul 2>&1
        powershell -NoProfile -Command "(Invoke-WebRequest -Uri 'http://localhost:1234/v1/models' -TimeoutSec 2).StatusCode" >nul 2>&1
        if !ERRORLEVEL! EQU 0 set "LMSTUDIO_READY=1"
    )
)
if !LMSTUDIO_READY! EQU 1 (
    echo   [OK] LM Studio server is running!
    set "STATUS_LLM=LM Studio"
) else (
    echo   [!!] LM Studio server not responding. Please verify manually.
    set "STATUS_LLM=LM Studio (server not verified)"
)
goto :STEP5_SHORTCUT

:: ═══════════════════════════════════════════════════════════════════
:: STEP 5/5: DESKTOP SHORTCUT + CONFIGURATION
:: ═══════════════════════════════════════════════════════════════════
:STEP5_SHORTCUT
set "STEP_CURRENT=5"
echo.
echo  ================================================================
echo    STEP 5/%STEP_TOTAL%: Desktop Shortcut + Configuration
echo  ================================================================
echo.

:: --- Write chosen backend to config_new.yaml ---
if "!LLM_BACKEND!" NEQ "none" (
    if exist "!CONFIG_FILE!" (
        echo   Configuring LLM backend: !LLM_BACKEND!
        call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import yaml; p='!CONFIG_FILE!'.replace('\\','/'); c=yaml.safe_load(open(p,'r',encoding='utf-8')); lv=c.setdefault('embedding',{}).setdefault('llm_vision',{}); lv['backend']='!LLM_BACKEND!'; lv['endpoint']='http://localhost:1234' if '!LLM_BACKEND!'=='lmstudio' else 'http://localhost:11434'; lv['model']='!LMSTUDIO_MODEL!' if '!LLM_BACKEND!'=='lmstudio' else '!OLLAMA_MODEL!'; yaml.dump(c,open(p,'w',encoding='utf-8'),default_flow_style=False,allow_unicode=True)" 2>nul
        if !ERRORLEVEL! EQU 0 (
            echo   [OK] Backend '!LLM_BACKEND!' saved to config_new.yaml
        ) else (
            echo   [!!] Config write failed. You can configure it from the Config Tab.
        )
    )
)

:: --- Desktop Shortcut ---
:: Detect real Desktop path from registry (supports OneDrive)
set "DESKTOP="
for /f "tokens=2*" %%a in ('reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul') do set "DESKTOP=%%b"
:: Expand variables in the path (e.g. %USERPROFILE%)
if defined DESKTOP call set "DESKTOP=!DESKTOP!"
:: Fallback
if not defined DESKTOP set "DESKTOP=%USERPROFILE%\Desktop"

set "SHORTCUT_NAME=OffGallery"

:: Check that the Launcher exists
if not exist "!LAUNCHER!" (
    echo   [!!] Launcher file not found: !LAUNCHER!
    echo       You can create the shortcut manually.
    set "STATUS_SHORTCUT=Failed"
    goto :SUMMARY
)

echo   Creating shortcut "!SHORTCUT_NAME!" on the Desktop...
echo.

powershell -NoProfile -Command "& { try { $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('!DESKTOP!\!SHORTCUT_NAME!.lnk'); $s.TargetPath = '!LAUNCHER!'; $s.WorkingDirectory = '!APP_ROOT!'; $s.Description = 'Launch OffGallery - Offline AI photo cataloguing'; $s.Save(); Write-Host '  [OK] Shortcut created on the Desktop.' } catch { Write-Host '  [ERROR]' $_.Exception.Message; exit 1 } }"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [!!] Shortcut creation failed.
    echo   You can manually copy the file to the Desktop:
    echo   !LAUNCHER!
    set "STATUS_SHORTCUT=Failed"
) else (
    set "STATUS_SHORTCUT=Created"
)

:: ═══════════════════════════════════════════════════════════════════
:: Create working folders required by the app (excluded from git)
:: ═══════════════════════════════════════════════════════════════════
if not exist "!APP_ROOT!\database" mkdir "!APP_ROOT!\database"
if not exist "!APP_ROOT!\INPUT"    mkdir "!APP_ROOT!\INPUT"
if not exist "!APP_ROOT!\logs"     mkdir "!APP_ROOT!\logs"

:: ═══════════════════════════════════════════════════════════════════
:: FINAL SUMMARY
:: ═══════════════════════════════════════════════════════════════════
:SUMMARY
echo.
echo  ================================================================
echo.
echo              INSTALLATION COMPLETE
echo.
echo  ================================================================
echo.
echo   Summary:
echo.
echo     Miniconda:          !STATUS_MINICONDA!
echo     Python Environment: !STATUS_ENV!
echo     Python Libraries:   !STATUS_PACKAGES! ^(PyTorch: !PYTORCH_VARIANT!^)
echo     Detected GPU:       !GPU_TYPE!
echo     LLM Backend:        !STATUS_LLM!
echo     LLM Model:          !STATUS_LLM_MODEL!
echo     Shortcut:           !STATUS_SHORTCUT!
echo.
echo  ----------------------------------------------------------------
echo.
echo   IMPORTANT - FIRST LAUNCH:
echo.
echo   On the first launch, OffGallery will automatically download
echo   approximately 7 GB of AI models. This is normal and happens
echo   only once:
echo.
echo     - CLIP (semantic search):              ~580 MB
echo     - DINOv2 (visual similarity):          ~330 MB
echo     - Aesthetic (aesthetic scoring):       ~1.6 GB
echo     - BioCLIP + TreeOfLife (nature):       ~4.2 GB
echo     - Argos Translate (translation):       ~92 MB
echo.
echo   After the first launch, the app will work completely OFFLINE.
echo.
echo  ----------------------------------------------------------------
echo.
echo   TO LAUNCH OFFGALLERY:
echo.
echo     Double click "OffGallery" on the Desktop
echo.
echo   IMPORTANT - CORRECT LAUNCH:
echo     ALWAYS use the shortcut (.lnk) created on the Desktop.
echo     Do NOT copy or move OffGallery_Launcher_EN.bat outside
echo     the installer\ folder: the .bat must remain in its
echo     original position to find the application.
echo     The .lnk shortcut on the Desktop points to the original .bat
echo     and works correctly from any location.
echo.
echo   NOTE: If you have just installed Miniconda, you may need
echo   to restart the computer before the first launch.
echo.
echo  ================================================================
echo.
pause
goto :END

:: ═══════════════════════════════════════════════════════════════════
:: EXIT HANDLING
:: ═══════════════════════════════════════════════════════════════════
:END_CANCELLED
echo.
echo   Installation cancelled by the user.
echo.
pause
goto :END

:END_ERROR
echo.
echo  ----------------------------------------------------------------
echo   Installation interrupted due to an error at step !STEP_CURRENT!.
echo.
echo   You can re-run this wizard: steps already completed
echo   will be detected automatically and skipped.
echo  ----------------------------------------------------------------
echo.
pause
goto :END

:END
endlocal
exit /b 0
