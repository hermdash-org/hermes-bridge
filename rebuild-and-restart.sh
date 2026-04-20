#!/bin/bash
# Rebuild Docker image and restart container
# Usage: ./rebuild-and-restart.sh

set -e

echo "🔨 Building Docker image..."
docker build -t hermes-dashboard .

echo "🛑 Stopping existing container..."
docker stop hermes-dashboard 2>/dev/null || true

echo "🗑️  Removing old container..."
docker rm hermes-dashboard 2>/dev/null || true

echo "🚀 Starting new container..."
docker run -d \
  --name hermes-dashboard \
  -p 8420:8420 \
  -v ~/.hermes:/opt/data \
  hermes-dashboard

echo "✅ Container restarted successfully!"
echo "📋 Checking logs..."
sleep 2
docker logs hermes-dashboard --tail 15
