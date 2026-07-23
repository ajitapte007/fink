# mcp/server.py
import sys
from pathlib import Path

# Add the mcp/ directory directly to sys.path to avoid name collision with 'mcp' pip package
mcp_dir = Path(__file__).parent.resolve()
if str(mcp_dir) not in sys.path:
    sys.path.insert(0, str(mcp_dir))

from fastmcp import FastMCP
from data.alphavantage_tool import fetch_alphavantage_data
from visualization.visualization_tool import generate_visualization_html

# Create the MCP server
mcp = FastMCP("Fink Financial Analytics Server")

# Custom route handlers to satisfy Open WebUI's naive connection verification (POST /sse or /sse/)
@mcp.custom_route("/sse", methods=["POST"])
async def handle_post_sse(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok"}, status_code=200)

@mcp.custom_route("/sse/", methods=["POST"])
async def handle_post_sse_slash(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok"}, status_code=200)

@mcp.tool()
def alphavantage(ticker: str, mock_data: bool = True) -> str:
    """
    Fetches comprehensive historical financials (earnings, cashflow, balance sheets) for a US listed ticker.
    Caches the results to the database and returns fetch metadata.
    
    Args:
        ticker: The US listed stock ticker symbol (e.g. 'AAPL', 'MSFT').
        mock_data: Whether to prefer reading from local seed mock files for testing (default: True).
        
    Returns:
        A JSON string containing the metadata (ticker, success, source, last_refreshed, expires_at).
    """
    import json
    result = fetch_alphavantage_data(ticker, mock_data=mock_data)
    return json.dumps(result, indent=2)

import html
from typing import List, Optional

@mcp.tool()
def visualization_internal(
    ticker: str,
    selected_metrics: Optional[List[str]] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> str:
    """
    Generates an interactive HTML-based time series widget leveraging Chart.js.
    Reads data directly from the shared cache. Renders multi-graph line charts with timeline controls.
    
    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL').
        selected_metrics: Optional list of metrics to check by default (e.g., ["price", "ps_ratio"]).
        start_year: Optional initial start year bound for the timeline.
        end_year: Optional initial end year bound for the timeline.
        
    Returns:
        An HTML iframe markdown block to render inside client chat webviews.
    """
    html_code = generate_visualization_html(ticker, selected_metrics, start_year, end_year)
    
    # Return the raw lightweight HTML code block directly
    return (
        f"```html\n"
        f"{html_code}\n"
        f"```"
    )

if __name__ == "__main__":
    mcp.run()
