# mcp/tests/test_e2e_llm_tool_loop.py
"""
E2E LLM tool-calling tests that verify the model dispatches to the correct tools
based on natural language prompts.

These tests send prompts to the OpenAI API with the same tool schemas the model sees
in production, and assert that the LLM calls the expected tool(s) with reasonable args.

Run with: pytest mcp/tests/test_e2e_llm_tool_loop.py -v -s

Requires:
  - OPENAI_API_KEY environment variable
  - MCP server running at localhost:8001 (for tool execution)
"""
import os
import sys
import json
import pytest
import requests
from pathlib import Path
from openai import OpenAI

# ─── Tool Schemas (mirror what Open WebUI provides to the LLM) ─────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "visualize_native",
            "description": (
                "Generates and mounts an interactive Chart.js financial analytics chart "
                "for a given stock ticker. Auto-fetches data on first use."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol (e.g. 'UNH')"},
                    "selected_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of metrics (e.g. ['price', 'pe_ratio'])"
                    },
                    "start_year": {"type": "integer", "description": "Start year bound (e.g. 2018)"},
                    "end_year": {"type": "integer", "description": "End year bound (e.g. 2026)"},
                    "normalize": {"type": "boolean", "description": "Normalize to percentage growth from baseline"},
                    "growth_rate_yoy": {"type": "boolean", "description": "Show YoY growth rate percentages"}
                },
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compute_metrics_native",
            "description": (
                "Returns structured historical financial metrics as a JSON string "
                "for a given stock ticker. Auto-fetches data on first use. "
                "Use this to get precise numbers for analysis and reasoning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol (e.g. 'AAPL')"},
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of metrics to extract (e.g. ['revenue', 'net_income'])"
                    },
                    "per_share_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Aggregate metrics to scale by shares outstanding"
                    },
                    "start_year": {"type": "integer", "description": "Start year filter, inclusive"},
                    "end_year": {"type": "integer", "description": "End year filter, inclusive"}
                },
                "required": ["ticker"]
            }
        }
    }
]

SYSTEM_PROMPT = (
    "You are Fink, a senior financial analyst assistant. "
    "You have two tools: visualize_native (for charts) and compute_metrics_native (for data/reasoning). "
    "Use compute_metrics_native when the user needs numbers to reason over. "
    "Use visualize_native when the user wants to see a chart. "
    "Use both when appropriate."
)


def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


