#!/bin/bash
set -e

echo "🔧 Generating native tools with metric descriptions from registry..."
python3 -c "
import sys; sys.path.insert(0, 'mcp')
from metrics_registry import get_metric_names_for_docstring
metric_names = get_metric_names_for_docstring()
for src, dst in [
    ('mcp/visualization/fink_compute_metrics_native_tool.py', '/tmp/fink_compute_metrics_native_tool.py'),
    ('mcp/visualization/fink_visualization_embed_native_tool.py', '/tmp/fink_visualization_embed_native_tool.py'),
]:
    content = open(src).read().replace('{{VALID_METRIC_NAMES}}', metric_names)
    assert '{{VALID_METRIC_NAMES}}' not in content, f'Placeholder replacement failed in {src}'
    open(dst, 'w').write(content)
    print(f'  ✅ {src} → {dst}')
"

echo "📄 Syncing chartUtils.js from canonical source..."
# mcp/visualization/chartUtils.js is the source of truth; open_webui/static/ is a
# generated artifact bind-mounted into the container and served at /static/fink/.
cp mcp/visualization/chartUtils.js open_webui/static/chartUtils.js
echo "  ✅ mcp/visualization/chartUtils.js → open_webui/static/chartUtils.js"

echo "🚚 Syncing native tools and scripts into open-webui container..."
docker cp /tmp/fink_visualization_embed_native_tool.py open-webui-fink-mcp:/app/backend/data/functions/visualize_native_tool.py
docker cp /tmp/fink_compute_metrics_native_tool.py open-webui-fink-mcp:/app/backend/data/functions/compute_metrics_native_tool.py
docker cp mcp/setup/seed_webui_db.py open-webui-fink-mcp:/app/backend/seed_webui_db.py
# seed_webui_db.py does `from system_prompt import build_system_prompt`, so the prompt
# module must sit beside it. Shared with mcp/tests/ so the dispatch tests exercise the
# real production prompt rather than a placeholder.
docker cp mcp/system_prompt.py open-webui-fink-mcp:/app/backend/system_prompt.py
# seed_webui_db.py imports build_system_prompt from this; they must land side by side.
docker cp mcp/system_prompt.py open-webui-fink-mcp:/app/backend/system_prompt.py

echo "🧹 Clearing Python bytecode cache..."
docker exec open-webui-fink-mcp bash -c "find /app/backend/data/functions/ -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; find /app/backend/data/functions/ -name '*.pyc' -delete 2>/dev/null" || true

echo "💾 Registering native tools and provisioning model..."
docker exec -e WEBUI_SECRET_KEY="test-secret" open-webui-fink-mcp python /app/backend/seed_webui_db.py \
  --viz-id visualize_native \
  --viz-name "Fink Visualize Native Tool" \
  --viz-file /app/backend/data/functions/visualize_native_tool.py \
  --metrics-id compute_metrics_native \
  --metrics-name "Fink Compute Metrics Native Tool" \
  --metrics-file /app/backend/data/functions/compute_metrics_native_tool.py \
  --model-id fink-with-mcp-server \
  --model-name "Fink Stock Analyst Agent"

echo "🔍 Verifying database registration..."
docker exec open-webui-fink-mcp python -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')

# Verify both tools
for tid in ['visualize_native', 'compute_metrics_native']:
    row = conn.execute('SELECT specs, content FROM tool WHERE id = ?', (tid,)).fetchone()
    if row and len(json.loads(row[0])) > 0:
        specs = json.loads(row[0])
        print(f'✅ Tool {tid}: method={specs[0][\"name\"]}')
        # Verify no placeholder remains
        assert '{{VALID_METRIC_NAMES}}' not in row[1], f'❌ {tid} still has placeholder!'
        assert 'free_cash_flow' in row[1], f'❌ {tid} missing metric descriptions in docstring!'
    else:
        print(f'❌ Tool {tid}: NOT FOUND or empty specs!')
        exit(1)

# Verify model toolIds
row = conn.execute(\"SELECT meta FROM model WHERE id = 'fink-with-mcp-server';\").fetchone()
meta = json.loads(row[0])
print(f'✅ Model toolIds: {meta.get(\"toolIds\")}')

# Verify the system prompt landed in params.system — the column Open WebUI actually
# reads. It was previously written only to meta.system and silently ignored.
row = conn.execute(\"SELECT params FROM model WHERE id = 'fink-with-mcp-server';\").fetchone()
sp = json.loads(row[0] or '{}').get('system', '')
assert '{{CURRENT_DATE}}' in sp, '❌ params.system missing {{CURRENT_DATE}} token!'
assert '## Timeframes' in sp, '❌ params.system missing Timeframes section!'
print(f'✅ System prompt in params.system ({len(sp)} chars): {sp.splitlines()[0]}')
print('✅ All docstrings correctly templated with metric descriptions')
"

echo "🔄 Applying compose config and restarting containers..."
# `up -d` rather than `restart`: restart reuses the container's existing config, so
# changes to environment/volumes in docker-compose.yml are silently ignored. `up -d`
# recreates only the services whose definition changed, and is a no-op otherwise.
docker-compose -f mcp/setup/docker-compose.yml up -d
echo "✅ Container configuration complete."
