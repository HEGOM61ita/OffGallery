@echo off
:: OffGallery - Aggiornamento automatico (Windows)
:: Doppio clic per aggiornare OffGallery all'ultima versione.

cd /d "%~dp0"

:: Cerca Python nell'ambiente conda OffGallery
set CONDA_ROOT=
set PYTHON_EXE=

:: Prova percorsi comuni di Miniconda/Anaconda
for %%P in (
    "%USERPROFILE%\miniconda3\envs\OffGallery\python.exe"
    "%USERPROFILE%\anaconda3\envs\OffGallery\python.exe"
    "C:\miniconda3\envs\OffGallery\python.exe"
    "C:\anaconda3\envs\OffGallery\python.exe"
    "C:\ProgramData\miniconda3\envs\OffGallery\python.exe"
    "C:\ProgramData\anaconda3\envs\OffGallery\python.exe"
    "%~d0\miniconda3\envs\OffGallery\python.exe"
    "%~d0\anaconda3\envs\OffGallery\python.exe"
) do (
    if exist %%P (
        set PYTHON_EXE=%%P
        goto :found
    )
)

echo [ERRORE] Ambiente conda OffGallery non trovato.
echo Assicurati che OffGallery sia installato correttamente.
pause
exit /b 1

:found
echo Avvio aggiornamento OffGallery...
echo.
"%PYTHON_EXE%" "%~dp0update.py"

if errorlevel 1 (
    echo.
    echo [ERRORE] Aggiornamento terminato con errore.
    pause
)
