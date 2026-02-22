@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ═══════════════════════════════════════════════════════════════════
:: OffGallery - Wizard di Installazione Unificato
:: Esegui con doppio click per installare tutti i componenti
:: ═══════════════════════════════════════════════════════════════════

:: === VARIABILI GLOBALI ===
set "SCRIPT_DIR=%~dp0"
set "APP_ROOT=%~dp0.."
set "REQUIREMENTS=%SCRIPT_DIR%requirements_offgallery.txt"
set "LAUNCHER=%SCRIPT_DIR%OffGallery_Launcher.bat"
set "ENV_NAME=OffGallery"
set "PYTHON_VER=3.12"
set "MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
set "MINICONDA_INSTALLER=%TEMP%\miniconda_installer.exe"
set "MINICONDA_DIR=%USERPROFILE%\miniconda3"
set "CONDA_BAT=%MINICONDA_DIR%\condabin\conda.bat"
set "OLLAMA_URL=https://ollama.com/download/OllamaSetup.exe"
set "OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe"
set "OLLAMA_MODEL=qwen3-vl:4b-instruct"
set "STEP_TOTAL=5"

:: Flag di stato per riepilogo
set "STATUS_MINICONDA=-"
set "STATUS_ENV=-"
set "STATUS_PACKAGES=-"
set "STATUS_OLLAMA=-"
set "STATUS_SHORTCUT=-"

:: ═══════════════════════════════════════════════════════════════════
:: HEADER
:: ═══════════════════════════════════════════════════════════════════
cls
echo.
echo  ================================================================
echo.
echo             OffGallery - Installazione Guidata
echo.
echo    Catalogazione automatica foto con AI - 100%% Offline
echo.
echo  ================================================================
echo.
echo   Questo wizard installera' tutti i componenti necessari.
echo   Tempo stimato: 20-40 minuti (dipende dalla connessione).
echo.
echo   Componenti:
echo     [1] Miniconda (gestore ambienti Python)
echo     [2] Ambiente Python OffGallery
echo     [3] Librerie Python (PyTorch, CLIP, BioCLIP, etc.)
echo     [4] Ollama + modello LLM Vision (opzionale)
echo     [5] Collegamento sul Desktop
echo.
echo  ----------------------------------------------------------------
echo.
echo   REQUISITI DI SISTEMA:
echo     Sistema Operativo:  Windows 10/11 64-bit
echo     RAM:                8 GB minimo, 16 GB consigliato
echo     Spazio Disco:       15-25 GB liberi
echo     GPU (opzionale):    NVIDIA con 4+ GB VRAM
echo     Internet:           Necessaria per l'installazione
echo.
echo  ----------------------------------------------------------------
echo.
set /p "CONFIRM_START=  Vuoi procedere con l'installazione? (S/N): "
if /i "!CONFIRM_START!" NEQ "S" goto :END_CANCELLED

:: ═══════════════════════════════════════════════════════════════════
:: STEP 1/5: MINICONDA
:: ═══════════════════════════════════════════════════════════════════
:STEP1_MINICONDA
set "STEP_CURRENT=1"
echo.
echo  ================================================================
echo    STEP 1/%STEP_TOTAL%: Miniconda
echo  ================================================================
echo.

:: --- Scenario A: Conda nel PATH ---
where conda >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    for /f "tokens=*" %%v in ('conda --version 2^>nul') do echo   [OK] %%v trovato nel sistema.
    set "STATUS_MINICONDA=Gia' presente"
    set "CONDA_CMD=conda"
    goto :STEP2_ENV
)

:: --- Scenario B: Miniconda/Anaconda installato ma non nel PATH ---
if exist "!CONDA_BAT!" (
    echo   [OK] Miniconda trovato in !MINICONDA_DIR!
    set "STATUS_MINICONDA=Gia' presente"
    set "CONDA_CMD=!CONDA_BAT!"
    goto :STEP2_ENV
)

