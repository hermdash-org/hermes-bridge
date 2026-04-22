#!/bin/bash
# Build Hermes Runtime with PyInstaller

set -e

echo "🔨 Building Hermes Runtime..."

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "📦 Installing PyInstaller..."
    pip install pyinstaller
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/

# Build the runtime
echo "🚀 Building standalone executable..."
pyinstaller runtime.spec

# Check result
if [ -f "dist/hermes-runtime" ] || [ -f "dist/hermes-runtime.exe" ]; then
    echo "✅ Build successful!"
    echo ""
    echo "📦 Output:"
    ls -lh dist/
    echo ""
    echo "🎯 To test: ./dist/hermes-runtime"
else
    echo "❌ Build failed!"
    exit 1
fi
