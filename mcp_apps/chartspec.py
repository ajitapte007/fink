"""Turn a finding into a chart the user can inspect.

The engine and the chart speak different vocabularies, for reasons that are
not accidental. The engine works in fiscal quarters off raw statement line
items and names them for what they are in an accounting sense — `cfo`,
`dandA`, `assets`. The chart works in monthly-aligned series off
`metrics_registry` and names them for what a reader would pick off a menu —
`operating_cash_flow`, `depreciation_amortization`, `total_assets`.

This module is the one place those two vocabularies meet. Every check already
declares the series its claim rests on (`Finding.chart_metrics`), so "chase the
finding" does not need to guess: it charts the evidence the check actually
used.

An unmapped name raises rather than silently dropping the metric. A chart
missing the series the finding is about is worse than no chart — it invites
the reader to conclude the claim is unsupported.
"""
from __future__ import annotations

from .data.metrics_registry import VALID_METRIC_KEYS

# Engine name -> chart metric id.
#
# Most are identity; the interesting entries are the ones that are not:
#
#   gross_profit  The registry has no absolute gross profit, only the margin.
#                 The margin is the better chart anyway — Q2 fires on a
#                 *changepoint in the margin*, and plotting the absolute would
#                 show a line dominated by revenue growth with the change the
#                 check found nearly invisible.
#
#   assets        The engine's ROIC denominator is invested capital,
#                 assets - current_liabilities. Both legs are charted so the
#                 reader can see which one moved.
#
#   equity        Only ever charted alongside net income for ROE.
ENGINE_TO_CHART: dict[str, list[str]] = {
    "revenue":          ["revenue"],
    "cogs":             ["cost_of_goods_sold"],
    "gross_profit":     ["gross_margin"],
    "operating_income": ["operating_income"],
    "net_income":       ["net_income"],
    "sga":              ["selling_general_admin"],
    "pretax_income":    ["operating_income"],
    "tax_expense":      ["operating_income"],

    "assets":           ["total_assets", "current_liabilities"],
    "current_liabs":    ["current_liabilities"],
    "inventory":        ["inventory"],
    "receivables":      ["receivables"],
    "payables":         ["payables"],
    "equity":           ["net_income"],
    "shares":           ["shares_outstanding"],

    "cfo":              ["operating_cash_flow"],
    "capex":            ["capex"],
    "dandA":            ["depreciation_amortization"],
    "buyback":          ["share_repurchase"],
}

# Charted alongside every finding. Price is the reason any of this matters —
# a fundamental divergence the market has already absorbed is a different
# situation from one it has not, and the two are indistinguishable without it.
ALWAYS_INCLUDE = ["price"]

# How much history to open with. Long enough to show the trailing window the
# checks score against (20 quarters), plus a little context before it so the
# reader can see what "normal" looked like.
DEFAULT_YEARS = 8


class UnmappedMetric(KeyError):
    """An engine metric with no chart equivalent.

    Raised rather than skipped. A silently dropped series produces a chart that
    does not show the evidence the finding claims, which reads as the claim
    being unsupported.
    """


def chart_metrics_for(engine_names: list[str]) -> list[str]:
    """Chart metric ids for a finding's evidence, order preserved, deduped."""
    out: list[str] = []
    for name in engine_names:
        try:
            mapped = ENGINE_TO_CHART[name]
        except KeyError:
            raise UnmappedMetric(
                f"engine metric {name!r} has no chart equivalent. Add it to "
                f"ENGINE_TO_CHART — dropping it would produce a chart that "
                f"omits the evidence its finding rests on.") from None
        for m in mapped:
            if m not in out:
                out.append(m)

    for m in ALWAYS_INCLUDE:
        if m not in out:
            out.append(m)

    unknown = [m for m in out if m not in VALID_METRIC_KEYS]
    if unknown:
        raise UnmappedMetric(
            f"{unknown} are not in VALID_METRIC_KEYS — the chart cannot "
            f"request them")
    return out


def spec_for(finding, dates: list[str]) -> dict:
    """The chartSpec a finding hands to the view.

    `dates` is the company's quarter-end dates, oldest first, used only to
    place the window. The window ends at the latest quarter rather than today
    because that is the last point the check could have seen.
    """
    metrics = chart_metrics_for(finding.chart_metrics)

    end_year = int(dates[-1][:4]) if dates else None
    start_year = None
    if end_year is not None:
        earliest = int(dates[0][:4])
        start_year = max(earliest, end_year - DEFAULT_YEARS)

    return {
        "metrics": metrics,
        "startYear": start_year,
        "endYear": end_year,
        # Absolute dollar series and percentage series on one axis makes the
        # percentages a flat line at zero. The view puts anything whose id ends
        # in _margin, or is a rate, on the right-hand axis.
        "rightAxis": [m for m in metrics
                      if m.endswith("_margin") or m in
                      ("roic", "roa", "roe", "price", "dividend_yield")],
    }
