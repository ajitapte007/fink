import os
import json
import requests
import time
import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "local_av_cache"
API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
FUNCTIONS = ["OVERVIEW", "TIME_SERIES_MONTHLY_ADJUSTED", "INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]

def fetch_data(function: str, symbol: str) -> dict:
    if not API_KEY:
        raise ValueError("ALPHAVANTAGE_API_KEY environment variable is not set.")
    url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={API_KEY}"
    print(f"Auto-fetching missing data: {function} for {symbol}...")
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_all_data_for_ticker(ticker: str, force_refresh: bool = False, ttl_hours: int = 168) -> dict:
    """
    Reads the locally seeded AlphaVantage data for the given ticker.
    If the data is missing from the local cache (e.g. new repo clone or new ticker), 
    it automatically hits the AlphaVantage API to fetch and cache it on the fly.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker.upper()}.json"
    
    ticker_data = {}
    file_age_hours = 0
    if cache_file.exists():
        with open(cache_file, "r") as f:
            try:
                ticker_data = json.load(f)
                
                # Check for the embedded timestamp first
                if "_meta_last_refreshed" in ticker_data:
                    dt_obj = datetime.datetime.strptime(ticker_data["_meta_last_refreshed"], '%Y-%m-%d %H:%M:%S')
                    file_age_hours = (datetime.datetime.now() - dt_obj).total_seconds() / 3600
                else:
                    # Fallback to filesystem mtime
                    mtime = os.path.getmtime(cache_file)
                    file_age_hours = (time.time() - mtime) / 3600
            except Exception:
                ticker_data = {}
                file_age_hours = ttl_hours + 1 # force refresh if JSON is corrupted
                
        # If the file is too old and we are not forcing a refresh, we just read from cache
        if force_refresh or file_age_hours > ttl_hours:
            ticker_data = {} # Reset to fetch fresh
            
    updated = False
    for func in FUNCTIONS:
        if func not in ticker_data:
            ticker_data[func] = fetch_data(func, ticker.upper())
            updated = True
            
    if updated:
        # Always inject the current timestamp before writing to disk
        dt_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ticker_data["_meta_last_refreshed"] = dt_str
        
        with open(cache_file, "w") as f:
            json.dump(ticker_data, f)
            
    return ticker_data
