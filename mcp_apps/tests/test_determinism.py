"""Identical inputs must produce identical output, run to run.

Not a theoretical concern. `clustering.CLUSTERS` maps a cluster id to a Python
*set* of check ids, and the code that picked a cluster's representative member
iterated that set unsorted. Under PYTHONHASHSEED variation GOOGL's follow-up
question flipped between `roic_decline` (score 6.3) and `fcf_compression`
(2.5) — a different question about a different metric, from the same data.

The panel shows `members[0]`'s follow-up, so this was user-visible. It is the
kind of bug that never reproduces in a single-process test run, which is why
this one spawns subprocesses with different seeds.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Runs in a fresh interpreter so PYTHONHASHSEED actually takes effect — setting
# it in-process after startup does nothing.
PROBE = """
import json, os, sys
sys.path.insert(0, %r)
from mcp_apps.data import adapters, prices
prices.get_latest_yahoo_price = lambda _t: None
from mcp_apps.engine import scan

out = {}
for t in ["AAPL", "AMZN", "GOOGL", "NEE"]:
    r = scan(adapters.load_company(t))
    out[t] = [
        {
            "id": c["id"],
            "score": round(c["score"], 6),
            "direction": c["direction"],
            "headline": c["headline"],
            "follow_up": c["members"][0].follow_up,
            "members": [m.check_id for m in c["members"]],
        }
        for c in r["clusters"]
    ]
sys.stdout.write("<<<" + json.dumps(out, sort_keys=True) + ">>>")
""" % str(REPO_ROOT)


def _run_with_seed(seed: str, tmp_db: Path) -> dict:
    env = {
        "PYTHONHASHSEED": seed,
        "FINK_DATA_MODE": "seed",
        "ALPHAVANTAGE_CACHE_DB": str(tmp_db),
        "PATH": "/usr/bin:/bin",
    }
    for passthrough in ("PYTHONPATH", "VIRTUAL_ENV", "HOME"):
        import os
        if os.environ.get(passthrough):
            env[passthrough] = os.environ[passthrough]

    proc = subprocess.run([sys.executable, "-c", PROBE], capture_output=True,
                          text=True, env=env, cwd=str(REPO_ROOT), timeout=600)
    assert proc.returncode == 0, f"seed {seed} failed:\n{proc.stderr[-3000:]}"
    body = proc.stdout.split("<<<")[1].split(">>>")[0]
    return json.loads(body)


@pytest.mark.slow
def test_scan_output_is_identical_across_hash_seeds(tmp_path):
    runs = {s: _run_with_seed(s, tmp_path / f"c{s}.db") for s in ("0", "1", "42")}

    first_seed, first = next(iter(runs.items()))
    for seed, result in runs.items():
        if seed == first_seed:
            continue
        assert result == first, (
            f"PYTHONHASHSEED={seed} produced different output from "
            f"{first_seed}. Something iterates a set or dict without sorting — "
            f"check clustering.cluster() and anything reading CLUSTERS.")


@pytest.mark.slow
def test_the_representative_member_is_stable(tmp_path):
    """The specific regression: which finding speaks for a cluster.

    Asserted separately from full equality because this is the field a user
    actually reads, and a failure here should say so rather than pointing at a
    large diff.
    """
    runs = [_run_with_seed(s, tmp_path / f"m{s}.db") for s in ("0", "7", "12345")]
    for ticker in runs[0]:
        questions = {json.dumps([c["follow_up"] for c in run[ticker]])
                     for run in runs}
        assert len(questions) == 1, (
            f"{ticker}: follow-up question depends on hash seed — {questions}")


def test_repeated_scans_in_one_process_agree(companies):
    """Cheap in-process check: no mutation of Company between scans.

    The engine takes a Company and should not modify it. If a check appended to
    `notes` or normalised a series in place, the second scan would differ.
    """
    from mcp_apps.engine import scan

    for ticker, c in companies.items():
        a = [(x["id"], x["score"]) for x in scan(c)["clusters"]]
        b = [(x["id"], x["score"]) for x in scan(c)["clusters"]]
        assert a == b, f"{ticker}: scan is not idempotent — it mutates Company"