:: Controlla anche percorsi Anaconda
for %%P in (
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\Anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\miniconda3\condabin\conda.bat"
) do (
    if exist %%P (
        echo   [OK] Conda trovato in %%~P
        set "STATUS_MINICONDA=Gia' presente"
        set "CONDA_CMD=%%~P"
        goto :STEP2_ENV
    )
)

:: --- Scenario C: Installazione necessaria ---
echo   Miniconda non trovato. Installazione in corso...
echo.
echo   Download Miniconda (~80 MB)...
echo.

powershell -Command "& { try { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '!MINICONDA_URL!' -OutFile '!MINICONDA_INSTALLER!' -UseBasicParsing; Write-Host '  [OK] Download completato.' } catch { Write-Host '  [ERRORE] Download fallito:' $_.Exception.Message; exit 1 } }"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERRORE] Download Miniconda fallito.
    echo   Verifica la connessione internet e riprova.
    echo.
    echo   In alternativa, scarica manualmente da:
    echo   https://docs.anaconda.com/miniconda/install/
    echo   poi riesegui questo wizard.
    goto :END_ERROR
)

:: Verifica che il file esista e non sia corrotto
if not exist "!MINICONDA_INSTALLER!" (
    echo   [ERRORE] File installer non trovato dopo il download.
    goto :END_ERROR
)

for %%A in ("!MINICONDA_INSTALLER!") do (
    if %%~zA LSS 50000000 (
        echo   [ERRORE] File scaricato troppo piccolo. Download probabilmente corrotto.
        echo   Elimina il file e riprova:
        echo   !MINICONDA_INSTALLER!
        goto :END_ERROR
    )
)

:: Se esiste una installazione parziale, chiedi se rimuoverla
if exist "!MINICONDA_DIR!" (
    echo   [!!] La cartella !MINICONDA_DIR! esiste gia'
    echo       ma conda non risulta funzionante.
    echo       Potrebbe essere un'installazione precedente incompleta.
    echo.
    set /p "REMOVE_OLD=  Vuoi rimuoverla e reinstallare? (S/N): "
    if /i "!REMOVE_OLD!"=="S" (
        echo   Rimozione in corso...
        rmdir /s /q "!MINICONDA_DIR!" 2>nul
        echo   Cartella rimossa.
    ) else (
        echo.
        echo   Impossibile procedere con la cartella esistente.
        echo   Rimuovila manualmente e riesegui il wizard.
        goto :END_ERROR
    )
)

