#!/bin/bash
# Developer test runner for the Fink MCP suite.
#
# This is a development loop tool, not a post-install smoke test: --deploy re-provisions
# the Open WebUI container, and tier 1 needs the venv and Playwright browsers created by
# mcp/setup/setup_host.sh.
#
#   ./mcp/tests/verify.sh                 Unit, integration and widget tests. Offline.
#   ./mcp/tests/verify.sh --with-llm      Also run the paid OpenAI dispatch tests.
#   ./mcp/tests/verify.sh --deploy        Re-provision the container, then server tests.
#
# Output goes to verify.log / verify-deploy.log at the repo root (both gitignored).
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1

DEPLOY=0
WITH_LLM=0
for arg in "$@"; do
    case "$arg" in
        --deploy)   DEPLOY=1 ;;
        --with-llm) WITH_LLM=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$DEPLOY" -eq 1 ]; then LOG=verify-deploy.log; else LOG=verify.log; fi
: > "$LOG"
FAILED=0

# mcp/tests/test_e2e_llm_tool_loop.py calls the OpenAI API directly, so those tests cost
# real money. They skip themselves when OPENAI_API_KEY is unset, so we only export it on
# request. Everything else runs without credentials: tier 1 is offline via
# FINK_DATA_MODE=seed (tests/conftest.py) and the container tests use a fixed dev key.
if [ "$WITH_LLM" -eq 1 ] && [ -f .env ]; then
    set -a; . ./.env; set +a
    echo "💸 --with-llm: OpenAI dispatch tests enabled (these bill your API key)"
fi

run() {
    echo "" | tee -a "$LOG"
    echo "════════════════════════════════════════════════════════" | tee -a "$LOG"
    echo "▶ $*" | tee -a "$LOG"
    echo "════════════════════════════════════════════════════════" | tee -a "$LOG"
    "$@" >> "$LOG" 2>&1
    local rc=$?
    [ $rc -ne 0 ] && FAILED=1
    echo "── exit code: $rc ──" | tee -a "$LOG"
}

wait_healthy() {
    # Containers report "health: starting" for up to ~30s after recreation. Running the
    # server-dependent tests before then yields spurious ConnectionResetErrors.
    echo "" | tee -a "$LOG"
    echo "⏳ Waiting for containers to become healthy (max 120s)..." | tee -a "$LOG"
    for i in $(seq 1 60); do
        mcp_ok=$(docker inspect -f '{{.State.Health.Status}}' fink-mcp-server 2>/dev/null)
        webui_up=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/health 2>/dev/null)
        if [ "$mcp_ok" == "healthy" ] && [ "$webui_up" == "200" ]; then
            echo "  ✅ both ready after ~$((i * 2))s" | tee -a "$LOG"
            return 0
        fi
        sleep 2
    done
    echo "  ⚠️  timed out — mcp=$mcp_ok webui_http=$webui_up (running tests anyway)" | tee -a "$LOG"
}

{
    echo "fink verification — $(date)"
    echo "branch: $(git branch --show-current)  head: $(git rev-parse --short HEAD)"
} | tee -a "$LOG"

if [ "$DEPLOY" -eq 1 ]; then
    run ./mcp/setup/setup_open_webui_container.sh
    wait_healthy
    run docker ps --format '{{.Names}}\t{{.Status}}'
    # Confirm the compose env reached the container. `docker-compose restart` would
    # silently keep the old value, leaving production serving seed fixtures.
    run docker exec fink-mcp-server sh -c 'echo "FINK_DATA_MODE=$FINK_DATA_MODE"'
    # Check the seeded prompt in webui.db, not files copied into the container: `up -d`
    # recreates containers on config change and discards the writable layer, but seeding
    # has already run and webui.db lives on a named volume.
    run docker exec open-webui-fink-mcp python -c "
import sqlite3, json
row = sqlite3.connect('/app/backend/data/webui.db').execute(
    \"SELECT params, meta FROM model WHERE id='fink-with-mcp-server'\").fetchone()
assert row, 'model not provisioned'
params, meta = json.loads(row[0] or '{}'), json.loads(row[1] or '{}')
sp = params.get('system') or ''
print(f'params.system: {len(sp)} chars | {sp.splitlines()[0] if sp else \"ABSENT\"}')
assert '{{CURRENT_DATE}}' in sp, 'params.system missing the {{CURRENT_DATE}} token'
assert '## Timeframes' in sp, 'params.system missing Timeframes section'
assert 'system' not in meta, 'meta.system should no longer be written'
"
    run venv/bin/pytest mcp/tests/test_e2e_tool_dispatch.py \
                        mcp/tests/test_e2e_llm_tool_loop.py \
                        mcp/tests/test_docker_e2e.py -v --tb=short
else
    # Collection-only first: surfaces import errors before anything executes.
    run venv/bin/pytest mcp/tests/ --collect-only -q
    run venv/bin/pytest mcp/tests/ -v --tb=short \
        --ignore=mcp/tests/test_docker_e2e.py \
        --ignore=mcp/tests/test_e2e_tool_dispatch.py \
        --ignore=mcp/tests/test_e2e_llm_tool_loop.py
fi

echo "" | tee -a "$LOG"
if [ "$FAILED" -eq 0 ]; then
    echo "✅ Done — all green. Full output in $LOG" | tee -a "$LOG"
else
    echo "❌ Done — FAILURES present. Full output in $LOG" | tee -a "$LOG"
fi
# Propagate status so `verify.sh && verify.sh --deploy` gates correctly.
exit "$FAILED"
