"""Structural fingerprint of the data layer's output.

The point of this file: phase 3 relocates ~1,500 lines of code and then adds
six fields. Those are two very different kinds of change, and only the second
is allowed to alter what the layer produces. This computes a hash over every
value `get_aligned_historical_data` emits for the 33 pre-existing metrics, so
"the move changed nothing" and "the new fields changed nothing else" are both
mechanically checkable rather than matters of opinion.

The baseline is recorded from **`mcp/data`, the origin**, not from the fork.
Recording it from the fork would only prove the fork agrees with itself; taking
it from the code being copied is what makes "the copy preserved behaviour" a
real claim.

    python mcp_apps/tests/golden_hash.py --write   # record, from mcp/data
    python mcp_apps/tests/golden_hash.py           # verify, against mcp_apps/data

`test_metrics_parity.py` imports `hash_all()` and asserts against the recorded
baseline, so the guarantee outlives the migration that motivated it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent               # mcp_apps/
REPO = PKG.parent
LEGACY = REPO / "mcp"

os.environ.setdefault("FINK_DATA_MODE", "seed")

# Both directories contain a package named `data`, so an unqualified
# `import data.*` resolves by sys.path position alone. Never leave that to
# chance — every entry point here states which tree it wants.
def use_tree(which: str) -> None:
    """Point `data.*` at either the fork or the legacy tree, exclusively."""
    for p in (str(PKG), str(REPO), str(LEGACY)):
        while p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, str(PKG if which == "fork" else LEGACY))
    for mod in [m for m in sys.modules
                if m == "data" or m.startswith("data.") or m == "metrics_registry"]:
        del sys.modules[mod]


BASELINE = HERE / "golden_metrics_hash.json"

# Every ticker in the seed corpus.
ALL_TICKERS = ["AAPL", "AMZN", "COST", "CPRT", "GOOGL", "NEE", "PG", "UNH", "WMT"]

# CPRT.json is missing CASH_FLOW — see KNOWN_INCOMPLETE in
# test_seed_corpus.py. It scanned fine during POC development because that ran
# against a developer SQLite cache holding the missing statement; `*.db` is
# gitignored, so a fresh clone cannot reproduce it. Hashing CPRT here would
# make the baseline depend on a file that is not in the repo. One AV call
# (`reseed_cache.py --tickers CPRT`) puts it back, after which move it up.
TICKERS = [t for t in ALL_TICKERS if t != "CPRT"]

# The 33 keys that existed before phase 3. Frozen deliberately: adding the six
# new metrics must not perturb these, and listing them explicitly is what makes
# that assertion meaningful. A field added later will not silently join the
# hash and mask a regression.
LEGACY_KEYS = [
    "date", "price",
    "revenue", "cost_of_goods_sold", "operating_income", "net_income",
    "operating_cash_flow", "capex", "free_cash_flow", "selling_general_admin",
    "research_development", "stock_based_compensation", "share_repurchase",
    "cash_and_equivalents", "total_debt", "market_cap", "enterprise_value",
    "ebitda",
    "pe_ratio", "ps_ratio", "pfcf_ratio", "pocf_ratio", "ev_ebitda",
    "shares_outstanding", "dividends", "dividend_yield", "payout_ratio_fcf",
    "payout_ratio_ocf",
    "roic", "operating_margin", "profit_margin", "gross_margin", "roa", "roe",
]


def _canon(v):
    """Round floats before hashing.

    Without this the hash is a float-repr test, not a behaviour test: reordering
    a sum can move the last bits of a double while the number stays correct to
    any precision anyone cares about. 6 significant figures is far tighter than
    the data's real accuracy and still immune to that noise.
    """
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return str(v)
        return f"{v:.6g}"
    return v


def _suppress_live_price() -> None:
    """Stop `get_aligned_historical_data` appending today's Yahoo quote.

    That injection adds a row dated *today* to the series, so the output
    changes with the calendar and with whether the network happens to be
    reachable. Hashing it would make this a test of the weather. The engine has
    the same problem for a more serious reason — see `adapters.load_company`,
    which turns the injection off outright.

    The import is function-local in both trees, so patching the *defining*
    module is what takes effect: `data.prices` in the fork, `data.fetch_utils`
    in legacy.
    """
    import importlib
    patched = False
    for modname in ("data.prices", "data.fetch_utils"):
        try:
            mod = importlib.import_module(modname)
        except ModuleNotFoundError:
            continue
        if hasattr(mod, "get_latest_yahoo_price"):
            mod.get_latest_yahoo_price = lambda _t: None
            patched = True
    if not patched:
        raise RuntimeError("could not neutralise the live-price injection — "
                           "the hash would depend on network and calendar")


def series_for(ticker: str) -> list[dict]:
    """Aligned history for one ticker, restricted to the legacy keys."""
    from data.cache_orchestrator import cache_ticker_data

    try:
        from data.metrics import get_aligned_historical_data
    except ModuleNotFoundError:              # pre-split layout
        from data.process_utils import get_aligned_historical_data

    _suppress_live_price()
    res = cache_ticker_data(ticker)
    if res.get("error"):
        raise RuntimeError(f"{ticker}: {res['error']}")

    out = []
    for pt in get_aligned_historical_data(res["raw_cache"]):
        d = pt.model_dump() if hasattr(pt, "model_dump") else pt.dict()
        out.append({k: _canon(d.get(k)) for k in LEGACY_KEYS})
    return out


def hash_all(tree: str = "fork") -> dict[str, str]:
    """{ticker: "rows:sha256"} over the legacy metric surface.

    Runs against a throwaway SQLite file so the shared cache is neither read
    nor written. Otherwise a stale row could make two different code paths
    agree, which is precisely the failure this is meant to catch.
    """
    use_tree(tree)
    with tempfile.TemporaryDirectory() as td:
        prev = os.environ.get("ALPHAVANTAGE_CACHE_DB")
        os.environ["ALPHAVANTAGE_CACHE_DB"] = str(Path(td) / "hash.db")
        try:
            digests = {}
            for t in TICKERS:
                rows = series_for(t)
                blob = json.dumps(rows, sort_keys=True, separators=(",", ":"))
                digests[t] = f"{len(rows)}:{hashlib.sha256(blob.encode()).hexdigest()}"
            return digests
        finally:
            if prev is None:
                os.environ.pop("ALPHAVANTAGE_CACHE_DB", None)
            else:
                os.environ["ALPHAVANTAGE_CACHE_DB"] = prev


def main() -> int:
    write = "--write" in sys.argv
    # Record from the origin; verify against the copy.
    current = hash_all("legacy" if write else "fork")

    if write:
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"wrote {BASELINE.relative_to(REPO)}")
        for t, h in sorted(current.items()):
            print(f"  {t:6} {h}")
        return 0

    if not BASELINE.exists():
        print(f"no baseline at {BASELINE} — run with --write first")
        return 2

    recorded = json.loads(BASELINE.read_text())
    bad = [t for t in TICKERS if recorded.get(t) != current.get(t)]
    for t in TICKERS:
        mark = "DIFF" if t in bad else "ok"
        print(f"  {t:6} {mark:5} {current[t]}")
        if t in bad:
            print(f"         was {recorded.get(t)}")
    print("\n" + ("FAIL — the data layer's output moved" if bad else "PASS"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
