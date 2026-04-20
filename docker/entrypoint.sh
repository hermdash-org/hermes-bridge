#!/bin/bash
# HemUI Bridge — Docker entrypoint
#
# Handles ALL user scenarios:
#   1. Existing hermes user (Mac/Linux/WSL) — ~/.hermes mounted at /opt/data
#   2. Fresh user with no hermes installed — creates everything from scratch
#   3. Profile users — preserves existing profile structure
#
# The HERMES_HOME env var is set ONCE here and must NEVER be mutated
# by profile switching code (the bridge stores the root at module load).

set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
export HERMES_HOME

echo "════════════════════════════════════════════════"
echo "  HemUI Bridge — Initializing"
echo "  Hermes Home: $HERMES_HOME"
echo "════════════════════════════════════════════════"

# ── Detect if this is a fresh install or existing user ──────────────
if [ -f "$HERMES_HOME/config.yaml" ]; then
    echo "  ✓ Existing hermes installation detected"
    echo "    Config: $HERMES_HOME/config.yaml"
    
    # Count existing profiles
    if [ -d "$HERMES_HOME/profiles" ]; then
        PROFILE_COUNT=$(find "$HERMES_HOME/profiles" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
        echo "    Profiles: $PROFILE_COUNT (+ default)"
    fi
    
    # Check for existing state.db
    if [ -f "$HERMES_HOME/state.db" ]; then
        echo "    Sessions DB: found"
    fi
    
    # Check for skills
    if [ -d "$HERMES_HOME/skills" ]; then
        SKILL_COUNT=$(find "$HERMES_HOME/skills" -name "SKILL.md" 2>/dev/null | wc -l)
        echo "    Skills: $SKILL_COUNT"
    fi
else
    echo "  ℹ Fresh installation — setting up from scratch"
    
    # Copy default config
    cp /opt/hermes/cli-config.yaml.example "$HERMES_HOME/config.yaml" 2>/dev/null || true
    echo "    ✓ Default config created"
fi

# ── Ensure all required directories exist ───────────────────────────
# These are needed regardless of fresh/existing install.
# mkdir -p is idempotent — safe to run on existing dirs.
REQUIRED_DIRS=(
    "sessions"
    "logs"
    "memories"
    "skills"
    "pairing"
    "hooks"
    "image_cache"
    "audio_cache"
    "cron"
    "profiles"
    "skins"
    "plans"
    "cache"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    mkdir -p "$HERMES_HOME/$dir"
done

# ── Seed bundled skills if skills dir is empty ──────────────────────
SKILL_COUNT=$(find "$HERMES_HOME/skills" -name "SKILL.md" 2>/dev/null | wc -l)
if [ "$SKILL_COUNT" -eq 0 ]; then
    echo "  ℹ Seeding bundled skills..."
    cd /opt/hermes
    python3 -c "
import os, sys
os.environ['HERMES_HOME'] = '$HERMES_HOME'
try:
    from tools.skills_sync import sync_skills
    result = sync_skills(quiet=True)
    if result:
        print(f'    ✓ Seeded {result.get(\"added\", 0)} skills')
except Exception as e:
    print(f'    ⚠ Skill seeding: {e}', file=sys.stderr)
" 2>&1 || true
fi

# ── Load .env if it exists ──────────────────────────────────────────
if [ -f "$HERMES_HOME/.env" ]; then
    set -a
    source "$HERMES_HOME/.env"
    set +a
    echo "  ✓ Loaded .env"
fi

# ── Verify API key ──────────────────────────────────────────────────
if [ -n "$OPENROUTER_API_KEY" ]; then
    # Show first/last 4 chars for verification
    KEY_LEN=${#OPENROUTER_API_KEY}
    if [ "$KEY_LEN" -gt 12 ]; then
        KEY_PREVIEW="${OPENROUTER_API_KEY:0:4}...${OPENROUTER_API_KEY: -4}"
        echo "  ✓ API key: $KEY_PREVIEW ($KEY_LEN chars)"
    else
        echo "  ✓ API key set ($KEY_LEN chars)"
    fi
else
    echo "  ⚠ No OPENROUTER_API_KEY — set it via the dashboard or .env file"
fi

echo "════════════════════════════════════════════════"
echo "  HemUI Bridge — Starting services"
echo "════════════════════════════════════════════════"

echo "  ✓ Starting bridge API on port 8420..."
# Start the bridge (this blocks)
# The bridge will start the cron ticker internally after profile initialization
exec python3 -m bridge
