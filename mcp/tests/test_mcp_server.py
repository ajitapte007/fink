# mcp/tests/test_mcp_server.py
import pytest
import json
from server import mcp

@pytest.mark.asyncio
async def test_mcp_tool_registration():
    # Retrieve tools asynchronously
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    
    assert "alphavantage" in tool_names
    assert "visualization_internal" in tool_names

@pytest.mark.asyncio
async def test_mcp_alphavantage_tool_call():
    # Call the tool using the standard client call_tool method
    results = await mcp.call_tool("alphavantage", {"ticker": "AMZN"})
    assert len(results.content) > 0
    response_str = results.content[0].text
    
    response = json.loads(response_str)
    assert response["success"] is True
    assert response["ticker"] == "AMZN"
    assert response["source"] in ["mock", "cache"]

@pytest.mark.asyncio
async def test_mcp_visualization_tool_call():
    # Get the data first (populates the cache)
    results_av = await mcp.call_tool("alphavantage", {"ticker": "AMZN"})
    
    # Render visualization (reads from cache, no data payload)
    results_viz = await mcp.call_tool("visualization_internal", {
        "ticker": "AMZN",
        "selected_metrics": ["price", "ps_ratio"],
        "start_year": 2018,
        "end_year": 2023
    })
    
    assert len(results_viz.content) > 0
    code_output = results_viz.content[0].text
    assert code_output.startswith('```html')
    assert 'dashboard.css' in code_output
    assert 'chart.js' in code_output
    assert 'chartUtils.js' in code_output
    assert 'amzn-data.json' in code_output

@pytest.mark.asyncio
async def test_mcp_invalid_tool_call():
    # Test call_tool throws ValueError or similar exception for non-existent tool
    with pytest.raises((ValueError, KeyError, AttributeError, Exception)):
        await mcp.call_tool("non_existent_tool_name_xyz", {})
