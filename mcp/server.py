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
    normalize: Optional[bool] = False,
    per_share_metrics: Optional[List[str]] = None,
    left_axis_metrics: Optional[List[str]] = None,
    right_axis_metrics: Optional[List[str]] = None,
    growth_rate_yoy: Optional[bool] = False
) -> str:
    """
    Generates an interactive HTML-based time series widget leveraging Chart.js.
    Reads data directly from the shared cache. Renders multi-graph line charts with timeline controls.
    
    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL').
        selected_metrics: Optional list of metrics to check by default (e.g., ["price", "ps_ratio"]).
        start_year: Optional initial start year bound for the timeline.
        end_year: Optional initial end year bound for the timeline.
        normalize: Optional global normalize state. Set to True to normalize chart data to percentage growth from baseline. Set to False for absolute values. At most one of 'normalize' or 'growth_rate_yoy' should be True.
        per_share_metrics: Optional list of aggregate metrics to scale by shares outstanding.
        left_axis_metrics: Optional list of metrics to force-plot on the left Y-axis.
        right_axis_metrics: Optional list of metrics to force-plot on the right Y-axis.
        growth_rate_yoy: Optional growth rate YoY state. Set to True to show Year-over-Year rate of growth percentage changes. Set to False for absolute values. At most one of 'normalize' or 'growth_rate_yoy' should be True.
        
    Returns:
        An HTML iframe markdown block to render inside client chat webviews.
    """
    html_code = generate_visualization_html(
        ticker=ticker,
        selected_metrics=selected_metrics,
        start_year=start_year,
        end_year=end_year,
        normalize=normalize,
        per_share_metrics=per_share_metrics,
        left_axis_metrics=left_axis_metrics,
        right_axis_metrics=right_axis_metrics,
        growth_rate_yoy=growth_rate_yoy
    )
    
    # Return an inline HTML iframe with a fixed height of 600px to override webui constraints
    import html as py_html
    escaped_html = py_html.escape(html_code)
    return (
        f'<iframe srcdoc="{escaped_html}" style="width: 100%; height: 600px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);"></iframe>'
    )


@mcp.tool()
def filter_metrics_tool(
    ticker: str,
    metrics: Optional[List[str]] = None,
    per_share_metrics: Optional[List[str]] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None
) -> str:
    """
    Returns a clean, token-efficient JSON string containing historical values for selected metrics over a custom timeframe.
    Useful for feeding precise quantitative data directly to LLM context.
    
    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL').
        metrics: Optional list of metrics to extract. If none specified, returns all available.
        per_share_metrics: Optional list of aggregate metrics to return scaled on-the-fly by outstanding shares.
        start_year: Optional start year filter (inclusive).
        end_year: Optional end year filter (inclusive).
    """
    import json
    from data.process_utils import get_aligned_historical_data
    from data.fetch_utils import FUNCTIONS, get_db_cache
    from data.models import VALID_METRIC_KEYS
    
    ticker = ticker.upper().strip()
    raw_cache = {}
    for func in FUNCTIONS:
        cached_entry = get_db_cache(ticker, func)
        if cached_entry is None:
            return json.dumps({"error": f"Ticker {ticker} not found in database cache. Call 'alphavantage' tool first."})
        raw_cache[func] = cached_entry[0]
        
    try:
        aligned_points = get_aligned_historical_data(raw_cache)
    except Exception as e:
        return json.dumps({"error": f"Failed aligning data for {ticker}: {str(e)}"})
        
    if metrics:
        # validate metrics
        invalid = [m for m in metrics if m not in VALID_METRIC_KEYS]
        if invalid:
            return json.dumps({"error": f"Invalid metrics requested: {invalid}. Allowed metrics: {VALID_METRIC_KEYS}"})
    else:
        metrics = list(VALID_METRIC_KEYS)
        
    if per_share_metrics is None:
        per_share_metrics = []
        
    # filter and map data points
    output_points = []
    for pt in aligned_points:
        pt_dict = pt.model_dump() if hasattr(pt, "model_dump") else pt.dict()
        date_str = pt_dict["date"]
        year = int(date_str.split("-")[0])
        if start_year and year < start_year:
            continue
        if end_year and year > end_year:
            continue
            
        shares = pt_dict.get("shares_outstanding")
        
        filtered_pt = {"date": date_str}
        for m in metrics:
            val = pt_dict.get(m)
            if val is not None:
                # check per-share scaling
                if m in per_share_metrics and shares and shares > 0:
                    val = val / shares
                filtered_pt[m] = val
        output_points.append(filtered_pt)
        
    return json.dumps({
        "ticker": ticker,
        "timeframe": {"start_year": start_year, "end_year": end_year},
        "data": output_points
    }, indent=2)

