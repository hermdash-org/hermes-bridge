#!/bin/bash
# Uninstall Hermes Runtime completely

echo "🗑️  Uninstalling Hermes Runtime..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    INSTALL_DIR="$HOME/Library/Application Support/Hermes"
    
    # Stop and remove LaunchAgent
    launchctl unload "$HOME/Library/LaunchAgents/com.hermes.runtime.plist" 2>/dev/null
    rm -f "$HOME/Library/LaunchAgents/com.hermes.runtime.plist"
    
    # Remove binary
    rm -rf "$INSTALL_DIR"
    
    echo "✅ Hermes uninstalled"
    echo "⚠️  User data preserved at: ~/.hermes"
    echo "   To remove data: rm -rf ~/.hermes"
else
    INSTALL_DIR="$HOME/.local/share/hermes"
    
    # Stop and disable systemd service
    systemctl --user stop hermes-runtime.service 2>/dev/null
    systemctl --user disable hermes-runtime.service 2>/dev/null
    rm -f "$HOME/.config/systemd/user/hermes-runtime.service"
    systemctl --user daemon-reload 2>/dev/null
    
    # Remove binary
    rm -rf "$INSTALL_DIR"
    
    echo "✅ Hermes uninstalled"
    echo "⚠️  User data preserved at: ~/.hermes"
    echo "   To remove data: rm -rf ~/.hermes"
fi
