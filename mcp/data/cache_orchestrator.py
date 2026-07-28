"""
Cache orchestrator — ensures all data for a ticker is ready in the SQLite cache.

Provides a single entry point `cache_ticker_data()` that auto-fetches
AlphaVantage data on cache miss, with per-ticker mutex protection to
prevent duplicate fetches.
"""
import threading

from data.alphavantage_tool import fetch_alphavantage_data
from data.fetch_utils import FUNCTIONS, get_db_cache, get_data_mode

_ticker_locks = {}
_global_lock = threading.Lock()


def _get_ticker_lock(ticker: str) -> threading.Lock:
    """Get or create a per-ticker lock for thread-safe fetching."""
    with _global_lock:
        if ticker not in _ticker_locks:
            _ticker_locks[ticker] = threading.Lock()
        return _ticker_locks[ticker]


def cache_ticker_data(ticker: str) -> dict:
    """Ensure all data for a ticker is in the cache. Thread-safe per ticker.

    If data is missing, fetches it from AlphaVantage. The per-ticker mutex
    prevents duplicate fetches when multiple tools call this function
    concurrently for the same ticker. Different tickers fetch in parallel
    without contention.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL').

    Returns:
        dict with keys:
            - raw_cache: dict of AV function name -> data
            - error: error dict or None
    """
    ticker = ticker.upper().strip()
    lock = _get_ticker_lock(ticker)
    with lock:
        return _fetch_if_needed(ticker)


def _fetch_if_needed(ticker):
    """Return cached data, fetching from AlphaVantage if anything is missing."""
    raw_cache = {}
    for func in FUNCTIONS:
        entry = get_db_cache(ticker, func)
        if entry is None:
            return _fetch_av(ticker)
        raw_cache[func] = entry[0]

    return {"raw_cache": raw_cache, "error": None}


def _fetch_av(ticker):
    """Fetch all AlphaVantage data and cache it.

    `mock_data` follows FINK_DATA_MODE rather than being hardcoded. In "live" it is
    False, so production serves real API data instead of silently shadowing the five
    seeded tickers (AAPL, AMZN, NEE, PG, UNH) with fixture data. In "seed" it is True
    and the network is unreachable, so tests are deterministic and offline.
    """
    use_seed = get_data_mode() == "seed"
    result = fetch_alphavantage_data(ticker, mock_data=use_seed)
    if result.get("success"):
        raw_cache = {}
        for func in FUNCTIONS:
            entry = get_db_cache(ticker, func)
            if entry:
                raw_cache[func] = entry[0]
        return {"raw_cache": raw_cache, "error": None}
    return {"raw_cache": {}, "error": result.get("error")}
