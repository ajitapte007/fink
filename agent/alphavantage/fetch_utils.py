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
    
    # Sleep to avoid AlphaVantage 1 request/sec limit
    time.sleep(2)
    
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    # Check if AlphaVantage returned a rate limit error (25/day limit)
    info = data.get("Information", "")
    if "rate limit" in info.lower() or "higher API call volume" in info.lower():
        raise Exception(f"AlphaVantage API Rate Limit Hit: {info}")
        
    return data

def get_all_data_for_ticker(ticker: str, force_refresh: bool = False, ttl_hours: int = 168) -> dict:
    """
    Reads the locally seeded AlphaVantage data for the given ticker.
    If the data is missing from the local cache, it hits the API.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker.upper()}.json"
    
    ticker_data = {}
    file_age_hours = 0
    if cache_file.exists():
        with open(cache_file, "r") as f:
            try:
                ticker_data = json.load(f)
                if "_meta_last_refreshed" in ticker_data:
                    dt_obj = datetime.datetime.strptime(ticker_data["_meta_last_refreshed"], '%Y-%m-%d %H:%M:%S')
                    file_age_hours = (datetime.datetime.now() - dt_obj).total_seconds() / 3600
                else:
                    mtime = os.path.getmtime(cache_file)
                    file_age_hours = (time.time() - mtime) / 3600
                    ticker_data["_meta_last_refreshed"] = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                ticker_data = {}
                file_age_hours = ttl_hours + 1
                
    needs_refresh = force_refresh or file_age_hours > ttl_hours or not cache_file.exists()
    
    if needs_refresh:
        print(f"Refreshing cache for {ticker}...")
        new_data = {}
        try:
            for func in FUNCTIONS:
                new_data[func] = fetch_data(func, ticker.upper())
                
            # If all fetches succeed, inject timestamp and overwrite cache
            dt_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            new_data["_meta_last_refreshed"] = dt_str
            
            with open(cache_file, "w") as f:
                json.dump(new_data, f)
            return new_data
            
        except Exception as e:
            print(f"Fetch failed: {e}")
            if ticker_data:
                print("Falling back to old cached data.")
                return ticker_data
            else:
                raise e
    
    return ticker_data
