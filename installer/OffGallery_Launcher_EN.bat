@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ═══════════════════════════════════════════════════════════════
:: OffGallery Launcher
:: Starts OffGallery by automatically locating conda
:: ═══════════════════════════════════════════════════════════════

set "OFFGALLERY_PATH=%~dp0.."
set "ENV_NAME=OffGallery"

:: --- Search for conda in multiple locations ---
set "CONDA_CMD="

:: 1. conda in PATH
where conda >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "CONDA_CMD=conda"
    goto :CONDA_FOUND
)

:: 2. Known Miniconda paths
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

:: 3. Known Anaconda paths
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

:: Conda not found
echo.
echo   [ERROR] Conda not found.
echo.
echo   Paths searched:
echo     - System PATH
echo     - %USERPROFILE%\miniconda3
echo     - %LOCALAPPDATA%\miniconda3
echo.
echo   If you just installed Miniconda, restart your computer.
echo   Otherwise run INSTALL_OffGallery_EN.bat
echo.
pause
exit /b 1

:CONDA_FOUND

:: Go to the app folder and launch with conda run
cd /d "%OFFGALLERY_PATH%"
call "!CONDA_CMD!" run -n %ENV_NAME% python gui_launcher.py

:: If the app crashes, show the error
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERROR] The application closed with an error.
    echo.
    pause
)

endlocal
