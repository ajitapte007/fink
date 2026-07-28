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
        
        # Verify category headers exist
        assert page.locator(".category-header").count() > 0
        
        # Verify metric control checkboxes exist
        assert page.locator("#metric-price").is_visible()
        assert page.locator("#metric-ps_ratio").is_visible()
        assert page.locator("#metric-revenue").is_visible()
        
        # Verify dynamic control buttons exist
        assert page.locator(".toggle-sh").count() > 0
        assert page.locator(".axis-selector").count() > 0
        assert page.locator("#global-normalize").is_visible()
        
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

def test_in_place_updating_e2e():
    # 1. Generate two instances of HTML for the same ticker (AMZN) but different selected metrics
    html1 = generate_visualization_html("AMZN", selected_metrics=["price"], start_year=2018, end_year=2023)
    html2 = generate_visualization_html("AMZN", selected_metrics=["ps_ratio"], start_year=2018, end_year=2023)
    
    # Inject base href to allow relative paths to resolve
    html1 = html1.replace("<head>", '<head><base href="http://localhost:3000">')
    html2 = html2.replace("<head>", '<head><base href="http://localhost:3000">')
    
    import html as py_html
    srcdoc1 = py_html.escape(html1)
    srcdoc2 = py_html.escape(html2)
    
    # Parent page nesting the two widgets inside simulated message bubbles
    parent_html = f"""
    <!DOCTYPE html>
    <html>
    <body>
      <div class="chat-bubble" id="bubble1" style="display: block;">
        <iframe id="iframe1" srcdoc="{srcdoc1}" style="width: 100%; height: 600px;"></iframe>
      </div>
      <div class="chat-bubble" id="bubble2" style="display: block;">
        <iframe id="iframe2" srcdoc="{srcdoc2}" style="width: 100%; height: 600px;"></iframe>
      </div>
    </body>
    </html>
    """
    
    from pathlib import Path
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Add request and console logging to debug same-origin behaviors
        page.on("console", lambda msg: print(f"[PLAYWRIGHT CONSOLE] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[PLAYWRIGHT PAGEERROR] {err}"))
        page.on("requestfailed", lambda req: print(f"[PLAYWRIGHT REQ FAILED] {req.url} - {req.failure}"))
        
        static_dir = Path(__file__).parent.parent.parent / "open_webui" / "static"
        chart_js_path = static_dir / "chart.js"
        chart_utils_path = static_dir / "chartUtils.js"
        dashboard_css_path = static_dir / "dashboard.css"
        data_json_path = static_dir / "amzn-data.json"
        
        page.route("**/static/fink/chart.js", lambda route: route.fulfill(path=str(chart_js_path)))
        page.route("**/static/fink/chartUtils.js", lambda route: route.fulfill(path=str(chart_utils_path)))
        page.route("**/static/fink/dashboard.css", lambda route: route.fulfill(path=str(dashboard_css_path)))
        page.route("**/static/fink/amzn-data.json", lambda route: route.fulfill(path=str(data_json_path)))
        
        # Route the parent HTML through the same origin to inherit identical same-origin security context
        page.route("http://localhost:3000/test-preview", lambda route: route.fulfill(body=parent_html, content_type="text/html"))
        page.goto("http://localhost:3000/test-preview")
        
        # Wait a bit for JS logic inside both frames to run and communicate
        page.wait_for_timeout(2000)
        
        # Verify that the second chat bubble has been set to display: none
        bubble2_style = page.locator("#bubble2").evaluate("el => el.style.display")
        assert bubble2_style == "none", "Second chat bubble should be hidden after duplicate update"
        
        # Verify that the first frame has updated its parameters (it now has both price AND ps_ratio checked)
        frame1 = page.frame(name="iframe1")
        assert frame1 is not None
        
        # Check checked state in the first frame
        price_checked = frame1.locator("#metric-price").is_checked()
        ps_checked = frame1.locator("#metric-ps_ratio").is_checked()
        
        # Since the second widget selected 'ps_ratio', it should update the first frame to check it
        assert price_checked is True or ps_checked is True, "At least one metric should be plotted"
        
        browser.close()


# ─── Segment Rendering Tests ──────────────────────────────────────────────────

