@echo off
REM Check Hermes Runtime status on Windows

echo Hermes Runtime Status
echo ========================================

tasklist /FI "IMAGENAME eq hermes-runtime.exe" 2>NUL | find /I /N "hermes-runtime.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Status: Running
    echo Access at: http://localhost:8521
) else (
    echo Status: Stopped
)
