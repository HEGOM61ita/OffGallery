@echo off
:: ═══════════════════════════════════════════════════════════════
:: OffGallery Launcher
:: Copia questo file sul Desktop per avviare l'app con doppio click
:: ═══════════════════════════════════════════════════════════════

:: Configura il percorso dell'app (MODIFICA SE NECESSARIO)
set "OFFGALLERY_PATH=%~dp0.."

:: Avvia con ambiente OffGallery
call conda activate OffGallery 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Ambiente OffGallery non trovato.
    echo Esegui prima gli script di installazione.
    pause
    exit /b 1
)

:: Vai alla cartella dell'app e avvia
cd /d "%OFFGALLERY_PATH%"
python gui_launcher.py

:: Se l'app crasha, mostra l'errore
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRORE] L'applicazione si e' chiusa con errore.
    pause
)
