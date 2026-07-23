# mcp/tests/test_e2e_widget.py
import pytest
from playwright.sync_api import sync_playwright
from data.alphavantage_tool import fetch_alphavantage_data
from visualization.visualization_tool import generate_visualization_html

def test_playwright_e2e_chart_render():
    # 1. Fetch mock data and generate HTML
    data_res = fetch_alphavantage_data("AMZN")
    assert data_res["success"] is True
    
    html_code = generate_visualization_html("AMZN", selected_metrics=["price", "ps_ratio"], start_year=2018, end_year=2023)
    # Inject base href to allow relative paths to resolve and trigger network requests in about:blank
    html_code = html_code.replace("<head>", '<head><base href="http://localhost:3000">')
    
    # 2. Launch headless Chromium browser
    from pathlib import Path
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Intercept static chart.js and serve from host local path
        static_dir = Path(__file__).parent.parent.parent / "open_webui" / "static"
        chart_js_path = static_dir / "chart.js"
        chart_utils_path = static_dir / "chartUtils.js"
        dashboard_css_path = static_dir / "dashboard.css"
        data_json_path = static_dir / "amzn-data.json"
        
        # Add request logging
        page.on("console", lambda msg: print(f"[PLAYWRIGHT CONSOLE] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[PLAYWRIGHT PAGEERROR] {err}"))
        page.on("request", lambda req: print(f"[PLAYWRIGHT REQ] {req.url}"))
        page.on("requestfailed", lambda req: print(f"[PLAYWRIGHT REQ FAILED] {req.url} - {req.failure}"))
        
        page.route("**/static/fink/chart.js", lambda route: route.fulfill(path=str(chart_js_path)))
        page.route("**/static/fink/chartUtils.js", lambda route: route.fulfill(path=str(chart_utils_path)))
        page.route("**/static/fink/dashboard.css", lambda route: route.fulfill(path=str(dashboard_css_path)))
        page.route("**/static/fink/amzn-data.json", lambda route: route.fulfill(path=str(data_json_path)))
        
        # Load the HTML content directly in the browser and wait for network/script to load
        page.set_content(html_code, wait_until="load")
        
        # Verify canvas element exists
        assert page.locator("#financialChart").is_visible()
        
        # Verify metric control checkboxes exist
        assert page.locator("#metric-price").is_visible()
        assert page.locator("#metric-ps_ratio").is_visible()
        assert page.locator("#metric-revenue").is_visible()
        
        # Verify slider controls exist
        assert page.locator("#leftSlider").is_visible()
        assert page.locator("#rightSlider").is_visible()
        
        # Verify default checkbox checked states: Price & P/S Ratio should be true
        assert page.locator("#metric-price").is_checked()
        assert page.locator("#metric-ps_ratio").is_checked()
        assert not page.locator("#metric-revenue").is_checked()
        
        # Verify that the chart was actually plotted inside the Canvas by querying the Chart.js instance
        chart_info = page.evaluate("""() => {
            const chart = Chart.getChart("financialChart");
            if (!chart) return null;
            return {
                datasetsCount: chart.data.datasets.length,
                labelsCount: chart.data.labels.length,
                datasets: chart.data.datasets.map(d => ({ label: d.label, dataLength: d.data.length }))
            };
        }""")
        
        assert chart_info is not None, "Chart.js failed to initialize on the canvas"
        assert chart_info["datasetsCount"] == 2, "Expected 2 datasets plotted (Price & P/S Ratio)"
        assert chart_info["labelsCount"] > 0, "Expected X-axis time series labels to be populated"
        
        # Verify correct dataset labels are plotted
        labels = [d["label"] for d in chart_info["datasets"]]
        assert any("Price" in l for l in labels)
        assert any("P/S Ratio" in l for l in labels)
        
        # Simulate user checking 'Revenue' and unchecking 'P/S Ratio'
        page.locator("#metric-revenue").check()
        page.locator("#metric-ps_ratio").uncheck()
        page.wait_for_timeout(500)
        
        assert page.locator("#metric-revenue").is_checked()
        assert not page.locator("#metric-ps_ratio").is_checked()
        
        # Verify chart updates datasets dynamically after user interaction
        updated_chart_info = page.evaluate("""() => {
            const chart = Chart.getChart("financialChart");
            return {
                datasetsCount: chart.data.datasets.length,
                datasets: chart.data.datasets.map(d => d.label)
            };
        }""")
        
        assert updated_chart_info["datasetsCount"] == 2
        updated_labels = updated_chart_info["datasets"]
        assert any("Price" in l for l in updated_labels)
        assert any("Revenue" in l for l in updated_labels)
        assert not any("P/S Ratio" in l for l in updated_labels)
        
        # Verify slider text labels exist
        start_label = page.locator("#slider-start-label").inner_text()
        end_label = page.locator("#slider-end-label").inner_text()
        assert start_label != ""
        assert end_label != ""
        
        browser.close()
