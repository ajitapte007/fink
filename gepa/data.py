import json
import os
import random
import pandas as pd
from datetime import datetime

CACHE_FILE = "stock_data.json"

def generate_synthetic_market_data(n_samples=130):
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

    def generate_history_array(current_val, num_periods=5, trend=0.0):
        """Generates a backwards-projected synthetic history array ending at the current fuzzed value."""
        if current_val is None or current_val == 0:
            return [0] * num_periods
        
        # We work backwards from the current value
        # A positive trend means the value grew over time, meaning past values were smaller.
        history = [fuzz(current_val)]
        for _ in range(num_periods - 1):
            prev_val = history[0] / (1.0 + trend + random.uniform(-0.05, 0.05))
            history.insert(0, float(f"{prev_val:.2f}"))
        return history

    def get_sector_macro_text(regime_name, sector):
        """Provides rich qualitative context for a sector during a specific time period."""
        if "COVID Bottom" in regime_name:
            if sector in ["Technology", "Communication Services"]:
                return "The sector was incredibly favored as the world shifted to remote work. Massive tailwinds for digital transformation and e-commerce."
            elif sector in ["Energy", "Industrials", "Consumer Cyclical"]:
                return "The sector faced an existential crisis due to global lockdowns. Extreme headwinds from zeroed-out demand and supply chain halts."
            else:
                return "The sector experienced severe panic selling as the macro narrative focused entirely on a sudden deflationary recession and healthcare crisis."
        elif "2021 Tech Top" in regime_name:
            if sector in ["Technology", "Communication Services", "Consumer Cyclical"]:
                return "The sector enjoyed euphoric sentiment and record-low interest rates. Growth at any cost was rewarded, leading to massive multiple expansion."
            else:
                return "The sector was largely ignored in favor of hyper-growth tech, but benefited from a generally hot post-stimulus economy."
        elif "2022 Bear Bottom" in regime_name:
            if sector == "Energy":
                return "The sector was the sole bright spot, experiencing massive tailwinds from geopolitical supply shocks and high commodity prices."
            elif sector in ["Technology", "Communication Services", "Real Estate"]:
                return "The sector was devastated by the fastest interest rate hiking cycle in decades. Extreme headwinds from multiple contraction and cost of capital shock."
            else:
                return "The sector struggled with generational inflation, margin compression from supply chain costs, and hawkish central bank policies."
        else: # Pre-COVID or Current
            return f"The {sector} sector operated in a mostly stable macro environment with normal cyclical headwinds and tailwinds."

    dataset = []
    
    tickers = [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "LLY", "V", 
        "JPM", "WMT", "UNH", "MA", "PG", "JNJ", "HD", "MRK", "ORCL", "CVX", 
        "CRM", "ABBV", "BAC", "COST", "PEP", "KO", "TMO", "MCD", "CSCO", "ABT", 
        "AMD", "NFLX", "WFC", "INTU", "QCOM", "TXN", "AMGN", "PFE", "PM", "CAT",
        "IBM", "NOW", "COP", "SPGI", "UNP", "ISRG", "GE", "HON", "AMAT", "RTX",
        "LOW", "SYK", "BKNG", "NKE", "MDT", "GS", "PGR", "SBUX", "ELV", "TJX", 
        "DE", "VRTX", "CB", "LMT", "ADP", "REGN", "MDLZ", "C", "BSX", "ADI", 
        "MMC", "GILD", "BMY", "CI", "CVS", "SCHW", "ZTS", "FI", "ETN", "SLB",
        "EOG", "KLAC", "SNPS", "PLD", "CDNS", "PANW", "MO", "MU", "CMCSA", "SO",
        "DUK", "SHW", "ICE", "ANET", "MCO", "ITW", "APH", "CHTR", "NOC", "CSX",
        "PYPL", "PH", "MRO", "ORLY", "OXY", "AON", "MPC", "AEP", "SRE", "AIG",
        "D", "KMB", "EXC", "PCAR", "WMB", "ROST", "CTAS", "AFL", "PAYX", "GPN",
        "KMI", "ALL", "TRV", "HLT", "WELL", "PSA", "DHI", "VLO", "NEM", "ODFL",
        "LEN", "MNST", "ROK", "ENPH", "MRNA", "ETSY", "SQ", "INTC", "WBA", "PARA",
        "M", "F", "GM", "T", "VZ", "WBD", "CCL", "DIS", "BA", "DAL", 
        "AAL", "UAL", "WYNN", "LVS", "MGM", "MAR", "EXPE", "UBER", "LYFT"
    ]
    
    regimes = [
        {"name": "Pre-COVID Top", "start_date": "2010-01-01", "end_date": "2020-01-01", "future_date": "2022-01-01"},
        {"name": "COVID Bottom", "start_date": "2010-03-01", "end_date": "2020-03-20", "future_date": "2022-03-20"},
        {"name": "2021 Tech Top", "start_date": "2011-11-01", "end_date": "2021-11-01", "future_date": "2023-11-01"},
        {"name": "2022 Bear Bottom", "start_date": "2012-10-01", "end_date": "2022-10-15", "future_date": "2024-10-15"},
        {"name": "March 2024 Current Data", "start_date": "2014-03-01", "end_date": "2024-03-01", "future_date": "2026-03-01"}
    ]

    
    from yf_extractor import fetch_stock_data
    
    print(f"Fetching real market data until we have {n_samples} valid profiles...")
    
    # We shuffle the list so we pull randomly, but tracking index
    random.shuffle(tickers)
    ticker_idx = 0
    
    while len(dataset) < n_samples + 20 and ticker_idx < len(tickers):
        ticker = tickers[ticker_idx]
        ticker_idx += 1
        
        regime = random.choice(regimes)
        
        try:
            raw_data = fetch_stock_data(ticker, regime["start_date"], regime["end_date"], regime["future_date"])
            
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
                
            # Calculate simple proxy for historical sentiment based on multi-year trend
            proxy_trend = raw_data['ten_year_return'] / 100.0 / 10.0 # simple annual approximation
            
            if proxy_trend > 0.15:
                historical_sentiment = "The stock was a consistent outperformer. Management executed exceptionally well, capturing significant market share and driving strong investor enthusiasm."
            elif proxy_trend < 0.0:
                historical_sentiment = "The stock was a severe underperformer. The company struggled with structural growth issues, lost market share to competitors, and faced highly pessimistic investor sentiment."
            else:
                historical_sentiment = "The stock performed roughly in-line with peers. Management maintained stability but failed to capture outsized market share, leading to neutral investor sentiment."
                
            macro_context = get_sector_macro_text(regime["name"], raw_data['sector'])
            
            # Historical arrays
            pe_history = generate_history_array(raw_data.get('pe', 0), trend=-proxy_trend) # if stock did well, PE likely expanded (so past was lower)
            ps_history = generate_history_array(raw_data.get('ps', 0), trend=-proxy_trend)
            pfcf_history = generate_history_array(raw_data.get('pfcf', 0), trend=-proxy_trend)
            
            shares_history = [int(x) for x in generate_history_array(raw_data.get('shares', 0), trend=-0.02)] # Assume slight share reduction/buybacks
            cash_history = [int(x) for x in generate_history_array(raw_data.get('cash', 0) / 1e9, trend=proxy_trend)]
            debt_history = [int(x) for x in generate_history_array(raw_data.get('debt', 0) / 1e9, trend=0.03)]
            capex_history = [int(x) for x in generate_history_array(abs(raw_data.get('capex', 0)) / 1e9, trend=0.05)]
            
            margin_history = generate_history_array(raw_data.get('margins', 0), trend=proxy_trend*0.5)
            rev_growth_history = generate_history_array(raw_data.get('revenue_growth', 0), trend=proxy_trend*0.5)
            div_history = generate_history_array(raw_data.get('dividend_yield', 0), trend=-0.01)
            roic_history = generate_history_array(raw_data.get('roic', 0), trend=proxy_trend*0.5)

            # Compile fuzzed dictionary
            dataset.append({
                "ticker": ticker,
                "regime_label": regime_label,
                "sector_label": raw_data['sector'],
                "sector_context": f"Sector: {raw_data['sector']} - Industry: {raw_data['industry']}. {macro_context} Evaluating the structural position over the last 10 years.",
                "historical_sentiment": historical_sentiment,
                "financials": (
                    f"Analysis Date: {regime['end_date']}. Lookback Start: {regime['start_date']}. Evaluation End: {regime['future_date']}.\n\n"
                    f"Historical arrays represent annual snapshots over the lookback period, ending at the Analysis Date:\n"
                    f"P/E ratio history: {pe_history}\n"
                    f"P/S ratio history: {ps_history}\n"
                    f"P/FCF ratio history: {pfcf_history}\n\n"
                    f"Shares Outstanding history: {shares_history}\n"
                    f"Cash history (Billions): {cash_history}\n"
                    f"Debt history (Billions): {debt_history}\n"
                    f"Capex history (Billions): {capex_history}\n\n"
                    f"Operating Margin history (%): {margin_history}\n"
                    f"Revenue Growth history (%): {rev_growth_history}\n"
                    f"Dividend Yield history (%): {div_history}\n"
                    f"ROIC history (%): {roic_history}"
                ),
                "price_history": (
                    f"10-Year historical return prior to analysis date was {fuzz(raw_data['ten_year_return'])}%.\n"
                    f"Annual sampled prices: {[fuzz(p) for p in raw_data.get('annual_prices', [])]}"
                ),
                "recommendation": recommendation,
                "future_return": future_return,
                "future_fundamentals_fact": future_fundamentals_fact,
                "future_sentiment_fact": future_sentiment_fact
            })
            print(f"Successfully processed {ticker} ({len(dataset)}/{n_samples})")
            
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            
    # If we still didn't hit targets, duplicate some
    target_len = n_samples + 20
    if len(dataset) < target_len and len(dataset) > 0:
        print(f"Ran out of valid tickers, duplicating some to meet target={target_len}")
        while len(dataset) < target_len:
            dataset.append(random.choice(dataset))
            
    # Hold out 20 for evaluation
    train_data = dataset[:n_samples]
    holdout_data = dataset[n_samples:n_samples+20]
    
    if len(holdout_data) > 0:
        try:
            with open("holdout_data.json", "w") as f:
                json.dump(holdout_data, f, indent=4)
            print(f"Persisted {len(holdout_data)} holdout profiles to holdout_data.json")
        except Exception as e:
            pass

    # Save cache
    if len(train_data) > 0:
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(train_data, f, indent=4)
            print(f"Persisted {len(train_data)} fuzzed profiles to {CACHE_FILE}")
        except Exception as e:
            print(f"Warning: Failed to persist cache to {CACHE_FILE}: {e}")

    print(f"Successfully generated {len(train_data)} training and {len(holdout_data)} test profiles.")
    return train_data

if __name__ == "__main__":
    generate_synthetic_market_data()
