import os
import json
import time
import shutil
import requests
from pathlib import Path

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
TICKERS = ["AAPL", "UNH", "PG", "AMZN", "NEE"]
FUNCTIONS = ["OVERVIEW", "TIME_SERIES_MONTHLY_ADJUSTED", "INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]
CACHE_DIR = Path(__file__).parent / "local_av_cache"
MCP_CACHE_DIR = Path(__file__).parent.parent.parent / "mcp" / "data" / "local_av_cache"

def ensure_cache_dirs():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MCP_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def is_valid_payload(data):
    if not isinstance(data, dict):
        return False
    # Check for rate-limiting warning messages
    info = data.get("Information", "")
    note = data.get("Note", "")
    err = data.get("Error Message", "")
    
    if "rate limit" in info.lower() or "call volume" in info.lower() or "rate limit" in note.lower() or err:
        return False
        
    # Must have some substantial keys
    if not any(k in data for k in ["Symbol", "Name", "annualReports", "quarterlyReports", "Monthly Adjusted Time Series", "Monthly Time Series"]):
        return False
        
    return True

def fetch_data(function, symbol):
    if not API_KEY:
        print(f"Skipping fetch for {symbol} {function} - ALPHAVANTAGE_API_KEY is not set.")
        return None
    url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={API_KEY}"
    print(f"Fetching {function} for {symbol}...")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not is_valid_payload(data):
            print(f"Invalid payload or rate-limit received for {symbol} {function}.")
            return None
        return data
    except Exception as e:
        print(f"Request failed for {symbol} {function}: {str(e)}")
        return None

def build_cache():
    ensure_cache_dirs()
    for symbol in TICKERS:
        cache_file = CACHE_DIR / f"{symbol}.json"
        
        ticker_data = {}
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    ticker_data = json.load(f)
            except Exception as e:
                print(f"Error reading existing cache file for {symbol}: {str(e)}")
                
        updated = False
        for func in FUNCTIONS:
            existing_valid = func in ticker_data and is_valid_payload(ticker_data[func])
            
            # Fetch if missing or force-refresh is wanted
            if not existing_valid:
                data = fetch_data(func, symbol)
                if data:
                    ticker_data[func] = data
                    updated = True
                    # Sleep to respect free tier limit
                    time.sleep(12)
                else:
                    print(f"Could not retrieve valid data for {symbol} {func}. Keeping existing cache if present.")
                    
        if updated:
            with open(cache_file, "w") as f:
                json.dump(ticker_data, f, indent=2)
            print(f"Successfully updated local cache for {symbol}!")
        else:
            print(f"Local cache for {symbol} is up to date (or fetch skipped/failed).")
            
        # Copy to MCP directory to ensure synchronization
        if cache_file.exists():
            shutil.copy(cache_file, MCP_CACHE_DIR / f"{symbol}.json")
            print(f"Synchronized {symbol}.json to MCP directory.")

if __name__ == "__main__":
    build_cache()
