@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: NeuroScraper Pro - Auto Installer and Launcher
:: ============================================================

title NeuroScraper Pro - Launcher
color 0A

echo.
echo ============================================================
echo         NeuroScraper Pro - Auto Installer ^& Launcher
echo ============================================================
echo.

:: ====================
:: Step 1: Find Python 3.12
:: ====================
echo [1/4] Finding Python 3.12...

set "PYTHON_EXE="
set "PYTHON_FOUND=0"

:: Attempt 1: py launcher with version 3.12
py -3.12 --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON_EXE=py -3.12"
    set "PYTHON_FOUND=1"
    echo [OK] Found Python via py launcher
    py -3.12 --version
    goto :python_found
)

:: Attempt 2: Standard Python 3.12 installation path
set "PYTHON_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
if exist "!PYTHON_PATH!" (
    set "PYTHON_EXE=!PYTHON_PATH!"
    set "PYTHON_FOUND=1"
    echo [OK] Found Python in AppData
    "!PYTHON_PATH!" --version
    goto :python_found
)

:: Attempt 3: Python 3.12 in Program Files
set "PYTHON_PATH=C:\Program Files\Python312\python.exe"
if exist "!PYTHON_PATH!" (
    set "PYTHON_EXE=!PYTHON_PATH!"
    set "PYTHON_FOUND=1"
    echo [OK] Found Python in Program Files
    "!PYTHON_PATH!" --version
    goto :python_found
)

:: Attempt 4: Any Python version via py launcher (fallback)
py --version >nul 2>&1
if !errorlevel! equ 0 (
    echo [!] Python 3.12 not found, but found another Python:
    py --version
    echo.
    echo [?] Use this version? (may be unstable)
    choice /C YN /M "Continue"
    if !errorlevel! equ 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_FOUND=1"
        goto :python_found
    ) else (
        goto :python_not_found
    )
)

:: Attempt 5: python in PATH
python --version >nul 2>&1
if !errorlevel! equ 0 (
    echo [!] Python 3.12 not found, but found system Python:
    python --version
    echo.
    echo [?] Use this version? (may be unstable)
    choice /C YN /M "Continue"
    if !errorlevel! equ 1 (
        set "PYTHON_EXE=python"
        set "PYTHON_FOUND=1"
        goto :python_found
    ) else (
        goto :python_not_found
    )
)

:python_not_found
color 0C
echo.
echo [ERROR] Python not found!
echo.
echo Please install Python 3.12:
echo https://www.python.org/downloads/release/python-3120/
echo.
echo Make sure to check during installation:
echo - "Add Python to PATH"
echo - "Install py launcher"
echo.
pause
exit /b 1

:python_found
echo.

:: ====================
:: Step 2: Create virtual environment
:: ====================
echo [2/4] Checking virtual environment...

if exist ".venv\Scripts\activate.bat" (
    echo [OK] Virtual environment already exists
) else (
    echo [->] Creating virtual environment .venv...
    %PYTHON_EXE% -m venv .venv
    if !errorlevel! neq 0 (
        color 0C
        echo [ERROR] Failed to create virtual environment!
        echo.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)
echo.

:: ====================
:: Step 3: Activate environment and install dependencies
:: ====================
echo [3/4] Installing dependencies...

call .venv\Scripts\activate.bat

if !errorlevel! neq 0 (
    color 0C
    echo [ERROR] Failed to activate virtual environment!
    echo.
    pause
    exit /b 1
)

echo [->] Updating pip...
python -m pip install --upgrade pip --quiet
if !errorlevel! neq 0 (
    echo [!] Warning: Failed to update pip, continuing...
)

echo [->] Installing libraries from requirements.txt...
pip install -r requirements.txt
if !errorlevel! neq 0 (
    color 0C
    echo.
    echo [ERROR] Failed to install dependencies!
    echo.
    echo Check requirements.txt file and internet connection.
    echo.
    pause
    exit /b 1
)

echo [OK] All dependencies installed
echo.

:: ====================
:: Step 4: Check .env and run bot
:: ====================
echo [4/4] Starting bot...

if not exist ".env" (
    color 0E
    echo.
    echo [!] WARNING: .env file not found!
    echo.
    echo Create .env file based on .env.example and fill in:
    echo - BOT_TOKEN (from @BotFather)
    echo - ADMIN_ID (your Telegram ID)
    echo - API_ID and API_HASH (from https://my.telegram.org)
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo                  NeuroScraper Pro Started!
echo            Press Ctrl+C to stop
echo ============================================================
echo.

python main.py

:: Handle program exit
if !errorlevel! neq 0 (
    color 0C
    echo.
    echo ============================================================
    echo                    EXECUTION ERROR!
    echo ============================================================
    echo.
    echo Bot exited with error (code: !errorlevel!)
    echo Check logs above for diagnostics.
    echo.
) else (
    color 0A
    echo.
    echo ============================================================
    echo              Bot finished successfully
    echo ============================================================
    echo.
)

pause
