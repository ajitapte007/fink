#!/bin/bash
set -e
echo "🚀 Starting master Fink MCP setup orchestrator..."
cd "$(dirname "$0")" # Navigate to the directory containing this script (mcp/setup/)
./setup_env.sh
./setup_host.sh
./setup_open_webui_container.sh
echo "🎉 Fink MCP environment and Open WebUI Native Tool successfully configured!"
