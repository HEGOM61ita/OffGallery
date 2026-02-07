@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║       OFFGALLERY INSTALLER - STEP 6: SETUP OLLAMA            ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: Verifica se Ollama è installato
where ollama >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!!] Ollama non trovato nel sistema.
    echo.
    echo Ollama è necessario per generare descrizioni e tag con AI.
    echo.
    echo ISTRUZIONI INSTALLAZIONE:
    echo.
    echo   1. Apri il browser e vai su:
    echo      https://ollama.com/download
    echo.
    echo   2. Scarica e installa "Ollama for Windows"
    echo.
    echo   3. Dopo l'installazione, RIAVVIA questo script
    echo.
    echo ─────────────────────────────────────────────────────────────────
    echo.
    set /p OPEN_BROWSER="Vuoi aprire la pagina di download ora? (S/N): "
    if /i "!OPEN_BROWSER!"=="S" (
        start https://ollama.com/download
    )
    echo.
    pause
    exit /b 1
)

echo [OK] Ollama trovato
ollama --version
echo.

:: Verifica se il modello è già presente
echo Verifica modello qwen3-vl:4b-instruct...
ollama list 2>nul | findstr /C:"qwen3-vl:4b-instruct" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Modello qwen3-vl:4b-instruct già installato
    echo.
    echo ═══════════════════════════════════════════════════════════════
    echo [OK] Ollama configurato correttamente!
    echo ═══════════════════════════════════════════════════════════════
    echo.
    echo Procedi con lo step finale: 07_verify_installation.py
    echo (Esegui: conda activate OffGallery ^&^& python 07_verify_installation.py)
    echo.
    pause
    exit /b 0
)

:: Download modello
echo.
echo Download modello qwen3-vl:4b-instruct (~3.3 GB)
echo Questo è il modello LLM Vision per generare descrizioni e tag.
echo.
echo ─────────────────────────────────────────────────────────────────
echo.

set /p DOWNLOAD="Vuoi scaricare il modello ora? (S/N): "
if /i "!DOWNLOAD!" NEQ "S" (
    echo.
    echo Download annullato. Puoi scaricarlo in seguito con:
    echo   ollama pull qwen3-vl:4b-instruct
    echo.
    pause
    exit /b 0
)

echo.
echo Download in corso... (potrebbe richiedere 5-15 minuti)
echo.

ollama pull qwen3-vl:4b-instruct

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRORE] Download modello fallito.
    echo Verifica la connessione internet e riprova con:
    echo   ollama pull qwen3-vl:4b-instruct
    echo.
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo [OK] Ollama configurato con successo!
echo ═══════════════════════════════════════════════════════════════
echo.
echo Modello installato: qwen3-vl:4b-instruct (3.3 GB)
echo.
echo Procedi con lo step finale: 07_verify_installation.py
echo (Esegui: conda activate OffGallery ^&^& python 07_verify_installation.py)
echo.
pause
