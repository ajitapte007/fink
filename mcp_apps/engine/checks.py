"""The eight checks, over six questions.

Every threshold is relative to the company's own trailing window. No absolute
constants except noise floors. Returning nothing on a healthy company is the
design target.
"""
from __future__ import annotations

from .scoring import Finding, Skip, WEIGHTS, _pct, _tail, WINDOW_Q, WINDOW_M, MIN_QUARTERS
from .stats import Company, percentile, safe_div, sustained, ttm, yoy, zscore

# ----------------------------------------------------------------- Q1 accruals
def q1_earnings_quality(c: Company) -> tuple[Finding | None, Skip | None]:
    if c.business_model == "financial":
        return None, Skip("Q1", "financials — accruals framework does not apply")

    ni, cfo, assets = c.series("net_income"), c.series("cfo"), c.series("assets")
    n = len(c.quarters)
    ratios: list[float | None] = [None] * n
    for i in range(n):
        a, b = ttm(ni, i), ttm(cfo, i)
        if a is None or b is None:
            continue
        avg_assets = None
        if assets[i] is not None and i >= 4 and assets[i - 4] is not None:
            avg_assets = (assets[i] + assets[i - 4]) / 2
        elif assets[i] is not None:
            avg_assets = assets[i]
        ratios[i] = safe_div(a - b, avg_assets)

    idx = [i for i, r in enumerate(ratios) if r is not None]
    if len(idx) < 8:
        return None, Skip("Q1", "fewer than 8 quarters of usable TTM data")

    i = idx[-1]
    cur = ratios[i]
    hist = [ratios[j] for j in _tail(idx[:-1], WINDOW_Q)]
    z = zscore(cur, hist)
    if z is None:
        return None, Skip("Q1", "insufficient variation in accrual history")

    rising = [
        (ratios[j] is not None and ratios[j - 1] is not None
         and ratios[j] > ratios[j - 1])
        for j in range(n)
    ]
    falling = [
        (ratios[j] is not None and ratios[j - 1] is not None
         and ratios[j] < ratios[j - 1])
        for j in range(n)
    ]

    positive = [(ratios[j] is not None and ratios[j] > 0) for j in range(n)]
    if cur > 0 and z >= 1.0:
        p = min(sustained(rising, i, 2), sustained(positive, i, 2))
        if p >= 2:
            return Finding(
                "Q1", "accruals_high", "risk",
                "Earnings are outrunning cash generation",
                f"TTM accrual ratio is {_pct(cur, 2)} of assets, {z:.1f}σ above "
                f"its own history, and has risen {p} quarters running.",
                z, p,
                benign=[
                    "A build in receivables from genuine revenue growth",
                    "Timing of a large customer payment across the quarter end",
                    "An acquisition with a different working capital profile",
                ],
                follow_up=f"Why has {c.ticker}'s net income grown faster than "
                          f"operating cash flow over the last year?",
                chart_metrics=["net_income", "cfo"],
            ), None

    if cur < 0 and z <= -1.0:
        p = sustained(falling, i, 2)
        if p >= 2:
            return Finding(
                "Q1", "accruals_low", "opportunity",
                "Cash generation is outrunning reported earnings",
                f"TTM accrual ratio is {_pct(cur, 2)} of assets, {abs(z):.1f}σ "
                f"below its own history, {p} quarters running. Conservative "
                f"recognition or a working-capital release.",
                abs(z), p,
                benign=[
                    "A one-off working capital unwind that will not repeat",
                    "Deferred revenue growth that flatters cash but not earnings",
                ],
                follow_up=f"Why is {c.ticker} generating more cash than reported "
                          f"earnings — is this sustainable?",
                chart_metrics=["net_income", "cfo"],
            ), None

    return None, None


