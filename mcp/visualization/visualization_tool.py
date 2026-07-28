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

import json
from data.process_utils import get_aligned_historical_data
from data.fetch_utils import FUNCTIONS, get_db_cache
from data.models import VALID_METRIC_KEYS

from metrics_registry import METRICS_REGISTRY as METRICS_CONFIG
from metrics_registry import DEFAULT_CHART_METRICS

def generate_visualization_html(
    ticker: str,
    selected_metrics: list = None,
    start_year: int = None,
    end_year: int = None,
    normalize: bool = False,
    per_share_metrics: list = None,
    left_axis_metrics: list = None,
    right_axis_metrics: list = None,
    growth_rate_yoy: bool = False
) -> str:
    """
    Generates interactive HTML visualization markdown block for Chart.js from aligned financial history.
    Reads data directly from the shared SQLite cache DB and prunes based on selected metrics and timeframe.
    """
    ticker = ticker.upper().strip()
    if not ticker:
        raise ValueError("Ticker symbol is mandatory.")
        
    if not selected_metrics:
        selected_metrics = list(DEFAULT_CHART_METRICS)
        
    if per_share_metrics is None:
        per_share_metrics = []
    if left_axis_metrics is None:
        left_axis_metrics = []
    if right_axis_metrics is None:
        right_axis_metrics = []
        
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

    # Get Corporate identity for branding
    from data.process_utils import get_corporate_identity
    overview = raw_cache.get("OVERVIEW", {})
    company_name = overview.get("Name", ticker)
    identity = get_corporate_identity(raw_cache)
    
    sector = overview.get("Sector") or (identity.sector if identity else "Unknown")
    industry = overview.get("Industry") or (identity.industry if identity else "Unknown")
    country = overview.get("Country") or (identity.country if identity else "US")
    
    raw_mcap = overview.get("MarketCapitalization") or (str(identity.market_cap) if identity and identity.market_cap else None)
    if raw_mcap and raw_mcap.isdigit():
        mval = int(raw_mcap)
        if mval >= 1e12:
            market_cap = f"${mval / 1e12:.2f}T"
        elif mval >= 1e9:
            market_cap = f"${mval / 1e9:.2f}B"
        elif mval >= 1e6:
            market_cap = f"${mval / 1e6:.2f}M"
        else:
            market_cap = f"${mval:,}"
    else:
        market_cap = raw_mcap or "Unknown"
        
    last_closing_price = "N/A"
    if identity and identity.last_closing_price and identity.last_closing_price != "N/A":
        try:
            last_closing_price = f"${float(identity.last_closing_price):.2f}"
        except ValueError:
            last_closing_price = f"${identity.last_closing_price}"

    # Process and align historical time series
    try:
        aligned_points = get_aligned_historical_data(raw_cache)
    except Exception as e:
        return f"<div style='color: #ef4444; padding: 15px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;'>Error aligning historical data: {str(e)}</div>"
        
    # Standard raw metrics alignment container
    aligned_metrics = {k: {} for k in VALID_METRIC_KEYS}
    
    for pt in aligned_points:
        pt_dict = pt.model_dump() if hasattr(pt, "model_dump") else pt.dict()
        date_str = pt_dict["date"]
        for metric_key in aligned_metrics.keys():
            val = pt_dict.get(metric_key)
            if val is not None:
                aligned_metrics[metric_key][date_str] = val
                
    # Keep all aligned metrics in the JSON dump
    processed_metrics = aligned_metrics

    # Write the data to a static JSON file to prevent code bloat and truncation
    static_dir = Path(__file__).parent.parent.parent / "open_webui" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    data_file_name = f"{ticker.lower()}-data.json"
    data_file_path = static_dir / data_file_name
    with open(data_file_path, "w", encoding="utf-8") as f:
        json.dump(processed_metrics, f)
        
    start_date_str = f"{start_year}-01-01" if start_year else ""
    end_date_str = f"{end_year}-12-31" if end_year else ""
    
    # Re-structure categories
    categories = ["Aggregates", "Valuation Ratios", "Shareholder Return", "Performance & Efficiency"]
    
    control_rows_html = ""
    for cat in categories:
        control_rows_html += f'<div class="category-header">{cat}</div>\n'
        cat_metrics = [m for m in METRICS_CONFIG if m["category"] == cat]
        for m in cat_metrics:
            m_id = m["id"]
            checked_attr = "checked" if m_id in selected_metrics else ""
            
            # Per share toggle (only for aggregates)
            sh_toggle_html = ""
            if m["isAggregate"]:
                is_sh_active = "active" if m_id in per_share_metrics else ""
                sh_toggle_html = f'<button class="toggle-sh {is_sh_active}" id="sh-{m_id}" onclick="togglePerShare(\'{m_id}\')">$/sh</button>'
                
            # L/R Axis toggle selector
            default_axis = m["defaultAxis"]
            # Check overrides
            if m_id in left_axis_metrics:
                default_axis = "y"
            elif m_id in right_axis_metrics:
                default_axis = "y1"
                
            axis_l_active = "active" if default_axis == "y" else ""
            axis_r_active = "active" if default_axis == "y1" else ""
            
            axis_toggle_html = f"""
            <div class="axis-selector" id="axis-selector-{m_id}">
                <button class="btn-axis {axis_l_active}" onclick="setMetricAxis('{m_id}', 'y')">L</button>
                <button class="btn-axis {axis_r_active}" onclick="setMetricAxis('{m_id}', 'y1')">R</button>
            </div>
            """
            
            control_rows_html += f"""
            <div class="metric-row">
              <label class="control-label" style="color: {m['color']};">
                <input type="checkbox" id="metric-{m_id}" {checked_attr} onchange="onMetricCheckedChange('{m_id}')">
                <span>{m['label']}</span>
              </label>
              <div class="metric-controls">
                {sh_toggle_html}
                {axis_toggle_html}
              </div>
            </div>
            """
        
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Financial Dashboard - {ticker}</title>
  <script>
    window.currentTicker = "{ticker}";
    window.initialTransform = "{'yoy' if growth_rate_yoy else ('normalize' if normalize else '')}" || null;
    window.initialPerShareMetrics = {json.dumps(per_share_metrics)};
    window.initialLeftAxisMetrics = {json.dumps(left_axis_metrics)};
    window.initialRightAxisMetrics = {json.dumps(right_axis_metrics)};
    window.metricsConfig = {json.dumps(METRICS_CONFIG)};
    
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
          metricsConfig: window.metricsConfig,
          initialMetrics: {json.dumps(selected_metrics)},
          initialStartDate: "{start_date_str}",
          initialEndDate: "{end_date_str}",
          initialTransform: window.initialTransform,
          initialPerShareMetrics: window.initialPerShareMetrics,
          initialLeftAxisMetrics: window.initialLeftAxisMetrics,
          initialRightAxisMetrics: window.initialRightAxisMetrics
        }});
      }};
      document.body.appendChild(scriptUtils);
    }}

    window.updateTransformPills = function() {{
        const btnNormalize = document.getElementById("btn-normalize");
        const btnYoy = document.getElementById("btn-yoy");
        if (!btnNormalize || !btnYoy) return;
        
        btnNormalize.classList.toggle("active", window.currentTransform === "normalize");
        btnYoy.classList.toggle("active", window.currentTransform === "yoy");
    }};
    
    window.toggleTransform = function(type) {{
        if (window.currentTransform === type) {{
            window.currentTransform = null;
        }} else {{
            window.currentTransform = type;
        }}
        window.updateTransformPills();
        if (window.updateChart) {{
            window.updateChart();
        }}
    }};

    document.addEventListener("DOMContentLoaded", () => {{
      document.body.appendChild(scriptChart);
    }});
  </script>