echo.
echo   Installazione Miniconda in corso...
echo   (Puo' richiedere 2-5 minuti, attendere...)
echo.

start /wait "" "!MINICONDA_INSTALLER!" /InstallationType=JustMe /RegisterPython=0 /AddToPath=1 /S /D=!MINICONDA_DIR!

:: Verifica post-installazione (check concreto invece di ERRORLEVEL)
if not exist "!CONDA_BAT!" (
    echo   [ERRORE] Installazione completata ma conda.bat non trovato.
    echo   Percorso atteso: !CONDA_BAT!
    echo   Riavvia il computer e riesegui il wizard.
    goto :END_ERROR
)

:: Pulizia installer
del /f /q "!MINICONDA_INSTALLER!" 2>nul

:: Inizializza conda per la sessione
call "!CONDA_BAT!" init >nul 2>&1

echo   [OK] Miniconda installato con successo!
set "STATUS_MINICONDA=Installato"
set "CONDA_CMD=!CONDA_BAT!"

:: ═══════════════════════════════════════════════════════════════════
:: STEP 2/5: AMBIENTE OFFGALLERY
:: ═══════════════════════════════════════════════════════════════════
:STEP2_ENV
set "STEP_CURRENT=2"
echo.
echo  ================================================================
echo    STEP 2/%STEP_TOTAL%: Ambiente Python
echo  ================================================================
echo.

:: Verifica se l'ambiente esiste gia' (conda env list + fallback filesystem)
call "!CONDA_CMD!" env list > "%TEMP%\og_envlist.tmp" 2>nul
findstr /C:"!ENV_NAME!" "%TEMP%\og_envlist.tmp" >nul 2>&1
set "ENV_EXISTS=!ERRORLEVEL!"
del /f /q "%TEMP%\og_envlist.tmp" 2>nul
:: Fallback filesystem: conda env list puo' fallire con ToS su Anaconda
if !ENV_EXISTS! NEQ 0 (
    if "!CONDA_CMD!" NEQ "conda" (
        for %%C in ("!CONDA_CMD!") do (
            for %%D in ("%%~dpC..") do set "_CBASE_E=%%~fD"
        )
        if exist "!_CBASE_E!\envs\!ENV_NAME!\python.exe" set "ENV_EXISTS=0"
    )
    if !ENV_EXISTS! NEQ 0 (
        for %%B in ("%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%USERPROFILE%\Anaconda3" "%LOCALAPPDATA%\miniconda3" "%LOCALAPPDATA%\anaconda3") do (
            if exist "%%~B\envs\!ENV_NAME!\python.exe" set "ENV_EXISTS=0"
        )
    )
)
if !ENV_EXISTS! EQU 0 (
    echo   [OK] Ambiente "!ENV_NAME!" gia' presente.
    echo.
    set /p "RECREATE_ENV=  Vuoi eliminarlo e ricrearlo da zero? (S/N): "
    if /i "!RECREATE_ENV!"=="S" (
        echo.
        echo   Rimozione ambiente esistente...
        call "!CONDA_CMD!" env remove -n !ENV_NAME! -y >nul 2>&1
        if !ERRORLEVEL! NEQ 0 (
            echo   [ERRORE] Impossibile rimuovere l'ambiente.
            echo   Prova manualmente: conda env remove -n !ENV_NAME! -y
            goto :END_ERROR
        )
        echo   Ambiente rimosso. Ricreazione in corso...
        echo.
    ) else (
        set "STATUS_ENV=Gia' presente"
        goto :STEP3_PACKAGES
    )
)

echo   Creazione ambiente "!ENV_NAME!" con Python !PYTHON_VER!...
echo   (1-3 minuti)
echo.

call "!CONDA_CMD!" create -n !ENV_NAME! python=!PYTHON_VER! --override-channels -c conda-forge -y
set "ENV_CREATED=!ERRORLEVEL!"

:: Verifica concreta nel filesystem: Anaconda puo' uscire con exit code non-zero
:: anche se l'ambiente e' stato creato correttamente (es. ToS warning residuo).
set "ENV_VERIFIED=0"
if "!CONDA_CMD!" NEQ "conda" (
    for %%C in ("!CONDA_CMD!") do (
        for %%D in ("%%~dpC..") do set "_CBASE_C=%%~fD"
    )
    if exist "!_CBASE_C!\envs\!ENV_NAME!\python.exe" set "ENV_VERIFIED=1"
)
if !ENV_VERIFIED! EQU 0 (
    for %%B in ("%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%USERPROFILE%\Anaconda3" "%LOCALAPPDATA%\miniconda3" "%LOCALAPPDATA%\anaconda3") do (
        if exist "%%~B\envs\!ENV_NAME!\python.exe" set "ENV_VERIFIED=1"
    )
)

if !ENV_CREATED! NEQ 0 (
    if !ENV_VERIFIED! EQU 1 (
        echo   [OK] Ambiente verificato nel filesystem ^(exit code !ENV_CREATED! ignorato^).
    ) else (
        echo.
        echo   [ERRORE] Creazione ambiente fallita.
        echo   Possibili cause:
        echo     - Termini di servizio Anaconda non accettati
        echo     - Spazio disco insufficiente
        echo     - Permessi mancanti
        echo.
        echo   Apri il Prompt Anaconda e digita:
        echo     conda create -n !ENV_NAME! python=!PYTHON_VER! --override-channels -c conda-forge -y
        echo   poi riesegui questo wizard.
        goto :END_ERROR
    )
)

echo.
echo   [OK] Ambiente "!ENV_NAME!" creato!
set "STATUS_ENV=Creato"

:: ═══════════════════════════════════════════════════════════════════
:: STEP 3/5: DIPENDENZE PYTHON
:: ═══════════════════════════════════════════════════════════════════
:STEP3_PACKAGES
set "STEP_CURRENT=3"
echo.
echo  ================================================================
echo    STEP 3/%STEP_TOTAL%: Dipendenze Python
echo  ================================================================
echo.

:: Verifica file requirements
if not exist "!REQUIREMENTS!" (
    echo   [ERRORE] File requirements non trovato:
    echo   !REQUIREMENTS!
    echo   Assicurati che la cartella installer sia completa.
    goto :END_ERROR
)

echo   Installazione librerie Python (PyTorch, CLIP, BioCLIP, etc.)
echo   Download stimato: ~3-4 GB
echo   Tempo stimato: 10-20 minuti
echo.
echo   Componenti:
echo     - PyTorch (GPU con CUDA se scheda NVIDIA presente, altrimenti CPU)
echo     - Transformers (HuggingFace)
echo     - BioCLIP (classificazione natura)
echo     - PyQt6 (interfaccia grafica)
echo     - OpenCV (elaborazione immagini)
echo     - Argos Translate (traduzione IT-EN)
echo.
echo   NOTA: Il download di PyTorch puo' sembrare bloccato per
echo   diversi minuti. E' normale, attendere pazientemente.
echo.
echo  ----------------------------------------------------------------
echo.

:: === RILEVAMENTO SCHEDA GRAFICA NVIDIA ===
echo   Rilevamento scheda grafica...
set "PYTORCH_VARIANT=cpu"
set "PYTORCH_INDEX=https://download.pytorch.org/whl/cpu"

nvidia-smi >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo   [OK] Scheda NVIDIA rilevata - PyTorch installato con supporto GPU ^(CUDA 11.8^)
    set "PYTORCH_VARIANT=cu118"
    set "PYTORCH_INDEX=https://download.pytorch.org/whl/cu118"
) else (
    echo   [INFO] Nessuna scheda NVIDIA rilevata - PyTorch installato in modalita' CPU
    echo         ^(se hai una GPU NVIDIA, installa prima i driver NVIDIA e riesegui^)
)
echo.

