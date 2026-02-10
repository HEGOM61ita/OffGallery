@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║     OFFGALLERY INSTALLER - STEP 3: INSTALLA PACCHETTI        ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: Verifica conda
where conda >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Conda non trovato. Esegui prima 01_install_miniconda.bat
    pause
    exit /b 1
)

:: Verifica ambiente OffGallery
conda env list | findstr /C:"OffGallery" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
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

:: Attiva ambiente e installa
call conda activate OffGallery

if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Impossibile attivare ambiente OffGallery
    pause
    exit /b 1
)

:: Aggiorna pip
echo [1/2] Aggiornamento pip...
python -m pip install --upgrade pip -q

:: Installa requirements
echo [2/2] Installazione dipendenze...
pip install -r "%SCRIPT_DIR%requirements_offgallery.txt"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRORE] Installazione pacchetti fallita.
    echo Controlla la connessione internet e riprova.
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
