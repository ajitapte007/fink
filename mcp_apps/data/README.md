# mcp_apps/data

Fetching, caching and shaping financial data for the MCP Apps server.

Forked from `mcp/data` on 2026-08-03 (phase 3). See **Migration policy** below
before changing either copy.

## Layout

```
config.py            FINK_DATA_MODE, log_info, OfflineDataUnavailable
cache.py             SQLite read-through cache — source-agnostic
prices.py            live quote lookup (Yahoo) — best effort, never raises
alphavantage/
    fetch.py         AV client, its five endpoints, offline-first read-through
    local_av_cache/  recorded AV responses, one JSON file per ticker
    reseed_cache.py  repairs and extends the corpus
metrics.py           composite metrics aligned to the monthly price series
identity.py          display strings for panel headers
models.py            pydantic schemas (ChartDataPoint, CorporateIdentity)
metrics_registry.py  single source of truth for metric ids, labels, colours
cache_orchestrator.py  cache_ticker_data() — per-ticker mutex, fetch on miss
adapters.py          the only coupling point to mcp_apps.engine
```

**Import direction is one-way.** `alphavantage/` imports `cache` and `config`;
nothing above imports back down into it except `cache_orchestrator` and
`adapters`. `test_data_paths.py::test_import_direction_is_one_way` enforces
this. When SEC EDGAR arrives it gets an `edgar/` sibling and reuses `cache.py`
and `config.py` unchanged — that is what the split bought.

## Two paths through this module, and why they differ

| | Chart | Engine |
|---|---|---|
| Entry point | `adapters.load_series` | `adapters.load_company` |
| Via | `metrics.get_aligned_historical_data` | AV `quarterlyReports` directly |
| Period | monthly, interpolated onto prices | fiscal quarters |
| Rows per ticker | ~320 | ~81 |
| Live quote appended | yes | **no** |

Reusing the chart pipeline for the engine is the most tempting mistake
available here, and it fails silently. The engine computes trailing-twelve-month
figures as `sum(series[i-3:i+1])` — four consecutive *quarters*. Fed monthly
rows, every TTM number becomes a four-month sum of carried-forward values:
roughly a third of the truth, with no gap, no `None`, and nothing raised.
`test_adapters.py::test_load_company_yields_fiscal_quarters_not_months` pins it.

The live quote matters for the same reason. `get_aligned_historical_data`
appends a row dated today carrying a Yahoo price, which is right for a chart and
wrong for a scan: a finding that moves because a quote moved is not a finding,
and no golden test could be stable.

## Cache resolution

`cache.get_db_path()` resolves two ways:

1. `$ALPHAVANTAGE_CACHE_DB`, if set — tests, deployment, or deliberately
   sharing one file with the legacy server
2. next to `cache.py`

**This package owns its own database.** `mcp/` has its own and the two are
independent, which is what lets `mcp_apps` be packaged (uvx, a container)
without depending on a path outside itself. Sharing is still available — point
both at the same `ALPHAVANTAGE_CACHE_DB` — but it is an explicit choice rather
than something path resolution arranges behind your back.

The cost of not sharing is bounded: a ticker outside the nine-ticker seed corpus
costs five AV calls, and only gets spent twice if you scan it here *and* chart
it in Open WebUI on the same day.

The legacy version had a third rule between these two: probe
`/app/backend/data/` and use it if writable. That path exists only inside the
Open WebUI container, and this server never runs there — it is launched over
stdio by the MCP host. So the probe could never succeed, and because
`get_db_cache` and `set_db_cache` each resolve the path afresh (12 times to
load one ticker) every call ran a `mkdir` and an sqlite `connect` against an
impossible directory before falling through.

The env var is read at call time, not import time. It used to be a module-level
constant, which froze it to whatever was set when the first importer ran — a
fixture setting it afterwards got the stale path and quietly used the
developer's real cache.

## Seed corpus

`alphavantage/local_av_cache/` holds recorded AV responses for nine tickers:
AAPL AMZN COST CPRT GOOGL NEE PG UNH WMT. `FINK_DATA_MODE=seed` serves only
from here and raises rather than reaching the network, which is what keeps the
suite offline and deterministic.

**Ownership moved here in phase 3.** `mcp/data/local_av_cache/` is frozen at its
current contents; this is the copy that gets repaired and extended:

```
export ALPHAVANTAGE_API_KEY=...
python -m mcp_apps.data.alphavantage.reseed_cache                # dry run
python -m mcp_apps.data.alphavantage.reseed_cache --apply --budget 6
```

**Known gap: CPRT is missing `CASH_FLOW`.** It scanned fine during POC
development because the developer's SQLite cache held the missing statement —
`*.db` is gitignored, so a fresh clone cannot reproduce it. One AV call closes
it. `test_seed_corpus.py::KNOWN_INCOMPLETE` asserts the gap set exactly, so
closing it will fail that test and tell you to update the constant.

## Migration policy

**Direction of travel.** `mcp_apps/data` is the future of this code. It was
forked from `mcp/data` on 2026-08-03. `mcp/data` is legacy: it exists to keep
the Open WebUI server running and receives **security and correctness fixes
only**. All feature work happens here.

**One-way door.** Fixes flow legacy → fork, never fork → legacy. If a bug exists
in both, fix this copy first and port back only if Open WebUI is actually
affected. Nothing is backported for symmetry.

**Exit condition.** `mcp/` is deleted when both are true:

1. `mcp_apps` ships the chart view at parity with `mcp/visualization`
   (phase 7–8), and
2. no one is running the Open WebUI container.

At that point `mcp/` has no unique asset left — it is self-contained and nothing
outside it imports it (verified 2026-08-03).

**If the exit condition is not met by the end of phase 8**, stop treating this
as temporary and convert to a permanent freeze.

**Precedent.** This is the second fork of this code. The first —
`open_webui/alphavantage` → `mcp/data`, commit `40fec91` — had no stated policy
and drifted 243 lines in `fetch_utils.py` without anyone choosing to. It cost
nothing only because the ancestor was abandoned. Do not rely on that twice.

## What changed in the fork

Behaviour-preserving, verified by `test_metrics_parity.py` against a hash
recorded from `mcp/data` before anything moved:

- `fetch_utils.py` split four ways (`alphavantage/fetch.py`, `cache.py`,
  `config.py`, `prices.py`)
- `process_utils.py` → `metrics.py` + `identity.py`
- `alphavantage_tool.py` folded into `cache_orchestrator._fetch_and_check`.
  It was never an MCP tool; nothing registered it, and its only caller read two
  of the ten keys it returned.
- `available_seed_tickers` now reads `CACHE_DIR` instead of rebuilding the path
  inline — the same location was written twice
- `smooth_series` iterates the model's fields instead of naming all 33 by hand

Behaviour-changing, deliberately:

- **Six new metrics** — `total_assets`, `current_liabilities`, `receivables`,
  `inventory`, `payables`, `depreciation_amortization`. These serve the *chart*,
  so "chase the finding" can show the evidence behind a working-capital or
  capital-intensity flag. The engine reads none of them; it builds its own
  quarterly series through `adapters.load_company`.
- **`depreciationDepletionAndAmortization` added to `merge_reports.keys_to_sum`.**
  `capitalExpenditures` was already there, so every capex/D&A comparison put a
  trailing-twelve-month numerator over a single-quarter denominator and came out
  ~4x too high — AAPL read 3.59 where the true ratio is 0.91. Nothing raised.
