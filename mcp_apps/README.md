# fink — MCP Apps server

A conversational due-diligence surface. Ask Claude to scan a company and you
get a panel of ranked findings — what is statistically unusual about its
fundamentals, why it might be innocent, and a chart of the evidence each claim
rests on.

```
You:     Scan GOOGL's fundamentals

Claude:  [panel]  GOOGL — Alphabet Inc Class A
                  81 quarters · 10 checks ran

                  [RISK] Reinvestment is outrunning the returns it earns  10.0/10
                    ROIC is 15.1%, down 1086bp from a 26.0% peak, 3.5σ below
                    its own history and falling 6 quarters running.
                    TTM free cash flow margin is 11.9%, down from 27.4%.
                    ▸ Innocent explanations to rule out first
                    [See chart] [Ask about this]

                  [OPPORTUNITY] Gross margin has expanded 273bp          3.4/10
```

The engine is deterministic: eight checks across seven questions, each able to
fire as a risk or an opportunity, scored against each company's *own* trailing
history rather than absolute thresholds. It declines to answer where it cannot
— insurers and REITs are out of scope, not approximated — and returning nothing
is a real result rather than an empty state.

---

## Quick start

**Requires** Python 3.11+, Claude Desktop, and this repo cloned.

**1. Install dependencies**

```bash
python3 -m venv venv
venv/bin/pip install -r mcp/requirements-dev.txt
```

**2. Verify it works before involving Claude**

```bash
./mcp_apps/tests/verify.sh          # 181 tests, offline, ~6s
venv/bin/python mcp_apps/scan_cli.py GOOGL
```

If the CLI prints findings, the engine and data layer are fine and anything
that goes wrong next is the MCP wiring or the panel.

**3. Register the server with Claude Desktop**

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(or **Settings → Developer → Edit Config**):

```json
{
  "mcpServers": {
    "fink-apps": {
      "command": "/ABSOLUTE/PATH/TO/fink/venv/bin/python",
      "args": ["/ABSOLUTE/PATH/TO/fink/mcp_apps/server.py", "--stdio"],
      "env": {
        "FINK_DATA_MODE": "seed"
      }
    }
  }
}
```

Absolute paths are required — Claude Desktop does not run this from the repo.

**`FINK_DATA_MODE=seed` is not optional for a first run.** In `live` mode the
fetch layer skips the checked-in corpus entirely and goes to the network, so
without an API key every ticker fails — including the nine whose data is
already on disk.

**4. Restart Claude Desktop**, open a **regular chat** (not a Cowork thread —
Cowork does not render MCP Apps panels), and try:

| Prompt | What it demonstrates |
|---|---|
| `Scan GOOGL's fundamentals` | two findings; the headline `capital_cycle` at 10/10 |
| `Scan COST` | clean — "10 checks ran and none cleared the floor" |
| `Scan UNH` | **declined**, not clean. An insurer; the schema has no premium revenue or claims reserves |
| `Scan NEE` | a utility: one finding, two checks skipped *with reasons* |
| `Chart GOOGL's ROIC and gross margin since 2018` | the standalone chart, no scan involved |

Then click **See chart** on a finding, and try the **Indexed to 100** toggle.

### Going beyond the seeded tickers

