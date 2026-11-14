@echo off
cd /d "%~dp0"
start "Landslide Backend :8000" /D "%~dp0" cmd /k "%~dp0start-backend.bat"
start "Landslide Frontend :5173" /D "%~dp0" cmd /k "%~dp0start-frontend.bat"
exit
