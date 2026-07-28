# mcp/tests/test_e2e_widget.py
import pytest
from playwright.sync_api import sync_playwright
from data.alphavantage_tool import fetch_alphavantage_data
from metrics_registry import METRICS_REGISTRY
from visualization.visualization_tool import generate_visualization_html, get_static_dir

# Chart dataset labels are built from the registry (plus an axis suffix), so derive
# expected labels from the same source rather than hardcoding display strings.
LABELS = {m["id"]: m["label"] for m in METRICS_REGISTRY}

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
        # Canonical source, not the generated open_webui/static/ artifact — otherwise a
        # stale artifact could keep this test green while the real file is broken.
        chart_utils_path = Path(__file__).parent.parent / "visualization" / "chartUtils.js"
        dashboard_css_path = static_dir / "dashboard.css"
        data_json_path = get_static_dir() / "amzn-data.json"
        
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
        assert page.locator("#btn-normalize").is_visible()
        assert page.locator("#btn-yoy").is_visible()
        
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
        assert any(LABELS["price"] in l for l in labels), f"expected {LABELS['price']!r} in {labels}"
        assert any(LABELS["ps_ratio"] in l for l in labels), f"expected {LABELS['ps_ratio']!r} in {labels}"
        
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
        assert any(LABELS["price"] in l for l in updated_labels)
        assert any(LABELS["revenue"] in l for l in updated_labels)
        assert not any(LABELS["ps_ratio"] in l for l in updated_labels), \
            f"{LABELS['ps_ratio']!r} should be gone after unchecking: {updated_labels}"
        
        # Verify slider text labels exist
        start_label = page.locator("#slider-start-label").inner_text()
        end_label = page.locator("#slider-end-label").inner_text()
        assert start_label != ""
        assert end_label != ""
        
        browser.close()


# ─── Transform (Normalize / Growth Rate) Tests ────────────────────────────────
#
# These assert on actual Chart.js dataset VALUES, not on strings in the HTML.
# The previous tests only checked that the server emitted `window.initialTransform`,
# which stayed green for as long as the transforms were completely non-functional.


def _open_chart(p, ticker="AMZN", metrics=None, **kwargs):
    """Render a chart and return (browser, page, js_errors)."""
    from pathlib import Path

    fetch_alphavantage_data(ticker)
    # metrics=None -> a sensible two-line chart for transform tests.
    # metrics=[]   -> pass nothing, so the server's DEFAULT_CHART_METRICS apply.
    if metrics is None:
        metrics = ["price", "revenue"]
    html = generate_visualization_html(
        ticker, selected_metrics=(metrics or None), **kwargs
    )
    html = html.replace("<head>", '<head><base href="http://localhost:3000">')

    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    static = Path(__file__).parent.parent.parent / "open_webui" / "static"
    # Serve the CANONICAL chartUtils.js, not the generated open_webui/static/ artifact,
    # so the test exercises the file that actually gets edited.
    canonical_utils = Path(__file__).parent.parent / "visualization" / "chartUtils.js"

    def _serve(file_path):
        """Build a 1-arg route handler.

        Playwright inspects handler arity: a 2-parameter callable is invoked as
        (route, request), so `lambda route, a=asset: ...` receives a Request in `a`
        rather than the default. The handler then raises, the request is never
        fulfilled, and set_content(wait_until="load") blocks until timeout.
        """
        return lambda route: route.fulfill(path=str(file_path))

    page.route("**/static/fink/chart.js", _serve(static / "chart.js"))
    page.route("**/static/fink/dashboard.css", _serve(static / "dashboard.css"))
    page.route("**/static/fink/chartUtils.js", _serve(canonical_utils))
    # Generated JSON lives in FINK_STATIC_DIR (a tmp dir under test), not the repo.
    page.route(f"**/static/fink/{ticker.lower()}-data.json",
               _serve(get_static_dir() / f"{ticker.lower()}-data.json"))
    # The header logo is fetched from an external CDN; stub it so tests never
    # depend on network egress.
    page.route("**/img.logo.dev/**", lambda route: route.abort())

    # domcontentloaded + explicit settle, rather than "load", so a single stalled
    # subresource can't cost 30s.
    page.set_content(html, wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.Chart && Chart.getChart('financialChart')", timeout=15000
    )
    page.wait_for_timeout(500)
    return browser, page, errors


def _dataset_values(page):
    return page.evaluate("""() => {
        const chart = Chart.getChart("financialChart");
        if (!chart) return null;
        return chart.data.datasets.map(d => d.data.filter(v => v !== null && v !== undefined));
    }""")


