"""What the model is told about how to read a scan.

Deterministic and hand-written. Not generated — asking a model how to narrate
before it narrates is circular, non-deterministic, and costs a round trip to
produce advice nobody reviewed.

WHY THIS EXISTS
---------------
Without it the model receives headlines, detail strings, benign explanations
and a 0-10 number, and narrates from them competently but with four specific
blind spots the payload cannot convey on its own:

  1. It reads 10/10 as "this company is in trouble". It means "this reading is
     extreme against this company's own history" — a statement about the
     distribution, not the business. GOOGL's capital_cycle scores 10/10 and the
     likeliest explanation is an AI build whose returns have not landed yet.

  2. It treats the benign explanations as boilerplate to list. They are the
     thing separating this from a short-seller newsletter, and the whole point
     is to weigh them, not recite them.

  3. It narrates a cluster's members as separate problems. Clustering exists
     precisely to stop `roic_decline` and `fcf_compression` reading as two
     things when they are one.

  4. It blends what was computed with what it knows about the company, and the
     reader cannot tell which is which. "This is the AI capex build" is model
     knowledge; "ROIC fell 1086bp" is in the payload.

The discipline below is carried over from the standalone POC's bull/bear
prompt, which had it and which the port to MCP initially lost.

WHY IT SHIPS IN THE RESULT RATHER THAN THE TOOL DESCRIPTION
-----------------------------------------------------------
A tool description sits in the model's context on every turn, whether or not
the tool is ever called. A result is paid for once, when the data it describes
is actually present. The description carries only enough to pick the right
tool; this carries the rest.
"""
from __future__ import annotations

# Applies whenever there is anything to narrate at all.
_ALWAYS = [
    "Every number you state must come from this payload. Anything you add from "
    "your own knowledge of the company — a product cycle, an acquisition, a "
    "macro event — must be marked `[from my knowledge — verify]` so the reader "
    "can tell computed fact from recollection.",

    "Do not give a buy or sell recommendation, a price target, or a view on "
    "whether the stock is cheap. The reader is deciding; you are helping them "
    "see what is there.",
]

_WITH_CLUSTERS = [
    "**A cluster is one story, not several problems.** Its `checks` list names "
    "the checks that agreed. Narrate the mechanism they share — "
    "`roic_decline` + `fcf_compression` is capital going in faster than "
    "returns are coming out, which is a single thing happening — rather than "
    "listing them separately.",

    "**`signal` is evidence strength, not severity.** It measures how extreme "
    "the reading is against this company's own trailing history. A 10/10 says "
    "the movement is unusual for this company; it says nothing about whether "
    "the cause is benign. Do not translate a high signal into alarm.",

    "**Weigh the `benign` explanations, do not recite them.** For each cluster, "
    "say which reading you find more likely — the innocent one or the "
    "concerning one — and why, given what you know about this company and "
    "period. An analyst who lists both and commits to neither has not helped.",

    "Say whether the movement looks company-specific or industry-wide in this "
    "period. A margin compression every competitor also saw is a different "
    "fact from one only this company saw, and the scan cannot tell them apart.",

    "End with **the crux**: the single variable this decision reduces to, "
    "stated as a falsifiable claim with a threshold and a time window. "
    "\"If FCF margin is not back above 15% within four quarters, the "
    "capacity-build reading is wrong.\" Not \"watch cash flow closely\".",
]

_CLEAN = [
    "The checks ran and found nothing. Say so plainly, name how many ran, and "
    "resist manufacturing concern from the skips or from your own knowledge of "
    "the company — a clean scan is a result, and reporting it as one is what "
    "makes a flagged scan worth believing.",

    "You may add context from your own knowledge, marked "
    "`[from my knowledge — verify]`, but be clear it is not something the scan "
    "found.",
]

_DECLINED = [
    "The scan was declined, not passed. This company's business model needs "
    "denominators Alpha Vantage's normalized schema does not carry — premium "
    "revenue, claims reserves, net interest margin. Explain that, and do not "
    "substitute a general impression of the company for the analysis that did "
    "not run.",

    "Do not present this as a clean bill of health. Nothing was checked.",
]

_INSUFFICIENT = [
    "There was not enough history to check anything — fewer than 12 usable "
    "quarters. Say so; do not scan what little there is by eye and report the "
    "result as if the engine had produced it.",
]

_SKIPS = (
    "Some checks did not run and say why in `skips`. Mention them if the "
    "reader would otherwise assume coverage — a working-capital check skipped "
    "because inventory is 1% of assets is worth a clause, not a paragraph."
)


def guidance_for(payload: dict) -> dict:
    """Instructions matched to what this particular scan produced.

    One static blob would tell the model to weigh benign explanations on a
    scan that has none, and to avoid manufacturing concern on one that found
    six real things. The situations need different advice.
    """
    if payload.get("error"):
        return {}

    if payload.get("declined"):
        rules = _DECLINED
    elif payload.get("insufficient"):
        rules = _INSUFFICIENT
    elif payload.get("clusters"):
        rules = _WITH_CLUSTERS
    else:
        rules = _CLEAN

    out = list(rules) + _ALWAYS
    if payload.get("skips") and not payload.get("declined"):
        out.insert(len(rules), _SKIPS)

    return {
        "howToRead": (
            "This is a deterministic scan, not an opinion. Thresholds are "
            "relative to the company's own trailing 20 quarters, never "
            "absolute. Each entry in `clusters` is one or more correlated "
            "checks that agreed."
        ),
        "writingTheNarrative": out,
    }
