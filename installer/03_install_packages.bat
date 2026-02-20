@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║     OFFGALLERY INSTALLER - STEP 3: INSTALLA PACCHETTI        ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: --- Cerca conda in piu' posizioni ---
set "CONDA_CMD="

where conda >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "CONDA_CMD=conda"
    goto :CONDA_FOUND
)

for %%P in (
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\Miniconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\Anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
) do (
    if exist %%P (
        set "CONDA_CMD=%%~P"
        goto :CONDA_FOUND
    )
)

echo [ERRORE] Conda non trovato. Esegui prima 01_install_miniconda.bat
pause
exit /b 1

:CONDA_FOUND

:: Verifica ambiente OffGallery
call "!CONDA_CMD!" env list > "%TEMP%\og_envlist.tmp" 2>nul
findstr /C:"OffGallery" "%TEMP%\og_envlist.tmp" >nul 2>&1
set "ENV_EXISTS=!ERRORLEVEL!"
del /f /q "%TEMP%\og_envlist.tmp" 2>nul

if !ENV_EXISTS! NEQ 0 (
    echo [ERRORE] Ambiente "OffGallery" non trovato. Esegui prima 02_create_env.bat
    pause
    exit /b 1
)

echo [OK] Ambiente "OffGallery" trovato
echo.

:: Ottieni il percorso di questo script
set "SCRIPT_DIR=%~dp0"

:: Verifica requirements file
if not exist "%SCRIPT_DIR%requirements_offgallery.txt" (
    echo [ERRORE] File requirements_offgallery.txt non trovato in %SCRIPT_DIR%
    pause
    exit /b 1
)

echo Installazione pacchetti Python...
echo Questo richiede 10-20 minuti (download ~3GB)
echo.
echo I seguenti pacchetti verranno installati:
echo   - PyTorch (GPU/CUDA 11.8)
echo   - Transformers (HuggingFace)
echo   - BioCLIP
echo   - PyQt6
echo   - OpenCV
echo   - E altre dipendenze...
echo.
echo ─────────────────────────────────────────────────────────────────
echo.

:: Aggiorna pip (usa conda run per evitare problemi con conda activate)
echo [1/2] Aggiornamento pip...
call "!CONDA_CMD!" run -n OffGallery --no-banner python -m pip install --upgrade pip -q
if !ERRORLEVEL! NEQ 0 (
    echo [!!] Aggiornamento pip fallito, continuo comunque...
)

:: Installa requirements
echo [2/2] Installazione dipendenze...
call "!CONDA_CMD!" run -n OffGallery --no-banner pip install -r "%SCRIPT_DIR%requirements_offgallery.txt"
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo [ERRORE] Installazione dipendenze fallita.
    echo.
    echo Possibili cause:
    echo   - Connessione internet assente o instabile
    echo   - Spazio disco insufficiente ^(servono ~6 GB^)
    echo   - Antivirus che blocca il download
    echo.
    echo Suggerimento: riprova questo script. I pacchetti gia'
    echo scaricati non vengono riscaricati.
    pause
    exit /b 1
)

:: Verifica pacchetti critici
echo.
echo Verifica installazione...
set "INSTALL_OK=1"

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import torch; print('[OK] PyTorch', torch.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] torch non trovato
    set "INSTALL_OK=0"
)

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import yaml; print('[OK] PyYAML', yaml.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] pyyaml non trovato
    set "INSTALL_OK=0"
)

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import PyQt6; print('[OK] PyQt6')" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] PyQt6 non trovato
    set "INSTALL_OK=0"
)

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import numpy; print('[OK] NumPy', numpy.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] numpy non trovato
    set "INSTALL_OK=0"
)

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import cv2; print('[OK] OpenCV', cv2.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] opencv non trovato
    set "INSTALL_OK=0"
)

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import PIL; print('[OK] Pillow', PIL.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] Pillow non trovato
    set "INSTALL_OK=0"
)

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import transformers; print('[OK] transformers', transformers.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] transformers non trovato
    set "INSTALL_OK=0"
)

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import open_clip; print('[OK] open-clip-torch')" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] open-clip-torch non trovato
    set "INSTALL_OK=0"
)

call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import rawpy; print('[OK] rawpy', rawpy.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo [ERRORE] rawpy non trovato
    set "INSTALL_OK=0"
)

if "!INSTALL_OK!"=="0" (
    echo.
    echo [ERRORE] Installazione incompleta. Uno o piu' pacchetti mancano.
    echo Controlla la connessione internet e riprova questo step.
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo [OK] Tutti i pacchetti installati con successo!
echo ═══════════════════════════════════════════════════════════════
echo.
echo Puoi avviare l'applicazione con: OffGallery_Launcher.bat
echo I modelli AI verranno scaricati automaticamente al primo avvio.
echo.
pause
