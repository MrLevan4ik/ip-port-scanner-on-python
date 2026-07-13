@echo off
title Proxy Scanner - GUI

cd /d "%~dp0\.."

echo ============================================
echo   Proxy Scanner - GUI Mode
echo ============================================
echo.

python main.py --gui

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start GUI.
    echo Install PyQt6: pip install PyQt6
    echo.
    pause
)
