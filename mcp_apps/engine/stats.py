"""Pure statistical helpers and business-model classification.

Lifted from the POC's metrics.py. The parsing half of that module is dropped:
mcp/data/process_utils.get_aligned_historical_data already does that job and is
better tested. Only the maths and the classifier come across.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Quarter:
    date: str                      # fiscalDateEnding, YYYY-MM-DD
    vals: dict[str, float | None] = field(default_factory=dict)

    def get(self, k: str) -> float | None:
        return self.vals.get(k)


@dataclass
class Company:
    ticker: str
    name: str
    sector: str
    industry: str
    market_cap: float | None
    quarters: list[Quarter]        # oldest first
    prices: list[tuple[str, float]]  # (YYYY-MM-DD, adj close), oldest first
    business_model: str = "generic"
    notes: list[str] = field(default_factory=list)

    def series(self, key: str) -> list[float | None]:
        return [q.get(key) for q in self.quarters]

    def dates(self) -> list[str]:
        return [q.date for q in self.quarters]


def classify(sector: str, industry: str) -> str:
    s, i = (sector or "").upper(), (industry or "").upper()

    # Managed care is an insurer wearing a healthcare label. AV files UNH under
    # LIFE SCIENCES / HOSPITAL & MEDICAL SERVICE PLANS, which would otherwise
    # slip through as a services company and produce a nonsense scan.
    if any(w in i for w in ("MEDICAL SERVICE PLAN", "HEALTHCARE PLAN",
                            "MANAGED CARE", "MEDICAL CARE PLAN")):
        return "financial"

    if any(w in s for w in ("FINANC", "INSURANCE", "BANK")) or any(
        w in i for w in ("BANK", "INSURANCE", "CAPITAL MARKETS", "REIT",
                         "ASSET MANAGEMENT", "MORTGAGE", "CREDIT SERVICES")
    ):
        return "financial"
    if "REAL ESTATE" in s:
        return "financial"

    # Utilities: rate-base accounting means capex persistently exceeds D&A by
    # design, so Q5 is meaningless. Own bucket rather than a wrong one.
    if "UTILIT" in s or "UTILIT" in i:
        return "utility"

    if "SOFTWARE" in i or "INFORMATION TECHNOLOGY SERVICES" in i:
        return "software"
    if any(w in i for w in ("RETAIL", "APPAREL", "GROCERY", "RESTAURANT",
                            "INTERNET RETAIL", "MAIL ORDER", "DISCOUNT STORE",
                            "DEPARTMENT STORE", "SUPERMARKET", "SPECIALTY STORE")):
        return "retail_consumer"
    if any(w in s for w in ("INDUSTRIAL", "ENERGY", "MATERIAL", "CONSUMER",
                            "MANUFACTURING")):
        return "industrial"
    if any(w in s for w in ("TECHNOLOGY", "COMMUNICATION", "HEALTH",
                            "LIFE SCIENCES")):
        return "services"
    return "generic"





def ttm(vals: list[float | None], i: int) -> float | None:
    """Trailing four quarters ending at index i."""
    if i < 3:
        return None
    window = vals[i - 3: i + 1]
    if any(v is None for v in window):
        return None
    return sum(window)  # type: ignore[arg-type]


def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def zscore(x: float, history: list[float]) -> float | None:
    """z of x against a prior distribution. Needs >=6 points and real spread."""
    clean = [h for h in history if h is not None]
    if len(clean) < 6:
        return None
    mu = sum(clean) / len(clean)
    var = sum((h - mu) ** 2 for h in clean) / (len(clean) - 1)
    sd = math.sqrt(var)
    if sd < 1e-9:
        return None
    return (x - mu) / sd


def percentile(x: float, history: list[float]) -> float | None:
    clean = sorted(h for h in history if h is not None)
    if len(clean) < 6:
        return None
    below = sum(1 for h in clean if h < x)
    return below / len(clean)


def yoy(vals: list[float | None], i: int) -> float | None:
    """Same-quarter year-over-year change. Kills seasonality."""
    if i < 4:
        return None
    a, b = vals[i], vals[i - 4]
    if a is None or b is None or b == 0:
        return None
    return (a - b) / abs(b)


def sustained(flags: list[bool], i: int, n: int) -> int:
    """How many consecutive True values end at index i."""
    c = 0
    while i - c >= 0 and flags[i - c]:
        c += 1
    return c
