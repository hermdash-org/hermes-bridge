#!/bin/bash
# HemUI Bridge — Docker entrypoint
#
# Sets up hermes config directory, loads .env, starts the bridge.

set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"

# Create hermes config dirs if they don't exist
mkdir -p "$HERMES_HOME"/{sessions,logs,memories,skills,pairing,hooks,image_cache,audio_cache,cron}

# Copy default config if none exists
if [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cp /opt/hermes/cli-config.yaml.example "$HERMES_HOME/config.yaml" 2>/dev/null || true
fi

# Load .env if it exists
if [ -f "$HERMES_HOME/.env" ]; then
    set -a
    source "$HERMES_HOME/.env"
    set +a
fi

echo "════════════════════════════════════════════════"
echo "  HemUI Bridge — Starting"
echo "  Port: 8420"
echo "  Hermes Home: $HERMES_HOME"
echo "════════════════════════════════════════════════"

# Start the bridge
exec python3 -m bridge