# ------------------------------------------------------------- Q2 core spread
def q2_core_spread(c: Company) -> tuple[Finding | None, Skip | None]:
    rev, gp = c.series("revenue"), c.series("gross_profit")
    cogs = c.series("cogs")
    n = len(c.quarters)
    gm: list[float | None] = [None] * n
    for i in range(n):
        if gp[i] is not None and rev[i]:
            gm[i] = gp[i] / rev[i]
        elif cogs[i] is not None and rev[i]:
            gm[i] = (rev[i] - cogs[i]) / rev[i]

    idx = [i for i, v in enumerate(gm) if v is not None]
    if len(idx) < 12:
        return None, Skip("Q2", "fewer than 12 quarters of margin data")

    recent = [gm[j] for j in idx[-4:]]
    prior = [gm[j] for j in idx[-12:-4]]
    r, p_ = sum(recent) / len(recent), sum(prior) / len(prior)
    delta_bp = (r - p_) * 10_000

    if abs(delta_bp) < 150:
        return None, None

    mag = min(abs(delta_bp) / 150.0, 4.0)
    direction = "risk" if delta_bp < 0 else "opportunity"
    word = "compressed" if delta_bp < 0 else "expanded"

    return Finding(
        "Q2", "margin_changepoint", direction,
        f"Gross margin has {word} {abs(delta_bp):.0f}bp",
        f"Last four quarters averaged {_pct(r)} versus {_pct(p_)} in the eight "
        f"before them — a {abs(delta_bp):.0f}bp {word.rstrip('ed')}sion.",
        mag, 4,
        benign=(
            ["Input cost inflation not yet passed through",
             "Mix shift toward lower-margin products",
             "A period of deliberate price investment to hold share"]
            if delta_bp < 0 else
            ["Mix shift toward higher-margin products",
             "Input costs easing after a spike",
             "One-off benefit that will not repeat"]
        ),
        follow_up=f"What drove the {abs(delta_bp):.0f}bp change in {c.ticker}'s "
                  f"gross margin over the last four quarters?",
        chart_metrics=["revenue", "gross_profit"],
    ), None


# ---------------------------------------------------------- Q3 working capital
def _wc_metric(c: Company, num_key: str, den_key: str) -> list[float | None]:
    numer, denom = c.series(num_key), c.series(den_key)
    out: list[float | None] = []
    for i in range(len(c.quarters)):
        d = safe_div(numer[i], denom[i])
        out.append(d * 91 if d is not None else None)
    return out


def q3_working_capital(c: Company) -> tuple[list[Finding], list[Skip]]:
    findings: list[Finding] = []
    skips: list[Skip] = []
    n = len(c.quarters)
    rev = c.series("revenue")

    inv, assets = c.series("inventory"), c.series("assets")
    inv_share = safe_div(
        next((v for v in reversed(inv) if v is not None), None),
        next((v for v in reversed(assets) if v is not None), None),
    )

    specs = [
        ("dso", "receivables", "revenue", "Days sales outstanding", True),
        ("dio", "inventory", "cogs", "Days inventory outstanding", True),
        ("dpo", "payables", "cogs", "Days payable outstanding", False),
    ]

    for key, num_key, den_key, label, two_sided in specs:
        if key == "dio":
            if c.business_model == "software":
                skips.append(Skip("Q3.dio", "software — inventory not meaningful"))
                continue
            if inv_share is not None and inv_share < 0.03:
                skips.append(Skip("Q3.dio",
                                  f"inventory is {_pct(inv_share)} of assets"))
                continue

        series = _wc_metric(c, num_key, den_key)
        changes = [yoy(series, i) for i in range(n)]
        lvl_idx = [i for i, v in enumerate(series) if v is not None]
        if len(lvl_idx) < 10:
            skips.append(Skip(f"Q3.{key}", "fewer than 10 comparable quarters"))
            continue

        i = lvl_idx[-1]
        cur = changes[i]
        if cur is None:
            skips.append(Skip(f"Q3.{key}", "no year-ago quarter to compare"))
            continue

        # z on the LEVEL against its own trailing history, not on the YoY change.
        # A steady multi-year drift produces near-constant YoY and would be
        # invisible to a change-based z-score — which is exactly the pattern
        # worth catching.
        z = zscore(series[i],
                   [series[j] for j in _tail(lvl_idx[:-1], WINDOW_Q)])
        if z is None:
            continue

        rev_growth_now = yoy(rev, i)
        rev_growth_prev = yoy(rev, i - 1) if i >= 5 else None
        accelerating = (
            rev_growth_now is not None and rev_growth_prev is not None
            and rev_growth_now > rev_growth_prev
        )

        up_flags = [(changes[j] or 0) > 0 for j in range(n)]
        down_flags = [(changes[j] or 0) < 0 for j in range(n)]

        if z >= 1.5 and cur > 0:
            if accelerating:
                skips.append(Skip(f"Q3.{key}",
                                  "expanding alongside accelerating revenue"))
                continue
            p = sustained(up_flags, i, 2)
            if p >= 2:
                findings.append(Finding(
                    "Q3", f"{key}_expansion", "risk",
                    f"{label} is stretching",
                    f"{label} rose {_pct(cur)} year over year, {z:.1f}σ above its "
                    f"own history, {p} quarters running, while revenue growth was "
                    f"{'flat or slowing' if not accelerating else 'accelerating'}.",
                    z, p,
                    benign=[
                        "A shift toward customers with longer payment terms",
                        "A single large order timing across the period end",
                        "Deliberate inventory build ahead of demand",
                    ],
                    follow_up=f"Why has {c.ticker}'s {label.lower()} risen while "
                              f"revenue growth has not?",
                    chart_metrics=[num_key, den_key],
                ))
        elif two_sided and z <= -1.5 and cur < 0:
            p = sustained(down_flags, i, 2)
            growing = rev_growth_now is not None and rev_growth_now > 0
            if p >= 2 and growing:
                findings.append(Finding(
                    "Q3", f"{key}_release", "opportunity",
                    f"{label} is improving while revenue grows",
                    f"{label} fell {_pct(abs(cur))} year over year, {abs(z):.1f}σ "
                    f"below its own history, {p} quarters running, with revenue "
                    f"up {_pct(rev_growth_now)}.",
                    abs(z), p,
                    benign=["A one-off collection or destocking that will not repeat"],
                    follow_up=f"Is {c.ticker}'s working capital improvement "
                              f"structural or a one-off?",
                    chart_metrics=[num_key, den_key],
                ))

    return findings, skips


