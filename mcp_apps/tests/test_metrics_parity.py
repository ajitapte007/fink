"""The fork must not have changed what the data layer produces.

`golden_metrics_hash.json` was recorded from `mcp/data` — the code being
copied — before a line of it was moved. Everything phase 3 did to the fork
(four-way split of fetch_utils, process_utils -> metrics + identity, six new
fields, the smooth_series rewrite) has to leave those 33 values untouched.

This outlives the migration. Once `mcp/` is retired the baseline stops being
"what the old code did" and becomes "what this code has always done", which is
the more useful guarantee anyway.
"""
from __future__ import annotations

import json

import pytest

from .golden_hash import BASELINE, LEGACY_KEYS, TICKERS, hash_all


@pytest.fixture(scope="module")
def digests():
    return hash_all("fork")


def test_baseline_exists_and_covers_every_ticker():
    assert BASELINE.exists(), (
        "no recorded baseline — run `python mcp_apps/tests/golden_hash.py "
        "--write` against mcp/data before trusting this suite")
    recorded = json.loads(BASELINE.read_text())
    assert set(recorded) == set(TICKERS)


@pytest.mark.slow
@pytest.mark.parametrize("ticker", TICKERS)
def test_legacy_metrics_are_unchanged(ticker, digests):
    """Every one of the 33 pre-existing metrics, on every date, per ticker.

    Parametrised rather than looped so a failure names the company instead of
    stopping at the first one — when this breaks, which ticker moved is the
    first diagnostic question.
    """
    recorded = json.loads(BASELINE.read_text())
    assert digests[ticker] == recorded[ticker], (
        f"{ticker}: the data layer's output moved. The fork was supposed to be "
        f"behaviour-preserving for these {len(LEGACY_KEYS)} keys — diff "
        f"get_aligned_historical_data against mcp/data/process_utils.py")


def test_the_hash_would_actually_catch_a_regression(monkeypatch):
    """Guard the guard.

    A hash test that passes because it hashes nothing is worse than no test.
    Perturb one value and confirm the digest moves — otherwise a silently empty
    series would sail through every assertion above.
    """
    from . import golden_hash

    baseline = golden_hash.hash_all("fork")

    real = golden_hash.series_for

    def perturbed(ticker):
        rows = real(ticker)
        if rows:
            rows[0] = dict(rows[0])
            rows[0]["revenue"] = "9.99e99"
        return rows

    monkeypatch.setattr(golden_hash, "series_for", perturbed)
    assert golden_hash.hash_all("fork") != baseline, (
        "changing a metric value did not change the hash — this test proves "
        "nothing")


def test_legacy_key_list_matches_the_model_minus_the_new_fields():
    """The frozen key list must stay honest.

    LEGACY_KEYS is hardcoded so that fields added later do not silently join the
    hash and mask a regression in the originals. The flip side is that it can
    drift out of sync with the model, so pin the relationship explicitly.
    """
    from mcp_apps.data.models import ChartDataPoint

    spec = getattr(ChartDataPoint, "__fields_spec__", None)
    fields = set(spec) if spec else set(ChartDataPoint.model_fields)

    new_in_phase3 = {"total_assets", "current_liabilities", "receivables",
                     "inventory", "payables", "depreciation_amortization"}
    assert set(LEGACY_KEYS) == fields - new_in_phase3
    assert new_in_phase3 <= fields
