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

# Create install directory
mkdir -p "$INSTALL_DIR"

# Download runtime
echo "📥 Downloading..."
curl -L "$BINARY_URL" -o "$INSTALL_DIR/hermes-runtime"
chmod +x "$INSTALL_DIR/hermes-runtime"

# Start in background
nohup "$INSTALL_DIR/hermes-runtime" > /dev/null 2>&1 &

# Add to startup (auto-start on boot)
if [[ "$OSTYPE" == "darwin"* ]]; then
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
    launchctl load "$HOME/Library/LaunchAgents/com.hermes.runtime.plist" 2>/dev/null || true
else
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$HOME/.config/systemd/user/hermes-runtime.service" <<EOF
[Unit]
Description=Hermes Runtime
After=network.target

[Service]
ExecStart=$INSTALL_DIR/hermes-runtime
Restart=always

[Install]
WantedBy=default.target
EOF
    systemctl --user enable hermes-runtime.service 2>/dev/null || true
    systemctl --user start hermes-runtime.service 2>/dev/null || true
fi

echo ""
echo "✅ Hermes installed!"
echo "🌐 Open hermdash.com to get started"
echo ""