# ----------------------------------------------------------------- Q4 dilution
def q4_dilution(c: Company) -> tuple[Finding | None, Skip | None]:
    shares = c.series("shares")
    buyback = c.series("buyback")
    n = len(c.quarters)

    changes = [yoy(shares, i) for i in range(n)]
    idx = [i for i, v in enumerate(changes) if v is not None]
    if len(idx) < 4:
        return None, Skip("Q4", "fewer than 4 comparable quarters of share count")

    i = idx[-1]
    cur = changes[i]
    bb_ttm = ttm(buyback, i) or 0.0

    if cur >= 0.015:
        p = sustained([(changes[j] or 0) >= 0.005 for j in range(n)], i, 1)
        mag = min(cur / 0.015, 4.0)
        if bb_ttm > 0:
            headline = "Buybacks are not keeping up with dilution"
            detail = (f"Shares outstanding rose {_pct(cur)} year over year while "
                      f"${bb_ttm / 1e9:.2f}B was spent on repurchases — issuance "
                      f"is outpacing the buyback.")
        else:
            headline = "Share count is creeping up"
            detail = (f"Shares outstanding rose {_pct(cur)} year over year with no "
                      f"offsetting repurchase.")
        return Finding(
            "Q4", "dilution", "risk", headline, detail, mag, max(p, 1),
            benign=[
                "Shares issued for an acquisition",
                "A deliberate equity raise to fund growth",
                "Stock compensation in a period of heavy hiring",
            ],
            follow_up=f"Is {c.ticker}'s share count increase stock compensation, "
                      f"an acquisition, or an equity raise?",
            chart_metrics=["shares"],
        ), None

    if cur <= -0.015:
        p = sustained([(changes[j] or 0) <= -0.005 for j in range(n)], i, 1)
        return Finding(
            "Q4", "share_shrink", "opportunity",
            "Share count is genuinely shrinking",
            f"Shares outstanding fell {_pct(abs(cur))} year over year with "
            f"${bb_ttm / 1e9:.2f}B of repurchases — buybacks are exceeding "
            f"issuance, which is rarer than it sounds.",
            min(abs(cur) / 0.015, 4.0), max(p, 1),
            benign=["A one-off tender that will not repeat"],
            follow_up=f"Is {c.ticker}'s share reduction sustainable at current "
                      f"free cash flow?",
            chart_metrics=["shares"],
        ), None

    return None, None


