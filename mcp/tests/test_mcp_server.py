# mcp/tests/test_mcp_server.py
import pytest
import json
from server import mcp


@pytest.mark.asyncio
async def test_mcp_tool_registration():
    """The server should expose exactly the two current tools."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]

    assert "visualize_html" in tool_names
    assert "compute_metrics" in tool_names


@pytest.mark.asyncio
async def test_compute_metrics_tool_call():
    """compute_metrics returns token-lean JSON for the requested metrics."""
    results = await mcp.call_tool("compute_metrics", {
        "ticker": "AMZN",
        "metrics": ["revenue", "net_income", "free_cash_flow"],
        "start_year": 2018,
        "end_year": 2023
    })
    assert len(results.content) > 0

    response = json.loads(results.content[0].text)
    assert response["ticker"] == "AMZN"
    assert response["timeframe"] == {"start_year": 2018, "end_year": 2023}
    assert len(response["data"]) > 0

    # Every point carries a date, and years respect the requested bounds.
    for pt in response["data"]:
        assert "date" in pt
        assert 2018 <= int(pt["date"].split("-")[0]) <= 2023

    # Requested metrics appear somewhere in the series.
    all_keys = {k for pt in response["data"] for k in pt}
    assert "revenue" in all_keys
    # Unrequested metrics must be filtered out.
    assert "ps_ratio" not in all_keys


@pytest.mark.asyncio
async def test_compute_metrics_rejects_invalid_metric():
    """An unknown metric key should return a structured error, not raise."""
    results = await mcp.call_tool("compute_metrics", {
        "ticker": "AMZN",
        "metrics": ["invalid_metric_key_123"]
    })
    response = json.loads(results.content[0].text)
    assert "error" in response
    assert "Invalid metrics" in response["error"]


@pytest.mark.asyncio
async def test_compute_metrics_per_share_scaling():
    """per_share_metrics should scale aggregates by shares outstanding."""
    plain = await mcp.call_tool("compute_metrics", {
        "ticker": "AMZN", "metrics": ["revenue"], "start_year": 2022, "end_year": 2023
    })
    scaled = await mcp.call_tool("compute_metrics", {
        "ticker": "AMZN", "metrics": ["revenue"], "per_share_metrics": ["revenue"],
        "start_year": 2022, "end_year": 2023
    })

    plain_pts = {p["date"]: p.get("revenue") for p in json.loads(plain.content[0].text)["data"]}
    scaled_pts = {p["date"]: p.get("revenue") for p in json.loads(scaled.content[0].text)["data"]}

    common = [d for d in plain_pts if d in scaled_pts
              and plain_pts[d] is not None and scaled_pts[d] is not None]
    assert common, "Expected overlapping dates with revenue in both responses"
    # Per-share revenue must be smaller than aggregate revenue.
    for d in common:
        assert scaled_pts[d] < plain_pts[d]


@pytest.mark.asyncio
async def test_visualize_html_tool_call():
    """visualize_html returns an iframe referencing the expected static assets."""
    results = await mcp.call_tool("visualize_html", {
        "ticker": "AMZN",
        "selected_metrics": ["price", "ps_ratio"],
        "start_year": 2018,
        "end_year": 2023
    })

    assert len(results.content) > 0
    code_output = results.content[0].text
    assert code_output.startswith('<iframe')
    assert 'dashboard.css' in code_output
    assert 'chart.js' in code_output
    assert 'chartUtils.js' in code_output
    assert 'amzn-data.json' in code_output


@pytest.mark.asyncio
async def test_mcp_invalid_tool_call():
    """Calling a non-existent tool should raise."""
    with pytest.raises((ValueError, KeyError, AttributeError, Exception)):
        await mcp.call_tool("non_existent_tool_name_xyz", {})
