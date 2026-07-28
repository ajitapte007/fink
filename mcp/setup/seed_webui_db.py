# mcp/setup/seed_webui_db.py
import argparse
import sqlite3
import time
import json
import asyncio
from system_prompt import build_system_prompt
from open_webui.utils.tools import get_tool_specs
from open_webui.utils.plugin import load_tool_module_by_id

async def register():
    parser = argparse.ArgumentParser(description="Register native tools and provision the model in Open WebUI.")
    parser.add_argument("--viz-id", required=True, help="Visualization tool ID (e.g. 'visualization_embed_native')")
    parser.add_argument("--viz-name", required=True, help="Visualization tool display name")
    parser.add_argument("--viz-file", required=True, help="Path to the visualization tool file in the container")
    parser.add_argument("--metrics-id", required=True, help="Compute metrics tool ID (e.g. 'compute_metrics_native')")
    parser.add_argument("--metrics-name", required=True, help="Compute metrics tool display name")
    parser.add_argument("--metrics-file", required=True, help="Path to the compute metrics tool file in the container")
    parser.add_argument("--model-id", required=True, help="LLM Model ID to provision (e.g. 'fink-with-mcp-server')")
    parser.add_argument("--model-name", required=True, help="LLM Model Name (e.g. 'Fink Stock Analyst Agent')")
    
    args = parser.parse_args()
    
    # 1. Locate the admin user ID
    conn = sqlite3.connect('/app/backend/data/webui.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM user WHERE role='admin' LIMIT 1;")
    admin = cursor.fetchone()
    if not admin:
        print("❌ Error: Admin user not found in database.")
        return
    admin_id = admin[0]
    
    # 2. Register both native tools
    tools_to_register = [
        (args.viz_id, args.viz_name, args.viz_file),
        (args.metrics_id, args.metrics_name, args.metrics_file),
    ]
    
    for tool_id, tool_name, tool_file in tools_to_register:
        with open(tool_file, 'r') as f:
            code = f.read()
        
        tool_module, _ = await load_tool_module_by_id(tool_id, content=code)
        specs = get_tool_specs(tool_module)
        
        cursor.execute("""
        INSERT OR REPLACE INTO tool (id, user_id, name, content, specs, meta, valves, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tool_id, admin_id, tool_name, code, json.dumps(specs), '{}', '{}', int(time.time()), int(time.time())))
        
        print(f"✅ Tool '{tool_id}' registered with {len(specs)} spec(s).")
    
    # 3. Build the system prompt referencing both native tool names
    # The LLM sees native tool method names, so we need the actual method names from specs
    viz_method = args.viz_id  # Open WebUI uses the tool ID as the callable name
    metrics_method = args.metrics_id
    
    system_prompt = build_system_prompt(viz_method, metrics_method)
    
    # 4. Check if the model already exists to preserve its existing columns
    cursor.execute("SELECT base_model_id, params, created_at FROM model WHERE id = ?", (args.model_id,))
    existing_row = cursor.fetchone()
    base_model_id = "gpt-5.4-mini"  # default fallback
    params_val = "{}"
    created_at = int(time.time())
    
    if existing_row:
        if existing_row[0]:
            base_model_id = existing_row[0]
            if base_model_id == "gpt-4o":
                base_model_id = "gpt-5.4-mini"  # Upgrade to the cheaper mini model
        if existing_row[1]:
            params_val = existing_row[1]
        if existing_row[2]:
            created_at = existing_row[2]

    # Open WebUI reads a workspace model's system prompt from `params.system`; `meta`
    # holds description/capabilities/suggestion_prompts. Writing it only to meta meant
    # every prompt update was ignored while a stale prompt persisted in params — which
    # is why tool selection worked (old prompt had intent rules) but timeframe handling
    # did not (it predates the ## Timeframes section).
    # Preserve any other params the user configured, but always own `system`.
    try:
        params_dict = json.loads(params_val) if params_val else {}
        if not isinstance(params_dict, dict):
            params_dict = {}
    except (json.JSONDecodeError, TypeError):
        params_dict = {}
    params_dict["system"] = system_prompt
    params_val = json.dumps(params_dict)
            
    # NOTE: no "system" key here. Open WebUI reads a workspace model's system prompt
    # from params.system (set above); meta carries presentation and capability flags.
    # It was previously written to both, which meant a stale params.system won silently.
    model_meta = {
        "base_model_id": base_model_id,
        "profile_image_url": "/static/favicon.png",
        "description": "Fink financial analyst assistant.",
        "capabilities": {
            "file_context": True,
            "vision": True,
            "file_upload": True,
            "web_search": True,
            "image_generation": True,
            "code_interpreter": True,
            "terminal": True,
            "citations": True,
            "status_updates": True,
            "builtin_tools": True
        },
        "suggestion_prompts": None,
        "tags": [],
        "toolIds": [
            args.viz_id,
            args.metrics_id
        ]
    }
    
    cursor.execute("""
    INSERT OR REPLACE INTO model (id, user_id, base_model_id, name, params, meta, created_at, updated_at, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (args.model_id, admin_id, base_model_id, args.model_name, params_val, json.dumps(model_meta), created_at, int(time.time()), 1))
    
    # 5. Seed default task models to prevent "Model '' was not found" during background title generation
    cursor.execute("UPDATE config SET value = ? WHERE key = 'task.model.default';", (json.dumps(base_model_id),))
    cursor.execute("UPDATE config SET value = ? WHERE key = 'task.model.external';", (json.dumps(base_model_id),))
    
    conn.commit()
    conn.close()
    print(f"✅ Model '{args.model_id}' ('{args.model_name}') provisioned with tools: {[args.viz_id, args.metrics_id]}")
    print("✅ WebUI task models seeded successfully!")

if __name__ == '__main__':
    asyncio.run(register())
