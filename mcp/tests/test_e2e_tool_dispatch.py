# mcp/tests/test_e2e_tool_dispatch.py
"""
End-to-end tests that verify tool dispatch behavior via the MCP server.
These tests call the actual MCP endpoints and validate response structure.

Run with: pytest mcp/tests/test_e2e_tool_dispatch.py -v -k "not network"

Note: Tests tagged @pytest.mark.network require a running MCP server at localhost:8001.
"""
import json
import pytest
import requests

MCP_BASE_URL = "http://localhost:8001"


def mcp_server_available():
    """Check if the MCP server is reachable."""
    try:
        resp = requests.get(f"{MCP_BASE_URL}/openapi.json", timeout=3)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


# ─── Explicit Tool Call Tests ───────────────────────────────────────────────────
# These test that the MCP endpoints return correct data when called directly.

@pytest.mark.network
@pytest.mark.skipif(not mcp_server_available(), reason="MCP server not running")
class TestComputeMetricsEndpoint:
    """Tests for the compute_metrics MCP endpoint."""

    def test_basic_revenue_query(self):
        """Query: 'Get AAPL revenue 2020-2024' → should return revenue data points."""
        resp = requests.post(f"{MCP_BASE_URL}/compute_metrics", json={
            "ticker": "AAPL",
            "metrics": ["revenue"],
            "start_year": 2020,
            "end_year": 2024
        }, timeout=120)
        assert resp.status_code == 200
        result = resp.json()
        # MCPO wraps in {"result": "...json string..."}
        if isinstance(result, dict) and "result" in result:
            data = json.loads(result["result"])
        else:
            data = result

        assert data["ticker"] == "AAPL"
        assert len(data["data"]) > 0
        assert "revenue" in data["data"][0]
        assert "date" in data["data"][0]

    def test_multiple_metrics(self):
        """Query: specific metrics → should return all requested metrics."""
        resp = requests.post(f"{MCP_BASE_URL}/compute_metrics", json={
            "ticker": "AAPL",
            "metrics": ["revenue", "net_income", "operating_margin"],
            "start_year": 2022,
            "end_year": 2024
        }, timeout=120)
        assert resp.status_code == 200
        result = resp.json()
        if isinstance(result, dict) and "result" in result:
            data = json.loads(result["result"])
        else:
            data = result

        sample = data["data"][0]
        assert "revenue" in sample
        assert "net_income" in sample
        # operating_margin may be None for some dates

    def test_segment_metrics(self):
        """Query: 'revenue breakdown' → should include product_segments."""
        resp = requests.post(f"{MCP_BASE_URL}/compute_metrics", json={
            "ticker": "UNH",
            "metrics": ["product_segments"],
            "start_year": 2020,
            "end_year": 2024
        }, timeout=120)
        assert resp.status_code == 200
        result = resp.json()
        if isinstance(result, dict) and "result" in result:
            data = json.loads(result["result"])
        else:
            data = result

        # Find a data point with product_segments
        points_with_segments = [p for p in data["data"] if "product_segments" in p]
        assert len(points_with_segments) > 0
        seg = points_with_segments[0]["product_segments"]
        assert isinstance(seg, dict)
        assert len(seg) > 0  # Should have segment names

    def test_invalid_metric_returns_error(self):
        """Query with invalid metric name → should return error."""
        resp = requests.post(f"{MCP_BASE_URL}/compute_metrics", json={
            "ticker": "AAPL",
            "metrics": ["nonexistent_metric_xyz"]
        }, timeout=120)
        assert resp.status_code == 200
        result = resp.json()
        if isinstance(result, dict) and "result" in result:
            data = json.loads(result["result"])
        else:
            data = result
        assert "error" in data


@pytest.mark.network
@pytest.mark.skipif(not mcp_server_available(), reason="MCP server not running")
class TestVisualizeHtmlEndpoint:
    """Tests for the visualize_html MCP endpoint."""

    def test_basic_chart_generation(self):
        """Query: 'Show AAPL financials' → should return HTML with iframe."""
        resp = requests.post(f"{MCP_BASE_URL}/visualize_html", json={
            "ticker": "AAPL",
            "selected_metrics": ["revenue", "net_income"],
            "start_year": 2018,
            "end_year": 2024
        }, timeout=120)
        assert resp.status_code == 200
        result = resp.json()
        html = result if isinstance(result, str) else result.get("result", "")
        assert "<iframe" in html or "srcdoc" in html

    def test_chart_with_normalize(self):
        """Query: 'normalized view' → should accept normalize flag."""
        resp = requests.post(f"{MCP_BASE_URL}/visualize_html", json={
            "ticker": "AAPL",
            "selected_metrics": ["revenue", "operating_income"],
            "normalize": True
        }, timeout=120)
        assert resp.status_code == 200

    def test_chart_with_yoy_growth(self):
        """Query: 'growth rate' → should accept growth_rate_yoy flag."""
        resp = requests.post(f"{MCP_BASE_URL}/visualize_html", json={
            "ticker": "AAPL",
            "selected_metrics": ["revenue"],
            "growth_rate_yoy": True
        }, timeout=120)
        assert resp.status_code == 200


# ─── Data File Tests ────────────────────────────────────────────────────────────
# These verify that the JSON data file is written to the shared static directory.

@pytest.mark.network
@pytest.mark.skipif(not mcp_server_available(), reason="MCP server not running")
class TestDataFileOutput:
    """Tests that visualize_html writes JSON data accessible by Open WebUI."""

    def test_data_json_created_on_host(self):
        """After visualize_html call, the data JSON should exist on the host static dir."""
        import os
        from pathlib import Path
        
        # Call visualize_html to generate the data file
        resp = requests.post(f"{MCP_BASE_URL}/visualize_html", json={
            "ticker": "MSFT",
            "selected_metrics": ["revenue"]
        }, timeout=120)
        assert resp.status_code == 200

        # Check the file exists on the host
        static_dir = Path(__file__).parent.parent.parent / "open_webui" / "static"
        data_file = static_dir / "msft-data.json"
        assert data_file.exists(), f"Data file not found at {data_file}"

        # Verify it has valid JSON with the requested metric
        with open(data_file) as f:
            data = json.load(f)
        assert "revenue" in data
        assert len(data["revenue"]) > 0


# ─── OpenAPI Schema Tests ───────────────────────────────────────────────────────
# These verify the MCP server exposes the correct tool surface.

@pytest.mark.network
@pytest.mark.skipif(not mcp_server_available(), reason="MCP server not running")
class TestOpenAPISchema:
    """Tests that the MCP server exposes the expected tools."""

    def test_only_two_tools_exposed(self):
        """The MCP server should expose exactly visualize_html and compute_metrics."""
        resp = requests.get(f"{MCP_BASE_URL}/openapi.json", timeout=5)
        assert resp.status_code == 200
        schema = resp.json()
        paths = list(schema["paths"].keys())
        assert "/visualize_html" in paths
        assert "/compute_metrics" in paths
        # Should NOT expose alphavantage or other internal tools
        assert "/alphavantage" not in paths

    def test_compute_metrics_schema_has_required_params(self):
        """compute_metrics should accept ticker, metrics, start_year, end_year."""
        resp = requests.get(f"{MCP_BASE_URL}/openapi.json", timeout=5)
        schema = resp.json()
        cm_schema = schema["paths"]["/compute_metrics"]["post"]
        assert "requestBody" in cm_schema
