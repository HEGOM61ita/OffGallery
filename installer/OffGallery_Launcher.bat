@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ═══════════════════════════════════════════════════════════════
:: OffGallery Launcher
:: Avvia OffGallery trovando conda automaticamente
:: ═══════════════════════════════════════════════════════════════

set "OFFGALLERY_PATH=%~dp0.."
set "ENV_NAME=OffGallery"

:: --- Cerca conda in piu' posizioni ---
set "CONDA_CMD="

:: 1. conda nel PATH
where conda >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "CONDA_CMD=conda"
    goto :CONDA_FOUND
)

:: 2. Percorsi noti di Miniconda
for %%P in (
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\Miniconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\miniconda3\condabin\conda.bat"
) do (
    if exist %%P (
        set "CONDA_CMD=%%~P"
        goto :CONDA_FOUND
    )
)

:: 3. Percorsi noti di Anaconda
for %%P in (
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\Anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
) do (
    if exist %%P (
        set "CONDA_CMD=%%~P"
        goto :CONDA_FOUND
    )
)

:: Conda non trovato
echo.
echo   [ERRORE] Conda non trovato.
echo.
echo   Percorsi cercati:
echo     - PATH di sistema
echo     - %USERPROFILE%\miniconda3
echo     - %LOCALAPPDATA%\miniconda3
echo.
echo   Se hai appena installato Miniconda, riavvia il computer.
echo   Altrimenti esegui INSTALLA_OffGallery.bat
echo.
pause
exit /b 1

:CONDA_FOUND

:: Vai alla cartella dell'app e avvia con conda run
cd /d "%OFFGALLERY_PATH%"
call "!CONDA_CMD!" run -n %ENV_NAME% python gui_launcher.py

:: Se l'app crasha, mostra l'errore
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERRORE] L'applicazione si e' chiusa con errore.
    echo.
    pause
)

endlocal
