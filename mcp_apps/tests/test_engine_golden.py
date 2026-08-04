"""Known-correct engine output on the seed corpus.

These clusters and scores were produced by the standalone POC and reviewed
finding by finding. Routing the same Alpha Vantage payloads through
`mcp_apps.data` must reproduce them exactly — that is the whole claim phase 3
makes, and any drift means the fork changed something it should not have.

The numbers are not arbitrary. GOOGL's `capital_cycle` at 6.6 is ROIC falling
25.5% -> 15.1% while invested capital doubled, plus a trailing-twelve-month FCF
margin halving — the highest-scoring finding in the corpus. PG, WMT, COST and
UNH returning nothing is equally load-bearing: a scanner that flags healthy
companies is worse than useless, so "clean" is an assertion, not an absence.
"""
from __future__ import annotations

import pytest

from mcp_apps.data import adapters
from mcp_apps.engine import scan

# ticker -> [(cluster id, score)], in the order the engine ranks them.
GOLDEN: dict[str, list[tuple[str, float]]] = {
    "AAPL":  [("margin_changepoint", 1.755), ("fcf_expansion", 1.329)],
    "AMZN":  [("fcf_compression", 2.400), ("margin_changepoint", 1.671)],
    "COST":  [],
    "GOOGL": [("capital_cycle", 6.625), ("margin_changepoint", 2.035)],
    "NEE":   [("margin_changepoint", 4.141)],
    "PG":    [],
    "UNH":   [],   # declined — insurer, not "clean"
    "WMT":   [],
}

CLEAN = ["COST", "PG", "WMT"]


@pytest.fixture(scope="module")
def results(companies):
    return {t: scan(c) for t, c in companies.items()}


@pytest.mark.parametrize("ticker", sorted(GOLDEN))
def test_clusters_match_the_poc_exactly(ticker, results):
    got = [(c["id"], round(c["score"], 3)) for c in results[ticker]["clusters"]]
    assert got == GOLDEN[ticker], (
        f"{ticker}: engine output moved.\n  expected {GOLDEN[ticker]}\n"
        f"  got      {got}\nThe fork was supposed to change nothing the engine "
        f"can see.")


def test_googl_capital_cycle_rests_on_the_numbers_it_claims(companies):
    """Guard the headline finding against a coincidentally-equal score.

    A cluster id and a score matching is necessary but not sufficient — the
    same 6.625 could arise from different underlying series. Check the two
    facts the narrative actually asserts.
    """
    from mcp_apps.engine.stats import ttm

    c = companies["GOOGL"]
    assets, cl = c.series("assets"), c.series("current_liabs")
    invested = [(a - (l or 0)) for a, l in zip(assets, cl) if a is not None]
    assert invested[-1] > 1.8 * invested[-21], (
        "invested capital did not roughly double over five years — the "
        "capital_cycle narrative does not hold")

    cfo, capex, rev = c.series("cfo"), c.series("capex"), c.series("revenue")
    n = len(c.quarters)
    fcf_margin = []
    for i in range(n):
        o, x, r = ttm(cfo, i), ttm(capex, i), ttm(rev, i)
        if None not in (o, x, r) and r:
            fcf_margin.append((o - x) / r)
    assert fcf_margin[-1] < 0.6 * max(fcf_margin[-25:]), (
        "TTM FCF margin did not compress materially")


def test_clean_companies_return_nothing_and_ran_the_checks(results):
    """"Clean" must mean the checks ran and found nothing.

    An earlier bug had AAPL report "nothing unusual" on zero quarters of data —
    every check skipped, the report cheerfully empty. Absence of findings is
    only meaningful alongside evidence of coverage.
    """
    for ticker in CLEAN:
        r = results[ticker]
        assert r["clusters"] == [], f"{ticker} unexpectedly flagged"
        assert not r.get("declined"), f"{ticker} was declined, not clean"
        assert not r.get("insufficient"), f"{ticker} had insufficient data"
        assert r["total_checks"] > 0, f"{ticker}: no checks ran"


def test_unh_is_declined_rather_than_scanned(results):
    """Refusing to answer is the correct answer for an insurer.

    Premium revenue, claims reserves and net interest margin do not survive AV's
    normalized schema. Approximating them would produce confident nonsense, so
    the engine declines — and that must not be reported as a clean bill.
    """
    r = results["UNH"]
    assert r["declined"] is True
    assert r["clusters"] == []
    assert r.get("clean") is not True
    assert any("scope" in s.reason or "financial" in s.reason.lower()
               for s in r["skips"])


def test_every_finding_carries_its_innocent_explanations(results):
    """What separates an analyst tool from a short-seller newsletter.

    A statistically unusual number is not a verdict. Every finding ships with
    the benign readings to rule out first, and a follow-up question — without
    them the panel is just an accusation.
    """
    for ticker, r in results.items():
        for cl in r["clusters"]:
            members = cl["members"]
            assert members, f"{ticker}/{cl['id']}: empty cluster"
            assert any(m.benign for m in members), (
                f"{ticker}/{cl['id']}: no innocent explanations offered")
            assert members[0].follow_up, (
                f"{ticker}/{cl['id']}: no follow-up question")
            assert cl["direction"] in ("risk", "opportunity")


def test_cluster_members_are_sorted_by_score(results):
    """Members come out of a Python set; unsorted iteration was hash-dependent.

    The panel shows `members[0]`'s follow-up question, so ordering is
    user-visible. Under PYTHONHASHSEED variation GOOGL's question flipped
    between roic_decline (6.3) and fcf_compression (2.5) — a different question
    about a different metric, from identical inputs.
    """
    for ticker, r in results.items():
        for cl in r["clusters"]:
            scores = [m.score for m in cl["members"]]
            assert scores == sorted(scores, reverse=True), (
                f"{ticker}/{cl['id']}: members unsorted {scores}")


def test_scores_are_bounded_and_ordered(results):
    for ticker, r in results.items():
        scores = [c["score"] for c in r["clusters"]]
        assert scores == sorted(scores, reverse=True), f"{ticker}: unranked"
        for s in scores:
            assert 1.0 <= s <= 10.0, f"{ticker}: score {s} outside 1-10"
