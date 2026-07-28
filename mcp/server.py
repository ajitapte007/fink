# mcp/server.py
import sys
import json
import html as py_html
from pathlib import Path
from typing import List, Optional

# Add the mcp/ directory directly to sys.path to avoid name collision with 'mcp' pip package
mcp_dir = Path(__file__).parent.resolve()
if str(mcp_dir) not in sys.path:
    sys.path.insert(0, str(mcp_dir))

from fastmcp import FastMCP
from data.cache_orchestrator import cache_ticker_data
from data.process_utils import get_aligned_historical_data, merge_revenue_segment_data
from metrics_registry import VALID_METRIC_KEYS
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
def visualize_html(
    ticker: str,
    selected_metrics: Optional[List[str]] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    normalize: Optional[bool] = False,
    per_share_metrics: Optional[List[str]] = None,
    left_axis_metrics: Optional[List[str]] = None,
    right_axis_metrics: Optional[List[str]] = None,
    growth_rate_yoy: Optional[bool] = False,
    revenue_segment_chart: Optional[str] = None
) -> str:
    """
    Generates an interactive HTML-based time series widget leveraging Chart.js.
    Auto-fetches data if not cached. Renders multi-graph line charts with timeline controls.
    
    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL').
        selected_metrics: Optional list of metrics to check by default (e.g., ["price", "ps_ratio"]).
        start_year: Optional initial start year bound for the timeline.
        end_year: Optional initial end year bound for the timeline.
        normalize: Optional global normalize state. Set to True to normalize chart data to percentage growth from baseline. At most one of 'normalize' or 'growth_rate_yoy' should be True.
        per_share_metrics: Optional list of aggregate metrics to scale by shares outstanding.
        left_axis_metrics: Optional list of metrics to force-plot on the left Y-axis.
        right_axis_metrics: Optional list of metrics to force-plot on the right Y-axis.
        growth_rate_yoy: Optional. Set to True to show Year-over-Year rate of growth percentage changes. At most one of 'normalize' or 'growth_rate_yoy' should be True.
        revenue_segment_chart: Optional segment type to render as stacked bars ('product_segments' or 'geographic_segments').
        
    Returns:
        An HTML iframe markdown block to render inside client chat webviews.
    """
    ticker = ticker.upper().strip()

    revenue_segment_metrics = {"product_segments", "geographic_segments"}
    needs_revenue_segments = bool(
        revenue_segment_chart or
        (selected_metrics and revenue_segment_metrics.intersection(selected_metrics))
    )
    result = cache_ticker_data(ticker, include_revenue_segments=needs_revenue_segments)
    if result["error"]:
        return f'<div style="color: #ef4444; padding: 15px;">Error fetching data: {json.dumps(result["error"])}</div>'

    html_code = generate_visualization_html(
        ticker=ticker,
        selected_metrics=selected_metrics,
        start_year=start_year,
        end_year=end_year,
        normalize=normalize,
        per_share_metrics=per_share_metrics,
        left_axis_metrics=left_axis_metrics,
        right_axis_metrics=right_axis_metrics,
        growth_rate_yoy=growth_rate_yoy,
        revenue_segment_chart=revenue_segment_chart
    )

    escaped_html = py_html.escape(html_code)
    return (
        f'<iframe srcdoc="{escaped_html}" style="width: 100%; height: 600px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);"></iframe>'
    )


@mcp.tool()
def compute_metrics(
    ticker: str,
    metrics: Optional[List[str]] = None,
    per_share_metrics: Optional[List[str]] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None
) -> str:
    """
    Returns a clean, token-efficient JSON string containing historical values for selected metrics.
    Auto-fetches data if not cached. Useful for feeding precise quantitative data to the LLM.
    
    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL').
        metrics: Optional list of metrics to extract. If none specified, returns all available.
        per_share_metrics: Optional list of aggregate metrics to return scaled on-the-fly by outstanding shares.
        start_year: Optional start year filter (inclusive).
        end_year: Optional end year filter (inclusive).
    """
    ticker = ticker.upper().strip()

    revenue_segment_metrics = {"product_segments", "geographic_segments"}
    needs_revenue_segments = bool(metrics and revenue_segment_metrics.intersection(metrics))
    result = cache_ticker_data(ticker, include_revenue_segments=needs_revenue_segments)
    if result["error"]:
        return json.dumps({"error": result["error"]})

    raw_cache = result["raw_cache"]

    try:
        aligned_points = get_aligned_historical_data(raw_cache)
    except Exception as e:
        return json.dumps({"error": f"Failed aligning data for {ticker}: {str(e)}"})

    # Merge revenue segment data if available
    if needs_revenue_segments and result["revenue_segment_data"]:
        aligned_points = merge_revenue_segment_data(aligned_points, result["revenue_segment_data"])

    if metrics:
        invalid = [m for m in metrics if m not in VALID_METRIC_KEYS]
        if invalid:
            return json.dumps({"error": f"Invalid metrics: {invalid}. Allowed: {VALID_METRIC_KEYS}"})
    else:
        metrics = list(VALID_METRIC_KEYS)

    if per_share_metrics is None:
        per_share_metrics = []

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
                if m in per_share_metrics and shares and shares > 0:
                    val = val / shares
                filtered_pt[m] = val

        # Include revenue segment dicts if requested
        for seg_key in revenue_segment_metrics.intersection(metrics or []):
            seg_val = pt_dict.get(seg_key)
            if seg_val:
                filtered_pt[seg_key] = seg_val

        output_points.append(filtered_pt)

    return json.dumps({
        "ticker": ticker,
        "timeframe": {"start_year": start_year, "end_year": end_year},
        "data": output_points
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
