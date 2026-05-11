#!/usr/bin/env bash
# LanguageNut Bot - Mobile launcher (Termux / Android / Linux)
# Usage: bash run.sh  or  chmod +x run.sh && ./run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  LanguageNut Bot - Mobile Launcher"
echo "========================================"
echo ""

# Step 1: Pull latest updates from GitHub
echo "[1/4] Checking for updates..."
if command -v git &> /dev/null && [ -d .git ]; then
    git pull 2>/dev/null && echo "  ✓ Update check complete." || echo "  ! Git pull had issues, continuing..."
else
    echo "  ! Git not available or not a repo. Skipping update."
fi
echo ""

# Step 2: Install Python dependencies
echo "[2/4] Installing dependencies..."
if command -v pip &> /dev/null; then
    pip install -r requirements.txt --quiet 2>/dev/null && echo "  ✓ Dependencies ready." || {
        echo "  ! pip install had issues, trying with output..."
        pip install -r requirements.txt
    }
elif command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt --quiet 2>/dev/null && echo "  ✓ Dependencies ready." || {
        echo "  ! pip3 install had issues, trying with output..."
        pip3 install -r requirements.txt
    }
else
    echo "  ! pip not found. Install Python + pip first."
    echo "    On Termux: pkg install python"
    exit 1
fi
echo ""

# Step 3: Start the bot
echo "[3/4] Starting LanguageNut bot..."
echo ""
python main.py 2>&1

# Step 4: Bot stopped
EXIT_CODE=$?
echo ""
echo "========================================"
echo "  Bot stopped (exit code: $EXIT_CODE)"
echo "  Run again: bash run.sh"
echo "========================================"
exit $EXIT_CODE

