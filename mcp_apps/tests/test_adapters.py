"""The seam between the data layer and the engine.

The tests that matter here are about the *shape* of what crosses the seam, not
about whether functions return something. The one that would have caught the
worst available bug is `test_load_company_yields_fiscal_quarters_not_months`:
reusing the chart pipeline for the engine produces a series that looks fine,
runs without error, and makes every trailing-twelve-month figure about a third
of its true value.
"""
from __future__ import annotations

import datetime

import pytest

from mcp_apps.data import adapters

SEED = ["AAPL", "AMZN", "COST", "GOOGL", "NEE", "PG", "UNH", "WMT"]


def _days_between(a: str, b: str) -> int:
    fmt = "%Y-%m-%d"
    return abs((datetime.datetime.strptime(b, fmt)
                - datetime.datetime.strptime(a, fmt)).days)


def test_load_company_yields_fiscal_quarters_not_months(companies):
    """The trap this module exists to avoid.

    `get_aligned_historical_data` emits ~318 monthly rows; the AV statements
    hold ~81 quarters. The engine's `ttm()` sums `series[i-3:i+1]` — four
    consecutive entries — so monthly rows would silently produce four-month
    sums of carried-forward values instead of a trailing year.

    Both the count and the spacing are asserted: a count check alone would pass
    for any resampling that happened to land near 81.
    """
    for ticker, c in companies.items():
        assert 40 < len(c.quarters) < 120, (
            f"{ticker}: {len(c.quarters)} periods — monthly rows (~318) would "
            f"make every TTM figure a four-month sum")
        gaps = [_days_between(c.quarters[i - 1].date, c.quarters[i].date)
                for i in range(1, len(c.quarters))]
        median_gap = sorted(gaps)[len(gaps) // 2]
        assert 80 <= median_gap <= 100, (
            f"{ticker}: median period gap {median_gap}d, expected ~91d. "
            f"These are not fiscal quarters.")


def test_quarters_are_chronological_and_unique(companies):
    """`ttm()` indexes positionally; out-of-order dates corrupt every window."""
    for ticker, c in companies.items():
        dates = [q.date for q in c.quarters]
        assert dates == sorted(dates), f"{ticker}: quarters not oldest-first"
        assert len(dates) == len(set(dates)), f"{ticker}: duplicate quarter dates"


@pytest.mark.parametrize("ticker", ["AAPL", "WMT", "PG", "COST"])
def test_ttm_of_four_quarters_reconciles_with_the_annual_filing(
        ticker, raw_cache, companies):
    """Prove the quarterly series is real, not resampled.

    If the four quarters ending on a fiscal year end sum to that year's reported
    revenue, the periods are genuine, correctly ordered, and correctly spaced.
    This is the strongest available statement that the engine sees what it
    thinks it does — monthly rows would come in around a third of the annual
    figure and fail every single year.

    Not asserted for *every* year, because a handful legitimately do not
    reconcile and demanding they do would be asserting a falsehood:

      - AAPL FY2009 is 4.8% light. Apple adopted ASU 2009-13 retrospectively,
        restating iPhone revenue away from subscription accounting. The annual
        reflects the restatement; the quarterlies as originally filed do not.
      - PG FY2012-14 are 2-8% heavy. P&G divested Pringles and later Duracell
        and much of beauty; discontinued operations are reclassified out of
        continuing-ops revenue in the annual but not retrospectively in the
        filed quarterlies.

    Both are properties of the filings, not of this code. So the bar is that the
    overwhelming majority reconcile and that no year is off by the kind of
    margin a structural bug produces.
    """
    from mcp_apps.engine.stats import ttm

    inc = raw_cache[ticker].get("INCOME_STATEMENT", {})
    annual = {r["fiscalDateEnding"]: r for r in inc.get("annualReports", [])}
    c = companies[ticker]
    rev = c.series("revenue")

    deltas: list[tuple[str, float]] = []
    for i, q in enumerate(c.quarters):
        if q.date not in annual:
            continue
        reported = annual[q.date].get("totalRevenue")
        computed = ttm(rev, i)
        if reported in (None, "None") or computed is None:
            continue
        deltas.append((q.date, abs(computed - float(reported)) / float(reported)))

    assert len(deltas) >= 15, (
        f"{ticker}: only {len(deltas)} fiscal years available to reconcile")

    reconciled = [d for d in deltas if d[1] < 0.02]
    assert len(reconciled) / len(deltas) >= 0.80, (
        f"{ticker}: only {len(reconciled)}/{len(deltas)} fiscal years reconcile "
        f"within 2%. Worst: {sorted(deltas, key=lambda x: -x[1])[:5]}")

    # A resampling or ordering bug does not miss by 8%, it misses by 65%.
    worst_date, worst = max(deltas, key=lambda x: x[1])
    assert worst < 0.15, (
        f"{ticker} FY{worst_date} is off by {worst:.0%} — too large for a "
        f"restatement, this looks structural")


def test_load_company_does_not_append_a_live_quote(companies, monkeypatch):
    """The scan must be reproducible; a chart need not be.

    `get_aligned_historical_data` appends a row dated today carrying the live
    Yahoo price. If that reached the engine, findings would shift with the
    market and the golden test could never be stable. `load_company` bypasses
    that path entirely, so the assertion is that no price is dated later than
    the last month AV actually reported.
    """
    for ticker, c in companies.items():
        assert c.prices, f"{ticker}: no price history"
        today = datetime.date.today().isoformat()
        assert c.prices[-1][0] < today, (
            f"{ticker}: last price is dated {c.prices[-1][0]} — a live quote "
            f"leaked into the engine's input")


def test_engine_field_names_are_all_populated(companies):
    """Every canonical name the checks read must actually carry values.

    A typo in FIELDS produces None for that field forever. The check that reads
    it then skips, the scan reports reduced coverage, and nothing says why. Only
    fields present for all business models are asserted here.
    """
    universal = ["revenue", "net_income", "operating_income", "assets",
                 "current_liabs", "equity", "cfo", "shares"]
    for ticker, c in companies.items():
        for field in universal:
            vals = [v for v in c.series(field) if v is not None]
            assert len(vals) > 20, (
                f"{ticker}: '{field}' has only {len(vals)} values — check the "
                f"AV key spelling in adapters.FIELDS")


def test_magnitude_fields_are_normalised(companies):
    for ticker, c in companies.items():
        for field in ("capex", "buyback", "dandA"):
            for v in c.series(field):
                assert v is None or v >= 0, f"{ticker}: negative {field} ({v})"


def test_classify_overrides_alpha_vantages_label_where_it_matters(companies):
    """OVERVIEW gives sector and industry. It does not give business_model.

    UNH is filed under LIFE SCIENCES / HOSPITAL & MEDICAL SERVICE PLANS. Taken
    at face value it scans as a services company and produces nonsense — it is
    an insurer, and the engine has no denominators for one. NEE must reach
    'utility' because rate-base accounting makes capex exceed D&A permanently by
    design, so the reinvestment check is meaningless there.
    """
    assert companies["UNH"].business_model == "financial", (
        "UNH classified from AV's raw label — managed care is an insurer")
    assert companies["NEE"].business_model == "utility"
    assert companies["COST"].business_model == "retail_consumer", (
        "COST is CONSUMER DEFENSIVE / DISCOUNT STORES; landing in 'industrial' "
        "was a real bug")
    assert companies["WMT"].business_model == "retail_consumer"


def test_load_series_returns_dated_values_for_the_chart():
    series = adapters.load_series("AAPL", ["revenue", "gross_margin"])
    assert set(series) >= {"revenue", "gross_margin", "shares_outstanding"}
    for metric, points in series.items():
        assert points, f"{metric} came back empty"
        for date, value in list(points.items())[:5]:
            assert len(date) == 10 and date[4] == "-"
            assert isinstance(value, (int, float))


def test_load_series_always_includes_shares_outstanding():
    """The view divides by it for per-share mode and yields nulls without it.

    Failure mode is a blank chart rather than an exception, so the guarantee has
    to live here.
    """
    series = adapters.load_series("AAPL", ["revenue"])
    assert "shares_outstanding" in series
    assert series["shares_outstanding"]


def test_load_series_rejects_unknown_metrics():
    """Fail loudly rather than returning an empty dict the view renders blank."""
    with pytest.raises(ValueError, match="unknown metrics"):
        adapters.load_series("AAPL", ["revenue", "ebitda_margin_pro_forma"])


def test_load_identity_carries_both_the_label_and_the_classification():
    ident = adapters.load_identity("UNH")
    assert ident["ticker"] == "UNH"
    assert ident["sector"] and ident["industry"]
    assert ident["name"] and ident["name"] != "UNH"
    # The panel has to be able to explain a declined scan, which means showing
    # the classification next to the label it disagrees with.
    assert ident["business_model"] == "financial"

    # AV files UNH as HEALTHCARE PLANS under LIFE SCIENCES — a label that reads
    # as a care provider, not an insurer. `classify` catches it on the
    # "HEALTHCARE PLAN" keyword. Pinned because the mapping is keyword-based:
    # if AV relabels the industry, classification silently falls through to
    # 'services' and UNH gets scanned with denominators that do not exist for
    # an insurer.
    assert ident["industry"].upper() == "HEALTHCARE PLANS", (
        f"AV's label for UNH changed to {ident['industry']!r} — verify "
        f"engine.stats.classify still maps it to 'financial'")


def test_unavailable_ticker_raises_rather_than_returning_empty():
    """A missing ticker must not look like a company with no anomalies."""
    with pytest.raises(adapters.TickerUnavailable):
        adapters.load_company("NOTATICKER123")