</head>
<body>
  <div class="dashboard">
    <div class="controls">
      <div class="dashboard-header" style="margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; display: flex; align-items: center; gap: 8px;">
        <img class="company-logo" src="https://img.logo.dev/ticker/{ticker.lower()}?token=pk_XJle0jznTP6QpTk_Dssexg" onerror="this.style.display='none';" style="width: 24px; height: 24px; border-radius: 4px;" />
        <div>
            <h1 class="dashboard-title" style="margin: 0; font-size: 14px; color: #0f172a; font-family: sans-serif; font-weight: 700; line-height: 1.2;">{ticker}</h1>
            <div class="company-name-label" style="font-size: 11px; color: #64748b; font-family: sans-serif; font-weight: 500;">{company_name}</div>
        </div>
      </div>
      <div class="metric-group-scrollable checkbox-group">
        {control_rows_html}
      </div>
      
      <!-- Mutual Exclusive Data Transformations -->
      <div class="transform-selectors" style="margin-top: 12px; display: flex; gap: 8px;">
        <button id="btn-normalize" class="toggle-sh" style="flex: 1; padding: 6px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; text-align: center;" onclick="toggleTransform('normalize')">Normalize (% Growth)</button>
        <button id="btn-yoy" class="toggle-sh" style="flex: 1; padding: 6px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; text-align: center;" onclick="toggleTransform('yoy')">Growth Rate (YoY %)</button>
      </div>





      <!-- Company Metadata Panel -->
      <div class="metadata-panel" style="margin-top: 15px; border-top: 1px solid #e2e8f0; padding-top: 12px; font-family: sans-serif;">
        <div style="display: flex; flex-direction: column; gap: 6px; font-size: 11px;">
          <div style="display: flex; justify-content: space-between;"><span style="color: #64748b; font-weight: 500;">Last Closing Price:</span><span style="color: #0f172a; font-weight: 600;">{last_closing_price}</span></div>
          <div style="display: flex; justify-content: space-between;"><span style="color: #64748b; font-weight: 500;">Market Cap:</span><span style="color: #0f172a; font-weight: 600;">{market_cap}</span></div>
          <div style="display: flex; justify-content: space-between;"><span style="color: #64748b; font-weight: 500;">Sector:</span><span style="color: #0f172a; font-weight: 600;">{sector}</span></div>
          <div style="display: flex; justify-content: space-between;"><span style="color: #64748b; font-weight: 500;">Industry:</span><span style="color: #0f172a; font-weight: 600;">{industry}</span></div>
          <div style="display: flex; justify-content: space-between;"><span style="color: #64748b; font-weight: 500;">HQ Country:</span><span style="color: #0f172a; font-weight: 600;">{country}</span></div>
        </div>
      </div>
    </div>
    
    <div class="chart-wrapper" style="display: flex; flex-direction: column; gap: 15px; flex: 1; min-height: 0;">
      <div style="flex: 1; min-height: 0; position: relative;">
        <canvas id="financialChart"></canvas>
      </div>
      <!-- Timeline Slider below the chart -->
      <div class="timeline-container-bottom" style="padding: 12px 20px; background: #f8fafc; border-top: 1px solid #e2e8f0; border-radius: 0 0 12px 12px;">
        <div class="timeframe-slider-container" style="margin-bottom: 4px;">
          <div class="slider-track"></div>
          <input type="range" id="leftSlider" class="timeframe-slider" min="0" max="1000" value="0">
          <input type="range" id="rightSlider" class="timeframe-slider" min="0" max="1000" value="1000">
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 10px; color: #64748b; font-weight: 500;">
          <span id="slider-start-label"></span>
          <span id="slider-end-label"></span>
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""
    return html

