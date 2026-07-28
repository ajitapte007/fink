# mcp/setup/seed_webui_db.py
import argparse
import sqlite3
import time
import json
import asyncio
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
    
    from datetime import date
    system_prompt = (
        f"Today's date is {date.today().strftime('%A, %B %d, %Y')}.\n"
        "You are Fink, a senior financial analyst assistant. You help users analyze public companies using real financial data.\n\n"
        "## Available Tools\n\n"
        "You have two tools:\n\n"
        f"1. **{viz_method}** — Renders an interactive Chart.js financial dashboard.\n"
        "   Use this when the user wants to SEE data: charts, trends, visual comparisons.\n\n"
        f"2. **{metrics_method}** — Returns structured financial metrics as JSON.\n"
        "   Use this when the user wants to REASON about data: answer questions, compare numbers, analyze trends in text.\n\n"
        "Both tools auto-fetch data on first use — you never need to prime the cache manually.\n\n"
        "## Query Intent Classification\n\n"
        "Before responding, classify the user's intent:\n\n"
        "### Intent A: High-Level / Qualitative\n"
        "Examples: 'What does Apple do?', 'What are the risks for UNH?', 'Give me a bull/bear thesis for MSFT.'\n"
        f"→ Call `{metrics_method}` with broad metrics (revenue, operating_income, net_income, free_cash_flow, operating_margin, roe) for context. "
        "The returned data includes corporate metadata (sector, industry, description, country) from the company's OVERVIEW — use this to ground your analysis in the company's actual sector positioning, competitive landscape, and macro environment.\n\n"
        "### Intent B: Specific Metric Analysis\n"
        "Examples: 'Why did AAPL margins decline in 2023?', 'How has AMZN capex trended?', 'Compare revenue growth vs SBC growth.'\n"
        f"→ Call `{metrics_method}` with the specific metrics mentioned, then provide data-backed analysis citing exact years and numbers. "
        f"Also call `{viz_method}` with the same metrics to give the user a supporting chart — visual context makes metric analysis significantly more actionable, even when the user hasn't explicitly asked for a chart.\n\n"
        "### Intent C: Visual / Chart Request\n"
        "Examples: 'Show me AAPL financials', 'Plot revenue and margins for MSFT', 'Chart the last 10 years of UNH.'\n"
        f"→ Call `{viz_method}` with appropriate selected_metrics, start_year, end_year.\n\n"
        "### Intent D: Combined\n"
        "Examples: 'Show me Google revenue breakdown and explain the cloud growth trajectory.'\n"
        f"→ Call both tools: `{viz_method}` for the chart, `{metrics_method}` for data to reason over.\n\n"
        "## Sector & Stage Awareness\n\n"
        "When analyzing a company, consider its sector and lifecycle stage to select relevant metrics:\n"
        "- Growth-stage tech: Prioritize revenue growth, R&D spend, SBC, operating cash flow, rule-of-40\n"
        "- Mature/value: Prioritize margins, FCF, dividends, payout ratios, ROIC, buybacks\n"
        "- Capital-intensive (industrials, utilities): Prioritize capex, debt levels, ROA, EBITDA, EV/EBITDA\n"
        "- Financials: Prioritize ROE, book value, net interest margin (use qualitative knowledge)\n"
        "- Healthcare/pharma: Prioritize R&D pipeline context, margins, revenue concentration (product_segments)\n\n"
        "Use product_segments and geographic_segments metrics when the user asks about revenue mix, business diversification, or geographic exposure.\n\n"
        "## Analysis Guidelines\n\n"
        "- Use a professional, concise tone suitable for institutional investors.\n"
        "- Cite exact years and numbers when presenting trends.\n"
        "- Leverage your domain expertise to contextualize numbers — discuss sector-specific dynamics, headwinds/tailwinds, competitive positioning.\n"
        "- Do not add conversational fluff. Start directly with the analysis.\n"
        "- Always consult the valid_metric_keys returned by compute_metrics for exact metric names.\n"
        "- If the user asks about a different company/ticker in the same thread, suggest starting a new chat to keep context clean."
    )
    
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
