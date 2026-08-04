"""The single coupling point between the data layer and the anomaly engine.

Three entry points, three consumers:

    load_company(ticker)   -> engine.Company   for the scan
    load_series(ticker)    -> {metric: {date: value}}  for the chart view
    load_identity(ticker)  -> dict             for panel headers

Everything else in `mcp_apps.data` is free to change shape as long as these
three keep their contract, and the engine imports nothing else from here.

WHY load_company DOES NOT USE get_aligned_historical_data
---------------------------------------------------------
The obvious implementation — reuse the chart pipeline and hand the engine its
output — is wrong, in a way that produces plausible numbers rather than an
error.

`get_aligned_historical_data` emits one row per *month*, interpolated onto the
price series, with statement values carried forward from the nearest report.
The engine computes trailing-twelve-month aggregates as `sum(series[i-3:i+1])`
— four consecutive *quarters*. Feed it monthly rows and every TTM figure
becomes a four-month sum of carried-forward values: roughly a third of the
true number, with no gap, no None, and nothing to notice.

So the engine gets its own path: fiscal quarters straight off the AV
statements, keyed by fiscalDateEnding. That is also what the POC did, which is
why `test_engine_golden.py` can compare the two and demand equality.
"""
from __future__ import annotations

import math

from .cache_orchestrator import cache_ticker_data
from .identity import get_corporate_identity
from .metrics import get_aligned_historical_data
from .metrics_registry import VALID_METRIC_KEYS

# Imported lazily inside functions to keep `mcp_apps.data` importable on its own
# — the Open WebUI fork of this tree has no engine package.

# Canonical engine name -> (statement, candidate AV keys in priority order).
#
# The engine speaks these names and nothing else; AV's spelling stops here.
# Kept deliberately identical to the POC's FIELDS map, because the golden
# findings were produced through it and any rename silently changes a score.
FIELDS: dict[str, tuple[str, list[str]]] = {
    "revenue":          ("income",  ["totalRevenue"]),
    "cogs":             ("income",  ["costOfRevenue"]),
    "gross_profit":     ("income",  ["grossProfit"]),
    "operating_income": ("income",  ["operatingIncome", "ebit"]),
    "net_income":       ("income",  ["netIncome"]),
    "sga":              ("income",  ["sellingGeneralAndAdministrative"]),
    "pretax_income":    ("income",  ["incomeBeforeTax"]),
    "tax_expense":      ("income",  ["incomeTaxExpense"]),

    "assets":           ("balance", ["totalAssets"]),
    "inventory":        ("balance", ["inventory"]),
    "receivables":      ("balance", ["currentNetReceivables"]),
    "payables":         ("balance", ["currentAccountsPayable"]),
    "current_liabs":    ("balance", ["totalCurrentLiabilities"]),
    "equity":           ("balance", ["totalShareholderEquity"]),
    "shares":           ("balance", ["commonStockSharesOutstanding"]),

    "cfo":              ("cash",    ["operatingCashflow"]),
    "capex":            ("cash",    ["capitalExpenditures"]),
    "dandA":            ("cash",    ["depreciationDepletionAndAmortization"]),
    "buyback":          ("cash",    ["paymentsForRepurchaseOfCommonStock"]),
}

_STATEMENT_KEY = {
    "income": "INCOME_STATEMENT",
    "balance": "BALANCE_SHEET",
    "cash": "CASH_FLOW",
}

# AV reports these three inconsistently as magnitudes or as negatives, varying
# by company and sometimes by period within one company. Left alone, the
# capex/D&A ratio comes out positive for some filers and negative for others,
# which inverts the reinvestment check silently rather than raising.
_MAGNITUDE_FIELDS = ("capex", "buyback", "dandA")


class TickerUnavailable(RuntimeError):
    """The ticker could not be loaded — missing statements, or a fetch error.

    Distinct from "loaded fine and the engine declined it": that is a Skip, and
    the scan reports it as coverage. This means there is nothing to scan.
    """


