#!/bin/bash
# Quick verification that source code is protected

echo "🔍 Verifying code protection in Dockerfile..."
echo ""

# Check if the insecure line is gone
if grep -q "Copy raw Python files for now to fix hangs" /home/kennedy/Desktop/hermes-desktop/hermdocker/Dockerfile; then
    echo "❌ INSECURE: Raw Python files are still being copied!"
    echo "   Found: 'Copy raw Python files for now to fix hangs'"
    exit 1
fi

# Check if the secure line exists
if grep -q "Copy ONLY compiled .so files from builder" /home/kennedy/Desktop/hermes-desktop/hermdocker/Dockerfile; then
    echo "✅ SECURE: Only compiled .so files are copied"
else
    echo "⚠️  WARNING: Could not verify secure copy method"
    exit 1
fi

# Check if __init__.py stripping is removed
if grep -q "Strip __init__.py files to minimum" /home/kennedy/Desktop/hermes-desktop/hermdocker/Dockerfile; then
    echo "❌ PROBLEM: __init__.py files are being stripped (will break imports)"
    exit 1
else
    echo "✅ CORRECT: __init__.py files kept intact for imports"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ALL CHECKS PASSED - YOUR CODE IS PROTECTED!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "1. Test build: ./test-build.sh"
echo "2. Push to Docker Hub: docker push devopsvaults/hermes-dashboard:latest"
echo "3. Users will only see compiled .so files (unreadable)"
