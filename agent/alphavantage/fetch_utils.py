import os
import json
import requests
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "local_av_cache"
API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "3G4CDSY4TJ4QVIXF")
FUNCTIONS = ["OVERVIEW", "TIME_SERIES_MONTHLY_ADJUSTED", "INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]

def fetch_data(function: str, symbol: str) -> dict:
    url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={API_KEY}"
    print(f"Auto-fetching missing data: {function} for {symbol}...")
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_all_data_for_ticker(ticker: str) -> dict:
    """
    Reads the locally seeded AlphaVantage data for the given ticker.
    If the data is missing from the local cache (e.g. new repo clone or new ticker), 
    it automatically hits the AlphaVantage API to fetch and cache it on the fly.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker.upper()}.json"
    
    ticker_data = {}
    if cache_file.exists():
        with open(cache_file, "r") as f:
            ticker_data = json.load(f)
            
    updated = False
    for func in FUNCTIONS:
        if func not in ticker_data:
            ticker_data[func] = fetch_data(func, ticker.upper())
            updated = True
            
    if updated:
        with open(cache_file, "w") as f:
            json.dump(ticker_data, f)
            
    return ticker_data
