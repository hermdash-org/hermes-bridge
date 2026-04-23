#!/bin/bash
# Start Hermes Runtime

echo "▶️  Starting Hermes Runtime..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac: Start LaunchAgent
    launchctl load "$HOME/Library/LaunchAgents/com.hermes.runtime.plist" 2>/dev/null
    echo "✅ Hermes started"
    echo "📍 Access at: http://localhost:8521"
else
    # Linux: Start systemd service
    systemctl --user start hermes-runtime.service 2>/dev/null
    echo "✅ Hermes started"
    echo "📍 Access at: http://localhost:8521"
fi
