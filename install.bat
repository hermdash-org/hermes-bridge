@echo off
setlocal enabledelayedexpansion

echo Installing Hermes Runtime...

set INSTALL_DIR=%LOCALAPPDATA%\Hermes
set R2_BASE=https://dl.hermdash.com
set BINARY_URL=%R2_BASE%/windows.exe

:: Create install directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Download runtime using curl (built into Windows 10+)
echo Downloading runtime...
curl -L "%BINARY_URL%" -o "%INSTALL_DIR%\hermes-runtime.exe"

if not exist "%INSTALL_DIR%\hermes-runtime.exe" (
    echo Download failed. Trying with PowerShell...
    powershell -Command "Invoke-WebRequest -Uri '%BINARY_URL%' -OutFile '%INSTALL_DIR%\hermes-runtime.exe'"
)

:: Download management scripts
echo Installing management tools...
if not exist "%INSTALL_DIR%\management" mkdir "%INSTALL_DIR%\management"
set MGMT_BASE=%R2_BASE%/management
for %%s in (stop.bat start.bat restart.bat status.bat uninstall.bat README.md) do (
    curl -sL "%MGMT_BASE%/%%s" -o "%INSTALL_DIR%\management\%%s" 2>nul
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
echo.
echo Management commands:
echo   Stop:      %INSTALL_DIR%\management\stop.bat
echo   Start:     %INSTALL_DIR%\management\start.bat
echo   Restart:   %INSTALL_DIR%\management\restart.bat
echo   Status:    %INSTALL_DIR%\management\status.bat
echo   Uninstall: %INSTALL_DIR%\management\uninstall.bat
