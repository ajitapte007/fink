# mcp/setup/register_native_tool.py
import argparse
import sqlite3
import time
import json
import asyncio
from open_webui.utils.tools import get_tool_specs
from open_webui.utils.plugin import load_tool_module_by_id

async def register():
    parser = argparse.ArgumentParser(description="Register a custom tool and provision the model in Open WebUI.")
    parser.add_argument("--id", required=True, help="Tool ID (e.g. 'visualization_embed_native')")
    parser.add_argument("--name", required=True, help="Display Name (e.g. 'Fink Visualization Embed Native Tool')")
    parser.add_argument("--file", required=True, help="Path to the tool file in the container")
    parser.add_argument("--model-id", required=True, help="LLM Model ID to provision (e.g. 'fink-with-mcp-server')")
    parser.add_argument("--model-name", required=True, help="LLM Model Name (e.g. 'Fink Analyst (GPT)')")
    parser.add_argument("--mcp-server-id", required=True, help="Exposed MCP server connection ID (e.g. 'server:fink-openapi-mcp')")
    
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
    
    # 2. Read the tool code
    with open(args.file, 'r') as f:
        code = f.read()
        
    # 3. Load the module dynamically to compile schemas/specs using Svelte's parser
    tool_module, _ = await load_tool_module_by_id(args.id)
    specs = get_tool_specs(tool_module)
    
    # 4. Register the tool globally in Open WebUI
    cursor.execute("""
    INSERT OR REPLACE INTO tool (id, user_id, name, content, specs, meta, valves, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (args.id, admin_id, args.name, code, json.dumps(specs), '{}', '{}', int(time.time()), int(time.time())))
    
    # 5. Provision the Model in webui.db
    # Extract the clean prefix name from connection ID (e.g. 'fink_openapi_mcp')
    conn_prefix = args.mcp_server_id.split(':')[-1].replace('-', '_')
    
    from datetime import date
    system_prompt = (
        f"Today's date is {date.today().strftime('%A, %B %d, %Y')}.\n"
        "You are Fink, a financial analyst. Use the available tools to retrieve financial metrics and draw charts.\n"
        f"- Use '{conn_prefix}_tool_alphavantage_post' to retrieve stock market financials.\n"
        f"- Use '{args.id}' (Fink Visualization Embed Native Tool) to render interactive visual charts.\n"
        f"- DO NOT call the raw internal '{conn_prefix}_tool_visualization_internal_post' tool.\n"
        "- Always interpret follow-up queries or chart adjustment requests (e.g., 'can you plot EPS instead?' or 'make it the last 3 years') in the context of the active conversation. Do not treat these as unrelated queries; instead, resolve the active ticker from the chat history and call the native visualizer tool.\n"
        "- If the user asks about a different company/ticker in the same chat thread, politely tell them to start a separate chat thread to keep the charts and context clean."
    )
    
    # Check if the model already exists to preserve its existing columns
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
            
    model_meta = {
        "base_model_id": base_model_id,
        "profile_image_url": "/static/favicon.png",
        "description": "Fink financial analyst assistant.",
        "system": system_prompt,
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
        "toolIds": [args.id, args.mcp_server_id]
    }
    
    cursor.execute("""
    INSERT OR REPLACE INTO model (id, user_id, base_model_id, name, params, meta, created_at, updated_at, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (args.model_id, admin_id, base_model_id, args.model_name, params_val, json.dumps(model_meta), created_at, int(time.time()), 1))
    
    conn.commit()
    conn.close()
    print(f"✅ Tool '{args.id}' registered with {len(specs)} parameter(s).")
    print(f"✅ Model '{args.model_id}' ('{args.model_name}') provisioned and configured successfully.")

if __name__ == '__main__':
    asyncio.run(register())
