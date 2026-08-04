"""Alpha Vantage client and offline-first read-through fetch.

Split out of `fetch_utils.py` during the phase 3 fork. What stayed behind:
the SQLite layer (`..cache`), the FINK_DATA_MODE switch (`..config`), and the
Yahoo quote lookup (`..prices`) — none of which are Alpha Vantage's business.

What lives here is everything that knows AV's shape: its five function names,
its response envelope, its habit of reporting errors inside a 200, and the
seed corpus of recorded responses.

Import direction is one-way: this module imports from the package above it,
never the reverse.
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3
import time
from pathlib import Path

import requests

from ..cache import get_db_cache, get_db_path, set_db_cache
from ..config import OfflineDataUnavailable, get_data_mode, log_info

# Recorded AV responses, one JSON file per ticker. Resolved relative to this
# file, so the corpus must sit beside it — `test_data_paths.py` pins that.
CACHE_DIR = Path(__file__).parent / "local_av_cache"

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

# The five endpoints a complete ticker needs. `is_ticker_cache_corrupt` treats
# a ticker missing any of them as incomplete and refetches the whole set, so
# the statements never drift out of sync with each other.
FUNCTIONS = ["OVERVIEW", "TIME_SERIES_MONTHLY_ADJUSTED", "INCOME_STATEMENT",
             "BALANCE_SHEET", "CASH_FLOW"]


def available_seed_tickers() -> set:
    """Tickers present in the local seed corpus.

    Reads CACHE_DIR rather than recomputing the path. In the pre-fork code this
    function built `Path(__file__).parent / "local_av_cache"` a second time,
    which meant the corpus location was written in two places and moving one
    would silently empty this set while `get_local_json_cache` kept working.
    """
    if not CACHE_DIR.is_dir():
        return set()
    return {p.stem.upper() for p in CACHE_DIR.glob("*.json")}


def fetch_data(function: str, symbol: str) -> dict:
    # Read API Key dynamically from environment
    api_key = os.getenv("ALPHAVANTAGE_API_KEY") or API_KEY
    if not api_key:
        raise ValueError("ALPHAVANTAGE_API_KEY environment variable is not set.")

    url = (f"https://www.alphavantage.co/query?function={function}"
           f"&symbol={symbol}&apikey={api_key}")
    log_info(f"Auto-fetching missing data: {function} for {symbol}...")

    # Sleep to avoid AlphaVantage 1 request/sec limit
    time.sleep(2)

    # 5s was too tight: a full TIME_SERIES_MONTHLY_ADJUSTED is several hundred
    # KB and would intermittently time out, writing a corrupt entry that nothing
    # ever retried.
    response = requests.get(url, timeout=int(os.getenv("AV_HTTP_TIMEOUT", "30")))
    response.raise_for_status()
    data = response.json()

    # AlphaVantage reports failure inside a 200 body, so raise_for_status above
    # is not enough on its own.
    info = data.get("Information", "")
    note = data.get("Note", "")
    err = data.get("Error Message", "")

    if ("rate limit" in info.lower() or "higher API call volume" in info.lower()
            or "rate limit" in note.lower()):
        raise Exception(f"AlphaVantage API Rate Limit Hit: {info or note}")
    if err:
        raise Exception(f"AlphaVantage API Error: {err}")

    return data


def get_local_json_cache(symbol: str, function: str) -> dict:
    """Reads from the permanent pre-seeded JSON cache files in local_av_cache/."""
    cache_file = CACHE_DIR / f"{symbol.upper()}.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                ticker_data = json.load(f)

                # Check direct key
                if function in ticker_data:
                    # Filter out rate limit responses inside JSON cache
                    func_data = ticker_data[function]
                    if (isinstance(func_data, dict) and "Information" not in func_data
                            and "Note" not in func_data):
                        return func_data

                # Special mapping fallback: if TIME_SERIES_DAILY is requested but only
                # TIME_SERIES_MONTHLY_ADJUSTED is in the seed JSON file, simulate it
                if function == "TIME_SERIES_DAILY" and "TIME_SERIES_MONTHLY_ADJUSTED" in ticker_data:
                    monthly_data = ticker_data["TIME_SERIES_MONTHLY_ADJUSTED"]
                    monthly_series = monthly_data.get("Monthly Adjusted Time Series", {})
                    if monthly_series:
                        log_info(f"Mapping Monthly Adjusted to Daily for {symbol} (Offline Fallback)...")
                        daily_series = {}
                        for date_str, values in monthly_series.items():
                            daily_series[date_str] = {
                                "1. open": values.get("1. open", "0.0"),
                                "2. high": values.get("2. high", "0.0"),
                                "3. low": values.get("3. low", "0.0"),
                                "4. close": values.get("5. adjusted close", values.get("4. close", "0.0")),
                                "5. volume": values.get("6. volume", "0")
                            }
                        return {
                            "Meta Data": {
                                "1. Information": "Daily Prices (open, high, low, close, volume) Daily Time Series",
                                "2. Symbol": symbol.upper()
                            },
                            "Time Series (Daily)": daily_series
                        }
        except Exception as e:
            log_info(f"Error reading local JSON cache file: {e}")
    return None


def is_data_corrupt(function: str, data: dict) -> bool:
    if not data or not isinstance(data, dict):
        return True
    if "Error Message" in data or "Note" in data or "Information" in data:
        return True

    # Check function-specific keys
    if function in ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]:
        if "annualReports" not in data or "quarterlyReports" not in data:
            return True
        if not data.get("annualReports") and not data.get("quarterlyReports"):
            return True
    elif function == "OVERVIEW":
        if "Symbol" not in data:
            return True
    elif function == "TIME_SERIES_MONTHLY_ADJUSTED":
        if ("Monthly Adjusted Time Series" not in data
                and "Monthly Time Series" not in data):
            return True
    return False


def calculate_robust_ttl(function: str, data: dict, default_ttl_seconds: int) -> int:
    """TTL from the gap between the last two report dates.

    Fundamentals only change when a company files, so expiring on a fixed clock
    either refetches unchanged statements or serves stale ones. This aims the
    expiry just past the next expected filing.
    """
    now = time.time()

    try:
        dates = []
        if function in ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]:
            # Look at quarterly reports
            reports = data.get("quarterlyReports", [])
            if not reports:
                reports = data.get("annualReports", [])

            for r in reports:
                d_str = r.get("fiscalDateEnding")
                if d_str:
                    dates.append(datetime.datetime.strptime(d_str, "%Y-%m-%d").date())
        elif function == "OVERVIEW":
            lq = data.get("LatestQuarter")
            if lq:
                dates.append(datetime.datetime.strptime(lq, "%Y-%m-%d").date())
        elif function == "TIME_SERIES_MONTHLY_ADJUSTED":
            return default_ttl_seconds

        if not dates:
            return default_ttl_seconds

        dates = sorted(list(set(dates)), reverse=True)
        if len(dates) >= 2:
            gap = (dates[0] - dates[1]).days
        else:
            gap = 90

        last_report = dates[0]
        next_expected = last_report + datetime.timedelta(days=gap)
        expires_date = next_expected + datetime.timedelta(days=15)
        expires_ts = time.mktime(expires_date.timetuple())

        if expires_ts < now:
            return 43200  # 12 hours

        ttl = int(expires_ts - now)
        return max(43200, min(ttl, 90 * 86400))

    except Exception as e:
        log_info(f"Error calculating robust TTL for {function}: {e}")
        return default_ttl_seconds


def get_av_data(symbol: str, function: str, force_refresh: bool = False,
                ttl_seconds: int = 86400, mock_data: bool = True) -> dict:
    """
    Offline-First Read-Through Cache Implementation:
    1. Checks SQLite database. If valid hit (not expired, not corrupt), returns it immediately.
    2. If SQLite cache is missing/expired/corrupt, check if mock_data is enabled.
       - If enabled and JSON file has it, write to SQLite and return it.
    3. If not found in mock JSON or mock_data is disabled, fetch from Alpha Vantage network.
    """
    symbol = symbol.upper()
    function = function.upper()

    # 1. Check SQLite cache (active, not expired, not corrupt)
    if not force_refresh:
        cached_entry = get_db_cache(symbol, function)
        if cached_entry is not None:
            data, timestamp, expires_at, source, is_corrupt = cached_entry
            # If not marked corrupt, not corrupt on-the-fly, and not expired, return it
            if is_corrupt == 0 and not is_data_corrupt(function, data) and time.time() < expires_at:
                return {
                    "data": data,
                    "timestamp": timestamp,
                    "expires_at": expires_at,
                    "source": source,
                    "is_corrupt": False
                }

    # 2. Try permanent local JSON cache first if mock_data is enabled (Offline-first)
    if mock_data:
        local_data = get_local_json_cache(symbol, function)
        if local_data is not None:
            log_info(f"Populating SQLite cache from local JSON cache: {symbol} - {function}")
            timestamp = time.time()
            is_corrupt = 1 if is_data_corrupt(function, local_data) else 0
            ttl_to_use = calculate_robust_ttl(function, local_data, ttl_seconds)
            expires_at = timestamp + ttl_to_use
            set_db_cache(symbol, function, local_data, timestamp, expires_at, "mock", is_corrupt)
            return {
                "data": local_data,
                "timestamp": timestamp,
                "expires_at": expires_at,
                "source": "mock",
                "is_corrupt": bool(is_corrupt)
            }

    # 3. Cache miss/expired/corrupt -> Fetch from network, unless we're in seed mode.
    if get_data_mode() == "seed":
        raise OfflineDataUnavailable(
            f"{symbol} - {function} is not in the SQLite cache or the seed corpus, and "
            f"FINK_DATA_MODE=seed forbids network access. Seeded tickers: "
            f"{', '.join(sorted(available_seed_tickers()))}."
        )

    log_info(f"Cache miss/refresh for {symbol} - {function}. Fetching from network...")
    try:
        data = fetch_data(function, symbol)
        timestamp = time.time()
        is_corrupt = 1 if is_data_corrupt(function, data) else 0
        ttl_to_use = calculate_robust_ttl(function, data, ttl_seconds)
        expires_at = timestamp + ttl_to_use
        set_db_cache(symbol, function, data, timestamp, expires_at, "api", is_corrupt)
        return {
            "data": data,
            "timestamp": timestamp,
            "expires_at": expires_at,
            "source": "api",
            "is_corrupt": bool(is_corrupt)
        }
    except Exception as e:
        log_info(f"Network fetch failed for {symbol} - {function}: {e}")

        # 4. Fallback to expired/stale SQLite cache entry but mark it as corrupt
        cached_entry = get_db_cache(symbol, function)
        if cached_entry is not None:
            data, timestamp, expires_at, source, is_corrupt = cached_entry
            log_info(f"Falling back to stale SQLite cache for {symbol} - {function} and marking corrupt")
            set_db_cache(symbol, function, data, timestamp, expires_at, source, is_corrupt=1)
            return {
                "data": data,
                "timestamp": timestamp,
                "expires_at": expires_at,
                "source": f"{source} (corrupt-stale)",
                "is_corrupt": True
            }

        # If no fallbacks are available, raise the original network error
        raise e


def is_ticker_cache_corrupt(symbol: str) -> bool:
    """
    Checks if a ticker's cache as a whole is incomplete, expired, or marked corrupt.
    """
    db_path = get_db_path()
    now = time.time()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT function, expires_at, is_corrupt FROM av_cache WHERE symbol = ?",
            (symbol.upper(),)
        )
        rows = cursor.fetchall()
        conn.close()

        cached_funcs = {row[0] for row in rows}
        # Incomplete cache if missing any required function
        if not all(func in cached_funcs for func in FUNCTIONS):
            return True

        for func, expires_at, is_corrupt in rows:
            if is_corrupt == 1:
                return True
            if expires_at < now:
                return True

        return False
    except Exception:
        return True


def get_all_data_for_ticker(ticker: str, force_refresh: bool = False,
                            ttl_hours: int = 168, mock_data: bool = True) -> dict:
    """
    Reads all financial statement and series metrics.
    Returns metadata summary along with the data dict.
    """
    ticker = ticker.upper()
    ttl_seconds = ttl_hours * 3600
    ticker_data = {}

    # Check if we need to force refetch all data globally to keep statements in sync
    global_refresh = force_refresh
    if not global_refresh:
        global_refresh = is_ticker_cache_corrupt(ticker)

    source = "unknown"
    min_expires_at = float("inf")
    max_timestamp = 0.0
    corrupt_functions = []

    for func in FUNCTIONS:
        try:
            res = get_av_data(ticker, func, global_refresh, ttl_seconds, mock_data)
            ticker_data[func] = res["data"]
            source = res["source"]
            min_expires_at = min(min_expires_at, res["expires_at"])
            max_timestamp = max(max_timestamp, res["timestamp"])
            if res.get("is_corrupt"):
                corrupt_functions.append(func)
        except Exception as e:
            log_info(f"Failed to load {func} for {ticker}: {e}")
            corrupt_functions.append(func)

    mtime_str = (datetime.datetime.fromtimestamp(max_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                 if max_timestamp else "Unknown")
    expires_str = (datetime.datetime.fromtimestamp(min_expires_at).strftime('%Y-%m-%d %H:%M:%S')
                   if min_expires_at != float("inf") else "Unknown")

    ticker_data["_meta_last_refreshed"] = mtime_str
    ticker_data["_meta_expires_at"] = expires_str
    ticker_data["_meta_source"] = source
    ticker_data["_meta_corrupt_functions"] = corrupt_functions
    return ticker_data
