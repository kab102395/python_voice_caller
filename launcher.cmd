@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python or run launcher.py from a terminal.
  pause
  exit /b 1
)

python launcher.py
set "exitcode=%errorlevel%"
if not "%exitcode%"=="0" (
  echo.
  echo Launcher exited with code %exitcode%.
  pause
)

endlocal
exit /b %exitcode%
