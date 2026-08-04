#!/usr/bin/env python3
"""Run a scan from the terminal. No MCP, no Claude Desktop, no panel.

Exists because the data layer and engine are finished well before anything
renders them, and because when a panel eventually shows something surprising
the first question is whether the surprise came from the engine or the view.
This answers that without a host in the loop.

    venv/bin/python mcp_apps/scan_cli.py GOOGL
    venv/bin/python mcp_apps/scan_cli.py --all
    venv/bin/python mcp_apps/scan_cli.py GOOGL --json   # what phase 4 will return

Seed mode by default, so it never spends an API call. Pass --live to allow
network fetches for tickers outside the corpus.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SEED = ["AAPL", "AMZN", "COST", "GOOGL", "NEE", "PG", "UNH", "WMT"]


def scan_one(ticker: str) -> dict:
    from mcp_apps.data import adapters
    from mcp_apps.engine import scan, severity_of, strength_of

    result = scan(adapters.load_company(ticker))
    c = result["company"]

    out = {
        "ticker": c.ticker,
        "name": c.name,
        "sector": c.sector,
        "industry": c.industry,
        "businessModel": c.business_model,
        "quarters": len(c.quarters),
        "checksRun": result.get("total_checks", 0),
        "declined": bool(result.get("declined")),
        "insufficient": bool(result.get("insufficient")),
        "findings": [
            {
                "id": cl["id"],
                "headline": cl["headline"],
                "direction": cl["direction"],
                "score": round(cl["score"], 3),
                "signal": strength_of(cl["score"]),
                "severity": severity_of(cl["score"]),
                "checks": [m.check_id for m in cl["members"]],
                "detail": [m.detail for m in cl["members"]],
                "benign": sorted({b for m in cl["members"] for b in m.benign}),
                "followUp": cl["members"][0].follow_up,
            }
            for cl in result["clusters"]
        ],
        "skips": [{"question": s.question, "reason": s.reason}
                  for s in result.get("skips", [])],
    }
    return out


def render(r: dict) -> str:
    L = [f"{r['ticker']} — {r['name']}",
         f"  {r['sector']} / {r['industry']}  ·  classified `{r['businessModel']}`",
         f"  {r['quarters']} quarters, {r['checksRun']} checks ran", ""]

    if r["declined"]:
        reason = r["skips"][0]["reason"] if r["skips"] else "out of scope"
        L.append(f"  DECLINED — {reason}")
        L.append("")
        L.append("  Refusing to answer is the answer here; approximating the")
        L.append("  missing denominators would produce confident nonsense.")
        return "\n".join(L)

    if not r["findings"]:
        L.append(f"  Nothing unusual. {r['checksRun']} checks ran and none cleared")
        L.append("  the significance floor. That is a result, not an empty state.")
        return "\n".join(L)

    for f in r["findings"]:
        L.append(f"  [{f['direction'].upper()}] {f['headline']}")
        L.append(f"      signal {f['signal']}/10 ({f['severity']})  ·  "
                 f"checks: {', '.join(f['checks'])}")
        for d in f["detail"]:
            L.append(f"      - {d}")
        if f["benign"]:
            L.append("      rule out first:")
            for b in f["benign"]:
                L.append(f"        · {b}")
        L.append(f"      follow up: {f['followUp']}")
        L.append("")

    if r["skips"]:
        L.append("  Checks not run:")
        for s in r["skips"]:
            L.append(f"    · {s['question']} — {s['reason']}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tickers", nargs="*", help="ticker symbols")
    ap.add_argument("--all", action="store_true", help="every seeded ticker")
    ap.add_argument("--json", action="store_true",
                    help="emit the dict phase 4's tool will return")
    ap.add_argument("--live", action="store_true",
                    help="allow network fetches (spends AlphaVantage quota)")
    args = ap.parse_args()

    if not args.live:
        os.environ["FINK_DATA_MODE"] = "seed"

    tickers = SEED if args.all else [t.upper() for t in args.tickers]
    if not tickers:
        ap.error("give a ticker or --all")

    # The live quote appended by the chart pipeline never reaches the engine,
    # but silence the lookup anyway so an offline run is not slowed by a DNS
    # timeout per ticker.
    if not args.live:
        from mcp_apps.data import prices
        prices.get_latest_yahoo_price = lambda _t: None

    from mcp_apps.data.adapters import TickerUnavailable

    results, failed = [], False
    for t in tickers:
        try:
            results.append(scan_one(t))
        except TickerUnavailable as e:
            failed = True
            print(f"{t}: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(results if len(results) != 1 else results[0], indent=2))
    else:
        for r in results:
            print(render(r))
            print("-" * 72)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
