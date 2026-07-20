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
            PRIMARY KEY (symbol, function)
        )
        """
    )
    conn.commit()
    conn.close()

# Auto-initialize database on load
init_db()

def fetch_data(function: str, symbol: str) -> dict:
    # Read API Key dynamically from environment
    api_key = os.getenv("ALPHAVANTAGE_API_KEY") or API_KEY
    if not api_key:
        raise ValueError("ALPHAVANTAGE_API_KEY environment variable is not set.")
        
    url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={api_key}"
    print(f"Auto-fetching missing data: {function} for {symbol}...")
    
    # Sleep to avoid AlphaVantage 1 request/sec limit
    time.sleep(2)
    
    response = requests.get(url)
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

def get_db_cache(symbol: str, function: str, ttl_seconds: int = 86400) -> dict:
    """Reads from SQLite cache if exists and not expired."""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data, timestamp FROM av_cache WHERE symbol = ? AND function = ?",
            (symbol.upper(), function.upper())
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            data_str, timestamp = row
            if time.time() - timestamp < ttl_seconds:
                return json.loads(data_str)
    except Exception as e:
        print(f"SQLite read cache error: {e}")
    return None

def set_db_cache(symbol: str, function: str, data: dict):
    """Writes to SQLite cache."""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO av_cache (symbol, function, data, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (symbol.upper(), function.upper(), json.dumps(data), time.time())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite write cache error: {e}")

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
                        print(f"Mapping Monthly Adjusted to Daily for {symbol} (Offline Fallback)...")
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
            print(f"Error reading local JSON cache file: {e}")
    return None

def get_av_data(symbol: str, function: str, force_refresh: bool = False, ttl_seconds: int = 86400) -> dict:
    """
    Read-Through Cache Implementation:
    1. Checks SQLite database. If valid hit (not expired), returns it.
    2. If miss/expired (or force_refresh), tries fetching from Alpha Vantage network.
    3. If network fetch succeeds, stores in SQLite cache and returns it.
    4. If network fetch fails (rate limit, offline, missing key):
       - Attempts to fall back to the pre-seeded JSON file cache.
       - If no JSON cache exists, attempts to fall back to the expired SQLite cache entry.
       - Otherwise, propagates the error.
    """
    symbol = symbol.upper()
    function = function.upper()
    
    # 1. Check SQLite cache (not expired)
    if not force_refresh:
        cached_data = get_db_cache(symbol, function, ttl_seconds)
        if cached_data is not None:
            return cached_data
            
    # 2. Cache miss/expired -> Try fetching from network
    print(f"Cache miss/expired for {symbol} - {function}. Fetching from network...")
    try:
        data = fetch_data(function, symbol)
        # Store in SQLite cache
        set_db_cache(symbol, function, data)
        return data
    except Exception as e:
        print(f"Network fetch failed for {symbol} - {function}: {e}")
        
        # 3. Fallback to permanent local JSON cache
        local_data = get_local_json_cache(symbol, function)
        if local_data is not None:
            print(f"Falling back to local pre-seeded JSON cache for {symbol} - {function}")
            # Cache it in SQLite so we don't repeat the fallback lookup
            set_db_cache(symbol, function, local_data)
            return local_data
            
        # 4. Fallback to expired SQLite cache entry
        db_path = get_db_path()
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM av_cache WHERE symbol = ? AND function = ?",
                (symbol, function)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                print(f"Falling back to stale SQLite cache for {symbol} - {function}")
                return json.loads(row[0])
        except Exception as ex:
            print(f"Error reading stale cache fallback: {ex}")
            
        # If no fallbacks are available, raise the original network error
        raise e

def get_all_data_for_ticker(ticker: str, force_refresh: bool = False, ttl_hours: int = 168) -> dict:
    """
    Reads all financial statement and series metrics.
    Preserves signature compatibility for process_utils.py.
    """
    ticker = ticker.upper()
    ttl_seconds = ttl_hours * 3600
    ticker_data = {}
    
    for func in FUNCTIONS:
        try:
            ticker_data[func] = get_av_data(ticker, func, force_refresh, ttl_seconds)
        except Exception as e:
            print(f"Failed to load {func} for {ticker}: {e}")
            
    # Inject metadata timestamp
    db_path = get_db_path()
    mtime_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp FROM av_cache WHERE symbol = ? AND function = ? ORDER BY timestamp DESC LIMIT 1",
            (ticker, "OVERVIEW")
        )
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            mtime_str = datetime.datetime.fromtimestamp(row[0]).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
        
    ticker_data["_meta_last_refreshed"] = mtime_str
    return ticker_data
