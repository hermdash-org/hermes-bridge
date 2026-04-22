@echo off
setlocal enabledelayedexpansion

echo Installing Hermes Runtime...

set INSTALL_DIR=%LOCALAPPDATA%\Hermes
set BINARY_URL=https://github.com/devops-vaults/hermes/releases/latest/download/hermes-runtime.exe

:: Create install directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Download runtime using curl (built into Windows 10+)
echo Downloading runtime...
curl -L "%BINARY_URL%" -o "%INSTALL_DIR%\hermes-runtime.exe"

if not exist "%INSTALL_DIR%\hermes-runtime.exe" (
    echo Download failed. Trying with PowerShell...
    powershell -Command "Invoke-WebRequest -Uri '%BINARY_URL%' -OutFile '%INSTALL_DIR%\hermes-runtime.exe'"
)

:: Add to startup (run hidden)
echo Adding to startup...
set STARTUP_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%STARTUP_PATH%\Hermes Runtime.lnk'); $SC.TargetPath = 'powershell.exe'; $SC.Arguments = '-WindowStyle Hidden -Command \"Start-Process -FilePath \"\"%INSTALL_DIR%\hermes-runtime.exe\"\" -WindowStyle Hidden\"'; $SC.WindowStyle = 7; $SC.Save()"

:: Start now (hidden in background)
echo Starting Hermes...
powershell -WindowStyle Hidden -Command "Start-Process -FilePath '%INSTALL_DIR%\hermes-runtime.exe' -WindowStyle Hidden"

echo.
echo Hermes installed and running!
echo Access at: http://localhost:8521
echo Will auto-start on boot
