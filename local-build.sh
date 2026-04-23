#!/bin/bash
set -e

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOCAL BUILD & DEPLOY — Hermes Runtime
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
#  WHAT THIS DOES:
#    Replaces GitHub Actions entirely. Builds the Hermes
#    runtime binary on YOUR machine, tests it, and uploads
#    it to Cloudflare R2 (dl.hermdash.com) for all users.
#
#  SAFETY PIPELINE:
#    1. Build binary with PyInstaller
#    2. Smoke test — starts the binary and hits /health
#    3. If smoke test FAILS → upload is BLOCKED (users safe)
#    4. If smoke test PASSES → uploads binary + version.json
#    5. Users auto-update within 1 hour (silent, background)
#
#  WHAT GETS UPLOADED:
#    dl.hermdash.com/linux        — the binary (32-60MB)
#    dl.hermdash.com/version.json — version + SHA256 checksum
#    dl.hermdash.com/install.sh   — one-liner installer
#    dl.hermdash.com/install.bat  — Windows installer
#
#  PREREQUISITES:
#    - Python 3.11+ installed
#    - ../hermes-agent/ cloned (auto-clones on first run)
#    - upload_to_r2.py in same directory (has R2 credentials)
#
#  USAGE:
#    ./local-build.sh              — build + test + upload
#
#  NOTES:
#    - First run takes ~5min (venv + deps + clone)
#    - Subsequent runs take ~1-2min (just rebuild + upload)
#    - Only builds for YOUR OS (Linux). Mac/Win need their
#      own machines or wait for GitHub Actions minutes to reset.
#    - GitHub Actions minutes (2000/mo free) reset monthly.
#      This script is the backup when those run out.
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# It builds → smoke tests → uploads to R2. That's it.

# Example to test it locally: use command below
# systemctl --user stop hermes-runtime.service && cp dist/hermes-runtime ~/.local/share/hermes/hermes-runtime && systemctl --user start hermes-runtime.service && echo "✅ Updated and running"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔨 Building Hermes Runtime locally..."

# 1. Set version
VERSION=$(date +%Y.%m%d.%H%M)
echo "VERSION = \"$VERSION\"" > version.py
echo "📌 Version: $VERSION"

# 2. Create/use virtual environment
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 3. Install deps
echo "📦 Installing dependencies..."
pip install -r requirements.txt -q
pip install pyinstaller python-multipart -q

# Clone hermes-agent if not present
if [ ! -d "../hermes-agent" ]; then
    echo "📥 Cloning hermes-agent..."
    git clone --recurse-submodules https://github.com/NousResearch/hermes-agent.git ../hermes-agent
fi
pip install -e ../hermes-agent -q

# 4. Build
echo "⚙️  Building with PyInstaller..."
pyinstaller runtime.spec --noconfirm
chmod +x dist/hermes-runtime

echo "✅ Binary built: dist/hermes-runtime ($(du -h dist/hermes-runtime | cut -f1))"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. SMOKE TEST — Binary must start and serve /health before upload
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "🧪 Smoke testing binary..."

# Kill any existing runtime on the test port
pkill -f "hermes-runtime" 2>/dev/null || true
sleep 1

# Start binary in background
./dist/hermes-runtime &
SMOKE_PID=$!

# Wait for /health to respond (max 15 seconds)
SMOKE_OK=false
for i in $(seq 1 15); do
    if curl -s http://localhost:8521/health > /dev/null 2>&1; then
        SMOKE_OK=true
        break
    fi
    sleep 1
done

# Kill the test process
kill $SMOKE_PID 2>/dev/null || true
wait $SMOKE_PID 2>/dev/null || true

if [ "$SMOKE_OK" = false ]; then
    echo ""
    echo "❌ SMOKE TEST FAILED — binary did not start properly!"
    echo "❌ Upload BLOCKED. Fix the build before deploying."
    echo ""
    exit 1
fi

echo "✅ Smoke test passed — /health responded OK"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Upload to R2 (only if smoke test passed)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "☁️  Uploading to R2..."
python upload_to_r2.py "dist/hermes-runtime" "linux"

# Update version.json
SHA=$(sha256sum dist/hermes-runtime | cut -d' ' -f1)
cat > version.json <<EOF
{
  "version": "$VERSION",
  "released_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "checksums": {
    "linux": "$SHA",
    "mac": "",
    "windows.exe": ""
  }
}
EOF
python upload_to_r2.py "version.json" "version.json"
python upload_to_r2.py "install.sh" "install.sh"
python upload_to_r2.py "install.bat" "install.bat"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Version $VERSION deployed to dl.hermdash.com"
echo "   Binary: https://dl.hermdash.com/linux"
echo "   SHA256: $SHA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