:: Aggiorna pip (usa conda run per evitare problemi con conda activate in batch)
echo   [1/3] Aggiornamento pip...
call "!CONDA_CMD!" run -n !ENV_NAME! python -m pip install --upgrade pip -q 2>nul

:: Pre-installa PyTorch con la variante corretta (CUDA o CPU)
echo   [2/3] Installazione PyTorch ^(!PYTORCH_VARIANT!^)...
echo         ^(download ~2 GB, attendere pazientemente^)
echo.
call "!CONDA_CMD!" run -n !ENV_NAME! pip install torch torchvision --index-url "!PYTORCH_INDEX!"
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [!!] Installazione PyTorch !PYTORCH_VARIANT! fallita. Riprovo con CPU...
    echo.
    call "!CONDA_CMD!" run -n !ENV_NAME! pip install torch torchvision --index-url "https://download.pytorch.org/whl/cpu"
)

:: Installa le restanti dipendenze
echo.
echo   [3/3] Installazione dipendenze in corso...
echo.

call "!CONDA_CMD!" run -n !ENV_NAME! pip install -r "!REQUIREMENTS!"
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERRORE] Installazione dipendenze fallita.
    echo.
    echo   Possibili cause:
    echo     - Connessione internet assente o instabile
    echo     - Spazio disco insufficiente ^(servono ~6 GB^)
    echo     - Antivirus che blocca il download
    echo.
    echo   Suggerimento: riesegui questo wizard. I pacchetti
    echo   gia' scaricati non verranno riscaricati.
    goto :END_ERROR
)

