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

From the repository root.

**Tier 1 — unit, integration and widget tests.** Fully offline: `tests/conftest.py`
forces `FINK_DATA_MODE=seed`, so no AlphaVantage quota is consumed and runtime is
deterministic.

```bash
venv/bin/pytest mcp/tests/ -v \
  --ignore=mcp/tests/test_docker_e2e.py \
  --ignore=mcp/tests/test_e2e_tool_dispatch.py \
  --ignore=mcp/tests/test_e2e_llm_tool_loop.py
```

**Tier 2 — server-dependent tests.** Requires the containers to be running and
`OPENAI_API_KEY` to be exported. Note `test_e2e_llm_tool_loop.py` calls the OpenAI API
directly, so these cost real money; they skip if the key is unset.

```bash
./mcp/setup/setup_open_webui_container.sh
set -a; . ./.env; set +a
venv/bin/pytest mcp/tests/test_e2e_tool_dispatch.py \
                mcp/tests/test_e2e_llm_tool_loop.py \
                mcp/tests/test_docker_e2e.py -v
```

Allow ~10s after provisioning for both containers to report healthy before running
tier 2; `docker inspect -f '{{.State.Health.Status}}' fink-mcp-server` will say
`healthy` when it is ready.