# ------------------------------------------------------------- Q5 reinvestment
def q5_reinvestment(c: Company) -> tuple[Finding | None, Skip | None]:
    if c.business_model == "software":
        return None, Skip("Q5", "asset-light — capex/D&A not meaningful")
    if c.business_model == "utility":
        return None, Skip(
            "Q5", "utility — rate-base growth means capex exceeds D&A by design")

    capex, da = c.series("capex"), c.series("dandA")
    n = len(c.quarters)
    ratio: list[float | None] = [safe_div(ttm(capex, i), ttm(da, i))
                                 for i in range(n)]
    idx = [i for i, v in enumerate(ratio) if v is not None]
    if len(idx) < 8:
        return None, Skip("Q5", "fewer than 8 quarters of capex and D&A")

    i = idx[-1]
    cur = ratio[i]

    low = [(ratio[j] is not None and ratio[j] < 0.8) for j in range(n)]
    p = sustained(low, i, 4)
    if p >= 4:
        return Finding(
            "Q5", "underinvestment", "risk",
            "Reinvestment has fallen below depreciation",
            f"Capex has run at {cur:.2f}× depreciation for {p} consecutive "
            f"quarters. Sustained underinvestment flatters near-term margins and "
            f"free cash flow.",
            min((0.8 - cur) / 0.15, 4.0), p,
            benign=[
                "A completed capacity expansion cycle",
                "A shift toward leased rather than owned assets",
                "Asset-light strategy pursued deliberately",
            ],
            follow_up=f"Is {c.ticker}'s low capex a completed build-out or "
                      f"deferred maintenance?",
            chart_metrics=["capex", "dandA"],
        ), None

    prior = [ratio[j] for j in idx[-8:-4]]
    if cur >= 1.2 and prior and all(v < 1.0 for v in prior):
        return Finding(
            "Q5", "reinvestment_restart", "opportunity",
            "Reinvestment has restarted after a lull",
            f"Capex is now {cur:.2f}× depreciation after four quarters below 1.0×. "
            f"This depresses near-term free cash flow and often precedes revenue "
            f"acceleration.",
            min((cur - 1.0) / 0.2, 4.0), 2,
            benign=["Replacement of assets deferred during a downturn",
                    "A one-off facility purchase"],
            follow_up=f"What is {c.ticker} spending the increased capex on?",
            chart_metrics=["capex", "dandA"],
        ), None

    return None, None


# ------------------------------------------------------ Q6 market disagreement
def _six_month_returns(prices: list[tuple[str, float]]) -> list[float]:
    out = []
    for i in range(6, len(prices)):
        a, b = prices[i][1], prices[i - 6][1]
        if b:
            out.append((a - b) / b)
    return out


def q6_market_disagreement(c: Company) -> tuple[Finding | None, Skip | None]:
    rets = _six_month_returns(c.prices)
    if len(rets) < 24:
        return None, Skip("Q6", "fewer than 24 months of price history")

    cur_ret = rets[-1]
    pctl = percentile(cur_ret, _tail(rets[:-1], WINDOW_M))
    if pctl is None:
        return None, None

    rev = c.series("revenue")
    n = len(c.quarters)
    rev_ttm = [ttm(rev, i) for i in range(n)]
    growth = next((yoy(rev_ttm, i) for i in range(n - 1, -1, -1)
                   if yoy(rev_ttm, i) is not None), None)

    op, revs = c.series("operating_income"), c.series("revenue")
    om = [safe_div(op[i], revs[i]) for i in range(n)]
    om_idx = [i for i, v in enumerate(om) if v is not None]
    om_delta = None
    if len(om_idx) >= 8:
        recent = [om[j] for j in om_idx[-4:]]
        prior = [om[j] for j in om_idx[-8:-4]]
        om_delta = sum(recent) / len(recent) - sum(prior) / len(prior)

    if growth is None:
        return None, Skip("Q6", "insufficient revenue history to judge fundamentals")

    improving = growth > 0 and (om_delta is None or om_delta >= -0.005)
    deteriorating = growth < 0 or (om_delta is not None and om_delta < -0.01)

    if pctl <= 0.10 and improving:
        return Finding(
            "Q6", "price_fundamental_divergence", "opportunity",
            "Price is weak while fundamentals are not",
            f"Six-month return of {_pct(cur_ret)} sits in the bottom "
            f"{pctl * 100:.0f}% of its own five-year range, while TTM revenue grew "
            f"{_pct(growth)} and operating margin was "
            f"{'stable' if om_delta is None or abs(om_delta) < 0.005 else _pct(om_delta) + ' changed'}.",
            min((0.10 - pctl) / 0.03 + 1.0, 4.0), 2,
            benign=[
                "The market is pricing something not yet in the financials",
                "Sector-wide de-rating unrelated to this company",
                "Guidance withdrawn or cut after the last reported quarter",
            ],
            follow_up=f"Why has {c.ticker} de-rated despite stable fundamentals — "
                      f"what does the market see?",
            chart_metrics=["revenue", "operating_income"],
        ), None

    if pctl >= 0.90 and deteriorating:
        return Finding(
            "Q6", "price_fundamental_divergence", "risk",
            "Price is strong while fundamentals soften",
            f"Six-month return of {_pct(cur_ret)} sits in the top "
            f"{(1 - pctl) * 100:.0f}% of its own five-year range, while TTM revenue "
            f"grew {_pct(growth)} and operating margin moved "
            f"{_pct(om_delta) if om_delta is not None else 'n/a'}.",
            min((pctl - 0.90) / 0.03 + 1.0, 4.0), 2,
            benign=[
                "The market is pricing a recovery not yet in the numbers",
                "A sector re-rating or index inclusion",
            ],
            follow_up=f"What is the market pricing into {c.ticker} that the "
                      f"fundamentals do not yet show?",
            chart_metrics=["revenue", "operating_income"],
        ), None

    return None, None



