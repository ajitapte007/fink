import os
import json
import time
import requests
from pathlib import Path

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "3G4CDSY4TJ4QVIXF")
TICKERS = ["AAPL", "UNH", "PG", "AMZN", "NEE"]
FUNCTIONS = ["OVERVIEW", "TIME_SERIES_MONTHLY_ADJUSTED", "INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]
CACHE_DIR = Path(__file__).parent / "local_av_cache"

def ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def fetch_data(function, symbol):
    url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={API_KEY}"
    print(f"Fetching {function} for {symbol}...")
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    if "Information" in data and "rate limit" in data["Information"].lower():
        print(f"Rate limited on {symbol} {function}. Waiting 60s...")
        time.sleep(60)
        return fetch_data(function, symbol) # Retry
    return data

def build_cache():
    ensure_cache_dir()
    for symbol in TICKERS:
        cache_file = CACHE_DIR / f"{symbol}.json"
        
        ticker_data = {}
        if cache_file.exists():
            with open(cache_file, "r") as f:
                ticker_data = json.load(f)
                
        updated = False
        for func in FUNCTIONS:
            if func not in ticker_data:
                data = fetch_data(func, symbol)
                ticker_data[func] = data
                updated = True
                # Sleep to respect standard 5 calls/min limit on free tier, just in case
                time.sleep(12)
                
        if updated:
            with open(cache_file, "w") as f:
                json.dump(ticker_data, f, indent=2)
            print(f"Successfully updated cache for {symbol}!")
        else:
            print(f"Cache for {symbol} is already up to date. Skipping.")

if __name__ == "__main__":
    build_cache()
