"""The seed corpus is a fixture checked into git. Treat it like one.

`local_av_cache/*.json` is the only data a fresh clone has. The SQLite cache is
gitignored, so anything the corpus lacks is unavailable offline — and that gap
is invisible on a developer machine whose cache was populated months ago from
calls nobody remembers making.

That is exactly how CPRT slipped: it scanned fine during POC development
because the developer's cache held its CASH_FLOW, while the checked-in JSON
never had it.
"""
from __future__ import annotations

import json

import pytest

from mcp_apps.data.alphavantage.fetch import CACHE_DIR, FUNCTIONS, is_data_corrupt

# Gaps we know about and have chosen to live with, ticker -> missing functions.
#
# Asserted as an exact match, not a subset: a new gap fails, and *closing* this
# one also fails, telling you to delete the entry. Silent drift in either
# direction is the thing being prevented.
KNOWN_INCOMPLETE = {
    "CPRT": ["CASH_FLOW"],
}


def _corpus() -> dict[str, dict]:
    return {p.stem.upper(): json.loads(p.read_text())
            for p in sorted(CACHE_DIR.glob("*.json"))}


def test_corpus_gaps_are_exactly_the_ones_we_know_about():
    """One AV call closes CPRT:

        python -m mcp_apps.data.alphavantage.reseed_cache --apply --budget 1

    After that, delete CPRT from KNOWN_INCOMPLETE and add it back to
    golden_hash.TICKERS and the engine golden set.
    """
    actual = {}
    for ticker, payload in _corpus().items():
        missing = [fn for fn in FUNCTIONS if fn not in payload]
        if missing:
            actual[ticker] = sorted(missing)

    expected = {k: sorted(v) for k, v in KNOWN_INCOMPLETE.items()}
    assert actual == expected, (
        f"seed corpus gaps changed.\n  known:  {expected}\n  actual: {actual}\n"
        f"If a gap was closed, remove it from KNOWN_INCOMPLETE. If one appeared, "
        f"the corpus regressed.")


def test_no_ticker_carries_an_alpha_vantage_error_payload():
    """AV signals failure inside a 200 body.

    A rate-limited response is a valid JSON dict with an 'Information' key, and
    it will happily sit in the corpus looking like data until something tries to
    parse statements out of it.
    """
    for ticker, payload in _corpus().items():
        for fn, blob in payload.items():
            if fn.startswith("_meta") or not isinstance(blob, dict):
                continue
            for marker in ("Error Message", "Note", "Information"):
                assert marker not in blob, (
                    f"{ticker}/{fn} is an AV error response, not data: "
                    f"{str(blob.get(marker))[:120]}")


def test_every_present_statement_survives_the_corruption_check():
    """Use the same predicate the fetch layer uses, so they cannot disagree."""
    for ticker, payload in _corpus().items():
        for fn in FUNCTIONS:
            if fn not in payload:
                continue
            assert not is_data_corrupt(fn, payload[fn]), (
                f"{ticker}/{fn} fails is_data_corrupt — it would be refetched "
                f"on every call, and in seed mode that raises")


def test_statements_carry_enough_history_for_the_engine():
    """Below 12 quarters the engine returns `insufficient` and scans nothing.

    Worth asserting on the corpus rather than only in the engine: a truncated
    fixture would turn every golden test into a vacuous pass.
    """
    for ticker, payload in _corpus().items():
        for fn in ("INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"):
            if fn not in payload:
                continue
            n = len(payload[fn].get("quarterlyReports", []))
            assert n >= 20, f"{ticker}/{fn}: only {n} quarterly reports"


def test_price_history_spans_the_statement_history():
    """Q6 compares price action against fundamentals; it needs both."""
    for ticker, payload in _corpus().items():
        ts = payload.get("TIME_SERIES_MONTHLY_ADJUSTED", {})
        series = (ts.get("Monthly Adjusted Time Series")
                  or ts.get("Monthly Time Series") or {})
        assert len(series) >= 60, (
            f"{ticker}: {len(series)} monthly prices, need 60 for the "
            f"market-disagreement window")


def test_overview_carries_the_fields_classification_depends_on():
    """No sector/industry means `classify` returns 'generic' and the wrong
    checks run — silently, because 'generic' is a legitimate value."""
    for ticker, payload in _corpus().items():
        ov = payload.get("OVERVIEW", {})
        assert ov.get("Symbol"), f"{ticker}: OVERVIEW has no Symbol"
        assert ov.get("Sector"), f"{ticker}: no Sector — classify would guess"
        assert ov.get("Industry"), f"{ticker}: no Industry"
        assert ov.get("Name"), f"{ticker}: no Name for the panel header"
