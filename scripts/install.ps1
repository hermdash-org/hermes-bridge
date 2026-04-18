# ─────────────────────────────────────────────────────────────────────
# Hermes Dashboard — Windows One-line Installer
#
# Usage: irm hermesdashboard.com/install.ps1 | iex
#
# What it does:
#   1. Installs Docker via winget (no Docker Desktop GUI needed)
#   2. Pulls the pre-built hermes-dashboard image
#   3. Runs it in background with auto-restart + auto-update
# ─────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

$IMAGE = "devopsvaults/hermes-dashboard:latest"
$CONTAINER = "hermes-dashboard"
$PORT = 8420

Write-Host ""
Write-Host "════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Hermes Dashboard — Windows Installer" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Install Docker if missing ───────────────────────────────

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "⏳ Installing Docker Desktop via winget..." -ForegroundColor Yellow
    winget install Docker.DockerDesktop --silent --accept-package-agreements --accept-source-agreements
    Write-Host "✅ Docker installed" -ForegroundColor Green
    Write-Host ""
    Write-Host "⚠  Please restart your computer, then run this script again." -ForegroundColor Yellow
    Write-Host "   Docker Desktop needs a reboot to finish setup." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "✅ Docker already installed" -ForegroundColor Green
}

# ── Step 2: Check Docker is running ─────────────────────────────────

try {
    docker info 2>$null | Out-Null
} catch {
    Write-Host "⏳ Starting Docker..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 15
}

# ── Step 3: Stop old container if running ───────────────────────────

$existing = docker ps -a --format "{{.Names}}" 2>$null | Where-Object { $_ -eq $CONTAINER }
if ($existing) {
    Write-Host "⏳ Removing old container..." -ForegroundColor Yellow
    docker stop $CONTAINER 2>$null
    docker rm $CONTAINER 2>$null
}

# ── Step 4: Pull + run ──────────────────────────────────────────────

Write-Host "⏳ Pulling latest image..." -ForegroundColor Yellow
docker pull $IMAGE

Write-Host "⏳ Starting Hermes Dashboard..." -ForegroundColor Yellow

$hermesHome = "$env:USERPROFILE\.hermes"
if (-not (Test-Path $hermesHome)) {
    New-Item -ItemType Directory -Path $hermesHome -Force | Out-Null
}

docker run -d `
    --name $CONTAINER `
    --restart=always `
    -p "${PORT}:${PORT}" `
    -v "${hermesHome}:/opt/data" `
    -v "${env:USERPROFILE}:/opt/data/user-home" `
    $IMAGE

# ── Step 5: Start auto-updater (Watchtower) ─────────────────────────

$wt = docker ps --format "{{.Names}}" 2>$null | Where-Object { $_ -eq "watchtower" }
if (-not $wt) {
    Write-Host "⏳ Setting up auto-updates..." -ForegroundColor Yellow
    docker run -d `
        --name watchtower `
        --restart=always `
        -v //var/run/docker.sock:/var/run/docker.sock `
        containrrr/watchtower `
        --cleanup --interval 300 $CONTAINER
}

Write-Host ""
Write-Host "════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ Hermes Dashboard is running!" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "  Open: https://hermesdashboard.com" -ForegroundColor White
Write-Host "  Port: localhost:$PORT" -ForegroundColor White
Write-Host "  Data: $hermesHome" -ForegroundColor White
Write-Host "" -ForegroundColor White
Write-Host "  Auto-updates: ON (checks every 5 min)" -ForegroundColor White
Write-Host "  Auto-start:   ON (starts on boot)" -ForegroundColor White
Write-Host "════════════════════════════════════════════════" -ForegroundColor Green
