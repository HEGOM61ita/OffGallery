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

:: Installa requirements
echo [2/2] Installazione dipendenze...
call "!CONDA_CMD!" run -n OffGallery --no-banner pip install -r "%SCRIPT_DIR%requirements_offgallery.txt"

:: Verifica concreta
call "!CONDA_CMD!" run -n OffGallery --no-banner python -c "import torch; print('[OK] PyTorch', torch.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 (
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
