"""
Cache orchestrator — ensures all data for a ticker is ready in the SQLite cache.

Provides a single entry point `cache_ticker_data()` that auto-fetches
AlphaVantage data on cache miss, with per-ticker mutex protection to
prevent duplicate fetches.

`_fetch_and_check` was `alphavantage_tool.fetch_alphavantage_data`, an 81-line
module in `mcp/data`. Despite the name it was never an MCP tool — nothing
registered it — and this was its only caller, reading two of the ten keys it
returned. The other eight (corporate_identity, valid_metric_keys, source,
last_refreshed, expires_at, error_details, corrupt_functions, ticker) were
computed on every fetch and discarded, including a `get_corporate_identity`
call that hits the network. Folded here in phase 3 step 10, after the golden
engine test was passing so that test guarded the change.
"""
import traceback
import threading

from .alphavantage.fetch import FUNCTIONS, get_all_data_for_ticker
from .cache import get_db_cache
from .config import get_data_mode

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


def _fetch_and_check(ticker: str, mock_data: bool) -> tuple[bool, dict | None]:
    """Fetch every AV function for a ticker. Returns (ok, error_or_None).

    AlphaVantage reports failure inside a 200 body, so a successful HTTP call
    proves nothing. Two independent things can go wrong and both are checked:
    an error envelope in any payload, and a function that `is_data_corrupt`
    rejected (surfaced by the fetch layer as `_meta_corrupt_functions`).
    """
    if not ticker:
        return False, {"message": "Ticker symbol cannot be empty",
                       "details": "Missing ticker parameter"}
    try:
        raw = get_all_data_for_ticker(ticker, mock_data=mock_data)
    except Exception as e:
        return False, {"message": str(e), "details": traceback.format_exc()}

    api_errors = ""
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        if "Error Message" in val:
            api_errors += f"API Error in {key}: {val['Error Message']}. "
        elif "Note" in val:
            api_errors += f"API Note in {key}: {val['Note']}. "

    corrupt = raw.get("_meta_corrupt_functions", [])
    if api_errors or corrupt:
        return False, {
            "message": "Data fetch failed or returned corrupt files",
            "details": f"Failed or corrupt functions: {corrupt}. "
                       f"API Errors: {api_errors}",
        }
    return True, None


def _fetch_av(ticker):
    """Fetch all AlphaVantage data and cache it.

    `mock_data` follows FINK_DATA_MODE rather than being hardcoded. In "live" it is
    False, so production serves real API data instead of silently shadowing the
    seeded tickers with fixture data. In "seed" it is True and the network is
    unreachable, so tests are deterministic and offline.

    Re-reads from SQLite rather than using the returned payloads: the fetch
    layer writes as it goes, and reading back proves the write landed.
    """
    ok, error = _fetch_and_check(ticker, mock_data=get_data_mode() == "seed")
    if not ok:
        return {"raw_cache": {}, "error": error}

    raw_cache = {}
    for func in FUNCTIONS:
        entry = get_db_cache(ticker, func)
        if entry:
            raw_cache[func] = entry[0]
    return {"raw_cache": raw_cache, "error": None}
