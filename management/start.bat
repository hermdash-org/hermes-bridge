@echo off
REM Start Hermes Runtime on Windows

echo Starting Hermes Runtime...

set INSTALL_DIR=%LOCALAPPDATA%\Hermes

if not exist "%INSTALL_DIR%\hermes-runtime.exe" (
    echo Error: Hermes not installed
    exit /b 1
)

REM Start hidden in background
powershell -WindowStyle Hidden -Command "Start-Process -FilePath '%INSTALL_DIR%\hermes-runtime.exe' -WindowStyle Hidden"

echo Hermes started
echo Access at: http://localhost:8521
