#!/usr/bin/env bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           SonicTranslator — AI Terminal Translator          ║${NC}"
echo -e "${CYAN}║              Powered by Duck.ai + Playwright                ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── Check Python ────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}[ERROR] Python not found.${NC} Install Python 3.8+ from https://python.org"
    exit 1
fi

PYVER=$($PYTHON --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}[OK]${NC} Python $PYVER detected"

# ─── Check pip ───────────────────────────────────────────────────────────
if ! $PYTHON -m pip --version &>/dev/null; then
    echo -e "${YELLOW}[WARN]${NC} pip not found, installing..."
    $PYTHON -m ensurepip --upgrade &>/dev/null || true
fi

# ─── Install dependencies ────────────────────────────────────────────────
echo -e "${CYAN}[..]${NC} Checking dependencies..."
if ! $PYTHON -c "import playwright, pyperclip, rich, prompt_toolkit" &>/dev/null; then
    echo -e "${CYAN}[..]${NC} Installing dependencies from requirements.txt..."
    $PYTHON -m pip install -r requirements.txt -q
    echo -e "${GREEN}[OK]${NC} Dependencies installed"
else
    echo -e "${GREEN}[OK]${NC} All dependencies present"
fi

# ─── Install Playwright Chromium ─────────────────────────────────────────
if ! $PYTHON -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.chromium; p.stop()" &>/dev/null; then
    echo -e "${CYAN}[..]${NC} Installing Playwright Chromium browser..."
    $PYTHON -m playwright install chromium
    echo -e "${GREEN}[OK]${NC} Chromium installed"
else
    echo -e "${GREEN}[OK]${NC} Chromium browser ready"
fi

# ─── Auto-update from GitHub ─────────────────────────────────────────────
if command -v git &>/dev/null; then
    echo -e "${CYAN}[..]${NC} Checking for updates..."
    if git fetch origin main --quiet 2>/dev/null; then
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse origin/main)
        if [ "$LOCAL" != "$REMOTE" ]; then
            echo -e "${YELLOW}[!!]${NC} Update available! Downloading..."
            if git pull origin main --quiet; then
                echo -e "${GREEN}[OK]${NC} Updated to latest version"
                echo -e "${CYAN}[..]${NC} Reinstalling dependencies..."
                $PYTHON -m pip install -r requirements.txt -q
                $PYTHON -m playwright install chromium
            else
                echo -e "${YELLOW}[WARN]${NC} Update failed, continuing with current version"
            fi
        else
            echo -e "${GREEN}[OK]${NC} Already up to date"
        fi
    else
        echo -e "${CYAN}[..]${NC} Cannot reach GitHub, skipping update check"
    fi
else
    echo -e "${CYAN}[..]${NC} Git not found, skipping auto-update"
fi

# ─── Run SonicTranslator ─────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[..]${NC} Starting SonicTranslator..."
echo ""
cd "$(dirname "$0")/src"
exec $PYTHON st.py "$@"
