@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ═══════════════════════════════════════════════════════════════
:: OffGallery Launcher
:: Avvia OffGallery trovando conda automaticamente
:: Starts OffGallery by automatically finding conda
:: ═══════════════════════════════════════════════════════════════

set "OFFGALLERY_PATH=%~dp0.."
set "ENV_NAME=OffGallery"

:: --- Cerca conda in piu' posizioni / Search for conda in known locations ---
set "CONDA_CMD="

:: 1. conda nel PATH / conda in PATH
where conda >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "CONDA_CMD=conda"
    goto :CONDA_FOUND
)

:: 2. Percorsi noti di Miniconda / Known Miniconda paths
for %%P in (
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\Miniconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\miniconda3\condabin\conda.bat"
    "C:\miniconda3\condabin\conda.bat"
    "C:\ProgramData\miniconda3\condabin\conda.bat"
    "%~d0\miniconda3\condabin\conda.bat"
) do (
    if exist %%P (
        set "CONDA_CMD=%%~P"
        goto :CONDA_FOUND
    )
)

:: 3. Percorsi noti di Anaconda / Known Anaconda paths
for %%P in (
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\Anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
    "C:\anaconda3\condabin\conda.bat"
    "C:\ProgramData\anaconda3\condabin\conda.bat"
    "%~d0\anaconda3\condabin\conda.bat"
) do (
    if exist %%P (
        set "CONDA_CMD=%%~P"
        goto :CONDA_FOUND
    )
)

:: Conda non trovato / Conda not found
echo.
echo   [ERRORE / ERROR] Conda non trovato. / Conda not found.
echo.
echo   Percorsi cercati / Paths searched:
echo     - PATH di sistema / System PATH
echo     - %USERPROFILE%\miniconda3
echo     - %LOCALAPPDATA%\miniconda3
echo.
echo   Se hai appena installato Miniconda, riavvia il computer.
echo   If you just installed Miniconda, restart your computer.
echo   Altrimenti esegui / Otherwise run: INSTALLA_OffGallery.bat (IT) or INSTALL_OffGallery_EN.bat (EN)
echo.
pause
exit /b 1

:CONDA_FOUND

:: Vai alla cartella dell'app e avvia con conda run / Go to app folder and start with conda run
cd /d "%OFFGALLERY_PATH%"
call "!CONDA_CMD!" run -n %ENV_NAME% python gui_launcher.py

:: Se l'app crasha, mostra l'errore / If the app crashes, show the error
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERRORE / ERROR] L'applicazione si e' chiusa con errore. / The application closed with an error.
    echo.
    pause
)

endlocal
