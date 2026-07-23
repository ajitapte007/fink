# mcp/tests/test_alphavantage_tool.py
import pytest
from data.alphavantage_tool import fetch_alphavantage_data

def test_fetch_valid_ticker_mock():
    # Test AMZN which has a mock JSON file in local_av_cache
    result = fetch_alphavantage_data("AMZN")
    assert result["success"] is True
    assert result["ticker"] == "AMZN"
    assert result["source"] in ["mock", "cache"]
    assert "last_refreshed" in result
    assert "expires_at" in result
    assert result["error_details"] is None

def test_fetch_invalid_ticker():
    # Test an empty ticker symbol or a ticker that is clearly invalid/not in mock and doesn't exist
    result = fetch_alphavantage_data("")
    assert result["success"] is False
    assert "error" in result
    
    result = fetch_alphavantage_data("INVALIDTICKER12345")
    if not result["success"]:
        assert "error" in result
