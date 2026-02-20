@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║         OFFGALLERY INSTALLER - STEP 1: MINICONDA             ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: Verifica se conda esiste già (PATH o percorsi noti)
where conda >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [OK] Conda trovato nel PATH
    conda --version
    echo.
    echo Puoi procedere con lo step successivo: 02_create_env.bat
    pause
    exit /b 0
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
        echo [OK] Conda trovato in %%~P
        call %%P --version
        echo.
        echo Puoi procedere con lo step successivo: 02_create_env.bat
        pause
        exit /b 0
    )
)

:: Conda non trovato
echo [!!] Conda non trovato nel sistema.
echo.
echo Per installare OffGallery hai bisogno di Miniconda.
echo.
echo ISTRUZIONI:
echo.
echo   1. Apri il browser e vai su:
echo      https://docs.anaconda.com/miniconda/install/#quick-command-line-install
echo.
echo   2. Scarica "Miniconda3 Windows 64-bit"
echo.
echo   3. Esegui l'installer con queste opzioni:
echo      - Install for: Just Me (recommended)
echo      - Add to PATH: SI (spunta la casella)
echo      - Register as default Python: SI
echo.
echo   4. RIAVVIA il terminale dopo l'installazione
echo.
echo   5. Riesegui questo script per verificare
echo.
echo ─────────────────────────────────────────────────────────────────
echo.

:: Chiedi se aprire il browser
set /p OPEN_BROWSER="Vuoi aprire la pagina di download ora? (S/N): "
if /i "!OPEN_BROWSER!"=="S" (
    start https://docs.anaconda.com/miniconda/install/#quick-command-line-install
)

echo.
pause
