import yfinance as yf

def fetch_stock_data(ticker, start_date, end_date, future_date):
    """
    Fetches historical pricing and fundamental data for a given ticker.
    Raises ValueError if there is not enough data.
    """
    stock = yf.Ticker(ticker)
    
    # Fetch historical history
    hist = stock.history(start=start_date, end=end_date)
    if len(hist) < 500:
        raise ValueError(f"Not enough history for {ticker}")
        
    start_price = hist['Close'].iloc[0]
    end_price = hist['Close'].iloc[-1]
    ten_year_return = ((end_price - start_price) / start_price) * 100
    
    # Fetch holdout future history
    future_hist = stock.history(start=end_date, end=future_date)
    if len(future_hist) == 0:
        raise ValueError(f"No future holdout data for {ticker}")
        
    future_start = future_hist['Close'].iloc[0]
    future_end = future_hist['Close'].iloc[-1]
    future_return = ((future_end - future_start) / future_start) * 100
    
    # Fetch fundamentals
    info = stock.info
    pe = info.get('trailingPE', 0)
    sector = info.get('sector', 'Unknown')
    industry = info.get('industry', 'Unknown')
    revenue_growth = info.get('revenueGrowth', 0) * 100
    margins = info.get('operatingMargins', 0) * 100
    
    return {
        "ticker": ticker,
        "ten_year_return": ten_year_return,
        "future_return": future_return,
        "pe": pe,
        "sector": sector,
        "industry": industry,
        "revenue_growth": revenue_growth,
        "margins": margins
    }

if __name__ == "__main__":
    import sys
    ticker = "AAPL" if len(sys.argv) == 1 else sys.argv[1]
    print(f"Testing extraction for {ticker}...")
    try:
        data = fetch_stock_data(ticker, "2014-03-01", "2024-03-01", "2026-03-01")
        for k, v in data.items():
            print(f"{k}: {v}")
    except Exception as e:
        print(f"Failed: {e}")
