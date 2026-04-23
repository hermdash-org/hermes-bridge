#!/bin/bash
set -e

echo "🚀 Installing Hermes Runtime..."

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
echo "📥 Downloading runtime..."
curl -L "$BINARY_URL" -o "$INSTALL_DIR/hermes-runtime"
chmod +x "$INSTALL_DIR/hermes-runtime"

# Download management scripts
echo "📦 Installing management tools..."
mkdir -p "$INSTALL_DIR/management"
MGMT_BASE="$R2_BASE/management"
for script in stop.sh start.sh restart.sh status.sh uninstall.sh README.md; do
    curl -sL "$MGMT_BASE/$script" -o "$INSTALL_DIR/management/$script" 2>/dev/null || true
    [ -f "$INSTALL_DIR/management/$script" ] && chmod +x "$INSTALL_DIR/management/$script" 2>/dev/null || true
done

# Run in background
echo "🔄 Starting Hermes..."
nohup "$INSTALL_DIR/hermes-runtime" > /dev/null 2>&1 &

# Add to startup
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

# Create system-wide commands
echo "🔗 Creating system-wide commands..."
mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/hermdash" <<WRAPPER
#!/bin/bash
bash "$INSTALL_DIR/management/status.sh"
WRAPPER

cat > "$HOME/.local/bin/hermdash-stop" <<WRAPPER
#!/bin/bash
bash "$INSTALL_DIR/management/stop.sh"
WRAPPER

cat > "$HOME/.local/bin/hermdash-start" <<WRAPPER
#!/bin/bash
bash "$INSTALL_DIR/management/start.sh"
WRAPPER

cat > "$HOME/.local/bin/hermdash-restart" <<WRAPPER
#!/bin/bash
bash "$INSTALL_DIR/management/restart.sh"
WRAPPER

cat > "$HOME/.local/bin/hermdash-status" <<WRAPPER
#!/bin/bash
bash "$INSTALL_DIR/management/status.sh"
WRAPPER

cat > "$HOME/.local/bin/hermdash-uninstall" <<WRAPPER
#!/bin/bash
bash "$INSTALL_DIR/management/uninstall.sh"
WRAPPER

chmod +x "$HOME/.local/bin/hermdash"*

# Add to PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ -f "$rc" ]; then
            if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$rc"; then
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
            fi
        fi
    done
    export PATH="$HOME/.local/bin:$PATH"
fi

echo ""
echo "✅ Hermes installed and running!"
echo "📍 Access at: http://localhost:8521"
echo ""
echo "📋 Commands (from anywhere):"
echo "   hermdash           - Check status"
echo "   hermdash-start     - Start"
echo "   hermdash-stop      - Stop"
echo "   hermdash-restart   - Restart"
echo "   hermdash-uninstall - Uninstall"
echo ""
echo "💡 Restart terminal or run: source ~/.bashrc"