:: Verifica concreta: controlla tutti i pacchetti critici
echo.
echo   Verifica installazione...
set "INSTALL_OK=1"

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import torch; print('  [OK] PyTorch', torch.__version__, '- CUDA:', 'SI' if torch.cuda.is_available() else 'NO (solo CPU)')" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] torch non trovato & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "from PyQt6.QtWidgets import QApplication; print('  [OK] PyQt6')" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] PyQt6 non trovato & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import cv2; print('  [OK] OpenCV', cv2.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] opencv non trovato & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import numpy; print('  [OK] NumPy', numpy.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] numpy non trovato & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import PIL; print('  [OK] Pillow', PIL.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] Pillow non trovato & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import transformers; print('  [OK] transformers', transformers.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] transformers non trovato & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import open_clip; print('  [OK] open-clip-torch')" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] open-clip-torch non trovato & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import rawpy; print('  [OK] rawpy', rawpy.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] rawpy non trovato & set "INSTALL_OK=0" )

call "!CONDA_CMD!" run -n !ENV_NAME! python -c "import yaml; print('  [OK] PyYAML', yaml.__version__)" 2>nul
if !ERRORLEVEL! NEQ 0 ( echo   [ERRORE] pyyaml non trovato & set "INSTALL_OK=0" )

if "!INSTALL_OK!"=="0" (
    echo.
    echo   [ERRORE] Installazione incompleta. Uno o piu' pacchetti mancano.
    echo   Riesegui questo wizard: i pacchetti gia' scaricati non verranno riscaricati.
    goto :END_ERROR
)

echo.
echo   [OK] Dipendenze Python installate!
set "STATUS_PACKAGES=Installato"

:: ═══════════════════════════════════════════════════════════════════
:: STEP 4/5: OLLAMA (OPZIONALE)
:: ═══════════════════════════════════════════════════════════════════
:STEP4_OLLAMA
set "STEP_CURRENT=4"
echo.
echo  ================================================================
echo    STEP 4/%STEP_TOTAL%: Ollama (Opzionale)
echo  ================================================================
echo.
echo   Ollama e' un programma per eseguire modelli LLM in locale.
echo   Serve per generare descrizioni e tag automatici con AI.
echo.
echo   Se non lo installi ora, puoi farlo in seguito.
echo   Le funzioni di ricerca e classificazione funzionano senza Ollama.
echo.

set /p "INSTALL_OLLAMA=  Vuoi installare Ollama? (S/N): "
if /i "!INSTALL_OLLAMA!" NEQ "S" (
    echo.
    echo   Ollama saltato. Potrai installarlo in seguito da:
    echo   https://ollama.com/download
    set "STATUS_OLLAMA=Saltato"
    goto :STEP5_SHORTCUT
)

:: Verifica se Ollama e' gia' installato
where ollama >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo.
    echo   [OK] Ollama gia' installato.
    goto :STEP4_MODEL
)

:: Download Ollama
echo.
echo   Download Ollama...
echo.

powershell -NoProfile -Command "& { try { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '!OLLAMA_URL!' -OutFile '!OLLAMA_INSTALLER!' -UseBasicParsing; Write-Host '  [OK] Download completato.' } catch { Write-Host '  [ERRORE] Download fallito:' $_.Exception.Message; exit 1 } }"

:: Verifica concreta che il file sia stato scaricato
if not exist "!OLLAMA_INSTALLER!" (
    echo.
    echo   [!!] Download Ollama fallito. Puoi installarlo manualmente da:
    echo       https://ollama.com/download
    echo.
    echo   Proseguo con gli step successivi...
    set "STATUS_OLLAMA=Fallito"
    pause
    goto :STEP5_SHORTCUT
)

:: Installazione Ollama
echo.
echo   Installazione Ollama...
echo   (Potrebbe apparire una finestra di installazione)
echo.

