@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" "scripts\dev_launcher.py" --stop
) else (
  python "scripts\dev_launcher.py" --stop
)
if errorlevel 1 pause
endlocal
