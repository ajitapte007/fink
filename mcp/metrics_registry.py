# mcp/metrics_registry.py
"""
Central metrics registry — single source of truth for all financial metric definitions.

All consumers (VALID_METRIC_KEYS, METRICS_CONFIG, native tool docstrings, validation logic)
derive from this registry. To add a new metric, add one entry here.
"""

METRICS_REGISTRY = [
    # ── Aggregates ─────────────────────────────────────────────────────────────
    {"id": "price",                   "label": "Stock Price",         "description": "Monthly closing stock price",                    "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": False, "color": "#3b82f6", "defaultChartMetric": True},
    {"id": "revenue",                 "label": "Revenue",             "description": "Total revenue, TTM-aligned",                     "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#ec4899", "defaultChartMetric": True},
    {"id": "cost_of_goods_sold",      "label": "COGS",               "description": "Cost of goods sold",                             "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#ef4444"},
    {"id": "operating_income",        "label": "Operating Income",    "description": "Operating income (EBIT)",                        "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#10b981"},
    {"id": "net_income",              "label": "Net Income",          "description": "Net income after taxes",                         "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#6366f1", "defaultChartMetric": True},
    {"id": "operating_cash_flow",     "label": "Operating Cash Flow", "description": "Cash flow from operations",                      "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#06b6d4"},
    {"id": "capex",                   "label": "CapEx",               "description": "Capital expenditures",                           "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#f97316"},
    {"id": "free_cash_flow",          "label": "Free Cash Flow",      "description": "Free cash flow (OCF minus CapEx)",               "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#8b5cf6"},
    {"id": "selling_general_admin",   "label": "SG&A Expenses",       "description": "Selling, general and administrative expenses",   "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#f43f5e"},
    {"id": "research_development",    "label": "R&D Expenses",        "description": "Research and development expenses",              "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#eab308"},
    {"id": "stock_based_compensation","label": "Stock-Based Comp",    "description": "Stock-based compensation expense",               "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#a855f7"},
    {"id": "share_repurchase",        "label": "Share Repurchases",   "description": "Payments for share repurchases (buybacks)",       "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#d946ef"},
    {"id": "cash_and_equivalents",    "label": "Cash & Equivalents",  "description": "Cash and cash equivalents on balance sheet",     "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#14b8a6"},
    {"id": "total_debt",              "label": "Total Debt",          "description": "Total long-term and short-term debt",            "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#64748b"},
    {"id": "market_cap",              "label": "Market Cap",          "description": "Market capitalization",                          "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#0284c7"},
    {"id": "enterprise_value",        "label": "Enterprise Value",    "description": "Enterprise value (market cap + debt - cash)",    "unit": "USD",  "category": "Aggregates",              "defaultAxis": "y",  "isAggregate": True,  "color": "#334155"},
    {"id": "ebitda",                  "label": "EBITDA",              "description": "Earnings before interest, taxes, depreciation and amortization", "unit": "USD", "category": "Aggregates", "defaultAxis": "y", "isAggregate": True, "color": "#ec4899"},

    # ── Valuation Ratios ───────────────────────────────────────────────────────
    {"id": "pe_ratio",    "label": "P/E (TTM)",        "description": "Price-to-earnings ratio, trailing twelve months",       "unit": "ratio", "category": "Valuation Ratios",         "defaultAxis": "y1", "isAggregate": False, "color": "#10b981"},
    {"id": "ps_ratio",    "label": "P/S (TTM)",        "description": "Price-to-sales ratio, trailing twelve months",          "unit": "ratio", "category": "Valuation Ratios",         "defaultAxis": "y1", "isAggregate": False, "color": "#a78bfa"},
    {"id": "pfcf_ratio",  "label": "P/FCF (TTM)",      "description": "Price-to-free-cash-flow ratio",                        "unit": "ratio", "category": "Valuation Ratios",         "defaultAxis": "y1", "isAggregate": False, "color": "#f97316"},
    {"id": "pocf_ratio",  "label": "P/OCF (TTM)",      "description": "Price-to-operating-cash-flow ratio",                   "unit": "ratio", "category": "Valuation Ratios",         "defaultAxis": "y1", "isAggregate": False, "color": "#06b6d4"},
    {"id": "ev_ebitda",   "label": "EV/EBITDA (TTM)",   "description": "Enterprise value to EBITDA ratio",                    "unit": "ratio", "category": "Valuation Ratios",         "defaultAxis": "y1", "isAggregate": False, "color": "#f43f5e"},

    # ── Shareholder Return ─────────────────────────────────────────────────────
    {"id": "shares_outstanding", "label": "Shares Outstanding",       "description": "Total shares outstanding",                    "unit": "count",  "category": "Shareholder Return",      "defaultAxis": "y1", "isAggregate": False, "color": "#6366f1"},
    {"id": "dividends",          "label": "Dividends",                "description": "TTM dividends paid",                          "unit": "USD",    "category": "Shareholder Return",      "defaultAxis": "y",  "isAggregate": False, "color": "#ef4444"},
    {"id": "dividend_yield",     "label": "Dividend Yield (%) (TTM)", "description": "Dividend yield, trailing twelve months",       "unit": "percent", "category": "Shareholder Return",     "defaultAxis": "y1", "isAggregate": False, "color": "#f43f5e"},
    {"id": "payout_ratio_fcf",   "label": "Payout Ratio (FCF %)",    "description": "Dividend payout as percentage of free cash flow", "unit": "percent", "category": "Shareholder Return",  "defaultAxis": "y1", "isAggregate": False, "color": "#eab308"},
    {"id": "payout_ratio_ocf",   "label": "Payout Ratio (OCF %)",    "description": "Dividend payout as percentage of operating cash flow", "unit": "percent", "category": "Shareholder Return", "defaultAxis": "y1", "isAggregate": False, "color": "#a855f7"},

    # ── Performance & Efficiency ───────────────────────────────────────────────
    {"id": "roic",             "label": "ROIC (%)",              "description": "Return on invested capital",              "unit": "percent", "category": "Performance & Efficiency", "defaultAxis": "y1", "isAggregate": False, "color": "#14b8a6"},
    {"id": "operating_margin", "label": "Operating Margin (%)",  "description": "Operating income as percentage of revenue", "unit": "percent", "category": "Performance & Efficiency", "defaultAxis": "y1", "isAggregate": False, "color": "#3b82f6", "defaultChartMetric": True},
    {"id": "profit_margin",    "label": "Net Margin (%)",        "description": "Net income as percentage of revenue",     "unit": "percent", "category": "Performance & Efficiency", "defaultAxis": "y1", "isAggregate": False, "color": "#6366f1"},
    {"id": "gross_margin",     "label": "Gross Margin (%)",      "description": "Gross profit as percentage of revenue",   "unit": "percent", "category": "Performance & Efficiency", "defaultAxis": "y1", "isAggregate": False, "color": "#10b981"},
    {"id": "roa",              "label": "ROA (%)",               "description": "Return on assets",                        "unit": "percent", "category": "Performance & Efficiency", "defaultAxis": "y1", "isAggregate": False, "color": "#ec4899"},
    {"id": "roe",              "label": "ROE (%)",               "description": "Return on equity",                        "unit": "percent", "category": "Performance & Efficiency", "defaultAxis": "y1", "isAggregate": False, "color": "#0284c7"},

    # NOTE: 10-K revenue segment metrics (product_segments, geographic_segments) were
    # removed on 2026-07-28 — their source was an LLM with web search, not a filings API.
    # See mcp/docs/REVENUE_SEGMENTS_RESTORATION.md before adding them back.
]

# ── Derived constants ──────────────────────────────────────────────────────────
# Used by server.py, models.py, visualization_tool.py, and alphavantage_tool.py
VALID_METRIC_KEYS = [m["id"] for m in METRICS_REGISTRY]

# Metrics plotted when a chart is requested without an explicit selection
# (e.g. "show me UNH financials"). A price anchor, two absolutes, and one ratio —
# the margin sits on the right axis, so the chart is dual-axis by construction.
DEFAULT_CHART_METRICS = [m["id"] for m in METRICS_REGISTRY if m.get("defaultChartMetric")]

# Same structure as the old METRICS_CONFIG — used by visualization_tool.py and chartUtils.js
METRICS_CONFIG = METRICS_REGISTRY


def get_metric_names_for_docstring() -> str:
    """Returns 'id: description' pairs for embedding in native tool parameter descriptions.
    Gives the LLM enough context to choose the right metric confidently.

    Example output:
        "price: Monthly closing stock price; revenue: Total revenue, TTM-aligned; ..."
    """
    return "; ".join(f'{m["id"]}: {m["description"]}' for m in METRICS_REGISTRY)
