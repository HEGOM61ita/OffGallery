@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║       OFFGALLERY INSTALLER - STEP 2: CREA AMBIENTE           ║
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
echo [OK] Conda trovato
call "!CONDA_CMD!" --version
echo.

:: Verifica se l'ambiente esiste già
call "!CONDA_CMD!" env list > "%TEMP%\og_envlist.tmp" 2>nul
findstr /C:"OffGallery" "%TEMP%\og_envlist.tmp" >nul 2>&1
set "ENV_EXISTS=!ERRORLEVEL!"
del /f /q "%TEMP%\og_envlist.tmp" 2>nul

if !ENV_EXISTS! EQU 0 (
    echo [!!] L'ambiente "OffGallery" esiste già.
    echo.
    set /p RECREATE="Vuoi eliminarlo e ricrearlo? (S/N): "
    if /i "!RECREATE!"=="S" (
        echo.
        echo Rimozione ambiente esistente...
        call "!CONDA_CMD!" env remove -n OffGallery -y
        if !ERRORLEVEL! NEQ 0 (
            echo [ERRORE] Impossibile rimuovere l'ambiente.
            echo Potrebbe essere in uso. Chiudi OffGallery e riprova.
            pause
            exit /b 1
        )
        echo [OK] Ambiente rimosso
    ) else (
        echo.
        echo Puoi procedere con lo step successivo: 03_install_packages.bat
        pause
        exit /b 0
    )
)

echo.
echo Accettazione Terms of Service Anaconda...
call "!CONDA_CMD!" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >nul 2>&1
call "!CONDA_CMD!" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >nul 2>&1
call "!CONDA_CMD!" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2 >nul 2>&1
echo [OK] Terms of Service accettati
echo.

echo Creazione ambiente "OffGallery" con Python 3.12...
echo Questo potrebbe richiedere qualche minuto...
echo.

call "!CONDA_CMD!" create -n OffGallery python=3.12 -y

:: Verifica concreta
call "!CONDA_CMD!" env list > "%TEMP%\og_envlist.tmp" 2>nul
findstr /C:"OffGallery" "%TEMP%\og_envlist.tmp" >nul 2>&1
set "ENV_CREATED=!ERRORLEVEL!"
del /f /q "%TEMP%\og_envlist.tmp" 2>nul

if !ENV_CREATED! NEQ 0 (
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
