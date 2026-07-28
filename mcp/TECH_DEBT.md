# Fink `mcp/` — Tech Debt Backlog

Parked items from the 2026-07-28 repo digest. Not blocking; revisit when the segment-chart work lands.

- [x] ~~**Out-of-date READMEs.**~~ Rewritten 2026-07-28. `API_GUIDE.md` now documents the real `visualize_html` / `compute_metrics` signatures; `README.md` has an accurate directory tree, tool table, data-mode section and test inventory; `data/README.md` reflects the segment removal and `FINK_DATA_MODE`; `setup/README.md` covers the `up -d` and `params.system` pitfalls. The in-place-update feature `README.md` §3 used to claim as shipped is now explicitly marked as never implemented.

- [x] ~~**`mock_data=True` is hardcoded.**~~ Resolved 2026-07-28 via the `FINK_DATA_MODE` env var (`live` | `seed`), read by `fetch_utils.get_data_mode()`. `_fetch_av()` now derives `mock_data` from it, so production (`FINK_DATA_MODE=live` in docker-compose) serves real API data instead of shadowing AAPL/AMZN/NEE/PG/UNH with fixtures. Still open: surfacing the `source` field in tool output so a seed-backed chart is visibly labelled.

- [x] ~~**Silent failure in the segment path.**~~ Resolved by removing the segment feature on 2026-07-28 — `mcp/` no longer makes LLM calls at all. The defect is documented in `mcp/docs/REVENUE_SEGMENTS_RESTORATION.md` §4.2 so it isn't reintroduced. Note `OPENAI_API_KEY` in `.env` is now unused by `mcp/` (the `agent/` and `community_analysis/` sub-projects may still need it).

- [ ] **Dead code in the native tool.** `visualize_native` strips ```` ```html ```` fences from the response, but `visualize_html` returns a bare `<iframe>`. Leftover from the markdown-injection era; the branch never fires.

- [x] ~~**Copies of `chartUtils.js`.**~~ *Folded into the segment-removal work.* Only two copies were ever in the MCP path: `mcp/visualization/chartUtils.js` (canonical) and `open_webui/static/chartUtils.js` (served artifact, manually synced). Fix: `cp` step in `setup_open_webui_container.sh`, tests repointed at the canonical source, artifact gitignored. The other three — `open_webui/chartUtils.js` (the pipe-based `data_pipe.py` implementation), `./chartUtils.js` (root standalone app), and `community_analysis/chartUtils.js` — belong to independent sub-projects and are deliberately left alone.

- [ ] **In-place chart update was never built.** Earlier revisions of `mcp/README.md` described client-side `window.parent` DOM checking that finds an active chart and updates it in place rather than appending a duplicate — §3 called it the "Winner" design. No such code exists: zero occurrences of `window.parent` or `postMessage` in `visualization_tool.py` or the native tools, on `main`, on `archive/revenue-segments`, or at `HEAD`. `test_in_place_updating_e2e` asserted it and had therefore never passed; deleted 2026-07-28. **The README is now corrected** and states plainly that re-invoking the tool renders a new widget — so this is a missing feature, not a docs bug. Build it if the duplicate-chart clutter is worth fixing.

- [x] ~~**Unit tests make live AlphaVantage calls.**~~ Resolved 2026-07-28. `mcp/tests/conftest.py` forces `FINK_DATA_MODE=seed`, so the suite is offline however pytest is invoked and an uncached, unseeded ticker raises `OfflineDataUnavailable` rather than calling out. The junk `INVALIDTICKER12345` rows have been purged from the cache DB. Note `mock_data=True` alone never achieved this — it only *prefers* the seed corpus and fell through to the network on a miss.

- [ ] **`test_e2e_widget.py` writes into the repo as a side effect.** `generate_visualization_html()` writes `open_webui/static/{ticker}-data.json`, so running the suite mutates tracked-adjacent files. Point the tests at a tmp dir (the static path should be injectable).

- [ ] **Redundant `sys.path` bootstraps in test files.** Now that `mcp/tests/conftest.py` handles the path, the hand-rolled `sys.path.insert(...)` blocks at the top of `test_cache_orchestrator.py`, `test_e2e_widget.py`, `test_visualization_tool.py`, and `test_mcp_server.py` are dead weight. Harmless, but worth deleting on the next pass through those files.

- [ ] **No separation of test dependencies.** `mcp/requirements.txt` is installed into *both* the server image (`Dockerfile.mcp`) and the host test venv (`setup_host.sh`), so test-only packages ship to production. `openai`, `pytest`, `pytest-asyncio`, and `playwright` all belong in a `requirements-dev.txt`. Surfaced while removing segments — `openai` looked dead after the LLM fetcher went, but `test_e2e_llm_tool_loop.py` still needs it.

- [ ] **Unpinned dependencies.** `mcp/requirements.txt` is all lower bounds (`fastmcp>=0.1.0`, `mcp>=0.1.0`, …). Combined with the `sys.path.insert` shim in `server.py` that works around the local `mcp/` dir shadowing the `mcp` pip package, a minor upstream release can break imports with no lockfile to fall back to.
