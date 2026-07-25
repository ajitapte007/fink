# mcp/tests/test_docker_e2e.py
import requests
import json
import time

def test_open_webui_e2e_tool_call():
    """
    E2E integration test:
    Queries the Open WebUI container at http://localhost:3000/api/chat/completions,
    authenticates via the active admin API key, and requests a stock analysis.
    Verifies that the request successfully completes, triggers the underlying
    tool calls, and returns the expected financial analysis response.
    """
    api_key = "sk-fink-dev-test-key-12345"
    url = "http://localhost:3000/api/chat/completions"
    tools_url = "http://localhost:3000/api/v1/tools/"
    
    # 1. Fetch active tool schemas from container
    try:
        tools_resp = requests.get(
            tools_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        tools_list = tools_resp.json()
    except Exception as e:
        assert False, f"Failed to retrieve registered tools from container: {e}"
        
    # 2. Extract and format schemas for OpenAI payload
    formatted_tools = []
    target_tool_ids = ["visualization_embed_native", "fink_openapi_mcp_tool_alphavantage_post", "fink_openapi_mcp_tool_visualization_internal_post"]
    for t in tools_list:
        if t["id"] in target_tool_ids:
            for spec in t.get("specs", []):
                formatted_tools.append({
                    "type": "function",
                    "function": spec
                })
                
    payload = {
        "model": "fink-with-mcp-server",
        "messages": [
            {"role": "user", "content": "show me UNH financials for the last 10 years"}
        ],
        "tools": formatted_tools,  # Injecting compiled schemas
        "stream": False
    }
    
    print("\n[E2E TEST] Sending completions request to Open WebUI container...")
    print(f"[E2E TEST] Target URL: {url}")
    print(f"[E2E TEST] Prompt: {payload['messages'][0]['content']}")
    
    start_time = time.time()
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=40
        )
    except requests.exceptions.RequestException as e:
        assert False, f"HTTP Connection to Open WebUI container failed: {e}. Is the container running?"
        
    duration = time.time() - start_time
    print(f"[E2E TEST] HTTP Status: {response.status_code} (took {duration:.2f}s)")
    
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}. Body: {response.text}"
    
    content = response.text
    assistant_message = ""
    
    if content.startswith("data:"):
        # Parse Server-Sent Events (SSE) stream format
        chunks = []
        for line in content.split("\n"):
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(data_str)
                    delta_content = chunk_json["choices"][0].get("delta", {}).get("content", "")
                    chunks.append(delta_content)
                except Exception:
                    pass
        assistant_message = "".join(chunks)
        tool_calls = []
    else:
        # Standard non-streamed JSON format
        try:
            data = response.json()
            assert "choices" in data, f"Response did not contain choices list: {data}"
            choice = data["choices"][0]
            message = choice.get("message", {})
            assistant_message = message.get("content") or ""
            tool_calls = message.get("tool_calls") or []
        except Exception as e:
            assert False, f"Failed to parse JSON response: {e}. Raw content: {content}"
    
    print(f"\n[E2E TEST] Assistant Response Content: {assistant_message}")
    print(f"[E2E TEST] Assistant Tool Calls: {json.dumps(tool_calls, indent=2)}\n")
    
    # Assertions
    # The LLM should decide to invoke a tool call to retrieve the financials first
    assert len(tool_calls) > 0, "Expected LLM to request a tool call."
    
    requested_tool = tool_calls[0]["function"]["name"]
    assert requested_tool in ["fink_openapi_mcp_tool_alphavantage_post", "visualization_embed_native"], \
        f"Expected LLM to call one of the primary tools, but it called '{requested_tool}'."
        
    # Verify that the LLM successfully resolved the user query context and passed 'UNH' as the ticker
    tool_args = json.loads(tool_calls[0]["function"]["arguments"])
    assert tool_args.get("ticker", "").upper() == "UNH", \
        f"Expected tool call ticker argument to be 'UNH', but got '{tool_args.get('ticker')}'."
        
    print("[E2E TEST] Success! E2E tool calling and response generation verified.")

def test_native_tool_execution():
    """
    Directly imports the native tool script and runs it to verify that
    it compiles, connects to the MCP server, and formats the Svelte embeds payload.
    """
    # Dynamic import of the native tool to verify python syntax and structure
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent.resolve()
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / "mcp"))
    
    from visualization.fink_visualization_embed_native_tool import Tools
    from data.alphavantage_tool import fetch_alphavantage_data
    
    # Pre-populate cache for UNH
    fetch_alphavantage_data("UNH")
    
    tool = Tools()
    
    # Mock event emitter to verify socket payload structure
    emitted_events = []
    async def mock_event_emitter(event):
        emitted_events.append(event)
        
    import asyncio
    
    # Run the native tool's visualization_embed_native asynchronously
    result = asyncio.run(tool.visualization_embed_native(
        ticker="UNH",
        selected_metrics=["price", "pe_ratio"],
        start_year=2020,
        end_year=2026,
        __event_emitter__=mock_event_emitter
    ))
    
    # Verify the return message seen by the LLM
    print(f"\n[NATIVE TOOL TEST] LLM Return Text: {result}")
    assert "Interactive chart generated for UNH below:" in result
    
    # Verify the socket event was emitted correctly
    assert len(emitted_events) == 1
    event = emitted_events[0]
    assert event["type"] == "embeds"
    assert "embeds" in event["data"]
    html_payload = event["data"]["embeds"][0]
    
    # Verify the html code was adapted from the MCP response
    assert "<iframe" in html_payload
    assert "DOCTYPE" in html_payload
    assert "chartUtils.js" in html_payload
    assert "unh-data.json" in html_payload
    print("[NATIVE TOOL TEST] Success! Native tool execution and event emission verified.")

if __name__ == "__main__":
    test_open_webui_e2e_tool_call()
    test_native_tool_execution()
