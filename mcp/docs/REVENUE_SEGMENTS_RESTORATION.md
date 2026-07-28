# Restoring Revenue Segment Metrics

**Status:** removed from `main` on 2026-07-28.
**Archive:** branch `archive/revenue-segments`, commit `015ffbe550a859aa05c0654eae6ac9ca3328a2d9`.

Every file described here can be recovered verbatim:

```bash
git show 015ffbe:mcp/data/revenue_segment_fetcher.py
git checkout 015ffbe -- mcp/data/revenue_segment_fetcher.py
git diff main 015ffbe -- mcp/            # everything that changed
```

Read this whole document before restoring. The feature did not work, and the reasons are specific.

---

## 1. What the feature did

Added two metrics — `product_segments` and `geographic_segments` — giving a revenue breakdown by business line and by region, sourced from SEC 10-K segment disclosures. They rendered as stacked bars behind the normal line metrics in the Chart.js widget, and were also returned by `compute_metrics` as `{date: {segment_name: usd_value}}`.

Data came from an LLM with web-search grounding, not from a filings API. That is the crux of why it was removed.

---

## 2. Why it was removed

**Provenance, not complexity.** Fink is a due-diligence tool. Every other number in it traces to AlphaVantage; segment figures traced to a model asked to search for 10-Ks and report what it found. The prompt forbade estimation and the response was schema-validated, but nothing verified the *values* against the filing. An unverified revenue breakdown presented next to audited figures — in the same chart, with the same visual weight — is a worse liability than any amount of rendering code.

Secondary: it was the only source of mixed chart types (bar + line), the only LLM dependency in `mcp/`, and it never actually rendered. Every cached payload came back empty. Removing it made `mcp/` a pure AlphaVantage + SQLite service with no non-deterministic data anywhere in it.

---

## 3. Inventory of what was removed

### Files deleted outright

| File | Lines | Contents |
|---|---|---|
| `mcp/data/revenue_segment_fetcher.py` | 135 | `_build_segment_prompt`, `_validate_segment_entry`, `_validate_and_clean_response`, `fetch_revenue_segments` |
| `mcp/data/llm_client.py` | 99 | `LLMClient` ABC, `OpenAIClient` (`query_json`, `query_text`, `query_json_with_search`), `get_llm_client` factory. Its only production consumer was the fetcher. |
| `mcp/tests/test_revenue_segment_fetcher.py` | 276 | 20 tests covering validation, cleaning, sorting, and mocked LLM calls |

### Files edited

| File | What came out |
|---|---|
| `mcp/metrics_registry.py` | The two `10-K Segments` entries. **This is the master switch** — it drives `VALID_METRIC_KEYS`, the widget checkbox list, and the native tool docstrings via `{{VALID_METRIC_NAMES}}`. |
| `mcp/data/cache_orchestrator.py` | `include_revenue_segments` param, seg-cache check, `_fetch_revenue_segments()`, `revenue_segment_data` return key. The `ThreadPoolExecutor` collapsed to a direct `_fetch_av()` call — it only ever had two jobs. |
| `mcp/data/fetch_utils.py` | `get_revenue_segment_cache()`, `set_revenue_segment_cache()`. The `av_cache` schema was left alone: `function` is a plain string column, so `REVENUE_SEGMENTS` rows need no migration to reintroduce. |
| `mcp/data/process_utils.py` | `merge_revenue_segment_data()` (~35 lines) |
| `mcp/data/models.py` | `product_segments` / `geographic_segments` fields on `ChartDataPoint` |
| `mcp/server.py` | `revenue_segment_chart` param on `visualize_html`, both `needs_revenue_segments` blocks, the `merge_revenue_segment_data` import and call, the seg-key loop in `compute_metrics` |
| `mcp/visualization/visualization_tool.py` | `revenue_segment_chart` param, the segment-injection block, `"10-K Segments"` from `categories` |
| `mcp/visualization/chartUtils.js` | `SEGMENT_COLORS`, the `isSegmentMetric` branch, `stacked: hasBarDatasets`, `x: { stacked: true }` |
| `mcp/setup/seed_webui_db.py` | Two system-prompt lines instructing the model to use segment metrics |
| `mcp/setup/setup_open_webui_container.sh` | The `assert 'product_segments' in row[1]` verification (repointed at a surviving metric) |
| `mcp/requirements.txt` | `openai>=1.0.0` |

### Tests pruned

| File | Removed |
|---|---|
| `test_e2e_widget.py` | 4 segment tests + `_setup_playwright_page` helper |
| `test_e2e_tool_dispatch.py` | `test_segment_metrics` |
| `test_cache_orchestrator.py` | `test_parallel_fetch_av_and_segments`, `test_segment_cache_hit_skips_fetch`; remaining tests simplified to drop the `include_revenue_segments` argument |

### What was deliberately kept

The **destroy-and-recreate chart lifecycle** in `chartUtils.js`. It was introduced to fix mixed line/bar rendering, but it replaced a dual-branch `if (chartInstance) update() else new Chart()` structure whose two halves had already drifted — the in-place branch was separately maintaining its own normalize-axis logic. One construction path is simpler and correct regardless of whether bars exist. Do not revert it when restoring.

---

## 4. Fix these before restoring

Four defects were found on review. All are preserved in the archive commit. **A restore that recovers those files verbatim reintroduces every one of them.**

### 4.1 `query_json_with_search` cannot parse its own output

