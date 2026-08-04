"""Chase the finding: does the chart show the evidence the finding claims?

The engine and the chart use different names for the same quantities, on
purpose — the engine works in fiscal quarters off raw statement lines (`cfo`,
`dandA`, `assets`), the chart in monthly-aligned registry ids
(`operating_cash_flow`, `depreciation_amortization`, `total_assets`).
`chartspec` is the only place they meet, so it is the only place that mapping
can rot.

The failure worth preventing is quiet: a metric that does not map gets dropped,
the chart renders happily without it, and the reader sees a chart that does not
support the claim above it. That reads as the claim being wrong.
"""
from __future__ import annotations

import pytest

from mcp_apps.chartspec import (ALWAYS_INCLUDE, ENGINE_TO_CHART, UnmappedMetric,
                                chart_metrics_for, spec_for)
from mcp_apps.data.metrics_registry import VALID_METRIC_KEYS


class _Ev:
    def __init__(self, names):
        self.chart_metrics = names


def test_every_metric_any_check_declares_can_be_charted(companies):
    """Scan the real corpus and resolve whatever the checks actually emit.

    Stronger than asserting over ENGINE_TO_CHART's own keys, which would only
    prove the table is self-consistent. This proves it covers the checks.
    """
    from mcp_apps.engine import scan

    seen: set[str] = set()
    for ticker, c in companies.items():
        for cl in scan(c)["clusters"]:
            for m in cl["members"]:
                seen.update(m.chart_metrics)
                chart_metrics_for(m.chart_metrics)   # raises if unmapped

    assert seen, "no finding declared any chart metrics"


def test_every_mapping_target_is_a_real_chart_metric():
    """A typo here produces an empty series rather than an error."""
    for engine_name, ids in ENGINE_TO_CHART.items():
        assert ids, f"{engine_name} maps to nothing"
        for i in ids:
            assert i in VALID_METRIC_KEYS, (
                f"{engine_name} -> {i}, which is not a chart metric")
    for i in ALWAYS_INCLUDE:
        assert i in VALID_METRIC_KEYS


def test_unmapped_metric_raises_rather_than_dropping_silently():
    """The whole point of the module.

    Dropping produces a chart missing the series its finding is about — worse
    than no chart, because it looks like evidence and is not.
    """
    with pytest.raises(UnmappedMetric, match="no chart equivalent"):
        chart_metrics_for(["a_metric_no_check_emits"])


def test_price_is_always_charted():
    """A divergence the market has already absorbed is a different situation
    from one it has not, and the two are indistinguishable without price."""
    assert "price" in chart_metrics_for(["cfo", "capex"])


def test_metrics_are_deduped_but_keep_their_order():
    """Evidence order is member-score order, so the strongest series is drawn
    first and reads as the primary line."""
    out = chart_metrics_for(["cfo", "capex", "cfo"])
    assert out == ["operating_cash_flow", "capex", "price"]


def test_roic_evidence_charts_both_legs_of_invested_capital():
    """`assets` in the engine means the ROIC denominator, which is
    assets - current_liabilities. Charting only assets would leave the reader
    unable to see which leg moved."""
    out = chart_metrics_for(["operating_income", "assets"])
    assert "total_assets" in out and "current_liabilities" in out


def test_gross_profit_charts_the_margin_not_the_absolute():
    """Q2 fires on a changepoint in the *margin*. Plotted absolute, the line is
    dominated by revenue growth and the change the check found is invisible."""
    assert "gross_margin" in chart_metrics_for(["gross_profit"])


def test_window_ends_at_the_last_quarter_not_today():
    """The last point any check could have seen."""
    dates = [f"{y}-12-31" for y in range(2005, 2027)]
    spec = spec_for(_Ev(["cfo"]), dates)
    assert spec["endYear"] == 2026
    assert spec["startYear"] == 2018      # endYear - DEFAULT_YEARS

    # Never earlier than the data actually starts.
    short = spec_for(_Ev(["cfo"]), ["2024-03-31", "2024-06-30"])
    assert short["startYear"] == 2024


def test_rates_and_absolutes_are_split_across_axes():
    """Dollars and percentages on one axis flattens the percentages to zero."""
    spec = spec_for(_Ev(["operating_income", "gross_profit"]),
                    ["2020-12-31", "2024-12-31"])
    assert "gross_margin" in spec["rightAxis"]
    assert "price" in spec["rightAxis"]
    assert "operating_income" not in spec["rightAxis"]


def test_empty_dates_do_not_explode():
    spec = spec_for(_Ev(["cfo"]), [])
    assert spec["startYear"] is None and spec["endYear"] is None
    assert spec["metrics"]


def test_scan_payload_attaches_a_spec_to_every_finding():
    """A finding with no chartSpec has a dead 'See chart' button."""
    from mcp_apps.scan_cli import scan_one

    for ticker in ("GOOGL", "AMZN", "AAPL", "NEE"):
        for f in scan_one(ticker)["clusters"]:
            spec = f["chartSpec"]
            assert spec["metrics"], f"{ticker}/{f['id']} has no chart metrics"
            assert spec["startYear"] and spec["endYear"]
            assert spec["startYear"] <= spec["endYear"]


def test_cluster_charts_all_of_its_members_evidence(companies):
    """A cluster is several checks telling one story.

    GOOGL's capital_cycle is roic_decline plus fcf_compression. Charting only
    the top-scoring member would show the ROIC collapse without the cash flow
    that makes it matter.
    """
    from mcp_apps.scan_cli import scan_one

    googl = {f["id"]: f for f in scan_one("GOOGL")["clusters"]}
    metrics = googl["capital_cycle"]["chartSpec"]["metrics"]
    assert {"total_assets", "current_liabilities"} <= set(metrics), "ROIC legs missing"
    assert {"operating_cash_flow", "capex"} <= set(metrics), "FCF legs missing"
