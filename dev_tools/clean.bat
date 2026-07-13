@echo off
title Proxy Scanner - Clean Build Files

cd /d "%~dp0\.."

echo ============================================
echo   Proxy Scanner - Clean Build Files
echo ============================================
echo.

echo Deleting build/...
if exist build rmdir /s /q build

echo Deleting dist/...
if exist dist rmdir /s /q dist

echo Deleting *.spec...
del /q *.spec 2>nul

echo Deleting __pycache__/...
for /d /r %%d in (__pycache__) do if exist "%%d" rmdir /s /q "%%d"

echo.
echo ============================================
echo   Done! Temp files removed.
echo ============================================
echo.
pause
