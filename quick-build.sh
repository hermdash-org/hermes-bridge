#!/bin/bash
# Self-Sufficient Quick Build - Handles everything automatically
# Just run: ./quick-build.sh

set -e

# Detect platform
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    INSTALL_DIR="$HOME/.local/share/hermes"
    BINARY_NAME="hermes-runtime"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    INSTALL_DIR="$HOME/Library/Application Support/Hermes"
    BINARY_NAME="hermes-runtime"
else
    echo "❌ Unsupported platform"
    exit 1
fi

echo "🔨 Self-sufficient build for local development..."
echo ""

# ── Setup Virtual Environment ────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv .venv
    echo "📦 Installing dependencies..."
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    pip install pyinstaller
else
    echo "🐍 Activating virtual environment..."
    source .venv/bin/activate
    
    # Ensure PyInstaller is available
    if ! command -v pyinstaller &> /dev/null; then
        echo "📦 Installing PyInstaller..."
        pip install pyinstaller
    fi
fi

# Verify we're in the right environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ Failed to activate virtual environment"
    exit 1
fi

echo "✅ Virtual environment active: $VIRTUAL_ENV"
echo ""

# ── Verify Dependencies ──────────────────────────────────────────────────
echo "🔍 Verifying dependencies..."

# Check hermes-agent engine
HERMES_AGENT_PATH="../hermes-agent"
if [ ! -d "$HERMES_AGENT_PATH" ]; then
    echo "❌ hermes-agent not found at $HERMES_AGENT_PATH"
    echo "   The build requires hermes-agent as a sibling directory"
    exit 1
fi

if [ ! -f "$HERMES_AGENT_PATH/agent/__init__.py" ]; then
    echo "❌ hermes-agent appears incomplete (missing agent module)"
    echo "   Try: cd $HERMES_AGENT_PATH && git pull"
    exit 1
fi

echo "✅ hermes-agent engine found at $HERMES_AGENT_PATH"

# ── Version Increment ────────────────────────────────────────────────────
YEAR=$(date +%Y)
MONTH_DAY=$(date +%m%d)
TIME=$(date +%H%M)

# Development version format: YYYY.MMDD.HHMM (includes time for uniqueness)
NEW_VERSION="${YEAR}.${MONTH_DAY}.${TIME}"

echo "📅 Date: $(date +%Y-%m-%d)"
echo "🔢 New version: $NEW_VERSION"
echo ""

# Update version.py
echo "📝 Updating version.py..."
cat > version.py << EOF
VERSION = "$NEW_VERSION"
EOF

# Update version.json (keep checksums empty for dev builds)
echo "📝 Updating version.json..."
cat > version.json << EOF
{
  "version": "$NEW_VERSION",
  "released_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "checksums": {
    "linux": "",
    "mac": "",
    "windows.exe": ""
  }
}
EOF

echo "✅ Version updated to: $NEW_VERSION"
echo ""

# ── Clean Build ──────────────────────────────────────────────────────────
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/ __pycache__/ *.pyc
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "🚀 Building binary (this may take a minute)..."
echo "   Using PyInstaller: $(which pyinstaller)"
echo "   Python version: $(python --version)"
echo ""

# Build with verbose output for debugging
pyinstaller runtime.spec --clean --noconfirm 2>&1 | while IFS= read -r line; do
    case "$line" in
        *"Building EXE"*|*"Completed successfully"*|*"ERROR"*|*"Analyzing"*)
            echo "   $line"
            ;;
    esac
done

if [ ! -f "dist/$BINARY_NAME" ]; then
    echo "❌ Build failed! Binary not found at dist/$BINARY_NAME"
    echo "   Check the build output above for errors"
    exit 1
fi

# Verify the binary is not corrupted
if ! file "dist/$BINARY_NAME" | grep -q "executable"; then
    echo "❌ Binary appears corrupted!"
    echo "   File info: $(file dist/$BINARY_NAME)"
    exit 1
fi

echo "✅ Build successful!"
echo "   Binary size: $(du -h dist/$BINARY_NAME | cut -f1)"
echo ""

# ── Stop Running Instance ────────────────────────────────────────────────
echo "🛑 Stopping any running instances..."
pkill -f "$BINARY_NAME" 2>/dev/null && echo "   Stopped existing instance" || echo "   No running instance found"
sleep 2

# ── Install ──────────────────────────────────────────────────────────────
echo "📥 Installing to: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Backup existing binary
if [ -f "$INSTALL_DIR/$BINARY_NAME" ]; then
    BACKUP="$INSTALL_DIR/${BINARY_NAME}.backup.$(date +%H%M%S)"
    cp "$INSTALL_DIR/$BINARY_NAME" "$BACKUP"
    echo "   Backed up existing binary to: $(basename $BACKUP)"
fi

# Install new binary
cp "dist/$BINARY_NAME" "$INSTALL_DIR/$BINARY_NAME"
chmod +x "$INSTALL_DIR/$BINARY_NAME"

# Verify installation
if [ ! -x "$INSTALL_DIR/$BINARY_NAME" ]; then
    echo "❌ Installation failed! Binary not executable"
    exit 1
fi

echo "✅ Installation complete!"
echo ""

# ── Auto-Start ───────────────────────────────────────────────────────────
echo "🚀 Starting Hermes runtime..."
nohup "$INSTALL_DIR/$BINARY_NAME" > /dev/null 2>&1 &
RUNTIME_PID=$!

# Wait a moment for startup
sleep 3

# Check if it's running
if kill -0 $RUNTIME_PID 2>/dev/null; then
    echo "✅ Runtime started successfully (PID: $RUNTIME_PID)"
else
    echo "❌ Runtime failed to start"
    echo "   Try running manually: $INSTALL_DIR/$BINARY_NAME"
    echo "   Check logs for errors"
    exit 1
fi

echo ""
echo "🎉 Build Complete!"
echo ""
echo "� Version: $NEW_VERSION"
echo "📍 Binary: $INSTALL_DIR/$BINARY_NAME"
echo "🌐 Dashboard: http://localhost:8420"
echo "🔧 PID: $RUNTIME_PID"
echo ""
echo "💡 Tip: Check version in dashboard to confirm update"
echo "🛑 Stop: pkill -f hermes-runtime"
