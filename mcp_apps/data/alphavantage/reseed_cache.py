#!/usr/bin/env python3
"""Repair the local_av_cache seed corpus.

Nothing else in the tree writes to `local_av_cache/` — it is hand-maintained —
so functions that failed at seed time stay broken forever, and every consumer
silently degrades. AMZN and PG are currently missing CASH_FLOW; AAPL is missing
four of five.

Refetches only the functions that are absent or that `is_data_corrupt` rejects.
Good entries are never touched, so this costs the minimum number of API calls.

    export ALPHAVANTAGE_API_KEY=...
    python -m mcp_apps.data.alphavantage.reseed_cache                # dry run
    python -m mcp_apps.data.alphavantage.reseed_cache --apply
    python -m mcp_apps.data.alphavantage.reseed_cache --apply --budget 6

Ownership moved here in phase 3. `mcp/data/local_av_cache/` is frozen at its
current contents; this corpus is the one that gets repaired and extended.

Free tier is 25 calls/day. The dry run tells you the cost before you spend it.
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

# Run as a module (`python -m mcp_apps.data.alphavantage.reseed_cache`) so the
# relative imports resolve. Running it as a bare file path cannot work: the
# package it belongs to would never be imported.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mcp_apps.data.alphavantage.fetch import (  # noqa: E402
    CACHE_DIR, FUNCTIONS, fetch_data, is_data_corrupt)


def audit(path: Path) -> tuple[dict, list[str]]:
    """Return (payloads, function names needing a refetch)."""
    blob = json.loads(path.read_text()) if path.exists() else {}
    broken = []
    for fn in FUNCTIONS:
        payload = blob.get(fn)
        if payload is None or is_data_corrupt(fn, payload):
            broken.append(fn)
    return blob, broken


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tickers", nargs="*",
                    help="default: every ticker already in local_av_cache")
    ap.add_argument("--apply", action="store_true",
                    help="actually fetch; without this it is a dry run")
    ap.add_argument("--budget", type=int, default=25,
                    help="max API calls to spend (default 25, the free-tier day)")
    args = ap.parse_args()

    tickers = [t.upper() for t in args.tickers] or sorted(
        p.stem.upper() for p in CACHE_DIR.glob("*.json"))
    if not tickers:
        print(f"no seed files in {CACHE_DIR}", file=sys.stderr)
        return 1

    plan: list[tuple[str, list[str]]] = []
    for t in tickers:
        _, broken = audit(CACHE_DIR / f"{t}.json")
        plan.append((t, broken))
        status = ", ".join(broken) if broken else "complete"
        print(f"{t:6} {len(FUNCTIONS) - len(broken)}/{len(FUNCTIONS)} good"
              f"   {status}")

    total = sum(len(b) for _, b in plan)
    print(f"\n{total} API calls needed")

    if not args.apply:
        print("dry run — nothing fetched. Re-run with --apply.")
        return 0
    if total == 0:
        print("nothing to do")
        return 0
    if total > args.budget:
        print(f"\n{total} calls needed but budget is {args.budget} — will fetch "
              f"what fits and stop. Re-run tomorrow to continue.\n")

    spent, failed = 0, []
    for ticker, broken in plan:
        if not broken:
            continue
        if spent >= args.budget:
            break
        path = CACHE_DIR / f"{ticker}.json"
        blob, _ = audit(path)

        # OVERVIEW first, and abandon the ticker if it fails. A typo'd symbol
        # would otherwise burn five calls returning five errors — a fifth of a
        # free-tier day for nothing.
        ordered = (["OVERVIEW"] if "OVERVIEW" in broken else []) + \
                  [f for f in broken if f != "OVERVIEW"]

        for fn in ordered:
            if spent >= args.budget:
                break
            try:
                data = fetch_data(fn, ticker)
                spent += 1
            except Exception as e:            # noqa: BLE001 — report and continue
                print(f"  {ticker}/{fn} FAILED: {e}", file=sys.stderr)
                failed.append(f"{ticker}/{fn}")
                if "Rate Limit" in str(e):
                    print("rate limit hit — stopping", file=sys.stderr)
                    _write(path, blob)
                    return 1
                if fn == "OVERVIEW":
                    print(f"  {ticker}: OVERVIEW failed, skipping remaining "
                          f"{len(ordered) - 1} calls — check the symbol",
                          file=sys.stderr)
                    break
                continue

            if is_data_corrupt(fn, data):
                print(f"  {ticker}/{fn} returned corrupt data, not written",
                      file=sys.stderr)
                failed.append(f"{ticker}/{fn}")
                continue

            blob[fn] = data
            print(f"  {ticker}/{fn} ok")

        blob["_meta_last_refreshed"] = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S")
        _write(path, blob)

    print(f"\nspent {spent} API calls")
    remaining = total - spent - len(failed)
    if remaining > 0:
        print(f"{remaining} calls still outstanding — re-run to continue")
    if failed:
        print(f"still broken: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def _write(path: Path, blob: dict) -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(".json.bak"))
    path.write_text(json.dumps(blob, indent=1))


if __name__ == "__main__":
    raise SystemExit(main())
