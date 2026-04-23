#!/bin/bash
# Check Hermes Runtime status

echo "📊 Hermes Runtime Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac: Check LaunchAgent
    if launchctl list | grep -q "com.hermes.runtime"; then
        echo "✅ Status: Running"
        echo "📍 Access at: http://localhost:8521"
    else
        echo "❌ Status: Stopped"
    fi
else
    # Linux: Check systemd service
    if systemctl --user is-active --quiet hermes-runtime.service; then
        echo "✅ Status: Running"
        echo "📍 Access at: http://localhost:8521"
        echo ""
        systemctl --user status hermes-runtime.service --no-pager
    else
        echo "❌ Status: Stopped"
    fi
fi
