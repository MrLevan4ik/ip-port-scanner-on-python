@echo off
title Proxy Scanner - Build Executable

cd /d "%~dp0\.."

echo ============================================
echo   Proxy Scanner - Build .exe
echo ============================================
echo.

pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] PyInstaller not found. Installing...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install PyInstaller!
        pause
        exit /b 1
    )
)

echo [1/2] Building CLI version (proxy_scanner.exe)...
pyinstaller --onefile --name proxy_scanner --clean --noconfirm ^
    --add-data "proxies;proxies" ^
    --hidden-import socks ^
    --hidden-import requests ^
    --hidden-import urllib3 ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [2/2] Building GUI version (proxy_scanner_gui.exe)...
pyinstaller --onefile --name proxy_scanner_gui --clean --noconfirm ^
    --windowed ^
    --add-data "proxies;proxies" ^
    --hidden-import socks ^
    --hidden-import requests ^
    --hidden-import urllib3 ^
    --hidden-import PyQt6 ^
    --hidden-import PyQt6.QtWidgets ^
    --hidden-import PyQt6.QtCore ^
    --hidden-import PyQt6.QtGui ^
    main.py --gui

if %errorlevel% neq 0 (
    echo.
    echo [WARNING] GUI build failed. Is PyQt6 installed?
    echo Install: pip install PyQt6
)

echo.
echo ============================================
echo   Build complete!
echo   Files in: dist\
echo     proxy_scanner.exe      - CLI version
echo     proxy_scanner_gui.exe  - GUI version
echo ============================================
echo.
pause
