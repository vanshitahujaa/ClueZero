#!/usr/bin/env bash
# Build the macOS ClueZero agent binary. Run this ON a Mac.
# Output lands in backend/static/agent-darwin so /binary/darwin can serve it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$(cd "$HERE/.." && pwd)"
STATIC_DIR="$(cd "$CLIENT_DIR/../backend/static" && pwd)"

pushd "$CLIENT_DIR" >/dev/null

echo "[build-macos] Setting up a fresh venv..."
python3 -m venv .build-venv
# shellcheck disable=SC1091
source .build-venv/bin/activate

echo "[build-macos] Installing deps + PyInstaller..."
pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller >/dev/null

echo "[build-macos] Running PyInstaller (single-file, no console)..."
rm -rf build dist
pyinstaller \
  --onefile \
  --name agent \
  --hidden-import=pynput.keyboard._darwin \
  --hidden-import=pynput.mouse._darwin \
  agent.py

mkdir -p "$STATIC_DIR"
cp -f dist/agent "$STATIC_DIR/agent-darwin"
chmod 755 "$STATIC_DIR/agent-darwin"

deactivate
popd >/dev/null

ls -la "$STATIC_DIR/agent-darwin"
echo "[build-macos] Done. Binary: $STATIC_DIR/agent-darwin"
echo "[build-macos] Note: on first launch, macOS may prompt for Screen Recording + Accessibility permissions (System Settings → Privacy & Security)."