:: Ollama usa installer NSIS: il flag silenzioso standard e' /S
start /wait "" "!OLLAMA_INSTALLER!" /S 2>nul
:: Se il silent install fallisce, prova installazione interattiva
where ollama >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        echo   Avvio installazione interattiva...
        start /wait "" "!OLLAMA_INSTALLER!"
    )
)

:: Pulizia
del /f /q "!OLLAMA_INSTALLER!" 2>nul

:: Aggiorna PATH per questa sessione
set "PATH=!PATH!;%LOCALAPPDATA%\Programs\Ollama"

:: Verifica post-install
where ollama >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "PATH=!PATH!;%LOCALAPPDATA%\Programs\Ollama"
    ) else (
        echo   [!!] Ollama installato ma non trovato nel PATH.
        echo       Riavvia il computer e poi esegui:
        echo       ollama pull !OLLAMA_MODEL!
        set "STATUS_OLLAMA=Richiede riavvio"
        goto :STEP5_SHORTCUT
    )
)

echo   [OK] Ollama installato!

:STEP4_MODEL
echo.
echo   Verifica modello !OLLAMA_MODEL!...

:: Attendi avvio servizio Ollama (retry con attesa crescente)
set "OLLAMA_READY=0"
for %%t in (8 5 5) do (
    if !OLLAMA_READY! EQU 0 (
        timeout /t %%t /nobreak >nul 2>&1
        ollama list >nul 2>&1 && set "OLLAMA_READY=1"
    )
)

ollama list 2>nul | findstr /C:"!OLLAMA_MODEL!" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo   [OK] Modello !OLLAMA_MODEL! gia' installato.
    set "STATUS_OLLAMA=Gia' presente"
    goto :STEP5_SHORTCUT
)

echo.
echo   Il modello !OLLAMA_MODEL! non e' installato.
echo   Dimensione download: ~3.3 GB
echo.
set /p "PULL_MODEL=  Vuoi scaricare il modello ora? (S/N): "
if /i "!PULL_MODEL!" NEQ "S" (
    echo.
    echo   Puoi scaricarlo in seguito con:
    echo   ollama pull !OLLAMA_MODEL!
    set "STATUS_OLLAMA=Senza modello"
    goto :STEP5_SHORTCUT
)

echo.
echo   Download modello in corso (5-15 minuti)...
echo.

ollama pull "!OLLAMA_MODEL!"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [!!] Download modello fallito.
    echo   Puoi riprovare con: ollama pull !OLLAMA_MODEL!
    set "STATUS_OLLAMA=Modello non scaricato"
    pause
    goto :STEP5_SHORTCUT
)

echo.
echo   [OK] Ollama + modello installati!
set "STATUS_OLLAMA=Installato"

:: ═══════════════════════════════════════════════════════════════════
:: STEP 5/5: COLLEGAMENTO DESKTOP
:: ═══════════════════════════════════════════════════════════════════
:STEP5_SHORTCUT
set "STEP_CURRENT=5"
echo.
echo  ================================================================
echo    STEP 5/%STEP_TOTAL%: Collegamento Desktop
echo  ================================================================
echo.

:: Rileva percorso Desktop reale dal registro (supporta OneDrive)
set "DESKTOP="
for /f "tokens=2*" %%a in ('reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul') do set "DESKTOP=%%b"
:: Espandi variabili nel percorso (es. %USERPROFILE%)
if defined DESKTOP call set "DESKTOP=!DESKTOP!"
:: Fallback
if not defined DESKTOP set "DESKTOP=%USERPROFILE%\Desktop"

set "SHORTCUT_NAME=OffGallery"

:: Verifica che il Launcher esista
if not exist "!LAUNCHER!" (
    echo   [!!] File Launcher non trovato: !LAUNCHER!
    echo       Puoi creare il collegamento manualmente.
    set "STATUS_SHORTCUT=Fallito"
    goto :SUMMARY
)

