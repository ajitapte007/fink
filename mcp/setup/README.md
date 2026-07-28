# Fink MCP Setup Framework

Orchestration for provisioning the **Fink Stock Analyst Agent** workspace.

---

## Quick Start

From the repository root:

```bash
./mcp/setup/setup.sh
```

This runs key collection, host virtualenv setup, container provisioning, database
seeding, and verification in sequence.

---

## Architecture

Setup is split so development iterations stay fast and host config is decoupled from
container state.

| Script | Role |
|---|---|
| `setup.sh` | Master orchestrator — runs the rest in order |
| `setup_env.sh` | Interactive key collection (OpenAI, AlphaVantage) → root `.env` |
| `setup_host.sh` | **One-time per host.** Python venv, test dependencies, Playwright chromium |
| `setup_open_webui_container.sh` | Templates native tools, syncs assets, seeds the DB, applies compose config |
| `seed_webui_db.py` | Runs *inside* the container; writes tool registrations and the system prompt into `webui.db` |

### What `setup_open_webui_container.sh` does

1. **Templates the native tools** — substitutes `{{VALID_METRIC_NAMES}}` with
   `id: description` pairs from `metrics_registry.py`, so the model's tool docstrings
   always match the registry.
2. **Syncs `chartUtils.js`** — copies `mcp/visualization/chartUtils.js` (canonical) to
   `open_webui/static/chartUtils.js` (generated artifact, gitignored).
3. **Copies into the container** — the two native tools, `seed_webui_db.py`, and
   `system_prompt.py` (which `seed_webui_db.py` imports).
4. **Seeds the database** — registers tools, binds them to the model, writes the
   system prompt.
5. **Verifies** — asserts no `{{VALID_METRIC_NAMES}}` placeholder survives, that both
   tools registered, and that the system prompt reached `params.system` with its
   `{{CURRENT_DATE}}` token and `## Timeframes` section intact.
6. **Applies compose config** via `docker-compose up -d`.

---

## Two things that are easy to get wrong

**`up -d`, not `restart`.** `docker-compose restart` reuses a container's existing
config, so changes to environment variables or volumes in `docker-compose.yml` are
silently ignored — `FINK_DATA_MODE=live` would never take effect. `up -d` recreates
only the services whose definition changed.

A consequence worth knowing: recreation discards files placed with `docker cp`, since
they live in the writable layer. That is harmless here because seeding runs *before*
the recreate and writes to `webui.db`, which is on a named volume. Don't assert on the
presence of copied `.py` helpers afterwards — assert on the database.

**The system prompt goes in `params.system`.** Open WebUI reads a workspace model's
system prompt from `model.params.system`; `meta` holds description, capabilities and
suggestion prompts. Writing it to `meta.system` means every prompt update is silently
discarded while a stale prompt keeps being served. The verification step now asserts
this explicitly.

---

## Fast Re-Registration

After editing a native tool, the registry, the system prompt, or `chartUtils.js`:

```bash
./mcp/setup/setup_open_webui_container.sh
```

Re-templates, re-syncs, re-seeds and restarts without rebuilding host dependencies.

---

## Environment

| Variable | Purpose |
|---|---|
| `ALPHAVANTAGE_API_KEY` | Financial data. Required in `live` mode. |
| `OPENAI_API_KEY` | Open WebUI chat model; also the LLM dispatch tests. |
| `FINK_DATA_MODE` | `live` (compose) or `seed` (tests). See [data/README.md](../data/README.md). |
| `ALPHAVANTAGE_CACHE_DB` | Cache path override; compose points it at the shared volume. |

---

## Verification

`mcp/tests/verify.sh` is the developer test runner. Note it is a development loop tool,
not a post-install smoke test — `--deploy` re-provisions the container, and the tests
need the venv and Playwright browsers from `setup_host.sh`.

```bash
./mcp/tests/verify.sh              # unit, integration, widget — offline, no credentials
./mcp/tests/verify.sh --with-llm   # additionally run the paid OpenAI dispatch tests
./mcp/tests/verify.sh --deploy     # re-provision, wait for health, then server tests
```

The default run needs no API keys: tier 1 is offline via `FINK_DATA_MODE=seed`
(`tests/conftest.py`), and the container tests use a fixed dev key. The OpenAI dispatch
tests in `test_e2e_llm_tool_loop.py` call the API directly and **cost real money**, so
they are opt-in — without `--with-llm` they skip themselves.

`--deploy` waits for both containers to report healthy before testing, and asserts that
`FINK_DATA_MODE` reached the container and that the seeded prompt landed in
`params.system` with its `{{CURRENT_DATE}}` token intact.

Output goes to `verify.log` / `verify-deploy.log` at the repo root (gitignored). The
script exits non-zero on failure, so `verify.sh && verify.sh --deploy` gates correctly.
