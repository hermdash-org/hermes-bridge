#!/bin/bash
# Start development server (no Docker)

set -e

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ Virtual environment not found. Run ./dev-setup.sh first"
    exit 1
fi

echo "🚀 Starting Hermes Bridge..."
echo "📡 Server will run on http://localhost:8521"
echo ""

# Start the bridge server
python runtime.py