def num(v) -> float | None:
    """AV emits strings, 'None', '-' and empty for missing values."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    s = str(v).strip()
    if s in ("", "None", "none", "-", "null", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _raw(ticker: str) -> dict:
    """Cached AV payloads for a ticker, or raise."""
    res = cache_ticker_data(ticker)
    if res.get("error"):
        raise TickerUnavailable(f"{ticker.upper()}: {res['error']}")
    raw = res.get("raw_cache") or {}
    if not raw:
        raise TickerUnavailable(f"{ticker.upper()}: no cached data")
    return raw


def load_company(ticker: str):
    """Build the engine's `Company` from AV quarterly statements.

    Quarters come from `quarterlyReports` keyed by fiscalDateEnding — the union
    across the three statements, so a quarter present in only one of them still
    appears (with Nones elsewhere) rather than being dropped.

    Prices come from the monthly series untouched: no live quote is appended.
    `get_aligned_historical_data` does append one, which is right for a chart
    and wrong here — a finding that changes because a quote moved is not a
    finding, and the golden test could not be stable.
    """
    from ..engine.stats import Company, Quarter, classify

    raw = _raw(ticker)
    ov = raw.get("OVERVIEW", {}) or {}

    reports: dict[str, dict[str, dict]] = {}
    for stmt, av_fn in _STATEMENT_KEY.items():
        rows = (raw.get(av_fn, {}) or {}).get("quarterlyReports", []) or []
        reports[stmt] = {r["fiscalDateEnding"]: r for r in rows
                         if r.get("fiscalDateEnding")}

    dates = sorted(set().union(*(set(r) for r in reports.values()))
                   if reports else set())

    quarters: list = []
    for d in dates:
        q = Quarter(date=d)
        for canon, (stmt, keys) in FIELDS.items():
            row = reports[stmt].get(d, {})
            val = None
            for k in keys:
                val = num(row.get(k))
                if val is not None:
                    break
            q.vals[canon] = val
        for k in _MAGNITUDE_FIELDS:
            if q.vals.get(k) is not None:
                q.vals[k] = abs(q.vals[k])
        quarters.append(q)

    prices: list[tuple[str, float]] = []
    ts = raw.get("TIME_SERIES_MONTHLY_ADJUSTED", {}) or {}
    series = (ts.get("Monthly Adjusted Time Series")
              or ts.get("Monthly Time Series") or {})
    for k, v in series.items():
        px = num(v.get("5. adjusted close") or v.get("4. close"))
        if px is not None:
            prices.append((k, px))
    prices.sort()

    sector = ov.get("Sector", "") or ""
    industry = ov.get("Industry", "") or ""

    return Company(
        ticker=ticker.upper(),
        name=ov.get("Name") or ticker.upper(),
        sector=sector or "Unknown",
        industry=industry or "Unknown",
        market_cap=num(ov.get("MarketCapitalization")),
        quarters=quarters,
        prices=prices,
        business_model=classify(sector, industry),
    )


def load_series(ticker: str, metrics: list[str] | None = None) -> dict:
    """Monthly-aligned chart series: {metric_id: {date: value}}.

    This one *does* go through `get_aligned_historical_data`, because a chart
    wants exactly what that produces — monthly points against the price line,
    including the fresh quote at the right-hand edge.

    `shares_outstanding` is always included regardless of `metrics`. The view's
    per-share toggle divides by it and yields nulls without complaint if it is
    absent, so the failure is a blank chart rather than an error.
    """
    raw = _raw(ticker)
    points = get_aligned_historical_data(raw)

    wanted = list(metrics) if metrics else list(VALID_METRIC_KEYS)
    unknown = [m for m in wanted if m not in VALID_METRIC_KEYS]
    if unknown:
        raise ValueError(f"unknown metrics: {unknown}. "
                         f"Valid: {sorted(VALID_METRIC_KEYS)}")
    if "shares_outstanding" not in wanted:
        wanted.append("shares_outstanding")

    out: dict[str, dict[str, float]] = {m: {} for m in wanted}
    for pt in points:
        d = pt.model_dump() if hasattr(pt, "model_dump") else pt.dict()
        for m in wanted:
            v = d.get(m)
            if v is not None:
                out[m][d["date"]] = v
    return out


def load_identity(ticker: str) -> dict:
    """Display strings for a panel header.

    `business_model` is included alongside AV's raw sector/industry because the
    two answer different questions. OVERVIEW files UNH under LIFE SCIENCES /
    HOSPITAL & MEDICAL SERVICE PLANS; taken at face value it scans as a services
    company and produces nonsense. `classify` maps it to `financial`, which is
    what determines whether the checks run at all — so a panel that shows the
    sector without the classification cannot explain why a scan was declined.
    """
    from ..engine.stats import classify

    raw = _raw(ticker)
    ident = get_corporate_identity(raw)
    d = ident.model_dump() if hasattr(ident, "model_dump") else ident.dict()
    ov = raw.get("OVERVIEW", {}) or {}
    d["name"] = ov.get("Name") or ticker.upper()
    d["business_model"] = classify(d.get("sector", ""), d.get("industry", ""))
    return d
