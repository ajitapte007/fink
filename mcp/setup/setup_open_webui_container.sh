#!/bin/bash
set -e
echo "🚚 Syncing scripts into open-webui container..."
docker cp mcp/visualization/fink_visualization_embed_native_tool.py open-webui-fink-mcp:/app/backend/data/functions/visualization_embed_native_tool.py
docker cp mcp/setup/register_native_tool.py open-webui-fink-mcp:/app/backend/register_native_tool.py

echo "💾 Running custom tool and model registration..."
docker exec -e WEBUI_SECRET_KEY="test-secret" open-webui-fink-mcp python /app/backend/register_native_tool.py \
  --id visualization_embed_native \
  --name "Fink Visualization Embed Native Tool" \
  --file /app/backend/data/functions/visualization_embed_native_tool.py \
  --model-id fink-with-mcp-server \
  --model-name "Fink Stock Analyst Agent" \
  --mcp-server-id "server:fink-openapi-mcp"

echo "🔍 Verifying database registration specs..."
docker exec open-webui-fink-mcp python -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')
row = conn.execute('SELECT specs FROM tool WHERE id = \'visualization_embed_native\';').fetchone()
if row and len(json.loads(row[0])) > 0:
    print('✅ Database specs verified successfully!')
else:
    print('❌ Database specs check failed!')
    exit(1)
"

echo "🔄 Restarting container to apply updates..."
docker-compose -f mcp/setup/docker-compose.yml restart
echo "✅ Container configuration complete."
