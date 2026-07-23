# mcp/tests/test_e2e_llm_tool_loop.py
import os
import sys
import json
from pathlib import Path
from openai import OpenAI

# Add project root to sys.path
mcp_dir = Path(__file__).parent.parent.resolve()
if str(mcp_dir) not in sys.path:
    sys.path.insert(0, str(mcp_dir))

from data.alphavantage_tool import fetch_alphavantage_data
from visualization.visualization_tool import generate_visualization_html

def test_llm_tool_calling_loop():
    """
    E2E Multi-turn LLM tool calling test using OpenAI API and local production tool handlers.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[SKIP] OPENAI_API_KEY not found in environment. Skipping E2E LLM Loop test.")
        return

    client = OpenAI(api_key=api_key)
    
    # 1. Define the tool schemas for OpenAI
    tools = [
        {
            "type": "function",
            "function": {
                "name": "tool_alphavantage_post",
                "description": "Fetches historical financials for a US stock ticker and saves to database cache.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "The stock ticker symbol (e.g. UNH)"},
                        "mock_data": {"type": "boolean", "description": "Prefer local mock files. Default is true."}
                    },
                    "required": ["ticker"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "tool_visualization_post",
                "description": "Generates interactive Chart.js HTML widget for stock metrics from database cache.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "The stock ticker symbol (e.g. UNH)"},
                        "selected_metrics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Metrics to graph (e.g., ['price', 'revenue'])"
                        },
                        "start_year": {"type": "integer", "description": "Filter data starting from this year"},
                        "end_year": {"type": "integer", "description": "Filter data up to this year"}
                    },
                    "required": ["ticker"]
                }
            }
        }
    ]
    
    messages = [
        {"role": "user", "content": "show me UNH financials for the last 5 years"}
    ]
    
    print("\n--- [LLM Loop Turn 1] Sending prompt to OpenAI ---")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    response_message = response.choices[0].message
    messages.append(response_message.model_dump(exclude_none=True))
    
    tool_calls = response_message.tool_calls
    assert tool_calls is not None, "Expected LLM to call tool_alphavantage_post"
    assert tool_calls[0].function.name == "tool_alphavantage_post"
    
    # Parse arguments
    args = json.loads(tool_calls[0].function.arguments)
    ticker = args.get("ticker", "UNH")
    print(f"LLM called tool_alphavantage_post for {ticker} (args: {args})")
    
    # 2. Execute tool_alphavantage_post locally
    tool_result = fetch_alphavantage_data(ticker, mock_data=args.get("mock_data", True))
    print(f"Tool returned lightweight metadata: {tool_result}")
    
    messages.append({
        "role": "tool",
        "tool_call_id": tool_calls[0].id,
        "name": tool_calls[0].function.name,
        "content": json.dumps(tool_result)
    })
    
    # 3. Turn 2: Feed back metadata and get visualization call
    print("\n--- [LLM Loop Turn 2] Sending metadata to OpenAI ---")
    response_turn2 = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    response_message_turn2 = response_turn2.choices[0].message
    messages.append(response_message_turn2.model_dump(exclude_none=True))
    
    tool_calls_turn2 = response_message_turn2.tool_calls
    assert tool_calls_turn2 is not None, "Expected LLM to call tool_visualization_post"
    assert tool_calls_turn2[0].function.name == "tool_visualization_post"
    
    # Parse arguments
    args_vis = json.loads(tool_calls_turn2[0].function.arguments)
    print(f"LLM called tool_visualization_post for {ticker} (args: {args_vis})")
    
    # 4. Execute tool_visualization_post locally
    vis_html = generate_visualization_html(
        ticker=ticker,
        selected_metrics=args_vis.get("selected_metrics"),
        start_year=args_vis.get("start_year"),
        end_year=args_vis.get("end_year")
    )
    # Check that HTML is returned and doesn't contain errors
    assert "<canvas" in vis_html
    assert "Error aligning" not in vis_html
    print("Successfully generated optimized HTML chart locally.")
    
    messages.append({
        "role": "tool",
        "tool_call_id": tool_calls_turn2[0].id,
        "name": tool_calls_turn2[0].function.name,
        "content": vis_html[:200] + "... [HTML truncated]"
    })
    
    # 5. Turn 3: Feed back HTML and get final text response
    print("\n--- [LLM Loop Turn 3] Sending HTML response back to OpenAI ---")
    response_turn3 = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    
    final_text = response_turn3.choices[0].message.content
    print(f"\nFinal Assistant Response:\n{final_text[:500]}...\n")
    assert "UNH" in final_text.upper() or "UNITEDHEALTH" in final_text.upper()
    print("test_llm_tool_calling_loop PASSED successfully!")

if __name__ == "__main__":
    test_llm_tool_calling_loop()
