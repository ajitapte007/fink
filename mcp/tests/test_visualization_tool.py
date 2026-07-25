# mcp/tests/test_visualization_tool.py
import pytest
from data.alphavantage_tool import fetch_alphavantage_data
from visualization.visualization_tool import generate_visualization_html

def test_generate_visualization_html():
    # Fetch mock data for AMZN (populates the cache)
    data_res = fetch_alphavantage_data("AMZN")
    assert data_res["success"] is True
    
    # Generate HTML code (reads directly from SQLite cache)
    html = generate_visualization_html("AMZN", selected_metrics=["price", "ps_ratio"], start_year=2018, end_year=2023)
    
    # Verify basic HTML integrity checks
    assert "<!DOCTYPE html>" in html
    assert "Financial Dashboard - AMZN" in html
    assert "dashboard.css" in html
    assert "chartUtils.js" in html
    assert "amzn-data.json" in html
    assert "const metricsConfig = " not in html # Metrics config is inside the options object, not a separate statement
    assert "new Chart" not in html # chart rendering is encapsulated inside chartUtils.js now
    assert "/static/fink/chart.js" in html
    
    # Verify bounds setup
    assert 'initialStartDate: "2018-01-01"' in html
    assert 'initialEndDate: "2023-12-31"' in html
    
    # Verify header layout displays the ticker and company name
    assert 'class="dashboard-title"' in html
    assert 'AMZN' in html
    assert 'company-logo' in html



    # Verify metadata fields are present and displayed in the correct order:
    # Last Closing Price, Market Cap, Sector, Industry, HQ Country
    idx_price = html.index("Last Closing Price:")
    idx_mcap = html.index("Market Cap:")
    idx_sector = html.index("Sector:")
    idx_industry = html.index("Industry:")
    idx_country = html.index("HQ Country:")
    assert idx_price < idx_mcap < idx_sector < idx_industry < idx_country

    # Verify timeline slider is positioned inside chart-wrapper
    idx_chart_wrapper = html.index('class="chart-wrapper"')
    idx_timeline_slider = html.index('class="timeframe-slider-container"')
    assert idx_chart_wrapper < idx_timeline_slider

def test_generate_visualization_html_normalize():
    html = generate_visualization_html("AMZN", selected_metrics=["price"], normalize=True)
    assert 'window.initialTransform = "normalize"' in html

def test_generate_visualization_html_growth_rate_yoy():
    html = generate_visualization_html("AMZN", selected_metrics=["price"], growth_rate_yoy=True)
    assert 'window.initialTransform = "yoy"' in html

