@echo off
title Landslide Backend :8000
cd /d "%~dp0backend"
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv\Scripts\activate.bat not found. Current dir: %CD%
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
echo Backend starting... http://127.0.0.1:8000
python -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
