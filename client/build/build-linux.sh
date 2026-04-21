#!/usr/bin/env bash
# Build the Linux ClueZero agent binary inside Docker and drop it
# in backend/static/agent-linux so /binary/linux can serve it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$(cd "$HERE/.." && pwd)"
STATIC_DIR="$(cd "$CLIENT_DIR/../backend/static" && pwd)"

echo "[build-linux] Building Docker image..."
docker build \
  -f "$HERE/Dockerfile.linux" \
  -t cluezero-agent-build:linux \
  "$CLIENT_DIR"

echo "[build-linux] Running container to extract agent-linux into $STATIC_DIR..."
docker run --rm -v "$STATIC_DIR:/out" cluezero-agent-build:linux

ls -la "$STATIC_DIR/agent-linux"
echo "[build-linux] Done."