# ------------------------------------------------------- Q5b free cash flow
def q5b_free_cash_flow(c: Company) -> tuple[Finding | None, Skip | None]:
    """Q1 compares net income to operating cash flow, which leaves capex
    entirely invisible — it is an investing outflow. Q5 compares capex to
    depreciation, which is a ratio and says nothing about the absolute drain.
    A company can therefore have collapsing free cash flow and trip neither.
    """
    cfo, capex, rev = c.series("cfo"), c.series("capex"), c.series("revenue")
    n = len(c.quarters)

    fcf_q: list[float | None] = [
        (cfo[i] - capex[i]) if (cfo[i] is not None and capex[i] is not None)
        else None for i in range(n)
    ]
    margin: list[float | None] = []
    for i in range(n):
        C, K, R = ttm(cfo, i), ttm(capex, i), ttm(rev, i)
        margin.append((C - K) / R if (C is not None and K is not None and R)
                      else None)

    idx = [i for i, v in enumerate(margin) if v is not None]
    if len(idx) < 10:
        return None, Skip("Q5b", "fewer than 10 quarters of cash flow and capex")

    i = idx[-1]
    cur = margin[i]
    z = zscore(cur, [margin[j] for j in _tail(idx[:-1], WINDOW_Q)])
    if z is None:
        return None, Skip("Q5b", "insufficient variation in FCF margin")

    falling = [(margin[j] is not None and margin[j - 1] is not None
                and margin[j] < margin[j - 1]) for j in range(n)]
    rising = [(margin[j] is not None and margin[j - 1] is not None
               and margin[j] > margin[j - 1]) for j in range(n)]

    # A single negative *quarter* is seasonal noise — retailers and utilities
    # produce them routinely. A negative *trailing twelve months*, in a business
    # that was positive within the window, is a state change.
    prior_positive = any(v is not None and v > 0.02
                         for v in [margin[j] for j in _tail(idx[:-1], WINDOW_Q)])
    went_negative = cur <= 0 and prior_positive

    if z <= -1.5 or went_negative:
        p = max(sustained(falling, i, 2), 2 if went_negative else 0)
        peak = max(margin[j] for j in _tail(idx[:-1], WINDOW_Q))
        detail = (f"TTM free cash flow margin is {_pct(cur)}, down from a "
                  f"{_pct(peak)} peak, {abs(z):.1f}σ below its own history.")
        if went_negative:
            detail += " Trailing twelve-month free cash flow is now negative."
        if fcf_q[i] is not None and fcf_q[i] < 0:
            detail += (f" The latest quarter was ${fcf_q[i] / 1e9:.1f}B.")
        return Finding(
            "Q5", "fcf_compression", "risk",
            "Free cash flow is being consumed by reinvestment",
            detail, max(abs(z), 2.0 if went_negative else 0.0), max(p, 2),
            benign=[
                "A deliberate capacity build with a known payback period",
                "Front-loaded spend on assets with long useful lives",
                "A one-off property or infrastructure purchase",
            ],
            follow_up=f"What is {c.ticker} spending capex on, and what return "
                      f"is management guiding to on it?",
            chart_metrics=["cfo", "capex"],
        ), None

    if z >= 1.5:
        p = sustained(rising, i, 2)
        if p >= 2:
            return Finding(
                "Q5", "fcf_expansion", "opportunity",
                "Free cash flow margin is expanding",
                f"TTM free cash flow margin is {_pct(cur)}, {z:.1f}σ above its "
                f"own history, {p} quarters running.",
                z, p,
                benign=["Capex deferred rather than genuinely lower",
                        "A working capital release that will not repeat"],
                follow_up=f"Is {c.ticker}'s free cash flow improvement lower "
                          f"reinvestment or genuine operating leverage?",
                chart_metrics=["cfo", "capex"],
            ), None

    return None, None


