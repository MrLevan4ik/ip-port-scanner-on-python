@echo off
chcp 65001 >nul
title Proxy Scanner - CLI

cd /d "%~dp0\.."

echo ============================================
echo   Proxy Scanner - CLI Mode
echo ============================================
echo.

python main.py %*

echo.
echo ============================================
echo   Нажмите любую клавишу для выхода...
echo ============================================
pause >nul
