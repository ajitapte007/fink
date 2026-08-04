"""Guidance is what turns a payload into a narrative worth reading.

Everything here is deterministic — no model in the loop, no generation. The
tests care about two things: that the advice matches the situation (telling a
clean scan to weigh benign explanations it does not have is noise that trains
the reader to skip guidance), and that the four specific corrections survive,
since each exists because the model gets that thing wrong without being told.
"""
from __future__ import annotations

import json

import pytest

from mcp_apps.narrative import guidance_for
from mcp_apps.scan_cli import scan_one


def _rules(payload) -> str:
    return " ".join(guidance_for(payload)["writingTheNarrative"])


# ------------------------------------------------------- situational matching
def test_a_scan_with_clusters_gets_the_full_discipline():
    r = scan_one("GOOGL")
    assert r["clusters"], "GOOGL should produce clusters"
    text = _rules(r)
    assert "one story, not several problems" in text
    assert "evidence strength, not severity" in text
    assert "Weigh the `benign` explanations" in text
    assert "the crux" in text


def test_a_clean_scan_is_told_not_to_manufacture_concern():
    """The failure mode for a clean result is inventing worry from the skips
    or from what the model happens to know about the company. A clean scan
    reported as clean is what makes a flagged scan worth believing."""
    r = scan_one("COST")
    assert not r["clusters"]
    text = _rules(r)
    assert "resist manufacturing concern" in text
    assert "Weigh the `benign`" not in text, "advice about findings it does not have"
    assert "the crux" not in text, "there is nothing to reduce to a crux"


def test_a_declined_scan_is_told_it_is_not_a_clean_bill():
    """The most dangerous confusion in the product. UNH returns zero clusters
    because nothing was checked, and zero clusters is what a healthy company
    also returns."""
    r = scan_one("UNH")
    assert r["declined"]
    text = _rules(r)
    assert "Do not present this as a clean bill of health" in text
    assert "Nothing was checked" in text
    assert "resist manufacturing concern" not in text, "wrong situation's advice"


def test_insufficient_history_gets_its_own_advice():
    fake = {"clusters": [], "insufficient": True, "skips": []}
    text = _rules(fake)
    assert "not enough history" in text
    assert "do not scan what little there is by eye" in text


def test_an_error_payload_gets_no_guidance():
    """Nothing was produced, so there is nothing to narrate. Instructions here
    would be advice about data that does not exist."""
    assert guidance_for({"ticker": "X", "error": "unavailable", "clusters": []}) == {}


def test_skip_advice_appears_only_when_there_are_skips():
    with_skips = {"clusters": [], "skips": [{"question": "Q3.dio", "reason": "x"}]}
    without = {"clusters": [], "skips": []}
    assert "did not run" in _rules(with_skips)
    assert "did not run" not in _rules(without)


# --------------------------------------------- the four corrections that matter
def test_signal_is_explained_as_evidence_strength_not_severity():
    """Without this the model reads 10/10 as "this company is in trouble".
    It means the reading is extreme against the company's own history —
    a statement about a distribution, not a business."""
    text = _rules(scan_one("GOOGL"))
    assert "how extreme the reading is" in text
    assert "says nothing about whether the cause is benign" in text


def test_model_knowledge_must_be_marked():
    """"This is the AI capex build" is recollection; "ROIC fell 1086bp" is in
    the payload. A reader cannot tell them apart unless the model says so."""
    for ticker in ("GOOGL", "COST", "UNH"):
        assert "[from my knowledge — verify]" in _rules(scan_one(ticker))


def test_no_investment_advice_in_every_situation():
    for ticker in ("GOOGL", "COST", "UNH"):
        text = _rules(scan_one(ticker))
        assert "Do not give a buy or sell recommendation" in text
        assert "price target" in text


def test_clusters_are_explained_as_one_story():
    """Clustering exists to stop roic_decline and fcf_compression reading as
    two problems. Guidance that does not say so wastes the clustering."""
    text = _rules(scan_one("GOOGL"))
    assert "roic_decline" in text and "fcf_compression" in text


def test_the_crux_demands_a_threshold_and_a_window():
    """"Watch cash flow closely" is not a falsifiable claim, and the difference
    is the whole point of asking for one."""
    text = _rules(scan_one("GOOGL"))
    assert "falsifiable" in text and "threshold" in text and "time window" in text


# ------------------------------------------------------------------- mechanics
def test_guidance_ships_in_the_scan_payload():
    assert scan_one("GOOGL")["guidance"]["writingTheNarrative"]
    assert scan_one("GOOGL")["guidance"]["howToRead"]


def test_guidance_is_small_enough_to_be_worth_sending():
    """It rides in the result, which is paid for once per call rather than on
    every turn like a tool description. It should still be cheap."""
    assert len(json.dumps(scan_one("GOOGL")["guidance"])) < 4000


def test_guidance_is_deterministic():
    """Hand-written constants, not generated. Two calls must be identical, or
    the narrative advice becomes another thing that varies run to run."""
    a, b = scan_one("GOOGL")["guidance"], scan_one("GOOGL")["guidance"]
    assert a == b


def test_guidance_is_json_serialisable():
    json.loads(json.dumps(scan_one("AMZN")["guidance"]))


def test_guidance_does_not_reach_the_panel_as_a_rendered_field():
    """It is for the model. The view rendering it would repeat instructions
    at the user, who did not ask for them.

    Reads server.py as text rather than importing it. Importing needs fastmcp
    stubbed, which another test module happens to do — so this passed in a
    full run and failed when run alone. An order-dependent test is worse than
    no test: it reports on whatever ran before it.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text()

    # Only the view constants. A slice running to `def selftest` also swept in
    # the tool docstrings, one of which *explains* that guidance is excluded --
    # so the test matched prose about the rule instead of a violation of it.
    view = src[src.index("SCAN_BODY = "):src.index("mcp = FastMCP(")]
    assert "guidance" not in view, (
        "the scan view references guidance — it is for the model, not the panel")