Nine companies ship with the repo: AAPL AMZN COST CPRT GOOGL NEE PG UNH WMT.
For anything else you need an [Alpha Vantage key](https://www.alphavantage.co/support/#api-key):

```json
"env": {
  "FINK_DATA_MODE": "live",
  "ALPHAVANTAGE_API_KEY": "your-key"
}
```

The free tier is 25 calls/day and a ticker costs 5. Note that live mode
re-fetches even seeded tickers rather than reading the corpus — deliberate, so
production serves fresh statements, but expensive for testing.

---

## The tools

Two reach the model. Two are hidden from it and callable only from inside a
panel.

| Tool | Visible to | Returns | Opens |
|---|---|---|---|
| `scan_fundamentals(ticker)` | model | ranked clusters, ~4KB | `ui://fink/scan` |
| `chart_fundamentals(ticker, metrics?, start_year?, end_year?)` | model | chart spec | `ui://fink/chart` |
| `fink_metric_series(ticker, metrics?, …)` | **panel only** | dated series, ~20KB | — |
| `fink_scan_payload(ticker)` | **panel only** | same as `scan_fundamentals` | — |

**Why two of them are hidden.** `visibility: ["app"]` keeps a tool out of the
model's tool list while leaving it callable from a view over
`app.callServerTool`. A metric series is hundreds of dated numbers the model
can do nothing useful with, and anything that enters the conversation is paid
for on *every subsequent turn*. So the chart fetches its own data and the model
never sees it. The scan itself does go to the model — a few KB, and it needs
the findings to answer whatever you ask next.

### What the model gets, and what it is told to do with it

`scan_fundamentals` returns **clusters**, not individual checks. Each entry
carries `checks: [...]` naming the checks that agreed, one `detail` string per
member, and the benign explanations merged across all of them. A cluster is one
story: `capital_cycle` is `roic_decline` + `fcf_compression`, which is capital
going in faster than returns come out — a single thing happening, not two.

Alongside the data the payload carries a **`guidance`** block: hand-written,
deterministic instructions on how to narrate the result. It is not generated —
asking a model how to narrate before it narrates is circular and
non-deterministic — and it is matched to the situation, since a declined scan,
a clean scan and a scan with clusters need different advice.

It exists because four things go wrong without it, none of which the payload
can convey on its own:

| Left alone the model… | Guidance says |
|---|---|
| reads 10/10 as "this company is in trouble" | `signal` is how extreme the reading is **against the company's own history** — a fact about a distribution, not a business |
| lists the benign explanations as boilerplate | weigh them; say which reading is more likely and why |
| narrates a cluster's members as separate problems | a cluster is one mechanism |
| blends what was computed with what it recalls | mark recollection `[from my knowledge — verify]` |

It also asks for **the crux** — the single variable the decision reduces to,
as a falsifiable claim with a threshold and a time window. "If FCF margin is
not back above 15% within four quarters, the capacity-build reading is wrong",
not "watch cash flow closely".

Guidance rides in the *result* rather than the tool description: a description
sits in context on every turn whether the tool is called or not, while a result
is paid for once, when the data it describes is actually there. It is ~2KB and
never reaches the panel — it is for the model, and rendering it would repeat
instructions at a reader who did not ask for them.

### End to end

```
"Scan GOOGL's fundamentals"
   │
   ├─ model calls scan_fundamentals("GOOGL")
   │     adapters.load_company  →  AV quarterlyReports  →  engine.Company
   │     engine.scan            →  findings → clustered → scored → capped
   │     chartspec.spec_for     →  which series each cluster rests on
   │     narrative.guidance_for →  how to narrate *this* result
   │
   ├─ host reads _meta.ui.resourceUri → fetches ui://fink/scan → sandboxed iframe
   │     view calls App.connect()  ← MANDATORY; without it the panel never shows
   │     host delivers the result via ontoolresult
   │
   └─ panel renders. Then, per finding:
         [See chart] → app.callServerTool("fink_metric_series", chartSpec)
                       ...draws inline. Never touches the model.
         [Ask]       → app.sendMessage({role, content}) → stages in the composer
```

---

## How the data works

Full detail in **[`data/README.md`](data/README.md)**. The two things worth
knowing up front:

**There are two paths through the data layer and conflating them fails
silently.** The chart uses `adapters.load_series` → ~320 monthly rows
interpolated onto the price series, with a live quote at the right edge. The
engine uses `adapters.load_company` → ~81 *fiscal quarters* straight off the AV
statements, no live quote. The engine computes trailing-twelve-month figures as
`sum(series[i-3:i+1])` — four consecutive quarters. Feed it monthly rows and
every TTM number becomes a four-month sum of carried-forward values: about a
third of the truth, with no gap, no `None`, and nothing raised.

**The cache is offline-first.** SQLite → seed JSON → network, and in
`FINK_DATA_MODE=seed` the last step raises instead. This package owns its own
database; `mcp/` has a separate one. Point both at the same
`ALPHAVANTAGE_CACHE_DB` if you want them to share.

---

## Layout

```
server.py         MCP tools, the two ui:// views, shared chart rendering
chartspec.py      engine metric names → chart metric ids
scan_cli.py       run a scan from the terminal, no MCP or host involved
engine/           the anomaly checks — see below
narrative.py      how the model is told to read a scan
data/             fetching, caching, metrics    → data/README.md
tests/            181 tests + verify.sh
STATE.md          working notes: decisions, dead ends, what not to re-derive
```

### The engine

Seven questions. Each can fire in either direction — a risk or the same
mechanism running favourably — which is why the same question yields two
check ids.

| Q | Check | What it measures | Fires when |
|---|---|---|---|
| **Q1** | `accruals_high` ⚠ | (TTM net income − TTM operating cash flow) ÷ total assets | Reported profit pulls away from cash collected, positive two quarters running |
| | `accruals_low` ✓ | same | Cash generation runs ahead of reported earnings |
| **Q2** | `margin_changepoint` ⚠✓ | Gross margin, last 4 quarters vs the 8 before | A step change in either direction, in basis points |
| **Q3** | `dso_expansion` ⚠ | Days sales outstanding — receivables ÷ revenue | Customers taking longer to pay, **while revenue growth is not accelerating** |
| | `dio_expansion` ⚠ | Days inventory outstanding — inventory ÷ COGS | Stock building relative to what is sold |
| | `dpo_expansion` ⚠ | Days payable outstanding — payables ÷ COGS | The company stretching its own suppliers |
| | `dso_release` / `dio_release` ✓ | same two | Working capital freeing up *while revenue grows* |
| **Q4** | `share_shrink` ✓ | Share count, net of issuance | Buybacks genuinely shrinking the count rather than offsetting dilution |
| **Q5** | `underinvestment` ⚠ | Capex ÷ D&A | Reinvestment sustained below the rate assets depreciate |
| | `reinvestment_restart` ✓ | same | Capex resuming after a lull |
| **Q5b** | `fcf_compression` ⚠ | TTM free cash flow margin | FCF margin collapsing, or TTM FCF going negative |
| | `fcf_expansion` ✓ | same | FCF margin expanding |
| **Q6** | `price_fundamental_divergence` ⚠✓ | 6-month price return vs fundamental direction | Price and fundamentals moving opposite ways — either sign |
| **Q7** | `roic_decline` ⚠ | TTM NOPAT ÷ (assets − current liabilities) | Returns falling while the capital base grows |
| | `roic_improvement` ✓ | same | Returns rising |

⚠ risk · ✓ opportunity

**Checks decline themselves where they would mislead.** `dio` skips for
software companies and anywhere inventory is under 3% of assets. Q5 skips for
utilities, because rate-base accounting makes capex exceed D&A permanently by
design. Financials, insurers and REITs are declined outright. Skips appear in
the panel with their reason — silence about coverage is how a scanner loses
trust.

#### Scoring

Each finding's raw score is a product:

```
score = magnitude × persistence × question_weight × confidence

  magnitude    z-score of the reading against the company's own trailing
               20 quarters, clipped at 4σ. Beyond 5σ it is far more likely a
               one-off item or a bad input than a trend, so it is scaled to
               0.4× and labelled "check inputs" rather than believed.
  persistence  quarters sustained ÷ 2, capped at 2. One quarter is noise.
  weight       Q1 1.0 · Q7 0.9 · Q2 0.8 · Q3 0.7 · Q4 0.7 · Q5 0.6 · Q6 0.5
               Opportunities are additionally scaled 0.7×.
```

Raw score is unbounded and means nothing on its own, so the panel shows
**signal strength on 0–10**: `min(score / 6.0, 1) × 10`, banded as
**high** ≥ 6.5, **medium** ≥ 3.5, **low** below.

**Read this as evidence strength for one check, not as a verdict on the
company.** 10/10 means the reading is extreme relative to that company's own
history — it says nothing about whether the cause is benign. GOOGL's
`capital_cycle` scores 10/10 and the most likely explanation is an AI
infrastructure build whose returns simply have not arrived yet.

Findings below **1.0** raw are dropped, and at most **5** are shown. Tripping
more than five is itself worth noting, so the overflow count is reported rather
than hidden.

**Why opportunities are discounted 0.7×.** GAAP recognises losses early and
gains late, so bad news is more likely to be visible in the statements than
good. Management also broadcasts good news without being asked, which makes an
undiscovered opportunity rarer than an undiscovered risk. Opportunities also
pass a not-yet-priced gate — if the market has already moved, it is not news.

#### Clustering

Correlated checks merge into one narrative row, because a single underlying
story should not read as several problems:

| Cluster | Members | Reads as |
|---|---|---|
| `revenue_quality` | `accruals_high` + `dso_expansion` | Earnings outrunning cash collection |
| `demand_softness` | `dio_expansion` + `margin_changepoint` | Inventory building as margins compress |
| `liquidity` | `dpo_expansion` + `underinvestment` | Stretching payables while deferring capex |
| `capital_cycle` | `fcf_compression` + `roic_decline` | Reinvestment outrunning the returns it earns |
| `operating_leverage` | `accruals_low` + `dso_release` + `dio_release` | Cash conversion improving as the business scales |

A cluster scores its strongest member plus 0.3 per additional member, and
charts the evidence of *all* of them — `capital_cycle` opens with both ROIC
legs and both FCF legs, since either alone under-explains it.

#### Design rules that are load-bearing

- **Relative thresholds only.** Never absolute constants, and never against all
  history — the cache holds 20 years for some tickers, and the latest point of
  a long drift is always extreme, so any structural trend would read as an
  anomaly.
- **Returning nothing is the target.** Precision on healthy companies beats
  recall. A scanner that flags everything gets ignored.
- **Every finding ships with innocent explanations.** This is what separates an
  analyst tool from a short-seller newsletter.
- **Financials are declined, not approximated.** Premium revenue and claims
  reserves do not survive AV's normalized schema. Guessing produces confident
  nonsense.

---

## Testing

```bash
./mcp_apps/tests/verify.sh              # everything, offline, no credentials
./mcp_apps/tests/verify.sh --quick      # skip the subprocess determinism tests
venv/bin/python mcp_apps/server.py --selftest   # the MCP wire contract alone
```

Offline by design: `FINK_DATA_MODE=seed`, a temp SQLite file per run, and the
Yahoo quote stubbed so nothing depends on the network or the calendar.

The suite is mutation-tested rather than merely passing — deliberate
regressions were introduced for each of the load-bearing behaviours and each
failed exactly one test. `mcp/tests/verify.sh` covers the legacy Open WebUI
server and must stay green independently.

---

## Troubleshooting

**The tool doesn't appear.** The server failed to start and Claude Desktop
shows nothing rather than an error. Run the `command` and `args` from your
config by hand — a traceback will explain it. Check the paths are absolute.

**A panel appears but stays empty.** The view completed its handshake and
received nothing. Check the status line at the top of the panel; it reports
the actual failure.

**Every ticker says "Could not scan".** Almost always `FINK_DATA_MODE`
unset or `live` without an API key — live mode bypasses the checked-in corpus.

**"Unable to reach fink-apps" after clicking something.** The host dropped the
connection, usually because a view sent a malformed request. Not a Python
crash; `~/Library/Logs/Claude/mcp-server-fink-apps.log` will show no traceback.

**Nothing renders in Cowork.** Expected — Cowork does not render MCP Apps
panels and shows raw JSON. Use a regular chat.

---

*Statistically unusual is not the same as wrong. Every number here is computed
from Alpha Vantage quarterly statements; nothing is model knowledge. This is
not investment advice.*
