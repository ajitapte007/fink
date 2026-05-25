import json
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "local_av_cache"

def get_all_data_for_ticker(ticker: str) -> dict:
    """
    Reads the locally seeded AlphaVantage data for the given ticker.
    This fulfills the Single-Ingestion, Cache-First Data Layer architecture requirement
    to prevent runaway latency and API costs.
    """
    cache_file = CACHE_DIR / f"{ticker.upper()}.json"
    if not cache_file.exists():
        return {"error": f"No cached data found for {ticker}."}
        
    with open(cache_file, "r") as f:
        return json.load(f)
