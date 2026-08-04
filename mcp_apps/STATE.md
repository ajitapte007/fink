# mcp_apps — state of play

Compact context for resuming work. Read this instead of a chat transcript.

## What this is

An MCP Apps prototype for fink: a conversational due-diligence surface where a
deterministic anomaly scan surfaces what is statistically unusual about a
company, rendered as an interactive panel inside Claude Desktop.

Product shape, in priority order:

1. **Scan** — ranked risk/opportunity findings. The entry point.
2. **Chase** — click a finding, get the chart for that specific divergence.
3. Argue / Commit / Return — bull-bear, thesis + falsifiers, watch loop. Later.

The differentiator is that the loop closes: the user records a thesis and what
would falsify it, and the system tells them when a falsifier trips.

## Status

| Phase | State |
|---|---|
| 0 — SDK choice | done: standalone `fastmcp` 3.4.4 |
| 1 — package skeleton, `_bootstrap` | done |
| 2 — `ui://` renders in Claude Desktop | **done, committed** |
| 3 — fork `mcp/data`, engine, `adapters.py` | **done** |
| 4 — `scan_fundamentals` returning real clusters | **done** |
| 5 — findings-list view | **done** |
| 6 — row click → follow-up question | **done — MVP complete, 101 tests green** |
| 7-8 — chart view, controls | next |

**MVP verified in Claude Desktop**: scan renders as a panel, findings rank
correctly, clicking a row stages its follow-up question in the composer. The
host stages rather than sends — its discretion, and the better default.

**Prototype scaffolding is gone.** `fink_hello`, `fink_echo`, the hello view
and `check_{sdk,app_param,fastmcpapp}.py` were all removed after phases 4-6.
Their conclusions are recorded in the server docstring; keeping the scripts
added a second tool to the model's list for no live benefit.

## Hard-won facts (do not re-derive)

**A view MUST call `App.connect()` or the host never displays it.** The host
fetches the resource, receives the HTML, then holds the iframe hidden awaiting
a readiness signal. Log signature: a successful `resources/read` followed by
silence. There is no such thing as a static MCP App panel. This cost several
hours; `view_html()` in server.py now makes the handshake structural and
`--selftest` fails if a view lacks a `connect()` call.

**Verified working in Claude Desktop:**

- `ui://` resource renders; mimeType `text/html;profile=mcp-app`
- `_meta.ui.resourceUri` on a tool links it to its view
- `visibility: ["app"]` genuinely hides a tool from the model
- the view calls that hidden tool via `app.callServerTool` — so bulk data
  reaches the view without entering model context. This is the whole
  context-cost argument and it holds.
- `ontoolresult` delivers the tool result into the iframe
- CSP `meta={"ui": {"csp": {"resourceDomains": [...]}}}` permits a CDN import

