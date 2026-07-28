#!/bin/bash
set -e
echo "📦 Setting up local Python virtual environment..."
cd "$(dirname "$0")/../.."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
echo "📥 Installing dependency libraries..."
venv/bin/pip install --upgrade pip
# requirements-dev.txt includes requirements.txt via -r, so this covers both.
venv/bin/pip install -r mcp/requirements-dev.txt
echo "🎭 Installing Playwright browser binaries..."
venv/bin/playwright install chromium
echo "✅ Host environment setup complete."
