"""fink anomaly engine.

    from mcp_apps.engine import scan
    result = scan(company)   # -> {"clusters": [...], "skips": [...], ...}

Returns clusters, not a flat findings list: correlated checks merge into one
narrative row so a single underlying story does not read as three problems.
"""
from __future__ import annotations

from .checks import (q1_earnings_quality, q2_core_spread, q3_working_capital,
                     q4_dilution, q5_reinvestment, q5b_free_cash_flow,
                     q6_market_disagreement, q7_returns_on_capital,
                     _six_month_returns)
from .clustering import CAP, CLUSTERS, FLOOR, cluster, severity_of, strength_of
from .scoring import (MIN_QUARTERS, NOT_PRICED_MAX_PCTL, WINDOW_M, WINDOW_Q,
                      Finding, Skip, _tail)
from .stats import Company, classify, percentile

__all__ = ["scan", "Company", "classify", "Finding", "Skip",
           "severity_of", "strength_of"]


def scan(c: Company) -> dict:
    findings: list[Finding] = []
    skips: list[Skip] = []

    usable = sum(1 for q in c.quarters if q.get("revenue") is not None)
    if usable < MIN_QUARTERS:
        return {
            "company": c, "clean": False, "declined": True,
            "insufficient": True, "clusters": [],
            "skips": [Skip("all", f"only {usable} quarters with usable revenue "
                                  f"(need {MIN_QUARTERS}) — nothing was checked")],
            "total_checks": 0,
        }

    if c.business_model == "financial":
        return {
            "company": c, "clean": False, "declined": True,
            "clusters": [], "skips": [Skip("all",
                "financials, insurers and REITs are out of scope — the checks "
                "need denominators this schema does not carry")],
            "total_checks": 0,
        }

    for fn in (q1_earnings_quality, q2_core_spread, q4_dilution,
               q5_reinvestment, q5b_free_cash_flow, q6_market_disagreement,
               q7_returns_on_capital):
        f, s = fn(c)
        if f:
            findings.append(f)
        if s:
            skips.append(s)

    wc_f, wc_s = q3_working_capital(c)
    findings.extend(wc_f)
    skips.extend(wc_s)

    # Opportunity gate: an improvement the market already repriced is not a find.
    rets = _six_month_returns(c.prices)
    price_pctl = (percentile(rets[-1], _tail(rets[:-1], WINDOW_M))
                  if len(rets) >= 24 else None)
    # A gated opportunity RAN — it was suppressed after the fact. Keeping it out
    # of `skips` matters because coverage is computed from that list, and a
    # suppression is not a blind spot.
    suppressed: list[Skip] = []
    kept: list[Finding] = []
    for f in findings:
        if (f.direction == "opportunity"
                and f.check_id != "price_fundamental_divergence"
                and price_pctl is not None
                and price_pctl > NOT_PRICED_MAX_PCTL):
            suppressed.append(Skip(f.question,
                                   f"{f.check_id}: improvement already priced "
                                   f"(6m return in {price_pctl * 100:.0f}th "
                                   f"percentile)"))
            continue
        kept.append(f)

    clusters = [c_ for c_ in cluster(kept) if c_["score"] >= FLOOR]
    overflow = max(0, len(clusters) - CAP)

    return {
        "company": c,
        "clean": len(clusters) == 0,
        "declined": False,
        "clusters": clusters[:CAP],
        "overflow": overflow,
        "skips": skips,
        "suppressed": suppressed,
        "checks_ran": 10 - len(skips),
        "total_checks": 10,
        "price_percentile": price_pctl,
    }