echo   Creazione collegamento "!SHORTCUT_NAME!" sul Desktop...
echo.

powershell -NoProfile -Command "& { try { $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('!DESKTOP!\!SHORTCUT_NAME!.lnk'); $s.TargetPath = '!LAUNCHER!'; $s.WorkingDirectory = '!APP_ROOT!'; $s.Description = 'Avvia OffGallery - Catalogazione foto AI offline'; $s.Save(); Write-Host '  [OK] Collegamento creato sul Desktop.' } catch { Write-Host '  [ERRORE]' $_.Exception.Message; exit 1 } }"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [!!] Creazione collegamento fallita.
    echo   Puoi copiare manualmente il file sul Desktop:
    echo   !LAUNCHER!
    set "STATUS_SHORTCUT=Fallito"
) else (
    set "STATUS_SHORTCUT=Creato"
)

:: ═══════════════════════════════════════════════════════════════════
:: Crea cartelle di lavoro necessarie all'app (escluse da git)
:: ═══════════════════════════════════════════════════════════════════
if not exist "!APP_ROOT!\database" mkdir "!APP_ROOT!\database"
if not exist "!APP_ROOT!\INPUT"    mkdir "!APP_ROOT!\INPUT"
if not exist "!APP_ROOT!\logs"     mkdir "!APP_ROOT!\logs"

:: ═══════════════════════════════════════════════════════════════════
:: RIEPILOGO FINALE
:: ═══════════════════════════════════════════════════════════════════
:SUMMARY
echo.
echo  ================================================================
echo.
echo              INSTALLAZIONE COMPLETATA
echo.
echo  ================================================================
echo.
echo   Riepilogo:
echo.
echo     Miniconda:          !STATUS_MINICONDA!
echo     Ambiente Python:    !STATUS_ENV!
echo     Librerie Python:    !STATUS_PACKAGES! ^(PyTorch: !PYTORCH_VARIANT!^)
echo     Ollama:             !STATUS_OLLAMA!
echo     Collegamento:       !STATUS_SHORTCUT!
echo.
echo  ----------------------------------------------------------------
echo.
echo   IMPORTANTE - PRIMO AVVIO:
echo.
echo   Al primo avvio, OffGallery scarichera' automaticamente
echo   circa 7 GB di modelli AI. Questo e' normale e avviene
echo   una sola volta:
echo.
echo     - CLIP (ricerca semantica):           ~580 MB
echo     - DINOv2 (similarita' visiva):        ~330 MB
echo     - Aesthetic (valutazione estetica):   ~1.6 GB
echo     - BioCLIP + TreeOfLife (natura):      ~4.2 GB
echo     - Argos Translate (traduzione):       ~92 MB
echo.
echo   Dopo il primo avvio, l'app funzionera' completamente OFFLINE.
echo.
echo  ----------------------------------------------------------------
echo.
echo   PER AVVIARE OFFGALLERY:
echo.
echo     Doppio click su "OffGallery" sul Desktop
echo     oppure esegui: installer\OffGallery_Launcher.bat
echo.
echo   NOTA: Se hai appena installato Miniconda, potrebbe essere
echo   necessario riavviare il computer prima del primo avvio.
echo.
echo  ================================================================
echo.
pause
goto :END

:: ═══════════════════════════════════════════════════════════════════
:: GESTIONE USCITE
:: ═══════════════════════════════════════════════════════════════════
:END_CANCELLED
echo.
echo   Installazione annullata dall'utente.
echo.
pause
goto :END

:END_ERROR
echo.
echo  ----------------------------------------------------------------
echo   Installazione interrotta per errore allo step !STEP_CURRENT!.
echo.
echo   Puoi rieseguire questo wizard: gli step gia' completati
echo   verranno rilevati automaticamente e saltati.
echo  ----------------------------------------------------------------
echo.
pause
goto :END

:END
endlocal
exit /b 0
