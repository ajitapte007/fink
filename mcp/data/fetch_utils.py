import os
import json
import sqlite3
import time
import datetime
from pathlib import Path
import requests

CACHE_DIR = Path(__file__).parent / "local_av_cache"
API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
FUNCTIONS = ["OVERVIEW", "TIME_SERIES_MONTHLY_ADJUSTED", "INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]

# SQLite Database Path Config
DB_PATH_DEFAULT = "/app/backend/data/alphavantage_cache.db"
DB_PATH_ENV = os.getenv("ALPHAVANTAGE_CACHE_DB")

def get_db_path() -> Path:
    if DB_PATH_ENV:
        return Path(DB_PATH_ENV)
    
    # Try the default directory in container
    default_path = Path(DB_PATH_DEFAULT)
    try:
        default_path.parent.mkdir(parents=True, exist_ok=True)
        # Check if writable by trying to create/open it
        conn = sqlite3.connect(str(default_path))
        conn.close()
        return default_path
    except Exception:
        # Fallback to local directory relative to this file
        fallback_path = Path(__file__).parent / "alphavantage_cache.db"
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        return fallback_path

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS av_cache (
            symbol TEXT,
            function TEXT,
            data TEXT,
            timestamp REAL,
            expires_at REAL,
            source TEXT,
            PRIMARY KEY (symbol, function)
        )
        """
    )
    # Upgrade old databases if columns don't exist
    try:
        cursor.execute("ALTER TABLE av_cache ADD COLUMN expires_at REAL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE av_cache ADD COLUMN source TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

# Auto-initialize database on load
init_db()

import sys

def log_info(msg: str):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()

def fetch_data(function: str, symbol: str) -> dict:
    # Read API Key dynamically from environment
    api_key = os.getenv("ALPHAVANTAGE_API_KEY") or API_KEY
    if not api_key:
        raise ValueError("ALPHAVANTAGE_API_KEY environment variable is not set.")
        
    url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={api_key}"
    log_info(f"Auto-fetching missing data: {function} for {symbol}...")
    
    # Sleep to avoid AlphaVantage 1 request/sec limit
    time.sleep(2)
    
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    
    # Check if AlphaVantage returned a rate limit error (25/day limit)
    info = data.get("Information", "")
    note = data.get("Note", "")
    err = data.get("Error Message", "")
    
    if "rate limit" in info.lower() or "higher API call volume" in info.lower() or "rate limit" in note.lower():
        raise Exception(f"AlphaVantage API Rate Limit Hit: {info or note}")
    if err:
        raise Exception(f"AlphaVantage API Error: {err}")
        
    return data

def get_db_cache(symbol: str, function: str) -> tuple:
    """Reads from SQLite cache. Returns (data, timestamp, expires_at, source) or None."""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data, timestamp, expires_at, source FROM av_cache WHERE symbol = ? AND function = ?",
            (symbol.upper(), function.upper())
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            data_str, timestamp, expires_at, source = row
            # Upgrade legacy entries if columns are empty
            if expires_at is None:
                expires_at = timestamp + 86400 * 7
            if source is None:
                source = "api"
            return json.loads(data_str), timestamp, expires_at, source
    except Exception as e:
        log_info(f"SQLite read cache error: {e}")
    return None

def set_db_cache(symbol: str, function: str, data: dict, timestamp: float, expires_at: float, source: str):
    """Writes to SQLite cache."""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO av_cache (symbol, function, data, timestamp, expires_at, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (symbol.upper(), function.upper(), json.dumps(data), timestamp, expires_at, source)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log_info(f"SQLite write cache error: {e}")

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
                    if isinstance(func_data, dict) and "Information" not in func_data and "Note" not in func_data:
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

def get_av_data(symbol: str, function: str, force_refresh: bool = False, ttl_seconds: int = 86400, mock_data: bool = True) -> dict:
    """
    Offline-First Read-Through Cache Implementation:
    1. Checks SQLite database. If valid hit (not expired), returns it immediately.
    2. If SQLite cache is missing/expired, check if mock_data is enabled.
       - If enabled and JSON file has it, write to SQLite and return it.
    3. If not found in mock JSON or mock_data is disabled, fetch from Alpha Vantage network.
    """
    symbol = symbol.upper()
    function = function.upper()
    
    # 1. Check SQLite cache (active and not expired)
    if not force_refresh:
        cached_entry = get_db_cache(symbol, function)
        if cached_entry is not None:
            data, timestamp, expires_at, source = cached_entry
            if time.time() < expires_at:
                return {
                    "data": data,
                    "timestamp": timestamp,
                    "expires_at": expires_at,
                    "source": source
                }
            
    # 2. Try permanent local JSON cache first if mock_data is enabled (Offline-first)
    if mock_data:
        local_data = get_local_json_cache(symbol, function)
        if local_data is not None:
            log_info(f"Populating SQLite cache from local JSON cache: {symbol} - {function}")
            timestamp = time.time()
            expires_at = timestamp + ttl_seconds
            set_db_cache(symbol, function, local_data, timestamp, expires_at, "mock")
            return {
                "data": local_data,
                "timestamp": timestamp,
                "expires_at": expires_at,
                "source": "mock"
            }
            
    # 3. Cache miss/expired -> Fetch from network
    log_info(f"Cache miss for {symbol} - {function}. Fetching from network...")
    try:
        data = fetch_data(function, symbol)
        timestamp = time.time()
        expires_at = timestamp + ttl_seconds
        set_db_cache(symbol, function, data, timestamp, expires_at, "api")
        return {
            "data": data,
            "timestamp": timestamp,
            "expires_at": expires_at,
            "source": "api"
        }
    except Exception as e:
        log_info(f"Network fetch failed for {symbol} - {function}: {e}")
        
        # 4. Fallback to expired SQLite cache entry
        cached_entry = get_db_cache(symbol, function)
        if cached_entry is not None:
            data, timestamp, expires_at, source = cached_entry
            log_info(f"Falling back to stale SQLite cache for {symbol} - {function}")
            return {
                "data": data,
                "timestamp": timestamp,
                "expires_at": expires_at,
                "source": f"{source} (stale)"
            }
            
        # If no fallbacks are available, raise the original network error
        raise e

def get_all_data_for_ticker(ticker: str, force_refresh: bool = False, ttl_hours: int = 168, mock_data: bool = True) -> dict:
    """
    Reads all financial statement and series metrics.
    Returns metadata summary along with the data dict.
    """
    ticker = ticker.upper()
    ttl_seconds = ttl_hours * 3600
    ticker_data = {}
    
    source = "unknown"
    min_expires_at = float("inf")
    max_timestamp = 0.0
    
    for func in FUNCTIONS:
        try:
            res = get_av_data(ticker, func, force_refresh, ttl_seconds, mock_data)
            ticker_data[func] = res["data"]
            source = res["source"]
            min_expires_at = min(min_expires_at, res["expires_at"])
            max_timestamp = max(max_timestamp, res["timestamp"])
        except Exception as e:
            log_info(f"Failed to load {func} for {ticker}: {e}")
            
    mtime_str = datetime.datetime.fromtimestamp(max_timestamp).strftime('%Y-%m-%d %H:%M:%S') if max_timestamp else "Unknown"
    expires_str = datetime.datetime.fromtimestamp(min_expires_at).strftime('%Y-%m-%d %H:%M:%S') if min_expires_at != float("inf") else "Unknown"
    
    ticker_data["_meta_last_refreshed"] = mtime_str
    ticker_data["_meta_expires_at"] = expires_str
    ticker_data["_meta_source"] = source
    return ticker_data
