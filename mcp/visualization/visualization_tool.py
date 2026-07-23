# mcp/visualization/visualization_tool.py
import sys
from pathlib import Path

# Add mcp/ root folder to sys.path to enable local imports
mcp_dir = Path(__file__).parent.parent.resolve()
if str(mcp_dir) not in sys.path:
    sys.path.insert(0, str(mcp_dir))

import json
from data.process_utils import get_aligned_historical_data

from data.fetch_utils import FUNCTIONS, get_db_cache

def generate_visualization_html(ticker: str, selected_metrics: list = None, start_year: int = None, end_year: int = None) -> str:
    """
    Generates interactive HTML visualization markdown block for Chart.js from aligned financial history.
    Reads data directly from the shared SQLite cache DB and prunes based on selected metrics and timeframe.
    """
    ticker = ticker.upper().strip()
    if not ticker:
        raise ValueError("Ticker symbol is mandatory.")
        
    if not selected_metrics:
        selected_metrics = ["price"]
        
    # Read the full dataset directly from the SQLite database cache
    raw_cache = {}
    last_timestamp = 0.0
    for func in FUNCTIONS:
        cached_entry = get_db_cache(ticker, func)
        if cached_entry is None:
            raise ValueError(f"Data not found in cache for ticker {ticker} (missing function {func}). Please fetch data first.")
        raw_cache[func] = cached_entry[0]
        last_timestamp = max(last_timestamp, cached_entry[1])
        
    import datetime
    raw_cache["_meta_last_refreshed"] = datetime.datetime.fromtimestamp(last_timestamp).strftime('%Y-%m-%d %H:%M:%S')

    # Process and align historical time series
    try:
        aligned_points = get_aligned_historical_data(raw_cache)
    except Exception as e:
        return f"<div style='color: #ef4444; padding: 15px; background: #1e293b; border-radius: 8px;'>Error aligning historical data: {str(e)}</div>"
        
    # Standard raw metrics alignment container
    aligned_metrics = {
        "price": {},
        "revenue": {},
        "operating_income": {},
        "net_income": {},
        "free_cash_flow": {},
        "roic": {},
        "eps": {},
        "pe_ratio": {},
        "ps_ratio": {},
        "shares_outstanding": {},
        "dividends": {}
    }
    
    for pt in aligned_points:
        pt_dict = pt.model_dump() if hasattr(pt, "model_dump") else pt.dict()
        date_str = pt_dict["date"]
        for metric_key in aligned_metrics.keys():
            val = pt_dict.get(metric_key)
            if val is not None:
                aligned_metrics[metric_key][date_str] = val
                
    # Keep all aligned metrics in the JSON dump to enable full checkbox and timeline slider interactivity in the UI
    processed_metrics = aligned_metrics
                
    # Write the data to a static JSON file to prevent code bloat and truncation
    static_dir = Path(__file__).parent.parent.parent / "open_webui" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    data_file_name = f"{ticker.lower()}-data.json"
    data_file_path = static_dir / data_file_name
    with open(data_file_path, "w", encoding="utf-8") as f:
        json.dump(processed_metrics, f)
        
    metrics_config = [
        { "id": "price", "label": "Stock Price ($)", "color": "#3b82f6", "axis": "y" },
        { "id": "pe_ratio", "label": "P/E Ratio", "color": "#10b981", "axis": "y1" },
        { "id": "eps", "label": "EPS ($)", "color": "#f59e0b", "axis": "y1" },
        { "id": "revenue", "label": "Revenue ($)", "color": "#ec4899", "axis": "y" },
        { "id": "free_cash_flow", "label": "Free Cash Flow ($)", "color": "#8b5cf6", "axis": "y" },
        { "id": "shares_outstanding", "label": "Shares Outstanding", "color": "#06b6d4", "axis": "y1" },
        { "id": "ps_ratio", "label": "P/S Ratio", "color": "#a78bfa", "axis": "y1" }
    ]
    
    def is_checked(m_id):
        return "checked" if m_id in selected_metrics else ""
        
    start_date_str = f"{start_year}-01-01" if start_year else ""
    end_date_str = f"{end_year}-12-31" if end_year else ""
        
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Financial Dashboard - {ticker}</title>
  <script>
    window.currentTicker = "{ticker}";
    
    // Check if a parent chart already exists in the chat thread to perform an in-place update
    try {{
      const parentDoc = window.parent.document;
      const iframes = Array.from(parentDoc.querySelectorAll("iframe"));
      const myFrame = window.frameElement;
      
      const activeFrame = iframes.find(iframe => 
        iframe !== myFrame && 
        iframe.contentDocument && 
        iframe.contentDocument.getElementById("financialChart") &&
        iframe.contentWindow.currentTicker === "{ticker}"
      );
      
      if (activeFrame) {{
        // Trigger update in the existing frame
        activeFrame.contentWindow.updateChartParameters({{
          metrics: {json.dumps(selected_metrics)},
          startDate: "{start_date_str}",
          endDate: "{end_date_str}"
        }});
        
        // Hide the new message bubble to avoid clutter
        if (myFrame) {{
          myFrame.style.display = "none";
          const bubble = myFrame.closest(".chat-bubble");
          if (bubble) bubble.style.display = "none";
        }}
        // Stop execution to prevent loading components in the duplicate frame
        window.stop();
      }}
    }} catch (e) {{
      console.warn("Could not check/update existing chart frame:", e);
    }}

    // Detect parent origin dynamically to support sandboxed Web Previews
    let parentOrigin = "http://localhost:3000";
    try {{
      if (window.location.ancestorOrigins && window.location.ancestorOrigins.length > 0) {{
        parentOrigin = window.location.ancestorOrigins[0];
      }} else if (document.referrer) {{
        parentOrigin = new URL(document.referrer).origin;
      }}
    }} catch (e) {{
      console.error("Could not resolve parent origin:", e);
    }}

    // Dynamically inject stylesheet
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = parentOrigin + '/static/fink/dashboard.css';
    document.head.appendChild(link);

    // Dynamically load Chart.js and then ChartUtils
    const scriptChart = document.createElement('script');
    scriptChart.src = parentOrigin + '/static/fink/chart.js';
    scriptChart.onerror = () => {{
      // Fallback to CDN if offline file fails to load
      const scriptCDN = document.createElement('script');
      scriptCDN.src = 'https://cdn.jsdelivr.net/npm/chart.js@3.7.1/dist/chart.min.js';
      scriptCDN.onload = loadUtils;
      document.body.appendChild(scriptCDN);
    }};
    scriptChart.onload = loadUtils;

    function loadUtils() {{
      const scriptUtils = document.createElement('script');
      scriptUtils.src = parentOrigin + '/static/fink/chartUtils.js';
      scriptUtils.onload = () => {{
        window.initFinancialChart({{
          ticker: "{ticker}",
          dataUrl: parentOrigin + "/static/fink/{data_file_name}",
          metricsConfig: {json.dumps(metrics_config)},
          initialMetrics: {json.dumps(selected_metrics)},
          initialStartDate: "{start_date_str}",
          initialEndDate: "{end_date_str}"
        }});
      }};
      document.body.appendChild(scriptUtils);
    }}

    document.addEventListener("DOMContentLoaded", () => {{
      document.body.appendChild(scriptChart);
    }});
  </script>
