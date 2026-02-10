@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║       OFFGALLERY INSTALLER - STEP 2: CREA AMBIENTE           ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: Verifica conda
where conda >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Conda non trovato. Esegui prima 01_install_miniconda.bat
    pause
    exit /b 1
)

echo [OK] Conda trovato
conda --version
echo.

:: Verifica se l'ambiente esiste già
conda env list | findstr /C:"OffGallery" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [!!] L'ambiente "OffGallery" esiste già.
    echo.
    set /p RECREATE="Vuoi eliminarlo e ricrearlo? (S/N): "
    if /i "!RECREATE!"=="S" (
        echo.
        echo Rimozione ambiente esistente...
        conda env remove -n OffGallery -y >nul 2>&1
        echo [OK] Ambiente rimosso
    ) else (
        echo.
        echo Puoi procedere con lo step successivo: 03_install_packages.bat
        pause
        exit /b 0
    )
)

echo.
echo Creazione ambiente "OffGallery" con Python 3.11...
echo Questo potrebbe richiedere qualche minuto...
echo.

conda create -n OffGallery python=3.11 -y

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRORE] Creazione ambiente fallita.
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo [OK] Ambiente "OffGallery" creato con successo!
echo ═══════════════════════════════════════════════════════════════
echo.
echo Procedi con lo step successivo: 03_install_packages.bat
echo.
pause
