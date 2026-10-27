@echo off
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo ===================================================================
echo   Starting Local Market Dashboard (http://127.0.0.1:8888) ...
echo ===================================================================

start "" http://127.0.0.1:8888
"%PYTHON_EXE%" web\server.py

pause
