"""The six balance-sheet metrics added in phase 3.

These tests care about two things existence checks would miss: whether the
values are *populated* rather than silently None, and whether flows and stocks
are aggregated differently — because getting that wrong produces a number that
is wrong by exactly 4x and raises nothing.
"""
from __future__ import annotations

import pytest

from mcp_apps.data.metrics import get_aligned_historical_data, merge_reports

NEW_FIELDS = ["total_assets", "current_liabilities", "receivables",
              "inventory", "payables", "depreciation_amortization"]

# Stocks: a point-in-time balance. Summing four quarters of these is nonsense.
STOCK_FIELDS = ["total_assets", "current_liabilities", "receivables",
                "inventory", "payables"]

# Flows: accumulate over a period, so they are TTM-summed like revenue.
FLOW_FIELDS = ["depreciation_amortization"]


@pytest.fixture(scope="module")
def points(raw_cache):
    return {t: get_aligned_historical_data(rc) for t, rc in raw_cache.items()}


def test_new_fields_reach_the_output_at_all(points):
    """Regression for the smooth_series enumeration bug.

    `smooth_series` used to list all 33 fields by hand and rebuild
    ChartDataPoint from that list. A field added to the model computed correctly
    upstream, survived as far as the smoother, and then came out None — no
    exception, no warning, just a column of nulls. All six new fields would have
    hit it.
    """
    for field in NEW_FIELDS:
        populated = any(getattr(p, field) is not None
                        for pts in points.values() for p in pts)
        assert populated, (
            f"{field} is None everywhere — it is computed in "
            f"get_aligned_historical_data but does not survive smooth_series")


@pytest.mark.parametrize("field", ["total_assets", "current_liabilities",
                                   "depreciation_amortization"])
def test_universal_fields_are_near_complete(points, field):
    """Every operating company has assets, current liabilities and D&A.

    Deliberately not asserted for receivables / inventory / payables: UNH is an
    insurer and reports none of the three, and GOOGL carries almost no
    inventory. Demanding those would be asserting a fact about the corpus
    rather than about the code.
    """
    for ticker, pts in points.items():
        coverage = sum(1 for p in pts if getattr(p, field) is not None) / len(pts)
        assert coverage > 0.90, f"{ticker}: {field} only {coverage:.0%} populated"


def test_working_capital_fields_present_for_companies_that_have_them(points):
    """Retailers must carry all three, or DSO/DIO/DPO cannot be computed."""
    for ticker in ("COST", "WMT", "AMZN", "PG"):
        for field in ("receivables", "inventory", "payables"):
            coverage = sum(1 for p in points[ticker] if getattr(p, field) is not None)
            assert coverage / len(points[ticker]) > 0.90, (
                f"{ticker}: {field} missing — the working capital check cannot run")


def test_stocks_are_not_ttm_summed(raw_cache):
    """The distinction that makes these numbers mean anything.

    `merge_reports` sums a fixed list of keys over four quarters. A balance-sheet
    stock landing in that list would be inflated ~4x with nothing to signal it.
    Compare the merged value against the raw filing: stocks must match exactly.
    """
    from mcp_apps.data.metrics import merge_reports

    bal = raw_cache["WMT"].get("BALANCE_SHEET", {})
    raw_rows = {r["fiscalDateEnding"]: r for r in bal.get("quarterlyReports", [])}
    merged = {r["fiscalDateEnding"]: r for r in merge_reports(bal)}

    checked = 0
    for date, row in list(merged.items()):
        if date not in raw_rows:
            continue
        for av_key in ("totalAssets", "inventory", "currentNetReceivables",
                       "currentAccountsPayable", "totalCurrentLiabilities"):
            raw_v, merged_v = raw_rows[date].get(av_key), row.get(av_key)
            if raw_v in (None, "None") or merged_v in (None, "None"):
                continue
            assert float(merged_v) == float(raw_v), (
                f"WMT {date} {av_key}: merge_reports altered a balance-sheet "
                f"stock ({raw_v} -> {merged_v}). Stocks must not be TTM-summed.")
            checked += 1
    assert checked > 50, "test did not actually compare anything"


