@echo off
setlocal
cd /d "%~dp0"

where pyw.exe >nul 2>&1
if %errorlevel%==0 (
    start "" pyw.exe -3 "%~dp0app.py"
    exit /b 0
)

where pythonw.exe >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw.exe "%~dp0app.py"
    exit /b 0
)

echo Python was not found.
echo Install Python from https://www.python.org/downloads/ and enable "Add Python to PATH".
pause
