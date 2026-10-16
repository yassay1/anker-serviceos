@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" "scripts\dev_launcher.py" %*
) else (
  python "scripts\dev_launcher.py" %*
)
if errorlevel 1 (
  echo.
  echo Startup did not complete. See .runtime\dev-launcher logs.
  pause
)
endlocal
