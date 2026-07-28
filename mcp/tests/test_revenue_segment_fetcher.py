"""
Tests for revenue_segment_fetcher.py and llm_client.py.

Unit tests (no network) use mocked LLM responses.
Integration tests (marked @pytest.mark.network) hit the real OpenAI API.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
mcp_dir = Path(__file__).parent.parent.resolve()
if str(mcp_dir) not in sys.path:
    sys.path.insert(0, str(mcp_dir))

from data.revenue_segment_fetcher import (
    _validate_segment_entry,
    _validate_and_clean_response,
    fetch_revenue_segments,
)


# --- Sample mock data ---

MOCK_VALID_RESPONSE = [
    {
        "fiscal_year_end": "2022-09-24",
        "product_segments": {
            "iPhone": 205489000000,
            "Mac": 40177000000,
            "iPad": 29292000000,
            "Wearables, Home and Accessories": 41241000000,
            "Services": 78129000000
        },
        "geographic_segments": {
            "Americas": 169658000000,
            "Europe": 95118000000,
            "Greater China": 74200000000,
            "Japan": 25977000000,
            "Rest of Asia Pacific": 29375000000
        }
    },
    {
        "fiscal_year_end": "2023-09-30",
        "product_segments": {
            "iPhone": 200583000000,
            "Mac": 29357000000,
            "iPad": 28300000000,
            "Wearables, Home and Accessories": 39845000000,
            "Services": 85200000000
        },
        "geographic_segments": {
            "Americas": 162560000000,
            "Europe": 94294000000,
            "Greater China": 72559000000,
            "Japan": 24257000000,
            "Rest of Asia Pacific": 29615000000
        }
    }
]

MOCK_WRAPPED_RESPONSE = {"data": MOCK_VALID_RESPONSE}


# ===========================================================================
# Unit Tests — _validate_segment_entry
# ===========================================================================

class TestValidateSegmentEntry:
    def test_valid_entry(self):
        entry = {
            "fiscal_year_end": "2023-09-30",
            "product_segments": {"iPhone": 200583000000},
            "geographic_segments": {"Americas": 162560000000}
        }
        assert _validate_segment_entry(entry) is True

    def test_missing_fiscal_year_end(self):
        entry = {
            "product_segments": {"iPhone": 200583000000},
            "geographic_segments": {"Americas": 162560000000}
        }
        assert _validate_segment_entry(entry) is False

    def test_bad_date_format(self):
        entry = {
            "fiscal_year_end": "2023/09/30",
            "product_segments": {},
            "geographic_segments": {}
        }
        assert _validate_segment_entry(entry) is False

    def test_non_dict_segments(self):
        entry = {
            "fiscal_year_end": "2023-09-30",
            "product_segments": "not a dict",
            "geographic_segments": {}
        }
        assert _validate_segment_entry(entry) is False

    def test_empty_segments_are_valid(self):
        entry = {
            "fiscal_year_end": "2023-09-30",
            "product_segments": {},
            "geographic_segments": {}
        }
        assert _validate_segment_entry(entry) is True

    def test_non_dict_input(self):
        assert _validate_segment_entry("not a dict") is False
        assert _validate_segment_entry(42) is False
        assert _validate_segment_entry(None) is False


# ===========================================================================
# Unit Tests — _validate_and_clean_response
# ===========================================================================

class TestValidateAndCleanResponse:
    def test_valid_list_response(self):
        result = _validate_and_clean_response(MOCK_VALID_RESPONSE)
        assert len(result) == 2
        assert result[0]["fiscal_year_end"] == "2022-09-24"
        assert result[1]["fiscal_year_end"] == "2023-09-30"
        assert "iPhone" in result[0]["product_segments"]
        assert result[0]["product_segments"]["iPhone"] == 205489000000

    def test_wrapped_response(self):
        result = _validate_and_clean_response(MOCK_WRAPPED_RESPONSE)
        assert len(result) == 2

    def test_single_entry_in_dict(self):
        single = {
            "fiscal_year_end": "2023-09-30",
            "product_segments": {"iPhone": 200583000000},
            "geographic_segments": {"Americas": 162560000000}
        }
        result = _validate_and_clean_response(single)
        assert len(result) == 1

    def test_invalid_entries_filtered_out(self):
        mixed = [
            {"fiscal_year_end": "2023-09-30", "product_segments": {}, "geographic_segments": {}},
            {"bad_key": "no fiscal year"},
            "not a dict at all"
        ]
        result = _validate_and_clean_response(mixed)
        assert len(result) == 1

    def test_string_values_converted_to_int(self):
        data = [{
            "fiscal_year_end": "2023-09-30",
            "product_segments": {"iPhone": "200583000000.0"},
            "geographic_segments": {"Americas": "162560000000"}
        }]
        result = _validate_and_clean_response(data)
        assert result[0]["product_segments"]["iPhone"] == 200583000000
        assert result[0]["geographic_segments"]["Americas"] == 162560000000

    def test_non_numeric_values_skipped(self):
        data = [{
            "fiscal_year_end": "2023-09-30",
            "product_segments": {"iPhone": "not_a_number", "Mac": 29357000000},
            "geographic_segments": {}
        }]
        result = _validate_and_clean_response(data)
        assert "iPhone" not in result[0]["product_segments"]
        assert result[0]["product_segments"]["Mac"] == 29357000000

    def test_sorted_by_date(self):
        data = [
            {"fiscal_year_end": "2023-09-30", "product_segments": {}, "geographic_segments": {}},
            {"fiscal_year_end": "2020-09-26", "product_segments": {}, "geographic_segments": {}},
            {"fiscal_year_end": "2022-09-24", "product_segments": {}, "geographic_segments": {}},
        ]
        result = _validate_and_clean_response(data)
        assert [r["fiscal_year_end"] for r in result] == ["2020-09-26", "2022-09-24", "2023-09-30"]

    def test_empty_list(self):
        assert _validate_and_clean_response([]) == []

    def test_non_list_non_dict(self):
        assert _validate_and_clean_response("garbage") == []
        assert _validate_and_clean_response(42) == []


# ===========================================================================
# Unit Tests — fetch_revenue_segments with mocked LLM
# ===========================================================================

class TestFetchRevenueSegmentsMocked:
    @patch("data.revenue_segment_fetcher.get_llm_client")
    def test_successful_fetch(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query_json_with_search.return_value = MOCK_VALID_RESPONSE
        mock_get_client.return_value = mock_client

        result = fetch_revenue_segments("AAPL", "Apple Inc.")
        assert len(result) == 2
        assert result[0]["fiscal_year_end"] == "2022-09-24"
        assert "iPhone" in result[0]["product_segments"]
        mock_client.query_json_with_search.assert_called_once()

    @patch("data.revenue_segment_fetcher.get_llm_client")
    def test_llm_returns_wrapped_response(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query_json_with_search.return_value = MOCK_WRAPPED_RESPONSE
        mock_get_client.return_value = mock_client

        result = fetch_revenue_segments("AAPL", "Apple Inc.")
        assert len(result) == 2

    @patch("data.revenue_segment_fetcher.get_llm_client")
    def test_llm_error_returns_empty(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query_json_with_search.side_effect = RuntimeError("API down")
        mock_get_client.return_value = mock_client

        result = fetch_revenue_segments("AAPL", "Apple Inc.")
        assert result == []

    @patch("data.revenue_segment_fetcher.get_llm_client")
    def test_llm_returns_garbage_json(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.query_json_with_search.return_value = {"random": "garbage"}
        mock_get_client.return_value = mock_client

        result = fetch_revenue_segments("AAPL", "Apple Inc.")
        assert result == []


# ===========================================================================
# Integration Tests — hit real OpenAI API
# ===========================================================================

@pytest.mark.network
class TestRevenueSegmentIntegration:
    """Integration tests that hit the OpenAI API with web search. Run with: pytest -m network"""

    def test_full_pipeline_aapl(self):
        """End-to-end: fetch AAPL revenue segments and validate structure."""
        result = fetch_revenue_segments("AAPL", "Apple Inc.")

        # Should have at least 5 years of data
        assert len(result) >= 5, f"Expected >=5 years, got {len(result)}"

        # Check most recent entry has recognizable segments
        latest = result[-1]
        assert latest["fiscal_year_end"] >= "2023-01-01", f"Latest year too old: {latest['fiscal_year_end']}"

        # Product segments should contain recognizable Apple product lines
        product_names = set(latest["product_segments"].keys())
        assert any(
            name.lower() in ["iphone", "services", "mac", "ipad"]
            for name in product_names
        ), f"No recognizable product segments found: {product_names}"

        # Geographic segments should contain recognizable regions
        geo_names = set(latest["geographic_segments"].keys())
        assert any(
            region.lower() in ["americas", "europe", "greater china", "united states"]
            for region in geo_names
        ), f"No recognizable geographic segments found: {geo_names}"

        # All revenue values should be positive and in raw USD (> 1 billion for AAPL)
        for seg_name, seg_val in latest["product_segments"].items():
            assert isinstance(seg_val, int), f"{seg_name} value not int: {type(seg_val)}"
            assert seg_val > 1_000_000_000, f"{seg_name} value looks too small (not raw USD?): {seg_val}"

        # Print summary for visual inspection
        print(f"\n--- AAPL Revenue Segments ({len(result)} years) ---")
        for entry in result[-3:]:  # Show last 3 years
            print(f"\nFY ending {entry['fiscal_year_end']}:")
            print(f"  Products: {json.dumps(entry['product_segments'], indent=4)}")
            print(f"  Geographic: {json.dumps(entry['geographic_segments'], indent=4)}")