**`callServerTool` response shape** (read `structuredContent`, don't reparse):

```json
{"content":[{"type":"text","text":"{...}"}], "structuredContent":{...}, "isError":false}
```

**Bisected and irrelevant:** the `.html` URI suffix (every published example
has one; not required) and `visibility: ["model"]` on entry-point tools.

**Read the ext-apps `.d.ts` before calling anything.** Two bugs came from not
doing so, and both were silent in different ways:

- `sendMessage({content: text})` was malformed — `role` is required and
  `content` is an array of typed blocks. A bad request on a live JSON-RPC
  channel is a protocol violation, not a no-op: the host dropped the whole
  connection and the panel reported "unable to reach fink-apps", which reads
  like a server crash. Correct shape:
  `{role: "user", content: [{type: "text", text}]}`.
- `notifySizeChanged` does not exist (it is `sendSizeChanged`). Optional
  chaining meant it no-oped silently for three phases. It is also unnecessary:
  `autoResize` defaults to true and the App watches `document.body` itself.

`test_no_unverified_host_methods_are_invoked` now enumerates the real App
surface and fails on anything outside it.

**Useful methods not yet used:** `updateModelContext()` (offload a large series
into model context without a tool result — wanted for the chart),
`createSamplingMessage()`, `requestDisplayMode()` for fullscreen/pip,
`getHostCapabilities()`.

**`mcp/__init__.py` was deleted** — it made `mcp/` a regular package that
shadowed the pip SDK whenever the repo root was on `sys.path`. Now a namespace
portion, so the real SDK wins. The `sys.path` shims stay; they serve sibling
imports, not collision avoidance.

**fastmcp's `app=` parameter** is thin sugar over `meta={"ui": ...}` and
`app=True` emits a useless `{"ui": true}`. **`FastMCPApp`** is a declarative
component library (approval/choice/form widgets) — it cannot run Chart.js.
Ignore both; hand-write `meta=`.

**Cowork cannot render MCP Apps.** Testing must happen in Claude Desktop.

## Data layer

**Forked to `mcp_apps/data` in phase 3.** `mcp/data` is legacy and frozen; full
policy and layout in `mcp_apps/data/README.md`. `mcp/` is otherwise untouched.

**The two paths differ, and conflating them fails silently.** The chart goes
through `adapters.load_series` → `get_aligned_historical_data` (~320 monthly
rows, live quote appended). The engine goes through `adapters.load_company` →
AV `quarterlyReports` directly (~81 fiscal quarters, no live quote). The engine
sums `series[i-3:i+1]` for TTM; monthly rows would make every TTM figure a
four-month sum of carried-forward values — about a third of the truth, with
nothing raised.

Seed corpus moved to `mcp_apps/data/alphavantage/local_av_cache/`, 9 tickers.
**CPRT is missing CASH_FLOW** — it worked during POC development only because
the developer's SQLite cache had it, and `*.db` is gitignored. One AV call
fixes it; `test_seed_corpus.KNOWN_INCOMPLETE` asserts the gap set exactly.

### Two real bugs found by building this

**capex/D&A was ~4x too high.** `merge_reports.keys_to_sum` TTM-sums a fixed
list of flow keys. `capitalExpenditures` was in it; D&A was not. So every
comparison put a trailing-twelve-month numerator over a single-quarter
denominator — AAPL read 3.59 where the truth is 0.91. Nothing raised.

**`smooth_series` enumerated all 33 fields by hand**, so any field added to
`ChartDataPoint` computed correctly, survived to the smoother, and came out
None. All six new metrics would have hit it. Now iterates the model.

### ROIC: the engine computes its own, deliberately

`VALID_METRIC_KEYS` has a `roic`, but it is EBIT / (assets − current
liabilities) on a *single quarter* — a charting metric. The engine wants TTM
NOPAT over invested capital, which is what the POC used and what GOOGL's
25.5% → 15.1% decline was measured with. Do not swap one for the other.

## Engine

Ported from a standalone POC. Eight checks over six questions, scored,
clustered, floored, capped at 5. Returns **`clusters`**, not a flat findings
list — correlated checks merge into one narrative row.

Design rules that matter:

- Relative thresholds only — z-scores/percentiles against the company's own
  trailing **20 quarters**, never all history and never absolute constants.
- Returning nothing is the target. Precision on healthy companies beats recall.
- Opportunities carry a not-yet-priced gate and 0.7x weight (GAAP recognises
  losses early and gains late; management broadcasts good news).
- Findings ship with `benignExplanations` — what separates an analyst tool from
  a short-seller newsletter.
- Financials/insurers/REITs are **declined**, not approximated. UNH included.
- Cluster `members` must be sorted by score descending: they come from a Python
  set, so unsorted iteration made the follow-up question hash-dependent.

Known real results on the seed corpus: GOOGL shows ROIC 25.5% -> 15.1% while
invested capital doubled, plus negative quarterly FCF — clusters as
`capital_cycle`. PG and WMT come back clean at 10/10 coverage.

## Testing

`./mcp_apps/tests/verify.sh` — 101 tests, offline, no credentials, ~6s.
Separate from `mcp/tests/verify.sh`, which needs Docker. Both must stay green
independently; that is the executable form of the migration policy.

conftest forces `FINK_DATA_MODE=seed`, redirects the SQLite cache to a temp
file (the legacy suite shares the developer's real cache, so a stale row can
make a test pass that should fail), and neutralises the Yahoo call so nothing
depends on the network or the calendar.

**Mutation-tested, not just passing.** Four deliberate regressions were
introduced and all four were caught: reverting the D&A TTM fix, pointing
`load_company` at the monthly pipeline, unsorting cluster members, and dropping
a field from `smooth_series`. `test_metrics_parity` also contains a test that
perturbs a value and asserts the hash moves — a hash test that hashes nothing
is worse than no test.

The load-bearing ones:

- `test_metrics_parity` — 33 legacy metrics hash identically to a baseline
  recorded from `mcp/data` *before* anything moved
- `test_engine_golden` — the 8-ticker POC results, plus assertions that GOOGL's
  `capital_cycle` rests on the numbers its narrative claims
- `test_adapters::test_ttm_of_four_quarters_reconciles_with_the_annual_filing` —
  4 quarters sum to the annual filing. AAPL FY2009 and PG FY2012-14 legitimately
  do not (revenue-recognition restatement; discontinued ops), so the bar is 80%
  within 2% and nothing off by more than 15%
- `test_determinism` — subprocesses at three `PYTHONHASHSEED` values
- `test_data_paths` — the three `__file__`-relative paths the split moved,
  which every ported test was blind to

## Open

- Vendor the ext-apps SDK and Chart.js instead of unpkg (phase 7)
- No persistence yet — thesis/falsifier store is post-MVP
- Sector-median check ("is this industry-wide?") needs SEC `frames`; deferred
