#!/bin/bash
# Development setup without Docker

set -e

echo "🔧 Setting up Hermes development environment..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Check if hermes-agent is cloned
if [ ! -d "../hermes-agent" ]; then
    echo "📥 Cloning hermes-agent..."
    cd ..
    git clone --recurse-submodules https://github.com/NousResearch/hermes-agent.git
    cd hermdocker
    echo "✅ hermes-agent cloned to ../hermes-agent"
else
    echo "✅ hermes-agent found at ../hermes-agent"
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# Install hermes-agent in development mode
echo "📥 Installing hermes-agent..."
pip install -e ../hermes-agent

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 To start development server:"
echo "   source venv/bin/activate"
echo "   python runtime.py"
echo ""
echo "🔨 To build runtime:"
echo "   ./build-runtime.sh"
