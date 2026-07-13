@echo off
chcp 65001 >nul
title Proxy Scanner - Build Executable

cd /d "%~dp0\.."

echo ============================================
echo   Proxy Scanner - Build .exe
echo ============================================
echo.

:: Проверка PyInstaller
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] PyInstaller не найден. Установка...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [ERROR] Не удалось установить PyInstaller!
        pause
        exit /b 1
    )
)

echo [1/2] Сборка CLI версии (proxy_scanner.exe)...
pyinstaller --onefile --name proxy_scanner --clean --noconfirm ^
    --add-data "proxies;proxies" ^
    --hidden-import socks ^
    --hidden-import requests ^
    --hidden-import urllib3 ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Ошибка сборки!
    pause
    exit /b 1
)

echo.
echo [2/2] Сборка GUI версии (proxy_scanner_gui.exe)...
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
    echo [WARNING] Сборка GUI не удалась. PyQt6 установлен?
    echo Установите: pip install PyQt6
)

echo.
echo ============================================
echo   Сборка завершена!
echo   Файлы в папке: dist\
echo     proxy_scanner.exe      - CLI версия
echo     proxy_scanner_gui.exe  - GUI версия
echo ============================================
echo.
pause
