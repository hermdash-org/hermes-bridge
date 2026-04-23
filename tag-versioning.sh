#!/bin/bash
# Automatic Date-Based Versioning System
# Usage: ./tag-versioning.sh

set -e

echo "🏷️  Automatic Versioning System"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Get current date
YEAR=$(date +%Y)
MONTH_DAY=$(date +%m%d)

# Find today's build number
TAG_PREFIX="v${YEAR}.${MONTH_DAY}"
EXISTING_TAGS=$(git tag -l "${TAG_PREFIX}.*" | sort -V)

if [ -z "$EXISTING_TAGS" ]; then
    BUILD_NUM=1
else
    LAST_TAG=$(echo "$EXISTING_TAGS" | tail -1)
    LAST_BUILD=$(echo "$LAST_TAG" | cut -d'.' -f3)
    BUILD_NUM=$((LAST_BUILD + 1))
fi

NEW_TAG="${TAG_PREFIX}.${BUILD_NUM}"

echo "📅 Date: $(date +%Y-%m-%d)"
echo "🔢 New version: $NEW_TAG"
echo ""

# Commit any changes
if ! git diff-index --quiet HEAD --; then
    echo "📝 Committing changes..."
    git add -A
    git commit -m "Release $NEW_TAG" || true
fi

# Create and push tag
echo "🏷️  Creating tag: $NEW_TAG"
git tag "$NEW_TAG"

echo "⬆️  Pushing to GitHub..."
git push origin main
git push origin "$NEW_TAG"

echo ""
echo "✅ Version $NEW_TAG released!"
echo "🚀 GitHub Actions will build and deploy automatically"
echo ""
echo "📍 View release: https://github.com/devops-vaults/hermes/releases/tag/$NEW_TAG"
