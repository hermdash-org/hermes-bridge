#!/bin/bash
# Stop Hermes Runtime

echo "🛑 Stopping Hermes Runtime..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac: Stop LaunchAgent
    launchctl unload "$HOME/Library/LaunchAgents/com.hermes.runtime.plist" 2>/dev/null
    echo "✅ Hermes stopped"
else
    # Linux: Stop systemd service
    systemctl --user stop hermes-runtime.service 2>/dev/null
    echo "✅ Hermes stopped"
fi
