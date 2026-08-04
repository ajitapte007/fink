"""Finding, scoring, severity, and the shared tuning constants.

Changes rarely — the checks get tuned constantly, this does not.
"""
from __future__ import annotations

from dataclasses import dataclass, field

WEIGHTS = {"Q1": 1.0, "Q2": 0.8, "Q3": 0.7, "Q4": 0.7, "Q5": 0.6, "Q6": 0.5,
           "Q7": 0.9}
OPPORTUNITY_SCALE = 0.7
# Opportunity gate. The spec wants "valuation percentile vs own history", which
# AV's schema cannot give cheaply, so this uses 6-month price return as a proxy.
# It is a blunter instrument, so the threshold is set where the price has
# clearly responded rather than merely being unremarkable — at 0.40 a stock with
# a median return counted as "already repriced", which suppressed real signals.
NOT_PRICED_MAX_PCTL = 0.75

# Baselines are a trailing window, not all history. The cache carries 20 years
# for some tickers; a z-score against two decades flags any structural trend as
# an anomaly, because the latest point of a long drift is always extreme.
# Five years is long enough for a distribution and short enough that the
# business model has not changed underneath it.
WINDOW_Q = 20    # quarters
WINDOW_M = 60    # months, for price percentiles
MIN_QUARTERS = 12


def _tail(xs: list, n: int) -> list:
    return xs[-n:] if len(xs) > n else xs


@dataclass
class Finding:
    question: str
    check_id: str
    direction: str               # "risk" | "opportunity"
    headline: str
    detail: str
    magnitude_z: float
    persistence: int             # quarters sustained
    confidence: float = 1.0
    benign: list[str] = field(default_factory=list)
    follow_up: str = ""
    chart_metrics: list[str] = field(default_factory=list)

    EXTREME_Z = 5.0

    @property
    def suspect(self) -> bool:
        """Beyond this, a reading is far more likely to be a one-off item
        or a bad input than a real trend."""
        return self.magnitude_z > self.EXTREME_Z

    @property
    def score(self) -> float:
        mag = max(0.0, min(self.magnitude_z, 4.0))
        if self.suspect:
            mag *= 0.4
        pers = min(self.persistence / 2, 2.0)
        w = WEIGHTS[self.question] * (
            OPPORTUNITY_SCALE if self.direction == "opportunity" else 1.0
        )
        return mag * pers * w * self.confidence

    # Raw score is an unbounded product and means nothing on its own. Strength
    # normalises it to 0-10 as EVIDENCE STRENGTH for this one check -- how
    # extreme the reading is -- not as a measure of how bad the company is.
    SCALE = 6.0

    @property
    def strength(self) -> float:
        return round(min(self.score / self.SCALE, 1.0) * 10, 1)

    @property
    def severity(self) -> str:
        if self.suspect:
            return "check inputs"
        st = self.strength
        return "high" if st >= 6.5 else ("medium" if st >= 3.5 else "low")


@dataclass
class Skip:
    question: str
    reason: str


def _pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


