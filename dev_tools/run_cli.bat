@echo off
title Proxy Scanner - CLI

cd /d "%~dp0\.."

echo ============================================
echo   Proxy Scanner - CLI Mode
echo ============================================
echo.

python main.py %*

echo.
echo ============================================
echo   Press any key to exit...
echo ============================================
pause >nul
