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
    
    # Verify header layout displays only the ticker name
    assert '<h1 class="dashboard-title" style="margin: 0; font-size: 16px; color: #f8fafc; font-family: sans-serif; font-weight: 600;">AMZN</h1>' in html
