#!/bin/bash
# Restart Hermes Runtime

echo "🔄 Restarting Hermes Runtime..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac: Restart LaunchAgent
    launchctl unload "$HOME/Library/LaunchAgents/com.hermes.runtime.plist" 2>/dev/null
    sleep 1
    launchctl load "$HOME/Library/LaunchAgents/com.hermes.runtime.plist" 2>/dev/null
    echo "✅ Hermes restarted"
    echo "📍 Access at: http://localhost:8521"
else
    # Linux: Restart systemd service
    systemctl --user restart hermes-runtime.service 2>/dev/null
    echo "✅ Hermes restarted"
    echo "📍 Access at: http://localhost:8521"
fi
