@echo off
chcp 65001 >nul
title Proxy Scanner - Install Dependencies

echo ============================================
echo   Proxy Scanner - Install Dependencies
echo ============================================
echo.

:: Проверка Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python не найден!
    echo Установите Python: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/2] Установка базовых зависимостей...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Ошибка установки базовых зависимостей!
    pause
    exit /b 1
)

echo.
echo [2/2] Установка PyQt6 для GUI...
pip install PyQt6
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] PyQt6 не установлен. GUI режим недоступен.
    echo CLI режим работает без PyQt6.
)

echo.
echo ============================================
echo   Готово! Все зависимости установлены.
echo ============================================
echo.
pause