@mcp.tool()
def qa_tool(
    ticker: str,
    financial_data: str,
    question: str,
    metadata_overrides: Optional[dict] = None
) -> str:
    """
    An LLM-backed analysis tool that combines clean quantitative data (from filter_metrics_tool)
    with sector-specific dynamics (risks, competitors, tailwinds/headwinds) to answer financial queries or write reports.
    Automatically resolves company metadata (sector, industry, description, Country (HQ)) from the cache.
    
    Args:
        ticker: The stock ticker symbol (e.g. 'AAPL').
        financial_data: Filtered financial data JSON payload returned by 'filter_metrics_tool'.
        question: Specific question or report instructions to address.
        metadata_overrides: Optional dict to override corporate metadata (e.g. Sector, Industry).
    """
    from google import genai
    from google.genai import types
    from data.fetch_utils import FUNCTIONS, get_db_cache
    from data.process_utils import get_corporate_identity
    import json
    
    ticker = ticker.upper().strip()
    raw_cache = {}
    for func in FUNCTIONS:
        cached_entry = get_db_cache(ticker, func)
        if cached_entry:
            raw_cache[func] = cached_entry[0]
            
    identity = get_corporate_identity(raw_cache) if raw_cache else None
    overview = raw_cache.get("OVERVIEW", {})
    
    # Resolve metadata
    metadata = metadata_overrides or {}
    company_name = metadata.get("company_name") or overview.get("Name", ticker)
    sector = metadata.get("sector") or (identity.sector if identity else "General Tech/Corporate")
    industry = metadata.get("industry") or (identity.industry if identity else "Diversified")
    description = metadata.get("description") or overview.get("Description", "")
    country = metadata.get("country") or (identity.country if identity else "US")
    market_cap = metadata.get("market_cap") or (identity.market_cap if identity else "Unknown")
    last_closing_price = metadata.get("last_closing_price") or (identity.last_closing_price if identity else "N/A")
    
    prompt = f"""You are a Senior Investment Analyst specializing in sector-specific due diligence.
Analyze the provided financial data for {ticker} ({company_name}) in the context of the resolved sector: {sector} ({industry}) and headquarters location.
 
[Corporate Metadata]
- Name: {company_name}
- Sector: {sector} / Industry: {industry}
- Description: {description}
- Country (HQ): {country}
- Market Cap: {market_cap}
- Last Closing Price: {last_closing_price}

[Financial Data Block]
{financial_data}

[User Query]
{question}

[Instructions]
- Answer the user query using a professional, concise tone suitable for institutional investors.
- Provide data-backed arguments. Cite exact dates, years, and numbers when presenting trends.
- Leverage your pre-trained domain expertise on the '{sector}' sector and '{industry}' industry to contextualize these numbers, discussing relevant sector-specific dynamics (such as headwinds/tailwinds, risk profiles, typical margins, and competitors).
- Do not add conversational fluff or introductory statements. Start directly with the analysis.
"""
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2
            )
        )
        return response.text
    except Exception as e:
        return f"Error executing Q&A analysis via Gemini API: {str(e)}"

if __name__ == "__main__":
    mcp.run()

