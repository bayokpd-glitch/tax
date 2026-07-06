@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Local Python environment not found.
  echo Create it with:
  echo   "C:\Users\Lenovo Thinkpad X1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

set "NLTK_DATA=%CD%\.venv\nltk_data"
".venv\Scripts\python.exe" "avatar_tax_gui.py"

if errorlevel 1 pause
