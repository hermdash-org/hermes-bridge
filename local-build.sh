#!/bin/bash
set -e

# ─── Local Build & Deploy ───────────────────────────────────
# Build PyInstaller binary locally and upload to R2
# No GitHub Actions needed!
#
# Usage:  ./local-build.sh
# Requires: Python 3.11, pip, R2 credentials in environment
# ─────────────────────────────────────────────────────────────

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

# 3. Build
echo "⚙️  Building with PyInstaller..."
pyinstaller runtime.spec --noconfirm
chmod +x dist/hermes-runtime

echo "✅ Binary built: dist/hermes-runtime ($(du -h dist/hermes-runtime | cut -f1))"

# 4. Upload to R2
if [ -n "$R2_ACCESS_KEY_ID" ]; then
    echo "☁️  Uploading to R2..."
    python upload_to_r2.py "dist/hermes-runtime" "hermes-downloads" "linux"

    # Update version.json
    cat > version.json <<EOF
{
  "version": "$VERSION",
  "released_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "checksums": {
    "linux": "$(sha256sum dist/hermes-runtime | cut -d' ' -f1)",
    "mac": "",
    "windows.exe": ""
  }
}
EOF
    python upload_to_r2.py "version.json" "hermes-downloads" "version.json"
    python upload_to_r2.py "install.sh" "hermes-downloads" "install.sh"
    python upload_to_r2.py "install.bat" "hermes-downloads" "install.bat"

    echo "✅ Uploaded to dl.hermdash.com"
else
    echo "⚠️  R2 credentials not set. Upload manually to R2 dashboard."
    echo "   Files: dist/hermes-runtime, version.json, install.sh, install.bat"
fi

echo ""
echo "🚀 Done! Version $VERSION deployed."
