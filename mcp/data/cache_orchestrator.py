"""
Cache orchestrator — ensures all data for a ticker is ready in the SQLite cache.

Provides a single entry point `cache_ticker_data()` that auto-fetches
AlphaVantage and revenue segment data on cache miss, with per-ticker
mutex protection to prevent duplicate fetches.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

from data.alphavantage_tool import fetch_alphavantage_data
from data.fetch_utils import (
    FUNCTIONS, get_db_cache,
    get_revenue_segment_cache, set_revenue_segment_cache
)
from data.revenue_segment_fetcher import fetch_revenue_segments

_ticker_locks = {}
_global_lock = threading.Lock()


def _get_ticker_lock(ticker: str) -> threading.Lock:
    """Get or create a per-ticker lock for thread-safe fetching."""
    with _global_lock:
        if ticker not in _ticker_locks:
            _ticker_locks[ticker] = threading.Lock()
        return _ticker_locks[ticker]


def cache_ticker_data(ticker: str, include_revenue_segments: bool = False) -> dict:
    """Ensure all data for a ticker is in the cache. Thread-safe per ticker.

    If data is missing, fetches it from AlphaVantage and/or via LLM search.
    Per-ticker mutex prevents duplicate fetches when multiple tools call
    this function concurrently for the same ticker.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL').
        include_revenue_segments: Whether to also fetch 10-K revenue segments.

    Returns:
        dict with keys:
            - raw_cache: dict of AV function name -> data
            - revenue_segment_data: list of segment entries or None
            - error: error dict or None
    """
    ticker = ticker.upper().strip()
    lock = _get_ticker_lock(ticker)
    with lock:
        return _fetch_if_needed(ticker, include_revenue_segments)


def _fetch_if_needed(ticker, include_revenue_segments):
    """Check cache completeness and fetch missing data in parallel."""
    # Check AV cache completeness
    raw_cache = {}
    av_missing = False
    for func in FUNCTIONS:
        entry = get_db_cache(ticker, func)
        if entry is None:
            av_missing = True
            break
        raw_cache[func] = entry[0]

    # Check revenue segment cache
    revenue_segment_data = None
    seg_missing = False
    if include_revenue_segments:
        revenue_segment_data = get_revenue_segment_cache(ticker)
        if revenue_segment_data is None:
            seg_missing = True

    # All cached — fast return
    if not av_missing and not seg_missing:
        return {
            "raw_cache": raw_cache,
            "revenue_segment_data": revenue_segment_data,
            "error": None
        }

    # Parallel fetch missing data.
    # Use ticker as fallback for company name to enable true parallel execution
    # (OVERVIEW with full company name may not be cached yet).
    company_name = raw_cache.get("OVERVIEW", {}).get("Name", ticker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {}
        if av_missing:
            futures["av"] = pool.submit(_fetch_av, ticker)
        if seg_missing:
            futures["seg"] = pool.submit(
                _fetch_revenue_segments, ticker, company_name
            )

        error = None
        if "av" in futures:
            av_result = futures["av"].result()
            if av_result.get("error"):
                error = av_result["error"]
            else:
                raw_cache = av_result["raw_cache"]

        if "seg" in futures:
            revenue_segment_data = futures["seg"].result()

    return {
        "raw_cache": raw_cache,
        "revenue_segment_data": revenue_segment_data,
        "error": error
    }


def _fetch_av(ticker):
    """Fetch all AlphaVantage data and cache it."""
    result = fetch_alphavantage_data(ticker, mock_data=True)
    if result.get("success"):
        raw_cache = {}
        for func in FUNCTIONS:
            entry = get_db_cache(ticker, func)
            if entry:
                raw_cache[func] = entry[0]
        return {"raw_cache": raw_cache, "error": None}
    return {"raw_cache": {}, "error": result.get("error")}


def _fetch_revenue_segments(ticker, company_name):
    """Fetch revenue segments via LLM search and cache them."""
    data = fetch_revenue_segments(ticker, company_name)
    if data:
        set_revenue_segment_cache(ticker, data)
    return data
