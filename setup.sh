#!/bin/bash

# --- ClueZero Setup & Background Runner ---

# Get the absolute directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "==========================================="
echo "🔍 Installing & Starting ClueZero Agent"
echo "==========================================="
echo ""

# 1. Setup Virtual Environment
if [ ! -d ".venv" ]; then
    echo "[+] Creating Python virtual environment..."
    python3 -m venv .venv
else
    echo "[+] Virtual environment found."
fi

# 2. Install dependencies
echo "[+] Installing client dependencies..."
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r client/requirements.txt -q

# 3. Setup .env file
if [ ! -f ".env" ]; then
    echo "[+] Creating default .env file..."
    cp .env.example .env
    echo "⚠️ NOTE: Please open the .env file and add your API keys!"
else
    echo "[+] .env file found."
fi

# 4. Stop any existing rogue background agents
echo "[+] Cleaning up any old background instances..."
pkill -9 -f "python client/agent.py" 2>/dev/null
pkill -9 -f "python agent.py" 2>/dev/null
sleep 1

# 5. Start the background service
echo "[+] Starting ClueZero agent in the background..."
cd "$DIR/client"
> agent.log # clear old logs
nohup ../.venv/bin/python agent.py > agent.log 2>&1 </dev/null &

echo ""
echo "✅ Done! ClueZero is now silently running in the background."
if [ "$(uname)" == "Darwin" ]; then
    DISPLAY_HOTKEY="Shift + Tab + Q"
else
    DISPLAY_HOTKEY="Shift + Tab + Q"
fi
echo "👉 You can trigger it anytime anywhere with: $DISPLAY_HOTKEY"
echo "👉 If you need to stop it, just run: pkill -f \"python agent.py\""
echo "==========================================="
