@echo off
REM Restart Hermes Runtime on Windows

echo Restarting Hermes Runtime...

REM Stop
taskkill /F /IM hermes-runtime.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Start
set INSTALL_DIR=%LOCALAPPDATA%\Hermes
powershell -WindowStyle Hidden -Command "Start-Process -FilePath '%INSTALL_DIR%\hermes-runtime.exe' -WindowStyle Hidden"

echo Hermes restarted
echo Access at: http://localhost:8521
