@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create-desktop-shortcut.ps1"
if errorlevel 1 (
    echo.
    echo The shortcut could not be created.
    pause
    exit /b 1
)
echo.
pause
