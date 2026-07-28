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
    # Empty ticker is rejected before any lookup
    result = fetch_alphavantage_data("")
    assert result["success"] is False
    assert "error" in result

    # A ticker absent from both the cache and the seed corpus must fail cleanly.
    # Under FINK_DATA_MODE=seed (forced by conftest) this cannot reach the network,
    # so the outcome is deterministic rather than "whatever AlphaVantage says today".
    result = fetch_alphavantage_data("INVALIDTICKER12345")
    assert result["success"] is False
    assert "error" in result


def test_seed_mode_never_reaches_the_network():
    """In seed mode an uncached, unseeded ticker raises instead of calling out.

    Guards the regression where mock_data=True still fell through to the live API,
    letting the unit suite consume AlphaVantage quota and vary in runtime by 6x.
    """
    import pytest
    from data.fetch_utils import (
        get_av_data, get_data_mode, available_seed_tickers, OfflineDataUnavailable
    )

    assert get_data_mode() == "seed", "conftest should force seed mode for tests"
    assert "INVALIDTICKER12345" not in available_seed_tickers()

    with pytest.raises(OfflineDataUnavailable):
        get_av_data("INVALIDTICKER12345", "OVERVIEW", force_refresh=True, mock_data=True)
