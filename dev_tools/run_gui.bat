@echo off
chcp 65001 >nul
title Proxy Scanner - GUI

cd /d "%~dp0\.."

echo ============================================
echo   Proxy Scanner - GUI Mode
echo ============================================
echo.

python main.py --gui

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Не удалось запустить GUI.
    echo Установите PyQt6: pip install PyQt6
    echo.
    pause
)
