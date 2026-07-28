# Fink `mcp/` — Tech Debt Backlog

Parked items from the 2026-07-28 repo digest. Not blocking; revisit when the segment-chart work lands.

- [ ] **Out-of-date READMEs.** `mcp/API_GUIDE.md` documents `alphavantage`/`visualization` with a two-call `data` handoff that no longer exists — the real tools are `visualize_html` and `compute_metrics`, and they auto-fetch. `mcp/README.md` §2/§4/§5 has the same drift plus a directory listing that omits `metrics_registry.py`, `cache_orchestrator.py`, `llm_client.py`, `revenue_segment_fetcher.py`, and both native tool files. Only `mcp/data/README.md` is accurate.

- [ ] **`mock_data=True` is hardcoded.** `cache_orchestrator._fetch_av()` passes it unconditionally, so the 5 seed tickers in `data/local_av_cache/` silently shadow live data. Promote to a top-level config (env var + explicit param) that a developer opts into, and surface the resulting `source` field in tool output so a mock-backed chart is visibly labelled.

- [ ] **Silent failure in the segment path.** `fetch_revenue_segments()` catches every exception, prints, and returns `[]`. If `DEFAULT_MODEL` (`gpt-5.4-mini`, overridable via `OPENAI_MODEL`) is wrong or empty, or the response isn't parseable JSON, segments just vanish with no signal to the caller or the user. Needs a real error channel — propagate a structured error dict the way `_fetch_av` does.

- [ ] **Dead code in the native tool.** `visualize_native` strips ```` ```html ```` fences from the response, but `visualize_html` returns a bare `<iframe>`. Leftover from the markdown-injection era; the branch never fires.

- [x] ~~**Copies of `chartUtils.js`.**~~ *Folded into the segment-removal work.* Only two copies were ever in the MCP path: `mcp/visualization/chartUtils.js` (canonical) and `open_webui/static/chartUtils.js` (served artifact, manually synced). Fix: `cp` step in `setup_open_webui_container.sh`, tests repointed at the canonical source, artifact gitignored. The other three — `open_webui/chartUtils.js` (the pipe-based `data_pipe.py` implementation), `./chartUtils.js` (root standalone app), and `community_analysis/chartUtils.js` — belong to independent sub-projects and are deliberately left alone.

- [ ] **Unpinned dependencies.** `mcp/requirements.txt` is all lower bounds (`fastmcp>=0.1.0`, `mcp>=0.1.0`, …). Combined with the `sys.path.insert` shim in `server.py` that works around the local `mcp/` dir shadowing the `mcp` pip package, a minor upstream release can break imports with no lockfile to fall back to.
