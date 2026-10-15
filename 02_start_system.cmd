@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Install dependencies as described in README.md first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "scripts\desktop.py" start
if errorlevel 1 (
    pause
    exit /b 1
)
exit /b 0