# --------------------------------------------------- Q7 returns on capital
def q7_returns_on_capital(c: Company) -> tuple[Finding | None, Skip | None]:
    """ROIC = NOPAT / (total assets - current liabilities).

    ROE is deliberately excluded: buybacks shrink the denominator, so a company
    returning capital shows rising ROE with no change in the business. ROA is
    the fallback when current liabilities are missing.
    """
    op, pretax, tax = (c.series("operating_income"), c.series("pretax_income"),
                       c.series("tax_expense"))
    assets, cl = c.series("assets"), c.series("current_liabs")
    ni = c.series("net_income")
    n = len(c.quarters)

    roic: list[float | None] = [None] * n
    basis = "ROIC"
    for i in range(n):
        O, P, X = ttm(op, i), ttm(pretax, i), ttm(tax, i)
        if O is not None and P and X is not None and assets[i] and cl[i]:
            rate = min(max(X / P, 0.0), 0.5)
            roic[i] = safe_div(O * (1 - rate), assets[i] - cl[i])

    if sum(1 for v in roic if v is not None) < 10:
        basis = "ROA"
        for i in range(n):
            roic[i] = safe_div(ttm(ni, i), assets[i])

    idx = [i for i, v in enumerate(roic) if v is not None]
    if len(idx) < 10:
        return None, Skip("Q7", "fewer than 10 quarters of return data")

    i = idx[-1]
    cur = roic[i]
    hist = [roic[j] for j in _tail(idx[:-1], WINDOW_Q)]
    z = zscore(cur, hist)
    if z is None:
        return None, Skip("Q7", "insufficient variation in returns")

    peak = max(hist)
    delta_bp = (cur - peak) * 10_000
    falling = [(roic[j] is not None and roic[j - 1] is not None
                and roic[j] < roic[j - 1]) for j in range(n)]
    rising = [(roic[j] is not None and roic[j - 1] is not None
               and roic[j] > roic[j - 1]) for j in range(n)]

    if z <= -1.5 and delta_bp <= -200:
        p = sustained(falling, i, 2)
        if p >= 2:
            return Finding(
                "Q7", "roic_decline", "risk",
                f"{basis} is falling as the capital base grows",
                f"{basis} is {_pct(cur)}, down {abs(delta_bp):.0f}bp from a "
                f"{_pct(peak)} peak, {abs(z):.1f}σ below its own history and "
                f"falling {p} quarters running.",
                abs(z), p,
                benign=[
                    "Capital deployed ahead of the revenue it will support",
                    "An acquisition that has not yet been integrated",
                    "A deliberate shift to a more capital-intensive mix",
                ],
                follow_up=f"Is {c.ticker}'s {basis} decline new capital not yet "
                          f"earning, or a permanently worse business?",
                chart_metrics=["operating_income", "assets"],
            ), None

    if z >= 1.5 and (cur - min(hist)) * 10_000 >= 200:
        p = sustained(rising, i, 2)
        if p >= 2:
            return Finding(
                "Q7", "roic_improvement", "opportunity",
                f"{basis} is improving",
                f"{basis} is {_pct(cur)}, {z:.1f}σ above its own history, "
                f"rising {p} quarters running.",
                z, p,
                benign=["Asset sales shrinking the denominator rather than "
                        "profits growing the numerator"],
                follow_up=f"Is {c.ticker}'s {basis} improvement higher profit "
                          f"or a smaller capital base?",
                chart_metrics=["operating_income", "assets"],
            ), None

    return None, None


# ------------------------------------------------------------------- pipeline
