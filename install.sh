#!/bin/bash
set -e

echo "🚀 Installing Hermes..."

# Detect OS
R2_BASE="https://dl.hermdash.com"

if [[ "$OSTYPE" == "darwin"* ]]; then
    BINARY_URL="$R2_BASE/mac"
    INSTALL_DIR="$HOME/Library/Application Support/Hermes"
else
    BINARY_URL="$R2_BASE/linux"
    INSTALL_DIR="$HOME/.local/share/hermes"
fi

# Kill any existing hermes-runtime processes (clean slate)
pkill -f hermes-runtime 2>/dev/null || true
sleep 1

# Create install directory
mkdir -p "$INSTALL_DIR"

# Download runtime (cache-busting to avoid CDN serving stale binary)
echo "📥 Downloading..."
curl -L -H "Cache-Control: no-cache" "$BINARY_URL?t=$(date +%s)" -o "$INSTALL_DIR/hermes-runtime"
chmod +x "$INSTALL_DIR/hermes-runtime"

# Set up as a managed service (NOT nohup — so auto-update can restart it)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: launchctl (managed by launchd)
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$HOME/Library/LaunchAgents/com.hermes.runtime.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hermes.runtime</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/hermes-runtime</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF
    launchctl unload "$HOME/Library/LaunchAgents/com.hermes.runtime.plist" 2>/dev/null || true
    launchctl load "$HOME/Library/LaunchAgents/com.hermes.runtime.plist"
else
    # Linux: systemd user service (managed — auto-update can restart it)
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$HOME/.config/systemd/user/hermes-runtime.service" <<EOF
[Unit]
Description=Hermes Runtime
# STABILITY FIX #2: Wait for network to be ONLINE, not just "up"
# Previously: After=network.target (network stack initialized, but no connectivity)
# Now: After=network-online.target (actual internet connectivity verified)
# This prevents startup failures when auto-update tries to check for updates before network is ready
After=network-online.target
Wants=network-online.target
StartLimitBurst=5
StartLimitIntervalSec=60

[Service]
ExecStart=$INSTALL_DIR/hermes-runtime
Restart=always
RestartSec=5
TimeoutStopSec=5
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable hermes-runtime.service
    systemctl --user restart hermes-runtime.service
fi

echo ""
echo "✅ Hermes installed!"
echo "🌐 Open hermdash.com to get started"
echo ""
