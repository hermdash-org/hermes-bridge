#!/bin/bash
set -e

echo "🚀 Installing Hermes Runtime..."

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    BINARY_URL="https://github.com/devops-vaults/hermes/releases/latest/download/mac"
    INSTALL_DIR="$HOME/Library/Application Support/Hermes"
else
    BINARY_URL="https://github.com/devops-vaults/hermes/releases/latest/download/linux"
    INSTALL_DIR="$HOME/.local/share/hermes"
fi

# Create install directory
mkdir -p "$INSTALL_DIR"

# Download runtime
echo "📥 Downloading runtime..."
curl -L "$BINARY_URL" -o "$INSTALL_DIR/hermes-runtime"
chmod +x "$INSTALL_DIR/hermes-runtime"

# Run in background
echo "🔄 Starting Hermes..."
nohup "$INSTALL_DIR/hermes-runtime" > /dev/null 2>&1 &

# Add to startup
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac: Create LaunchAgent
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
    # Linux: Create systemd user service
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

echo "✅ Hermes installed and running!"
echo "📍 Access at: http://localhost:8521"
echo "🔄 Will auto-start on boot"