def test_depreciation_is_ttm_summed_like_the_flows_it_is_compared_against(raw_cache):
    """The bug this suite exists to prevent recurring.

    `capitalExpenditures` was in `keys_to_sum`; D&A was not. Every capex/D&A
    comparison therefore divided a trailing-twelve-month numerator by a
    single-quarter denominator and came out ~4x too high — AAPL read 3.59 where
    the true ratio is 0.91. Both must be aggregated the same way.
    """
    cf = raw_cache["AAPL"].get("CASH_FLOW", {})
    raw_rows = sorted(cf.get("quarterlyReports", []),
                      key=lambda r: r.get("fiscalDateEnding", ""))
    merged = {r["fiscalDateEnding"]: r for r in merge_reports(cf)}

    key = "depreciationDepletionAndAmortization"
    compared = 0
    for i in range(3, len(raw_rows)):
        date = raw_rows[i]["fiscalDateEnding"]
        if date not in merged:
            continue
        window = [raw_rows[i - j].get(key) for j in range(4)]
        if any(v in (None, "None") for v in window):
            continue
        expected = sum(float(v) for v in window)
        actual = float(merged[date][key])
        assert actual == pytest.approx(expected, rel=1e-6), (
            f"AAPL {date}: D&A is not TTM-summed. Got {actual}, expected "
            f"{expected} — capex/D&A will be off by ~4x.")
        compared += 1
    assert compared > 20, "test did not actually compare anything"


def test_capex_and_depreciation_are_both_magnitudes(points):
    """AV signs these inconsistently; a flip inverts the ratio silently."""
    for ticker, pts in points.items():
        for p in pts:
            if p.capex is not None:
                assert p.capex >= 0, f"{ticker} {p.date}: negative capex {p.capex}"
            if p.depreciation_amortization is not None:
                assert p.depreciation_amortization >= 0, (
                    f"{ticker} {p.date}: negative D&A")


def test_capex_to_depreciation_lands_in_a_plausible_band(points):
    """The economic sanity check the ~4x bug failed.

    A company reinvesting at replacement rate sits near 1.0. Utilities and
    growth compounders run higher; nobody sustains 15x. This is the assertion
    that would have caught the misalignment on its own — the coverage and sign
    tests above both passed while the number was four times too large.
    """
    observed = {}
    for ticker, pts in points.items():
        usable = [p for p in pts if p.capex and p.depreciation_amortization]
        if not usable:
            continue
        p = usable[-1]
        observed[ticker] = p.capex / p.depreciation_amortization

    assert observed, "no ticker had both capex and D&A"
    for ticker, ratio in observed.items():
        assert 0.2 < ratio < 12.0, (
            f"{ticker}: capex/D&A = {ratio:.2f}, outside the plausible band. "
            f"A ~4x reading means the two are aggregated differently.")

    # AAPL is the tightest anchor: a mature hardware business reinvesting at
    # roughly replacement rate. If this drifts far from 1, something structural
    # changed in how one of the two is computed.
    assert 0.5 < observed["AAPL"] < 2.0, (
        f"AAPL capex/D&A = {observed['AAPL']:.2f}; expected near 1.0")


def test_new_metrics_are_registered_for_the_chart():
    """A metric the view cannot request is not usable by 'chase the finding'."""
    from mcp_apps.data.metrics_registry import METRICS_REGISTRY, VALID_METRIC_KEYS

    for field in NEW_FIELDS:
        assert field in VALID_METRIC_KEYS
    by_id = {m["id"]: m for m in METRICS_REGISTRY}
    for field in NEW_FIELDS:
        entry = by_id[field]
        assert entry["label"] and entry["description"]
        assert entry["defaultAxis"] in ("y", "y1")
        assert "color" in entry, f"{field} has no colour; the chart needs one"