```python
response = self.client.responses.create(
    model=self.model,
    tools=[{"type": "web_search"}],
    input=combined_input,
    temperature=temperature      # <-- GPT-5.x reasoning models are picky about this
)
return json.loads(response.output_text)   # <-- no fence-stripping
```

Search-grounded responses usually arrive fenced in ```` ```json ```` or with a citation preamble, despite the prompt's "output ONLY the JSON" instruction. `json.loads` then raises. This is the most likely reason every cached payload came back empty.

Fix: strip fences and extract the outermost JSON array before parsing; drop `temperature` or make it conditional on the model family; assert on a parsed non-empty result rather than trusting it.

### 4.2 Failures were silent

`fetch_revenue_segments` caught every exception, printed, and returned `[]`. Downstream, `visualization_tool.py` pre-creates `aligned_metrics = {k: {} for k in VALID_METRIC_KEYS}`, so an empty fetch was indistinguishable from a successful one — no error surfaced to the tool, the LLM, or the user. Compounding it, `set_revenue_segment_cache` was only called on truthy data, so empty results were never cached and the failing call repeated on every render.

Fix: return a structured error the way `_fetch_av` does, and propagate it into the tool response.

### 4.3 Fiscal-year date mismatch

Segment keys were raw `fiscal_year_end` strings from the LLM. Chart labels are month-end-rounded by `round_date_to_end_of_month`. UNH (Dec 31) aligned by luck; Apple's `2024-09-28` would never match `2024-09-30`, and every bar would land `null`.

Worse, the two consumers disagreed: `merge_revenue_segment_data` (the `compute_metrics` path) matched by *year* and was immune, while the `visualize_html` path matched by exact date string. Same data, two different alignment rules.

Fix: normalize segment dates through `round_date_to_end_of_month` at ingest, and use one alignment rule for both paths.

### 4.4 Segments could not work as a client-side toggle

Segment data was only written into the static JSON when the *server* was asked for it up front (`needs_revenue_segments`). Every other metric is populated unconditionally, so its checkbox toggles client-side. Ticking the segment checkbox found `processedMetrics.product_segments === {}` and silently did nothing.

Fix: either fetch segments eagerly like everything else, or make the checkbox trigger a server round-trip. The first is simpler and consistent; the second avoids the cost of an unwanted fetch.

### 4.5 Never implemented

The original plan's **Fix 3 — `skipNull: true` on bar datasets** — was specified but never added. Whether it's actually needed depends on how nulls are handled after 4.3 is fixed.

---

## 5. Before rebuilding: reconsider the data source

The removal reason was provenance. Restoring the same LLM-search design fixes none of that, no matter how clean the code is. Resolve the source question first.

### SEC XBRL — the obvious candidate, with a real caveat

`data.sec.gov` is free and needs no API key (it does require a descriptive `User-Agent` header). But **the easy endpoint will not give you segments.**

`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` returns consolidated us-gaap facts only. Segment breakdowns are *dimensional* — they hang off axes like `srt:ProductOrServiceAxis`, `us-gaap:StatementBusinessSegmentsAxis`, and `srt:StatementGeographicalAxis` — and `companyfacts` is dimension-collapsed. The `frames` API has the same limitation.

To get segment values you need one of:

- the filing's dimensional XBRL instance (`*_htm.xml`) from the submission, parsed with an XBRL library
- the R-files enumerated in `FilingSummary.xml`, which contain the rendered segment tables
- SEC's quarterly **Financial Statement Data Sets**, whose `num.txt` carries a `segments` column in recent vintages

All three are a genuine parsing project, not a drop-in API call. **Verify this yourself against a current filing before committing to an estimate** — SEC endpoints do change, and this assessment is from July 2026.

Second consideration even with clean data: segment *names* change between filings (companies rename and re-cut business units). Any multi-year chart needs a name-reconciliation strategy, or bars will fragment across years. The old LLM prompt punted on this by asking for "the exact segment names as they appear in each year's filing."

### Prior art worth checking

`mcp/tests/__pycache__/` contained an orphaned `test_edgar_extractor.cpython-311-pytest-9.1.1.pyc` with no matching source file and nothing in git history — evidence that a deterministic EDGAR extraction path was attempted and abandoned before the LLM approach was written. Nobody recorded why. Worth understanding that before starting again; the answer may be exactly the parsing difficulty described above.

---

## 6. Restoration checklist

1. [ ] Decide the data source. If it's still LLM-based, be deliberate about that and label the provenance in the UI.
2. [ ] `git diff main 015ffbe -- mcp/` to see the full original change.
3. [ ] Restore `metrics_registry.py` entries first — everything else keys off them.
4. [ ] Restore the data layer, applying fixes 4.1 and 4.2.
5. [ ] Restore the alignment path, applying fix 4.3, with one rule shared by both consumers.
6. [ ] Restore the chart branch, applying fix 4.4. Keep the existing destroy-and-recreate lifecycle.
7. [ ] Restore the pruned tests. Make sure they fail against empty data — the originals passed vacuously (two of the four asserted only "no JS errors," which holds trivially when zero bars render).
8. [ ] Seed a `REVENUE_SEGMENTS` cache row for one ticker so tests are deterministic and need no API key.
9. [ ] Re-add `openai` to `requirements.txt` only if the LLM path returns.
10. [ ] Restore the `product_segments` assertion in `setup_open_webui_container.sh`.
11. [ ] Restore the segment guidance lines in `seed_webui_db.py`.
