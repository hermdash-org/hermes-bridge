#!/bin/bash
# Test script to verify Cython compilation works

set -e

echo "🔨 Testing Cython compilation..."

# Build the Docker image
docker build -t hermes-dashboard-test .

echo ""
echo "✅ Build successful!"
echo ""
echo "🔍 Checking what's inside the container..."

# Check what files are in the bridge directory
docker run --rm hermes-dashboard-test find /opt/bridge/bridge -type f -name "*.py" -o -name "*.so" | head -20

echo ""
echo "📊 Summary:"
docker run --rm hermes-dashboard-test sh -c '
echo "Python source files (.py): $(find /opt/bridge/bridge -name "*.py" ! -name "__init__.py" ! -name "__main__.py" | wc -l)"
echo "Compiled modules (.so): $(find /opt/bridge/bridge -name "*.so" | wc -l)"
echo "__init__.py files: $(find /opt/bridge/bridge -name "__init__.py" | wc -l)"
'

echo ""
echo "✅ If you see .so files and NO .py files (except __init__.py), your code is protected!"
