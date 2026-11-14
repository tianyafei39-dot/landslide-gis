@echo off
title Landslide Frontend :5173
cd /d "%~dp0frontend"
if not exist "package.json" (
    echo [ERROR] package.json not found. Current dir: %CD%
    pause
    exit /b 1
)
echo Frontend starting... http://127.0.0.1:5173
echo /api and /static will proxy to backend port 8000
npm run dev
pause
