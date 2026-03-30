import json
import os
import random
import pandas as pd
from datetime import datetime

CACHE_FILE = "stock_data.json"

def generate_synthetic_market_data(n_samples=20):
    """
    Fetches real-world historical data for S&P 500 stocks.
    Uses data from 2014 to 2024 to generate the analyst prompt context.
    Evaluates the 'future_return' based on the holdout period from 2024 to 2026.
    
    The raw financial numbers are randomly fuzzed (+/- 10%) so the AI cannot
    simply memorize the exact ticker based on hyper-specific decimal values.
    """
    
    # Check cache first
    if os.path.exists(CACHE_FILE):
        print(f"Loading cached stock data from {CACHE_FILE}...")
        try:
            with open(CACHE_FILE, "r") as f:
                cached_data = json.load(f)
                if len(cached_data) >= n_samples:
                    print(f"Successfully loaded {len(cached_data)} cached profiles.")
                    # Return exactly the requested amount
                    return cached_data[:n_samples]
                else:
                    print(f"Cache only has {len(cached_data)} samples, but {n_samples} were requested. Refetching...")
        except Exception as e:
            print(f"Error reading cache file {CACHE_FILE}: {e}")
            
    def fuzz(val, fuzz_percent=10):
        if val is None or val == 0: return 0
        factor = 1.0 + (random.uniform(-fuzz_percent, fuzz_percent) / 100.0)
        return float(f"{val * factor:.2f}")

    dataset = []
    
    tickers = [
        # Value Traps / Declining Legacy
        "INTC", "T", "WBA", "PARA", "M", "F", 
        # Quality Breakouts
        "NVDA", "MSFT", "AAPL", "AMZN", "META", "GOOGL",
        # Zombies / Slow Staples
        "KO", "PEP", "PG", "VZ", "JNJ", "PFE",
        # Bubble / Hyper-growth Crashers
        "TSLA", "ENPH", "MRNA", "ETSY", "PYPL", "SQ"
    ]
    
    start_date = "2014-03-01"
    end_date = "2024-03-01" # Training cut-off
    future_date = "2026-03-01" # Evaluation hold-out window
    
    from yf_extractor import fetch_stock_data
    
    print(f"Fetching real market data until we have {n_samples} valid profiles...")
    
    # We shuffle the list so we pull randomly, but tracking index
    random.shuffle(tickers)
    ticker_idx = 0
    
    while len(dataset) < n_samples and ticker_idx < len(tickers):
        ticker = tickers[ticker_idx]
        ticker_idx += 1
        
        try:
            raw_data = fetch_stock_data(ticker, start_date, end_date, future_date)
            
            # Determine correct action and generate multi-factor ground truths
            future_return = raw_data["future_return"]
            regime_label = "Unknown"
            if future_return > 15:
                recommendation = "Buy"
                regime_label = "Quality Breakout"
                future_fundamentals_fact = "Revenues and margins continued to expand significantly as the company maintained its structural moat."
                future_sentiment_fact = "Market sentiment remained highly bullish, constantly rewarding the stock with multiple expansion and euphoric price targets."
            elif future_return < -10:
                recommendation = "Sell"
                # Check if it was a deep crash (Bubble) or slow bleed (Trap)
                if future_return < -40:
                    regime_label = "Bubble"
                    future_fundamentals_fact = "Growth completely rapidly evaporated. Margins compressed heavily under brutal competition and inventory glut."
                    future_sentiment_fact = "The narrative completely broke. Euphoria instantly rotated into panic, causing massive multiple contraction and institutional dumping."
                else:
                    regime_label = "Value Trap"
                    future_fundamentals_fact = "The legacy business continued to structurally decay. Earnings missed repeatedly."
                    future_sentiment_fact = "Sentiment became overwhelmingly bearish. It was treated as dead money and sold off consistently."
            else:
                recommendation = "Hold"
                regime_label = "Zombie"
                future_fundamentals_fact = "The fundamentals remained perfectly stable. Neither significant growth nor notable decay occurred."
                future_sentiment_fact = "Sentiment was entirely apathetic. The market traded the stock as a low-volatility bond proxy."
                
            # Compile fuzzed dictionary
            dataset.append({
                "ticker": ticker,
                "regime_label": regime_label,
                "sector_label": raw_data['sector'],
                "sector_context": f"Sector: {raw_data['sector']} - Industry: {raw_data['industry']}. Evaluating the structural position over the last 10 years.",
                "financials": f"P/E ratio: {fuzz(raw_data['pe'])}, Revenue Growth: {fuzz(raw_data['revenue_growth'])}%, Operating Margin: {fuzz(raw_data['margins'])}%.",
                "price_history": f"10-Year historical return prior to analysis date was {fuzz(raw_data['ten_year_return'])}%.",
                "recommendation": recommendation,
                "future_return": future_return,
                "future_fundamentals_fact": future_fundamentals_fact,
                "future_sentiment_fact": future_sentiment_fact
            })
            print(f"Successfully processed {ticker} ({len(dataset)}/{n_samples})")
            
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            
    # If we still didn't hit n_samples because too many tickers failed, we might just duplicate some to fulfill the requested shape
    if len(dataset) < n_samples and len(dataset) > 0:
        print(f"Ran out of valid tickers, duplicating some to meet n_samples={n_samples}")
        while len(dataset) < n_samples:
            dataset.append(random.choice(dataset))
            
    # Save cache
    if len(dataset) > 0:
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(dataset, f, indent=4)
            print(f"Persisted {len(dataset)} fuzzed profiles to {CACHE_FILE}")
        except Exception as e:
            print(f"Warning: Failed to persist cache to {CACHE_FILE}: {e}")

    print(f"Successfully generated {len(dataset)} fuzzed real-world profiles.")
    return dataset
