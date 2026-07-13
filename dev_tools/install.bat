@echo off
title Proxy Scanner - Install Dependencies

echo ============================================
echo   Proxy Scanner - Install Dependencies
echo ============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo Install Python: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/2] Installing base dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install base dependencies!
    pause
    exit /b 1
)

echo.
echo [2/2] Installing PyQt6 for GUI...
pip install PyQt6
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] PyQt6 not installed. GUI mode unavailable.
    echo CLI mode works without PyQt6.
)

echo.
echo ============================================
echo   Done! All dependencies installed.
echo ============================================
echo.
pause
