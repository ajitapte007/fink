"""Alignment behaviour on degenerate inputs.

Ported from mcp/tests/test_edge_cases.py in the phase 3 fork, minus the three
system-prompt cases — those import `server` and test Open WebUI's prompt, which
has no counterpart here.
"""
import json

import pytest

from mcp_apps.data.metrics import get_aligned_historical_data

def test_alignment_edge_cases():
    # Mock data structure representing empty/zero/missing values
    raw_cache = {
        "TIME_SERIES_MONTHLY_ADJUSTED": {
            "Monthly Adjusted Time Series": {
                "2023-12-31": {"5. adjusted close": "150.0"},
                "2023-11-30": {"5. adjusted close": "145.0"}
            }
        },
        "INCOME_STATEMENT": {
            "annualReports": [
                {
                    "fiscalDateEnding": "2023-12-31",
                    "totalRevenue": "0.0",  # Zero revenue to trigger margins protection
                    "operatingIncome": "1000.0",
                    "netIncome": "500.0",
                    "costOfRevenue": "0.0",
                    "researchAndDevelopment": "200.0",
                    "sellingGeneralAndAdministrative": "300.0"
                }
            ],
            "quarterlyReports": []
        },
        "BALANCE_SHEET": {
            "annualReports": [
                {
                    "fiscalDateEnding": "2023-12-31",
                    "commonStockSharesOutstanding": "0",  # Zero shares to trigger per-share protection
                    "cashAndCashEquivalentsAtCarryingValue": "500.0",
                    "longTermDebt": "200.0",
                    "shortTermDebt": "100.0"
                }
            ],
            "quarterlyReports": []
        },
        "CASH_FLOW": {
            "annualReports": [
                {
                    "fiscalDateEnding": "2023-12-31",
                    "operatingCashflow": "600.0",
                    "capitalExpenditures": "100.0",
                    "stockBasedCompensation": "50.0",
                    "paymentsForRepurchaseOfCommonStock": "25.0"
                }
            ],
            "quarterlyReports": []
        }
    }
    
    aligned = get_aligned_historical_data(raw_cache)
    # Filter for the smoothed point or final points
    assert len(aligned) > 0
    pt = aligned[0]
    
    # Assert safeguards triggered: zero/missing revenue sets margin metrics to None
    assert pt.operating_margin is None
    assert pt.profit_margin is None
    assert pt.gross_margin is None
    
    # Zero shares outstanding must not blow up per-share derivations
    assert pt.shares_outstanding == 0.0

    # Ratios with a zero divisor (earnings, revenue, cash flow) should resolve to None
    assert pt.pe_ratio is None
    assert pt.ps_ratio is None
    assert pt.pfcf_ratio is None
    assert pt.pocf_ratio is None


def test_alignment_handles_empty_cache():
    """Aligning an empty cache should not raise."""
    try:
        aligned = get_aligned_historical_data({})
    except Exception as e:
        pytest.fail(f"get_aligned_historical_data({{}}) raised {type(e).__name__}: {e}")
    assert aligned == [] or len(aligned) == 0


# ─── Timeframe resolution ─────────────────────────────────────────────────────

