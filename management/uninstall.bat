@echo off
REM Uninstall Hermes Runtime on Windows

echo Uninstalling Hermes Runtime...

set INSTALL_DIR=%LOCALAPPDATA%\Hermes
set STARTUP_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Hermes Runtime.lnk

REM Stop runtime
taskkill /F /IM hermes-runtime.exe >nul 2>&1

REM Remove startup link
if exist "%STARTUP_LINK%" (
    del "%STARTUP_LINK%"
)

REM Remove installation directory
if exist "%INSTALL_DIR%" (
    rmdir /S /Q "%INSTALL_DIR%"
)

echo Hermes uninstalled
echo.
echo User data preserved at: %USERPROFILE%\.hermes
echo To remove data: rmdir /S /Q "%USERPROFILE%\.hermes"
