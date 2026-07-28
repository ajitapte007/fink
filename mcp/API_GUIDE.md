# MCP Financial Analytics — API & Tool Reference

Schemas and workflows for the two tools the Fink MCP server exposes.

Both tools **auto-fetch on cache miss** — there is no separate "fetch first" step. Data
resolution is handled by `cache_ticker_data()` (see [data/README.md](./data/README.md)).

---

## Tool Reference

### 1. `visualize_html`

Renders an interactive Chart.js dashboard and returns it as an embeddable iframe.

```python
visualize_html(
    ticker: str,
    selected_metrics: Optional[List[str]] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    normalize: Optional[bool] = False,
    per_share_metrics: Optional[List[str]] = None,
    left_axis_metrics: Optional[List[str]] = None,
    right_axis_metrics: Optional[List[str]] = None,
    growth_rate_yoy: Optional[bool] = False,
) -> str
```

| Parameter | Notes |
|---|---|
| `ticker` | US ticker, case-insensitive. Required. |
| `selected_metrics` | Any of `VALID_METRIC_KEYS`. **Omit** to get `DEFAULT_CHART_METRICS` — `price`, `revenue`, `net_income`, `operating_margin`. Do not pass a single guess. |
| `start_year` / `end_year` | Inclusive bounds. An omitted `end_year` resolves to the current year server-side. |
| `normalize` | Rebase every series to 100% of its first visible value. |
| `growth_rate_yoy` | Year-over-year % change, each point against 12 months prior. |
| `per_share_metrics` | Aggregate metrics to divide by shares outstanding. |
| `left_axis_metrics` / `right_axis_metrics` | Force specific metrics onto an axis, overriding `defaultAxis`. |

`normalize` and `growth_rate_yoy` are mutually exclusive — set at most one. Both
collapse all series onto the left axis, since both produce percentages.

**Returns** an `<iframe srcdoc="...">` string. The chart HTML loads
`/static/fink/chartUtils.js` and a per-ticker `{ticker}-data.json` written at render
time, which keeps multi-year series out of the model's token budget.

---

### 2. `compute_metrics`

Returns aligned historical values as JSON, for reasoning rather than display.

```python
compute_metrics(
    ticker: str,
    metrics: Optional[List[str]] = None,
    per_share_metrics: Optional[List[str]] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> str
```

| Parameter | Notes |
|---|---|
| `metrics` | Omit to return **all** metrics. Unknown keys produce a structured error listing the valid ones. |
| `per_share_metrics` | Scaled by shares outstanding on the fly; `None` where shares are missing or zero. |
| `start_year` / `end_year` | Inclusive. An omitted `end_year` resolves to the current year. |

**Returns** a JSON string:

```json
{
  "ticker": "AMZN",
  "timeframe": { "start_year": 2018, "end_year": 2026 },
  "data": [ { "date": "2018-01-31", "revenue": 193194000000.0 } ]
}
```

Metrics with no value at a given date are omitted from that point rather than emitted
as `null`, so sparse series stay compact.

---

## Metrics

Every metric is defined once in [`metrics_registry.py`](./metrics_registry.py) — id,
label, description, unit, category, default axis, colour, and whether it is an
aggregate. Adding a metric there propagates to validation, the chart's checkbox list,
and the native tool docstrings (via a `{{VALID_METRIC_NAMES}}` placeholder substituted
at registration).

Categories: **Aggregates**, **Valuation Ratios**, **Shareholder Return**,
**Performance & Efficiency**. 33 metrics as of this writing.

> 10-K revenue segment metrics were removed on 2026-07-28 — see
> [docs/REVENUE_SEGMENTS_RESTORATION.md](./docs/REVENUE_SEGMENTS_RESTORATION.md).

---

## Timeframe resolution

Relative ranges ("the last 10 years") are resolved in two layers:

1. **System prompt** — a shared `## Timeframes` section instructs the model to compute
   ranges from today's date, which Open WebUI injects per request via `{{CURRENT_DATE}}`.
   It applies to both tools.
2. **Server-side** — `_resolve_end_year()` defaults an omitted `end_year` to the current
   year, so the upper bound does not depend on the model getting the arithmetic right.

An explicitly supplied `end_year` is always respected; a user may legitimately want a
window that ends in the past.

---

## Workflows

### Chart request

1. *"Show me UNH financials for the last 5 years."*
2. The model calls `visualize_native` (the Open WebUI wrapper), which POSTs to
   `visualize_html` on the MCP server.
3. Data is fetched if absent, the widget HTML and its JSON payload are written, and an
   iframe is emitted into the chat.
4. The user adjusts metrics, axes, per-share scaling, the year slider, or the
   Normalize / Growth Rate buttons directly in the widget — all client-side, no round trip.

### Conversational refinement

1. *"Plot revenue instead, from 2018."*
2. The model re-invokes the tool with the new parameters; a fresh widget is rendered.

### Analysis request

1. *"Why did AMZN's margins move in 2022?"*
2. The model calls `compute_metrics` for the relevant metrics and reasons over the JSON,
   typically also rendering a supporting chart (Intent B in the system prompt).
