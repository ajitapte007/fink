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
    
    try:
        annual_prices = [round(x, 2) for x in hist['Close'].resample('YE').last().tolist()]
    except Exception:
        step = max(1, len(hist) // 10)
        annual_prices = [round(x, 2) for x in hist['Close'].iloc[::step].tolist()]
    
    # Fetch holdout future history
    future_hist = stock.history(start=end_date, end=future_date)
    if len(future_hist) == 0:
        raise ValueError(f"No future holdout data for {ticker}")
        
    future_start = future_hist['Close'].iloc[0]
    future_end = future_hist['Close'].iloc[-1]
    future_return = ((future_end - future_start) / future_start) * 100
    
    # Fetch fundamentals
    info = stock.info
    pe = info.get('trailingPE') or 0
    ps = info.get('priceToSalesTrailing12Months') or 0
    shares = info.get('sharesOutstanding') or 0
    cash = info.get('totalCash') or 0
    debt = info.get('totalDebt') or 0
    
    operating_cf = info.get('operatingCashflow') or 0
    capex = info.get('capitalExpenditures') or 0
    fcf = operating_cf + capex if capex < 0 else operating_cf - capex
    market_cap = info.get('marketCap') or 0
    pfcf = (market_cap / fcf) if fcf > 0 else 0
    
    dividend_yield = (info.get('dividendYield') or 0) * 100
    
    roe = info.get('returnOnEquity')
    roa = info.get('returnOnAssets')
    roic = (roe if roe is not None else roa if roa is not None else 0) * 100
    
    sector = info.get('sector', 'Unknown')
    industry = info.get('industry', 'Unknown')
    revenue_growth = (info.get('revenueGrowth') or 0) * 100
    margins = (info.get('operatingMargins') or 0) * 100
    
    return {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "future_date": future_date,
        "ten_year_return": ten_year_return,
        "future_return": future_return,
        "annual_prices": annual_prices,
        "pe": pe,
        "ps": ps,
        "pfcf": pfcf,
        "shares": shares,
        "cash": cash,
        "debt": debt,
        "capex": capex,
        "dividend_yield": dividend_yield,
        "roic": roic,
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