</head>
<body>
  <div class="dashboard">
    <div class="controls">
      <div class="dashboard-header" style="margin-bottom: 15px; border-bottom: 1px solid #334155; padding-bottom: 8px;">
        <h1 class="dashboard-title" style="margin: 0; font-size: 16px; color: #f8fafc; font-family: sans-serif; font-weight: 600;">{ticker}</h1>
      </div>
      <div class="section-title">Metrics</div>
      <div class="checkbox-group">
        <label class="control-label" style="color: #3b82f6;"><input type="checkbox" id="metric-price" {is_checked('price')}> Price</label>
        <label class="control-label" style="color: #10b981;"><input type="checkbox" id="metric-pe_ratio" {is_checked('pe_ratio')}> P/E Ratio</label>
        <label class="control-label" style="color: #f59e0b;"><input type="checkbox" id="metric-eps" {is_checked('eps')}> EPS</label>
        <label class="control-label" style="color: #ec4899;"><input type="checkbox" id="metric-revenue" {is_checked('revenue')}> Revenue</label>
        <label class="control-label" style="color: #8b5cf6;"><input type="checkbox" id="metric-free_cash_flow" {is_checked('free_cash_flow')}> FCF</label>
        <label class="control-label" style="color: #06b6d4;"><input type="checkbox" id="metric-shares_outstanding" {is_checked('shares_outstanding')}> Shares</label>
        <label class="control-label" style="color: #a78bfa;"><input type="checkbox" id="metric-ps_ratio" {is_checked('ps_ratio')}> P/S Ratio</label>
      </div>
      <div class="section-title">Timeline</div>
      <div class="timeframe-slider-container">
        <div class="slider-track"></div>
        <input type="range" id="leftSlider" class="timeframe-slider" min="0" max="1000" value="0">
        <input type="range" id="rightSlider" class="timeframe-slider" min="0" max="1000" value="1000">
      </div>
      <div style="display: flex; justify-content: space-between; font-size: 11px; color: #cbd5e1; margin-top: 8px;">
        <span id="slider-start-label"></span>
        <span id="slider-end-label"></span>
      </div>
    </div>
    
    <div class="chart-wrapper">
      <canvas id="financialChart"></canvas>
    </div>
  </div>
</body>
</html>"""
    return html
