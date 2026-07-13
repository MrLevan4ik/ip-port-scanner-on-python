@echo off
chcp 65001 >nul
title Proxy Scanner - Clean Build Files

cd /d "%~dp0\.."

echo ============================================
echo   Proxy Scanner - Clean Build Files
echo ============================================
echo.

echo Удаление build/...
if exist build rmdir /s /q build

echo Удаление dist/...
if exist dist rmdir /s /q dist

echo Удаление *.spec...
del /q *.spec 2>nul

echo Удаление __pycache__/...
for /d /r %%d in (__pycache__) do if exist "%%d" rmdir /s /q "%%d"

echo.
echo ============================================
echo   Готово! Временные файлы удалены.
echo ============================================
echo.
pause