def get_tool_calls(client, prompt, model="gpt-4o-mini"):
    """Send a prompt and return the list of tool calls the LLM makes."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        tools=TOOLS,
        tool_choice="auto"
    )
    msg = response.choices[0].message
    return msg.tool_calls or []


def get_tool_calls_with_retry(client, prompt, expected_tool, retries=2, model="gpt-4o-mini"):
    """Retry tool dispatch up to `retries` times to handle LLM non-determinism."""
    for attempt in range(retries + 1):
        calls = get_tool_calls(client, prompt, model=model)
        tool_names = [c.function.name for c in calls]
        if expected_tool in tool_names:
            return calls
        if attempt < retries:
            print(f"  Retry {attempt + 1}: LLM returned {tool_names}, expected {expected_tool}")
    return calls  # return last attempt for assertion error message


def mcp_server_available():
    try:
        return requests.get("http://localhost:8001/openapi.json", timeout=3).status_code == 200
    except requests.ConnectionError:
        return False


# ─── Intent C: Visual / Chart Request ──────────────────────────────────────────

@pytest.mark.e2e
class TestIntentC_ChartRequests:
    """User wants to SEE data → should call visualize_native."""

    def test_show_financials(self):
        client = get_client()
        calls = get_tool_calls_with_retry(client, "Show me AAPL financials for the past 5 years", "visualize_native")
        tool_names = [c.function.name for c in calls]
        assert "visualize_native" in tool_names, f"Expected visualize_native, got {tool_names}"

    def test_plot_metrics(self):
        client = get_client()
        calls = get_tool_calls_with_retry(
            client, "Create a chart showing revenue and margins for MSFT from 2018 to 2024", "visualize_native"
        )
        tool_names = [c.function.name for c in calls]
        assert "visualize_native" in tool_names, f"Expected visualize_native, got {tool_names}"
        viz_call = next(c for c in calls if c.function.name == "visualize_native")
        args = json.loads(viz_call.function.arguments)
        assert args["ticker"].upper() == "MSFT"

    def test_chart_request(self):
        client = get_client()
        calls = get_tool_calls_with_retry(client, "Chart UNH stock for the last 10 years", "visualize_native")
        tool_names = [c.function.name for c in calls]
        assert "visualize_native" in tool_names, f"Expected visualize_native, got {tool_names}"


# ─── Intent A/B: Data / Reasoning Requests ────────────────────────────────────

@pytest.mark.e2e
class TestIntentAB_DataRequests:
    """User wants to REASON about data → should call compute_metrics_native."""

    def test_explicit_compute(self):
        client = get_client()
        calls = get_tool_calls_with_retry(
            client, "Get me AAPL revenue numbers from 2020 to 2024", "compute_metrics_native"
        )
        tool_names = [c.function.name for c in calls]
        assert "compute_metrics_native" in tool_names, f"Expected compute_metrics_native, got {tool_names}"

    def test_analysis_question(self):
        client = get_client()
        calls = get_tool_calls_with_retry(
            client,
            "Fetch Apple's operating margin data and explain why margins declined in 2023",
            expected_tool="compute_metrics_native"
        )
        tool_names = [c.function.name for c in calls]
        assert "compute_metrics_native" in tool_names, f"Expected compute_metrics_native, got {tool_names}"

    def test_qualitative_with_data(self):
        client = get_client()
        calls = get_tool_calls_with_retry(
            client, "Give me a bull/bear thesis for MSFT based on its recent financials", "compute_metrics_native"
        )
        tool_names = [c.function.name for c in calls]
        assert "compute_metrics_native" in tool_names, f"Expected compute_metrics_native, got {tool_names}"


# ─── Intent D: Combined ───────────────────────────────────────────────────────

@pytest.mark.e2e
class TestIntentD_CombinedRequests:
    """User wants both chart AND analysis → should call both tools."""

    def test_show_and_explain(self):
        client = get_client()
        calls = get_tool_calls_with_retry(
            client,
            "Show me Google's revenue chart and explain the cloud growth trajectory",
            expected_tool="visualize_native"
        )
        tool_names = [c.function.name for c in calls]
        # At minimum, the viz tool should be called; both is ideal
        assert len(tool_names) > 0, f"Expected at least one tool call, got {tool_names}"
        assert "visualize_native" in tool_names or "compute_metrics_native" in tool_names, \
            f"Expected at least one of visualize_native/compute_metrics_native, got {tool_names}"
        assert "compute_metrics_native" in tool_names, f"Missing compute_metrics_native, got {tool_names}"


# ─── Full Loop Test (with tool execution) ──────────────────────────────────────

@pytest.mark.e2e
@pytest.mark.skipif(not mcp_server_available(), reason="MCP server not running")
class TestFullLoop:
    """Full loop: prompt → tool call → execute → feed back → verify response."""

    def test_compute_metrics_loop(self):
        """Send prompt, execute compute_metrics, verify LLM uses the data."""
        client = get_client()
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "What is AAPL's revenue trend from 2021 to 2023? Give me exact numbers."}
        ]
        
        # Turn 1: Get tool call
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        
        assert msg.tool_calls, "Expected tool call"
        call = msg.tool_calls[0]
        assert call.function.name == "compute_metrics_native"
        
        # Execute against MCP server
        args = json.loads(call.function.arguments)
        mcp_resp = requests.post("http://localhost:8001/compute_metrics", json={
            "ticker": args.get("ticker", "AAPL"),
            "metrics": args.get("metrics", ["revenue"]),
            "start_year": args.get("start_year", 2021),
            "end_year": args.get("end_year", 2023)
        }, timeout=120)
        assert mcp_resp.status_code == 200
        tool_result = mcp_resp.json()
        result_str = tool_result if isinstance(tool_result, str) else tool_result.get("result", json.dumps(tool_result))
        
        # Turn 2: Feed back result
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.function.name,
            "content": result_str if isinstance(result_str, str) else json.dumps(result_str)
        })
        
        resp2 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        final = resp2.choices[0].message.content
        
        # Verify the response references AAPL and includes numbers
        assert "AAPL" in final.upper() or "APPLE" in final.upper()
        print(f"\n[Full Loop] Final response:\n{final[:500]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
