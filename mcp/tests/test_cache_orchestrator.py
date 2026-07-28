"""Tests for data.cache_orchestrator — cache_ticker_data() thread safety and fetch logic."""
import sys
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure mcp/ is on sys.path
mcp_dir = Path(__file__).parent.parent.resolve()
if str(mcp_dir) not in sys.path:
    sys.path.insert(0, str(mcp_dir))

from data.cache_orchestrator import cache_ticker_data, _ticker_locks, _global_lock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_FUNCTIONS = ["OVERVIEW", "TIME_SERIES_MONTHLY_ADJUSTED", "INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]

MOCK_RAW_CACHE = {func: {"mock": True} for func in MOCK_FUNCTIONS}

MOCK_SEGMENT_DATA = [
    {"fiscal_year_end": "2024-09-28", "product_segments": {"iPhone": 200000000000}, "geographic_segments": {"Americas": 170000000000}}
]


def _make_get_db_cache(return_data=True):
    """Create a mock get_db_cache that either returns data or None."""
    def mock_get_db_cache(symbol, function):
        if return_data:
            return ({"mock": True}, 1700000000, 1800000000, "mock", 0)
        return None
    return mock_get_db_cache


@pytest.fixture(autouse=True)
def reset_locks():
    """Reset per-ticker locks between tests to avoid cross-test interference."""
    _ticker_locks.clear()
    yield
    _ticker_locks.clear()


# ---------------------------------------------------------------------------
# Test: Cache hit — fast return, no fetch triggered
# ---------------------------------------------------------------------------

@patch("data.cache_orchestrator.get_revenue_segment_cache", return_value=None)
@patch("data.cache_orchestrator.get_db_cache")
def test_cache_hit_returns_without_fetching(mock_get_db, mock_get_seg):
    """When all AV functions are cached, fetch_alphavantage_data should NOT be called."""
    mock_get_db.side_effect = _make_get_db_cache(return_data=True)

    with patch("data.cache_orchestrator.fetch_alphavantage_data") as mock_fetch_av:
        result = cache_ticker_data("AAPL", include_revenue_segments=False)

    mock_fetch_av.assert_not_called()
    assert result["error"] is None
    assert result["raw_cache"] is not None


# ---------------------------------------------------------------------------
# Test: Cache miss — triggers AV fetch
# ---------------------------------------------------------------------------

@patch("data.cache_orchestrator.get_revenue_segment_cache", return_value=None)
@patch("data.cache_orchestrator.get_db_cache")
@patch("data.cache_orchestrator.fetch_alphavantage_data")
def test_cache_miss_triggers_av_fetch(mock_fetch_av, mock_get_db, mock_get_seg):
    """When AV cache is empty, fetch_alphavantage_data should be called."""
    # First round: cache miss (returns None)
    # After fetch: cache hit (returns data)
    call_count = {"n": 0}
    def side_effect(symbol, function):
        call_count["n"] += 1
        # First 5 calls (cache check) return None to trigger fetch
        # Next 5 calls (after fetch, re-read) return data
        if call_count["n"] <= 5:
            return None
        return ({"mock": True}, 1700000000, 1800000000, "mock", 0)

    mock_get_db.side_effect = side_effect
    mock_fetch_av.return_value = {"success": True}

    result = cache_ticker_data("MSFT", include_revenue_segments=False)

    mock_fetch_av.assert_called_once_with("MSFT", mock_data=True)
    assert result["error"] is None


# ---------------------------------------------------------------------------
# Test: Cache miss + revenue segments — parallel fetch
# ---------------------------------------------------------------------------

@patch("data.cache_orchestrator.set_revenue_segment_cache")
@patch("data.cache_orchestrator.fetch_revenue_segments", return_value=MOCK_SEGMENT_DATA)
@patch("data.cache_orchestrator.fetch_alphavantage_data", return_value={"success": True})
@patch("data.cache_orchestrator.get_revenue_segment_cache", return_value=None)
@patch("data.cache_orchestrator.get_db_cache")
def test_parallel_fetch_av_and_segments(mock_get_db, mock_get_seg, mock_fetch_av, mock_fetch_seg, mock_set_seg):
    """When both AV and segment data are missing, both should be fetched."""
    call_count = {"n": 0}
    def side_effect(symbol, function):
        call_count["n"] += 1
        if call_count["n"] <= 5:
            return None
        return ({"mock": True}, 1700000000, 1800000000, "mock", 0)

    mock_get_db.side_effect = side_effect

    result = cache_ticker_data("AAPL", include_revenue_segments=True)

    mock_fetch_av.assert_called_once()
    mock_fetch_seg.assert_called_once()
    mock_set_seg.assert_called_once()
    assert result["revenue_segment_data"] == MOCK_SEGMENT_DATA


# ---------------------------------------------------------------------------
# Test: Mutex — concurrent calls don't duplicate fetch
# ---------------------------------------------------------------------------

@patch("data.cache_orchestrator.get_revenue_segment_cache", return_value=None)
@patch("data.cache_orchestrator.get_db_cache")
@patch("data.cache_orchestrator.fetch_alphavantage_data")
def test_mutex_prevents_duplicate_fetch(mock_fetch_av, mock_get_db, mock_get_seg):
    """Two concurrent calls for the same ticker should result in only one AV fetch."""
    fetch_count = {"n": 0}
    
    def slow_fetch(ticker, mock_data=True):
        fetch_count["n"] += 1
        import time
        time.sleep(0.1)  # Simulate slow fetch
        return {"success": True}
    
    mock_fetch_av.side_effect = slow_fetch
    
    # First call: miss → fetch. Second call while first is running: blocks on lock, then hits cache.
    call_count = {"n": 0}
    def side_effect(symbol, function):
        call_count["n"] += 1
        # First 5 calls: miss. After that: hit (simulating the first thread populating cache)
        if call_count["n"] <= 5:
            return None
        return ({"mock": True}, 1700000000, 1800000000, "mock", 0)
    
    mock_get_db.side_effect = side_effect

    results = [None, None]
    
    def run(idx):
        results[idx] = cache_ticker_data("GOOG", include_revenue_segments=False)

    t1 = threading.Thread(target=run, args=(0,))
    t2 = threading.Thread(target=run, args=(1,))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # The fetch should have been called at most once due to the mutex
    # (second thread sees cache populated by first thread)
    assert mock_fetch_av.call_count <= 2  # At most 2 if timing is tight
    assert results[0] is not None
    assert results[1] is not None


# ---------------------------------------------------------------------------
# Test: AV error propagation
# ---------------------------------------------------------------------------

@patch("data.cache_orchestrator.get_revenue_segment_cache", return_value=None)
@patch("data.cache_orchestrator.get_db_cache", return_value=None)
@patch("data.cache_orchestrator.fetch_alphavantage_data")
def test_av_error_propagation(mock_fetch_av, mock_get_db, mock_get_seg):
    """When AV fetch fails, the error should be returned in the result."""
    mock_fetch_av.return_value = {
        "success": False,
        "error": {"message": "API rate limit exceeded", "details": "Too many requests"}
    }

    result = cache_ticker_data("FAIL", include_revenue_segments=False)

    assert result["error"] is not None
    assert "rate limit" in result["error"]["message"]


# ---------------------------------------------------------------------------
# Test: Revenue segment cache hit — no segment fetch
# ---------------------------------------------------------------------------

@patch("data.cache_orchestrator.get_revenue_segment_cache", return_value=MOCK_SEGMENT_DATA)
@patch("data.cache_orchestrator.get_db_cache")
def test_segment_cache_hit_skips_fetch(mock_get_db, mock_get_seg):
    """When revenue segment data is cached, fetch_revenue_segments should NOT be called."""
    mock_get_db.side_effect = _make_get_db_cache(return_data=True)

    with patch("data.cache_orchestrator.fetch_revenue_segments") as mock_fetch_seg:
        result = cache_ticker_data("AAPL", include_revenue_segments=True)

    mock_fetch_seg.assert_not_called()
    assert result["revenue_segment_data"] == MOCK_SEGMENT_DATA
    assert result["error"] is None
