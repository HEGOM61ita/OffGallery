@echo off
:: Build script per OffGallery Manager (Windows)
:: Richiede: pip install pyinstaller
::
:: Uso: doppio click su build.bat
::      oppure: build.bat
::
:: Output: dist\OffGallerySetup.exe

setlocal
cd /d "%~dp0"

echo.
echo  OffGallery Manager -- Build
echo  ============================
echo.

:: Verifica pyinstaller
python -m pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [!!] PyInstaller non trovato. Installalo con:
    echo      pip install pyinstaller
    pause
    exit /b 1
)

:: Pulisci build precedente
if exist dist\OffGallerySetup.exe (
    echo [..] Rimozione build precedente...
    del /q dist\OffGallerySetup.exe
)
if exist build\ (
    rmdir /s /q build
)

:: Build
echo [..] Build in corso...
python -m pyinstaller OffGallerySetup.spec

if errorlevel 1 (
    echo.
    echo [!!] Build fallita. Controlla gli errori sopra.
    pause
    exit /b 1
)

:: Risultato
echo.
echo [OK] Build completata.
echo      File: dist\OffGallerySetup.exe
for %%I in (dist\OffGallerySetup.exe) do echo      Dimensione: %%~zI byte
echo.

:: Test rapido avvio
set /p LAUNCH="Avviare OffGallerySetup.exe per testare? (S/N): "
if /i "%LAUNCH%"=="S" (
    start "" "dist\OffGallerySetup.exe"
)

pause
