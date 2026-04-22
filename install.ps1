Write-Host "🚀 Installing Hermes Runtime..." -ForegroundColor Green

$InstallDir = "$env:LOCALAPPDATA\Hermes"
$BinaryUrl = "https://github.com/devops-vaults/hermes/releases/latest/download/hermes-runtime.exe"

# Create install directory
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# Download runtime
Write-Host "📥 Downloading runtime..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $BinaryUrl -OutFile "$InstallDir\hermes-runtime.exe"

# Add to startup
Write-Host "🔄 Adding to startup..." -ForegroundColor Yellow
$StartupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$ShortcutPath = "$StartupPath\Hermes Runtime.lnk"
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$InstallDir\hermes-runtime.exe"
$Shortcut.Save()

# Start now
Write-Host "🔄 Starting Hermes..." -ForegroundColor Yellow
Start-Process -FilePath "$InstallDir\hermes-runtime.exe" -WindowStyle Hidden

Write-Host "✅ Hermes installed and running!" -ForegroundColor Green
Write-Host "📍 Access at: http://localhost:8521"
Write-Host "🔄 Will auto-start on boot"