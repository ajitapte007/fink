"""cache_ticker_data() — thread safety and fetch logic.

Ported from mcp/tests in the phase 3 fork. Only the import paths changed: the
orchestrator itself is unmodified, so its behaviour must be too.
"""
import threading
from unittest.mock import patch

import pytest

from mcp_apps.data.cache_orchestrator import cache_ticker_data, _ticker_locks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_FUNCTIONS = ["OVERVIEW", "TIME_SERIES_MONTHLY_ADJUSTED", "INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]

MOCK_RAW_CACHE = {func: {"mock": True} for func in MOCK_FUNCTIONS}


def _make_get_db_cache(return_data=True):
    """Create a mock get_db_cache that either returns data or None."""
    def mock_get_db_cache(symbol, function):
        if return_data:
            return ({"mock": True}, 1700000000, 1800000000, "mock", 0)
        return None
    return mock_get_db_cache


def _miss_then_hit(miss_count=5):
    """get_db_cache stub: first `miss_count` calls miss, subsequent calls hit.

    Models the cache being populated by the fetch that the misses triggered.
    """
    call_count = {"n": 0}

    def side_effect(symbol, function):
        call_count["n"] += 1
        if call_count["n"] <= miss_count:
            return None
        return ({"mock": True}, 1700000000, 1800000000, "mock", 0)

    return side_effect


@pytest.fixture(autouse=True)
def reset_locks():
    """Reset per-ticker locks between tests to avoid cross-test interference."""
    _ticker_locks.clear()
    yield
    _ticker_locks.clear()


# ---------------------------------------------------------------------------
# Test: Cache hit — fast return, no fetch triggered
# ---------------------------------------------------------------------------

@patch("mcp_apps.data.cache_orchestrator.get_db_cache")
def test_cache_hit_returns_without_fetching(mock_get_db):
    """When all AV functions are cached, fetch_alphavantage_data should NOT be called."""
    mock_get_db.side_effect = _make_get_db_cache(return_data=True)

    with patch("mcp_apps.data.cache_orchestrator._fetch_and_check") as mock_fetch_av:
        result = cache_ticker_data("AAPL")

    mock_fetch_av.assert_not_called()
    assert result["error"] is None
    assert result["raw_cache"] is not None
    assert set(result["raw_cache"].keys()) == set(MOCK_FUNCTIONS)


# ---------------------------------------------------------------------------
# Test: Cache miss — triggers AV fetch
# ---------------------------------------------------------------------------

@patch("mcp_apps.data.cache_orchestrator.get_db_cache")
@patch("mcp_apps.data.cache_orchestrator._fetch_and_check")
def test_cache_miss_triggers_av_fetch(mock_fetch_av, mock_get_db):
    """When AV cache is empty, fetch_alphavantage_data should be called."""
    # A miss on the very first function short-circuits the completeness loop,
    # so only one miss is needed before the refetch.
    mock_get_db.side_effect = _miss_then_hit(miss_count=1)
    mock_fetch_av.return_value = (True, None)

    result = cache_ticker_data("MSFT")

    mock_fetch_av.assert_called_once_with("MSFT", mock_data=True)
    assert result["error"] is None
    assert set(result["raw_cache"].keys()) == set(MOCK_FUNCTIONS)


# ---------------------------------------------------------------------------
# Test: Partial cache — a single missing function refetches the whole set
# ---------------------------------------------------------------------------

@patch("mcp_apps.data.cache_orchestrator.get_db_cache")
@patch("mcp_apps.data.cache_orchestrator._fetch_and_check")
def test_partial_cache_triggers_full_refetch(mock_fetch_av, mock_get_db):
    """A miss on any one function should trigger a fetch, not a partial return."""
    calls = {"n": 0}

    def side_effect(symbol, function):
        calls["n"] += 1
        # Third function of the completeness check misses; everything after hits.
        if calls["n"] == 3:
            return None
        return ({"mock": True}, 1700000000, 1800000000, "mock", 0)

    mock_get_db.side_effect = side_effect
    mock_fetch_av.return_value = (True, None)

    result = cache_ticker_data("NEE")

    mock_fetch_av.assert_called_once_with("NEE", mock_data=True)
    assert result["error"] is None


# ---------------------------------------------------------------------------
# Test: Mutex — concurrent calls don't duplicate fetch
# ---------------------------------------------------------------------------

@patch("mcp_apps.data.cache_orchestrator.get_db_cache")
@patch("mcp_apps.data.cache_orchestrator._fetch_and_check")
def test_mutex_prevents_duplicate_fetch(mock_fetch_av, mock_get_db):
    """Two concurrent calls for the same ticker should serialize on the per-ticker lock."""
    def slow_fetch(ticker, mock_data=True):
        import time
        time.sleep(0.1)  # Simulate slow fetch
        return (True, None)

    mock_fetch_av.side_effect = slow_fetch
    mock_get_db.side_effect = _miss_then_hit(miss_count=1)

    results = [None, None]

    def run(idx):
        results[idx] = cache_ticker_data("GOOG")

    t1 = threading.Thread(target=run, args=(0,))
    t2 = threading.Thread(target=run, args=(1,))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # Second thread blocks on the lock, then sees the cache the first thread populated.
    assert mock_fetch_av.call_count == 1
    assert results[0] is not None
    assert results[1] is not None


# ---------------------------------------------------------------------------
# Test: Distinct tickers get distinct locks
# ---------------------------------------------------------------------------

@patch("mcp_apps.data.cache_orchestrator.get_db_cache")
def test_distinct_tickers_get_distinct_locks(mock_get_db):
    """Different tickers should not contend on the same lock."""
    mock_get_db.side_effect = _make_get_db_cache(return_data=True)

    cache_ticker_data("AAPL")
    cache_ticker_data("MSFT")

    assert "AAPL" in _ticker_locks
    assert "MSFT" in _ticker_locks
    assert _ticker_locks["AAPL"] is not _ticker_locks["MSFT"]


# ---------------------------------------------------------------------------
# Test: Ticker normalization
# ---------------------------------------------------------------------------

@patch("mcp_apps.data.cache_orchestrator.get_db_cache")
def test_ticker_is_normalized(mock_get_db):
    """Lowercase/whitespace-padded tickers should normalize to a single lock entry."""
    mock_get_db.side_effect = _make_get_db_cache(return_data=True)

    cache_ticker_data("  aapl  ")

    assert "AAPL" in _ticker_locks
    assert len(_ticker_locks) == 1


# ---------------------------------------------------------------------------
# Test: AV error propagation
# ---------------------------------------------------------------------------

@patch("mcp_apps.data.cache_orchestrator.get_db_cache", return_value=None)
@patch("mcp_apps.data.cache_orchestrator._fetch_and_check")
def test_av_error_propagation(mock_fetch_av, mock_get_db):
    """When AV fetch fails, the error should be returned in the result."""
    mock_fetch_av.return_value = (
        False,
        {"message": "API rate limit exceeded", "details": "Too many requests"},
    )

    result = cache_ticker_data("FAIL")

    assert result["error"] is not None
    assert "rate limit" in result["error"]["message"]
    assert result["raw_cache"] == {}


# ---------------------------------------------------------------------------
# _fetch_and_check — folded in from alphavantage_tool.py in phase 3 step 10.
#
# This is the only place that decides whether a fetch "worked". AlphaVantage
# reports failure inside a 200 body, so HTTP success proves nothing, and the
# two failure modes are independent: an error envelope in a payload, and a
# payload that parsed but failed is_data_corrupt. Missing either one caches
# garbage and every downstream metric silently becomes None.
# ---------------------------------------------------------------------------

from mcp_apps.data.cache_orchestrator import _fetch_and_check  # noqa: E402

_GOOD = {
    "OVERVIEW": {"Symbol": "X"},
    "INCOME_STATEMENT": {"quarterlyReports": [{"fiscalDateEnding": "2024-01-01"}]},
    "_meta_corrupt_functions": [],
}


@patch("mcp_apps.data.cache_orchestrator.get_all_data_for_ticker")
def test_fetch_and_check_accepts_a_clean_payload(mock_get):
    mock_get.return_value = dict(_GOOD)
    assert _fetch_and_check("X", mock_data=True) == (True, None)


@patch("mcp_apps.data.cache_orchestrator.get_all_data_for_ticker")
def test_fetch_and_check_rejects_an_error_envelope_inside_a_200(mock_get):
    """The failure mode raise_for_status cannot see."""
    payload = dict(_GOOD)
    payload["CASH_FLOW"] = {"Error Message": "Invalid API call"}
    mock_get.return_value = payload
    ok, err = _fetch_and_check("X", mock_data=True)
    assert ok is False
    assert "Invalid API call" in err["details"]


@patch("mcp_apps.data.cache_orchestrator.get_all_data_for_ticker")
def test_fetch_and_check_rejects_a_rate_limit_note(mock_get):
    """A throttled response is valid JSON that looks nothing like an error."""
    payload = dict(_GOOD)
    payload["BALANCE_SHEET"] = {"Note": "higher API call volume"}
    mock_get.return_value = payload
    ok, err = _fetch_and_check("X", mock_data=True)
    assert ok is False
    assert "higher API call volume" in err["details"]


@patch("mcp_apps.data.cache_orchestrator.get_all_data_for_ticker")
def test_fetch_and_check_rejects_corrupt_functions(mock_get):
    """Second, independent failure mode: parsed fine, failed is_data_corrupt."""
    payload = dict(_GOOD)
    payload["_meta_corrupt_functions"] = ["CASH_FLOW"]
    mock_get.return_value = payload
    ok, err = _fetch_and_check("X", mock_data=True)
    assert ok is False
    assert "CASH_FLOW" in err["details"]


@patch("mcp_apps.data.cache_orchestrator.get_all_data_for_ticker")
def test_fetch_and_check_converts_an_exception_into_an_error(mock_get):
    """Must not propagate — cache_ticker_data's contract is to return, not raise."""
    mock_get.side_effect = ConnectionError("network down")
    ok, err = _fetch_and_check("X", mock_data=False)
    assert ok is False
    assert "network down" in err["message"]
    assert "Traceback" in err["details"]


def test_fetch_and_check_rejects_an_empty_ticker():
    ok, err = _fetch_and_check("", mock_data=True)
    assert ok is False
    assert "empty" in err["message"].lower()


@patch("mcp_apps.data.cache_orchestrator.get_all_data_for_ticker")
def test_fetch_and_check_passes_mock_data_through(mock_get):
    """FINK_DATA_MODE reaches the fetch layer, or seed mode silently hits the network."""
    mock_get.return_value = dict(_GOOD)
    _fetch_and_check("X", mock_data=True)
    assert mock_get.call_args.kwargs["mock_data"] is True
    _fetch_and_check("X", mock_data=False)
    assert mock_get.call_args.kwargs["mock_data"] is False