def test_normalize_button_transforms_data():
    """Clicking Normalize must rebase the series to % of the window's first value."""
    with sync_playwright() as p:
        browser, page, errors = _open_chart(p)

        raw = _dataset_values(page)
        assert raw and any(len(s) > 0 for s in raw), "expected raw data before transform"

        page.locator("#btn-normalize").click()
        page.wait_for_timeout(600)
        normalized = _dataset_values(page)

        assert normalized != raw, "Normalize did not change any dataset values"
        # Every series should start at 100% of its own baseline.
        for series in normalized:
            if series:
                assert abs(series[0] - 100.0) < 0.01, f"expected baseline 100, got {series[0]}"

        assert "active" in (page.locator("#btn-normalize").get_attribute("class") or "")
        assert len(errors) == 0, f"JS errors: {errors}"
        browser.close()


def test_yoy_button_transforms_data():
    """Growth Rate must produce YoY percentages distinct from raw and from normalize."""
    with sync_playwright() as p:
        browser, page, errors = _open_chart(p)

        raw = _dataset_values(page)

        page.locator("#btn-normalize").click()
        page.wait_for_timeout(400)
        normalized = _dataset_values(page)

        page.locator("#btn-yoy").click()
        page.wait_for_timeout(600)
        yoy = _dataset_values(page)

        assert yoy != raw, "YoY did not change any dataset values"
        assert yoy != normalized, "YoY produced the same values as Normalize"
        assert "active" in (page.locator("#btn-yoy").get_attribute("class") or "")
        assert len(errors) == 0, f"JS errors: {errors}"
        browser.close()


def test_transforms_are_mutually_exclusive():
    """Only one transform pill may be active at a time."""
    with sync_playwright() as p:
        browser, page, errors = _open_chart(p)

        page.locator("#btn-normalize").click()
        page.wait_for_timeout(300)
        page.locator("#btn-yoy").click()
        page.wait_for_timeout(300)

        norm_cls = page.locator("#btn-normalize").get_attribute("class") or ""
        yoy_cls = page.locator("#btn-yoy").get_attribute("class") or ""
        assert "active" not in norm_cls, "Normalize stayed active after selecting YoY"
        assert "active" in yoy_cls
        assert len(errors) == 0, f"JS errors: {errors}"
        browser.close()


def test_transform_toggles_back_off():
    """Clicking an active transform twice returns the chart to raw values."""
    with sync_playwright() as p:
        browser, page, errors = _open_chart(p)

        raw = _dataset_values(page)
        page.locator("#btn-normalize").click()
        page.wait_for_timeout(400)
        page.locator("#btn-normalize").click()
        page.wait_for_timeout(400)

        assert _dataset_values(page) == raw, "values did not return to raw after toggling off"
        assert "active" not in (page.locator("#btn-normalize").get_attribute("class") or "")
        assert len(errors) == 0, f"JS errors: {errors}"
        browser.close()


def test_server_side_normalize_parameter_applies():
    """normalize=True on the tool call must render an already-normalized chart.

    This is the regression that the old substring test could not see: the value was
    passed as `initialTransform` but destructured as `initialNormalize`, so it was
    dropped before reaching the chart.
    """
    with sync_playwright() as p:
        browser, page, errors = _open_chart(p, normalize=True)

        assert page.evaluate("() => window.currentTransform") == "normalize"
        for series in _dataset_values(page):
            if series:
                assert abs(series[0] - 100.0) < 0.01, \
                    f"chart not normalized on load; first value {series[0]}"
        assert "active" in (page.locator("#btn-normalize").get_attribute("class") or "")
        assert len(errors) == 0, f"JS errors: {errors}"
        browser.close()


def test_server_side_growth_rate_yoy_parameter_applies():
    """growth_rate_yoy=True on the tool call must render an already-YoY chart."""
    with sync_playwright() as p:
        browser, page, errors = _open_chart(p, growth_rate_yoy=True)

        assert page.evaluate("() => window.currentTransform") == "yoy"
        assert "active" in (page.locator("#btn-yoy").get_attribute("class") or "")
        assert len(errors) == 0, f"JS errors: {errors}"
        browser.close()


def test_default_metrics_plotted_when_none_requested():
    """A bare chart request plots the registry default set, not a single metric."""
    from metrics_registry import DEFAULT_CHART_METRICS

    with sync_playwright() as p:
        # metrics=[] means "pass nothing through", so the server default applies.
        browser, page, errors = _open_chart(p, metrics=[])

        for metric in DEFAULT_CHART_METRICS:
            assert page.locator(f"#metric-{metric}").is_checked(), \
                f"default metric {metric} not checked on a bare request"

        plotted = _dataset_values(page)
        assert len(plotted) == len(DEFAULT_CHART_METRICS), \
            f"expected {len(DEFAULT_CHART_METRICS)} datasets, got {len(plotted)}"
        assert len(errors) == 0, f"JS errors: {errors}"
        browser.close()
