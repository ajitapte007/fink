"""Cluster correlated checks into one narrative row, then floor and cap."""
from __future__ import annotations

from .scoring import Finding

CLUSTERS = {
    "revenue_quality": ({"accruals_high", "dso_expansion"},
                        "Earnings are outrunning cash collection"),
    "demand_softness": ({"dio_expansion", "margin_changepoint"},
                        "Inventory building as margins compress"),
    "liquidity": ({"dpo_expansion", "underinvestment"},
                  "Stretching payables while deferring capex"),
    "capital_cycle": ({"fcf_compression", "roic_decline"},
                      "Reinvestment is outrunning the returns it earns"),
    "operating_leverage": ({"accruals_low", "dso_release", "dio_release"},
                           "Cash conversion improving as the business scales"),
}


def strength_of(raw: float) -> float:
    return round(min(raw / Finding.SCALE, 1.0) * 10, 1)


def severity_of(raw: float) -> str:
    st = strength_of(raw)
    return "high" if st >= 6.5 else ("medium" if st >= 3.5 else "low")


def cluster(findings: list[Finding]) -> list[dict]:
    by_id = {f.check_id: f for f in findings}
    used: set[str] = set()
    out: list[dict] = []

    for name, (members, headline) in CLUSTERS.items():
        # CLUSTERS values are sets, so iteration order is hash-dependent and
        # varies with PYTHONHASHSEED. members[0] drives the cluster's follow-up
        # question, so leaving this unsorted makes the headline question
        # nondeterministic -- and it picked the weakest member as often as not.
        hit = sorted((by_id[m] for m in members if m in by_id),
                     key=lambda f: f.score, reverse=True)
        if len(hit) < 2:
            continue
        if any(h.direction != hit[0].direction for h in hit):
            continue
        used.update(h.check_id for h in hit)
        base = max(h.score for h in hit)
        out.append({
            "id": name, "headline": headline, "direction": hit[0].direction,
            "score": base + 0.3 * (len(hit) - 1), "members": hit,
        })

    for f in findings:
        if f.check_id not in used:
            out.append({"id": f.check_id, "headline": f.headline,
                        "direction": f.direction, "score": f.score,
                        "members": [f]})

    out.sort(key=lambda d: d["score"], reverse=True)
    return out


FLOOR = 1.0
CAP = 5
