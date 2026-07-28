# Fink Data Module

## Architecture

The data module handles fetching, caching, and serving financial data for Fink.

```
User query → Chat Model (GPT-5.4-mini)
                ├── visualize_native (Open WebUI native tool)
                │       └── HTTP POST → visualize_html (MCP tool)
                │                           └── cache_ticker_data(ticker)
                └── compute_metrics (MCP tool via MCP connection)
                            └── cache_ticker_data(ticker)

cache_ticker_data(ticker)
    ├── Per-ticker mutex lock
    ├── Check SQLite cache completeness
    │   ├── All cached? → fast return
    │   └── Missing? → ThreadPoolExecutor(max_workers=2)
    │       ├── _fetch_av(ticker)           → AlphaVantage API × 5 functions
    │       └── _fetch_revenue_segments()   → OpenAI + web_search grounding
    └── Return { raw_cache, revenue_segment_data, error }
```

## Key Files

| File | Purpose |
|---|---|
| `cache_orchestrator.py` | Central entry point — `cache_ticker_data()` with per-ticker mutex |
| `alphavantage_tool.py` | Fetches 5 AlphaVantage functions (OVERVIEW, TIME_SERIES, INCOME, BALANCE, CASH_FLOW) |
| `fetch_utils.py` | SQLite cache I/O, AV API calls, cache TTL management |
| `revenue_segment_fetcher.py` | Extracts product/geographic revenue segments via LLM + web search |
| `llm_client.py` | Centralized LLM abstraction (`OpenAIClient` with Chat Completions + Responses API) |
| `process_utils.py` | Data alignment, corporate identity extraction, revenue segment merging |
| `models.py` | Pydantic models (`ChartDataPoint`, `CorporateIdentity`, `VALID_METRIC_KEYS`) |

## Data Flow

1. **`cache_ticker_data(ticker)`** is called by both MCP tools (`visualize_html`, `compute_metrics`)
2. It checks the SQLite cache (`av_cache` table) for completeness
3. On cache miss, it fetches missing data in parallel:
   - **AlphaVantage**: 5 API calls for financial statements, price history, and company overview
   - **Revenue Segments**: Single OpenAI API call with `web_search` tool grounding for 10-K segment data
4. Results are cached in SQLite with TTLs (AV data: configurable, segments: 1 year)
5. Downstream tools read from cache and process data (alignment, filtering, visualization)

## Cache Schema

SQLite table `av_cache`:
```sql
CREATE TABLE av_cache (
    symbol TEXT,
    function TEXT,       -- e.g., 'OVERVIEW', 'INCOME_STATEMENT', 'REVENUE_SEGMENTS'
    data TEXT,           -- JSON blob
    timestamp REAL,      -- Unix timestamp of when data was cached
    expires_at REAL,     -- Unix timestamp of expiration
    source TEXT,         -- e.g., 'alphavantage', 'llm_search', 'mock'
    is_corrupt INTEGER,  -- 0 = valid, 1 = corrupt
    PRIMARY KEY (symbol, function)
);
```

## Thread Safety

`cache_ticker_data()` uses a per-ticker `threading.Lock` to prevent duplicate fetches when
`visualize_html` and `compute_metrics` are called concurrently for the same ticker. Different
tickers can be fetched in parallel without contention.
