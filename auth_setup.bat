@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title NeuroScraper Pro - Session Setup
color 0B

echo.
echo ============================================================
echo         NeuroScraper Pro - Session Authorization
echo ============================================================
echo.

:: Check virtual environment
if not exist ".venv\Scripts\activate.bat" (
    color 0C
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please run run_bot.bat first to create the environment.
    echo.
    pause
    exit /b 1
)

:: Activate environment
call .venv\Scripts\activate.bat

:: Run authorization script
python auth.py

pause
