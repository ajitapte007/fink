# Fink Data Module

Fetching, caching, and serving financial data.

## Architecture

```
User query → Chat model (Open WebUI)
                ├── visualize_native (native tool)
                │       └── HTTP POST → visualize_html (MCP tool)
                │                           └── cache_ticker_data(ticker)
                └── compute_metrics_native
                        └── HTTP POST → compute_metrics (MCP tool)
                                            └── cache_ticker_data(ticker)

cache_ticker_data(ticker)
    ├── Per-ticker mutex
    ├── Check SQLite cache for all 5 AlphaVantage functions
    │   ├── Complete? → return immediately
    │   └── Any missing? → _fetch_av(ticker)
    └── Return { raw_cache, error }
```

A missing entry for *any* function triggers a refetch of the whole set rather than a
partial return, so downstream alignment always sees a consistent snapshot.

## Key Files

| File | Purpose |
|---|---|
| `cache_orchestrator.py` | `cache_ticker_data()` — single entry point, per-ticker `threading.Lock` |
| `alphavantage_tool.py` | Fetches the 5 AV functions, shapes errors and corruption metadata |
| `fetch_utils.py` | SQLite cache I/O, AV API calls, TTL derivation, `FINK_DATA_MODE` |
| `process_utils.py` | Alignment, TTM, interpolation, smoothing, corporate identity |
| `models.py` | Pydantic `ChartDataPoint` |
| `local_av_cache/` | Seed corpus — AAPL, AMZN, NEE, PG, UNH |

AlphaVantage functions: `OVERVIEW`, `TIME_SERIES_MONTHLY_ADJUSTED`, `INCOME_STATEMENT`,
`BALANCE_SHEET`, `CASH_FLOW`.

## Data Modes

`FINK_DATA_MODE` decides where data may come from:

| Mode | Order | Set by |
|---|---|---|
| `live` (default) | SQLite → AlphaVantage network | `docker-compose.yml` |
| `seed` | SQLite → `local_av_cache/` → `OfflineDataUnavailable` | `tests/conftest.py` |

In `live`, `_fetch_av()` passes `mock_data=False`, so production serves real API data
rather than shadowing the five seeded tickers with fixtures. In `seed` it passes `True`
and the network path raises, keeping the suite offline and deterministic.

> `mock_data=True` alone never guaranteed offline behavior — it only *prefers* the seed
> corpus and falls through to the live API for any ticker it doesn't have. That is why
> the unit suite was making real AlphaVantage calls and varying 6x in runtime.

## Cache Schema

```sql
CREATE TABLE av_cache (
    symbol TEXT,
    function TEXT,       -- 'OVERVIEW', 'INCOME_STATEMENT', ...
    data TEXT,           -- JSON blob
    timestamp REAL,      -- when cached
    expires_at REAL,     -- derived TTL
    source TEXT,         -- 'api' | 'mock'
    is_corrupt INTEGER,  -- 0 valid, 1 corrupt
    PRIMARY KEY (symbol, function)
);
```

TTLs come from `calculate_robust_ttl()`, which infers cadence from the gap between the
last two reported periods — annual statements aren't refetched daily. On a network
failure a stale entry is served and flagged `is_corrupt=1` rather than erroring out.

## Thread Safety

`cache_ticker_data()` takes a per-ticker lock so concurrent `visualize_html` and
`compute_metrics` calls for the same ticker fetch once. Different tickers proceed in
parallel without contention.

## Timeframes

`_resolve_end_year()` in `server.py` defaults an omitted `end_year` to the current year.
An explicit value is respected — a window ending in the past is legitimate.

> Historical note: the agent previously mis-resolved "last 10 years" because the seeded
> system prompt was written to `model.meta.system`, while Open WebUI reads
> `model.params.system`. Prompt updates were silently discarded. Fixed in
> `setup/seed_webui_db.py`, which now asserts the prompt reached `params.system`.
