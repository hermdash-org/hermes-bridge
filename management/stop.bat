@echo off
REM Stop Hermes Runtime on Windows

echo Stopping Hermes Runtime...

taskkill /F /IM hermes-runtime.exe >nul 2>&1

if %ERRORLEVEL% EQU 0 (
    echo Hermes stopped
) else (
    echo Hermes is not running
)
