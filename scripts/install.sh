#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
# Hermes Dashboard — One-line installer
#
# Usage: curl -fsSL hermesdashboard.com/install | bash
#
# What it does:
#   1. Installs Docker Engine if missing (no Docker Desktop GUI)
#   2. Pulls the pre-built hermes-dashboard image
#   3. Runs it in background with auto-restart + auto-update
# ─────────────────────────────────────────────────────────────────────

set -e

IMAGE="devopsvaults/hermes-dashboard:latest"
CONTAINER="hermes-dashboard"
PORT=8521

echo "════════════════════════════════════════════════"
echo "  Hermes Dashboard — Installer"
echo "════════════════════════════════════════════════"

# ── Step 1: Install Docker if missing ───────────────────────────────

if ! command -v docker &>/dev/null; then
    echo "⏳ Installing Docker..."

    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl -fsSL https://get.docker.com | sh
        sudo systemctl enable --now docker
        sudo usermod -aG docker "$USER"
        echo "✅ Docker installed (Linux)"

    elif [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            brew install colima docker docker-compose
            colima start --memory 4 --cpu 2
            echo "✅ Docker installed via Colima (macOS)"
        else
            echo "❌ Install Homebrew first: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            exit 1
        fi
    else
        echo "❌ Unsupported OS. Use the Windows installer: irm hermesdashboard.com/install.ps1 | iex"
        exit 1
    fi
else
    echo "✅ Docker already installed"
fi

# ── Step 2: Start Docker if not running ─────────────────────────────

if ! docker info &>/dev/null; then
    echo "⏳ Starting Docker..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        colima start 2>/dev/null || true
    else
        sudo systemctl start docker 2>/dev/null || true
    fi
    sleep 3
fi

# ── Step 3: Stop old container if running ───────────────────────────

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "⏳ Removing old container..."
    docker stop "$CONTAINER" 2>/dev/null || true
    docker rm "$CONTAINER" 2>/dev/null || true
fi

# ── Step 4: Pull + run ──────────────────────────────────────────────

echo "⏳ Pulling latest image..."
docker pull "$IMAGE"

echo "⏳ Starting Hermes Dashboard..."
mkdir -p "$HOME/.hermes"

docker run -d \
    --name "$CONTAINER" \
    --restart=always \
    -p ${PORT}:${PORT} \
    -v "$HOME/.hermes:/opt/data" \
    -v "$HOME:/opt/data/user-home" \
    "$IMAGE"

# ── Step 5: Start auto-updater (Watchtower) ─────────────────────────

if ! docker ps --format '{{.Names}}' | grep -q "^watchtower$"; then
    echo "⏳ Setting up auto-updates..."
    docker run -d \
        --name watchtower \
        --restart=always \
        -v /var/run/docker.sock:/var/run/docker.sock \
        containrrr/watchtower \
        --cleanup --interval 300 "$CONTAINER"
fi

echo ""
echo "════════════════════════════════════════════════"
echo "  ✅ Hermes Dashboard is running!"
echo ""
echo "  Open: https://hermesdashboard.com"
echo "  Port: localhost:${PORT}"
echo "  Data: ~/.hermes/"
echo ""
echo "  Auto-updates: ON (checks every 5 min)"
echo "  Auto-start:   ON (starts on boot)"
echo "════════════════════════════════════════════════"
