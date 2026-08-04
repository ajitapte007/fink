"""Corporate identity and its presentation formatting.

Split out of `process_utils.py` during the phase 3 fork. This is not metrics
code: it produces display strings for a panel header — name, sector, market cap,
last close — and reaches across to a different vendor (`..prices`) to freshen
the quote. Nothing here feeds the anomaly engine.

That separation matters for determinism. `get_corporate_identity` makes a live
network call and silently degrades when it fails, so its output differs between
an online and an offline run. Keeping it out of `metrics.py` keeps the scored
surface reproducible.
"""
from __future__ import annotations

from .models import CorporateIdentity
from .prices import get_latest_yahoo_price

def format_market_cap(mcap: float) -> str:
    if mcap >= 1.0e12:
        return f"${mcap / 1.0e12:.2f}T"
    elif mcap >= 1.0e9:
        return f"${mcap / 1.0e9:.2f}B"
    elif mcap >= 1.0e6:
        return f"${mcap / 1.0e6:.2f}M"
    else:
        return f"${mcap:,.0f}"

def get_corporate_identity(raw_cache: dict) -> 'CorporateIdentity':
    
    overview = raw_cache.get("OVERVIEW", {})
    ticker = overview.get("Symbol", "")
    sector = overview.get("Sector", "Unknown Sector")
    industry = overview.get("Industry", "Unknown Industry")
    country = overview.get("Country", "US")
    
    # Try to parse Market Cap
    try:
        mcap_val = float(overview.get("MarketCapitalization", 0.0))
        market_cap_str = format_market_cap(mcap_val) if mcap_val > 0 else "N/A"
    except (ValueError, TypeError):
        market_cap_str = "N/A"
        
    # Get last closing price
    last_closing_price_str = "N/A"
    ts = raw_cache.get("TIME_SERIES_MONTHLY_ADJUSTED", {})
    ts_data = ts.get("Monthly Adjusted Time Series") or ts.get("Monthly Time Series") or {}
    if ts_data:
        # Get the most recent date key
        latest_date = sorted(ts_data.keys(), reverse=True)[0]
        item = ts_data[latest_date]
        try:
            price = float(item.get("5. adjusted close") or item.get("4. close") or item.get("close") or 0.0)
            last_closing_price_str = f"${price:,.2f}"
        except (ValueError, TypeError):
            pass

    # Overwrite price and market cap with Yahoo Finance latest if available
    if ticker:
        try:
            latest_price = get_latest_yahoo_price(ticker)
            if latest_price:
                last_closing_price_str = f"${latest_price:,.2f}"
                shares = float(overview.get("SharesOutstanding", 0.0))
                if shares > 0:
                    mcap_val = latest_price * shares
                    market_cap_str = format_market_cap(mcap_val)
        except Exception:
            pass
            
    return CorporateIdentity(
        ticker=ticker,
        last_closing_price=last_closing_price_str,
        market_cap=market_cap_str,
        sector=sector,
        industry=industry,
        country=country,
        last_refreshed=raw_cache.get("_meta_last_refreshed", "Unknown")
    )
