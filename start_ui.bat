@echo off
setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=UTF8"
set "UV_PROJECT_ENVIRONMENT=%CD%\.uv-env"

if exist ".uv-env\Scripts\python.exe" (
  ".uv-env\Scripts\python.exe" ui.py
  if not errorlevel 1 goto :end
)

where uv >nul 2>nul
if not errorlevel 1 (
  uv run python ui.py
  if errorlevel 1 pause
  goto :end
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" ui.py
  if errorlevel 1 pause
  goto :end
)

where python >nul 2>nul
if not errorlevel 1 (
  python ui.py
  if errorlevel 1 pause
  goto :end
)

where py >nul 2>nul
if not errorlevel 1 (
  py ui.py
  if errorlevel 1 pause
  goto :end
)

echo No uv or Python launcher found. Install uv, or run: uv run python ui.py
pause

:end
endlocal
