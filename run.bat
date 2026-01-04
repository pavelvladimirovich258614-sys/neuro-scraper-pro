@echo off
chcp 65001 > nul
echo =====================================
echo   NeuroScraper Pro Bot Launcher
echo =====================================
echo.

:: Check if venv exists
if not exist "venv\" (
    echo Virtual environment not found!
    echo Creating virtual environment...
    python -m venv venv
    echo.
    echo Installing dependencies...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo Starting bot...
echo.
python main.py

pause