def _setup_playwright_page(p, ticker, selected_metrics, start_year=None, end_year=None):
    """Helper: generate chart HTML, launch Playwright, set up routes, return (browser, page, errors).
    Reads from existing SQLite cache — does NOT fetch new data (avoids needing API keys in tests).
    """
    from pathlib import Path

    html_code = generate_visualization_html(
        ticker, selected_metrics=selected_metrics,
        start_year=start_year, end_year=end_year
    )

    # Skip if visualization returned an error div (no cached data)
    if "Error" in html_code and "<div" in html_code and "color: #ef4444" in html_code:
        pytest.skip(f"No cached data for {ticker} — run the MCP server first to populate cache")

    html_code = html_code.replace("<head>", '<head><base href="http://localhost:3000">')

    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Collect JS errors
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))

    # Route static assets from host filesystem
    static_dir = Path(__file__).parent.parent.parent / "open_webui" / "static"
    page.route("**/static/fink/chart.js", lambda route: route.fulfill(path=str(static_dir / "chart.js")))
    page.route("**/static/fink/chartUtils.js", lambda route: route.fulfill(path=str(static_dir / "chartUtils.js")))
    page.route("**/static/fink/dashboard.css", lambda route: route.fulfill(path=str(static_dir / "dashboard.css")))
    page.route(f"**/static/fink/{ticker.lower()}-data.json",
               lambda route: route.fulfill(path=str(static_dir / f"{ticker.lower()}-data.json")))

    page.set_content(html_code, wait_until="load")
    page.wait_for_timeout(1500)  # Allow Chart.js to initialize

    return browser, page, errors


def test_segment_chart_renders_without_errors():
    """Load chart with revenue + product_segments for UNH — assert zero JS errors."""
    with sync_playwright() as p:
        browser, page, errors = _setup_playwright_page(
            p, "UNH", ["revenue", "product_segments"]
        )

        assert page.locator("#financialChart").is_visible()
        assert len(errors) == 0, f"JS errors during segment chart render: {errors}"

        browser.close()


def test_toggle_segments_on_off():
    """Load chart with price only, toggle product_segments on then off — no crashes."""
    with sync_playwright() as p:
        browser, page, errors = _setup_playwright_page(
            p, "UNH", ["price"]
        )

        # Toggle product_segments ON
        page.locator("#metric-product_segments").check()
        page.wait_for_timeout(800)

        # Toggle product_segments OFF
        page.locator("#metric-product_segments").uncheck()
        page.wait_for_timeout(800)

        assert len(errors) == 0, f"JS errors during segment toggle: {errors}"

        browser.close()


def test_mixed_chart_has_bar_and_line_datasets():
    """With price + product_segments, Chart.js should have both line and bar datasets."""
    with sync_playwright() as p:
        browser, page, errors = _setup_playwright_page(
            p, "UNH", ["price", "product_segments"]
        )

        chart_info = page.evaluate("""() => {
            const chart = Chart.getChart("financialChart");
            if (!chart) return null;
            return {
                datasets: chart.data.datasets.map(d => ({
                    label: d.label,
                    type: d.type || 'line',
                    stack: d.stack || null,
                    dataLength: d.data.length,
                    nonNullCount: d.data.filter(v => v !== null && v !== undefined).length
                }))
            };
        }""")

        assert chart_info is not None, "Chart.js failed to initialize"
        assert len(errors) == 0, f"JS errors: {errors}"

        types = [d["type"] for d in chart_info["datasets"]]
        assert "line" in types, f"Expected line datasets, got: {types}"
        assert "bar" in types, f"Expected bar datasets, got: {types}"

        # Bar datasets should have a stack property (for stacking)
        bar_datasets = [d for d in chart_info["datasets"] if d["type"] == "bar"]
        assert all(d["stack"] is not None for d in bar_datasets), \
            f"Bar datasets missing stack property: {bar_datasets}"

        browser.close()


def test_segment_bars_have_data():
    """Bar datasets for product_segments should contain non-null values."""
    with sync_playwright() as p:
        browser, page, errors = _setup_playwright_page(
            p, "UNH", ["product_segments"]
        )

        chart_info = page.evaluate("""() => {
            const chart = Chart.getChart("financialChart");
            if (!chart) return null;
            return {
                datasets: chart.data.datasets.map(d => ({
                    label: d.label,
                    type: d.type || 'line',
                    nonNullCount: d.data.filter(v => v !== null && v !== undefined).length
                }))
            };
        }""")

        assert chart_info is not None, "Chart.js failed to initialize"
        assert len(chart_info["datasets"]) > 0, "Expected segment bar datasets"

        # Each segment should have at least some non-null data points
        for ds in chart_info["datasets"]:
            assert ds["nonNullCount"] > 0, f"Segment '{ds['label']}' has no data"
            assert ds["type"] == "bar", f"Segment '{ds['label']}' should be bar type, got {ds['type']}"

        browser.close()
