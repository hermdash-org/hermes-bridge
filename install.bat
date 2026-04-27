@echo off
setlocal enabledelayedexpansion

echo Installing Hermes...

set INSTALL_DIR=%LOCALAPPDATA%\Hermes
set BINARY_URL=https://dl.hermdash.com/windows.exe

:: Create install directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Kill any existing hermes-runtime (clean slate)
taskkill /F /IM hermes-runtime.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: Download runtime (cache-busting to avoid CDN serving stale binary)
:: Use PowerShell directly (more reliable than curl on Windows)
echo Downloading...
set "TIMESTAMP=%date:~-4%%date:~-7,2%%date:~-10,2%%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%BINARY_URL%?t=%TIMESTAMP%' -OutFile '%INSTALL_DIR%\hermes-runtime.exe' -Headers @{'Cache-Control'='no-cache'}"

:: Add to startup (run hidden)
:: STABILITY NOTE: Windows Startup folder runs AFTER network is ready (unlike Linux systemd)
:: Combined with Fix #1 (non-blocking auto-update in runtime.py), this ensures reliable startup
set STARTUP_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%STARTUP_PATH%\Hermes Runtime.lnk'); $SC.TargetPath = 'powershell.exe'; $SC.Arguments = '-WindowStyle Hidden -Command \"Start-Process -FilePath \"\"' + $env:LOCALAPPDATA + '\Hermes\hermes-runtime.exe\"\" -WindowStyle Hidden\"'; $SC.WindowStyle = 7; $SC.Save()"

:: Start now (hidden)
powershell -WindowStyle Hidden -Command "Start-Process -FilePath '%INSTALL_DIR%\hermes-runtime.exe' -WindowStyle Hidden"

echo.
echo Hermes installed!
echo Open hermdash.com to get started
