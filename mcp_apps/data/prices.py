"""Live quote lookup. A different vendor from the fundamentals path.

Split out of `fetch_utils.py` during the phase 3 fork, because Yahoo has
nothing to do with Alpha Vantage and burying it in the AV module implied
otherwise.

Deliberately uncached and best-effort: `identity.get_corporate_identity` calls
this to freshen a displayed price and falls back to the AV monthly close when
it returns None. Nothing in the anomaly engine reads it — every metric the
engine scores comes from AV statements, so a Yahoo outage changes what is shown
in a panel header and never changes a finding.
"""
from __future__ import annotations

import requests

from .config import log_info


def get_latest_yahoo_price(ticker: str) -> float:
    """Latest close from Yahoo Finance, or None on any failure.

    Never raises: the caller is display code and a missing price is cosmetic.
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        data = res.json()
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        return float(price) if price else None
    except Exception as e:
        log_info(f"Failed to fetch latest Yahoo price for {ticker}: {e}")
        return None
