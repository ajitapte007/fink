#!/bin/bash
# Test runner for mcp_apps. Offline, no credentials, no containers.
#
# Deliberately separate from mcp/tests/verify.sh rather than an extension of it.
# That one provisions Docker containers, polls health endpoints and inspects
# webui.db — none of which applies here. Both suites must stay green
# independently; that is the executable form of the migration policy in
# mcp_apps/data/README.md.
#
#   ./mcp_apps/tests/verify.sh            unit + integration + golden
#   ./mcp_apps/tests/verify.sh --quick    skip the slow subprocess tests
#
# Output goes to verify-apps.log at the repo root (gitignored).
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1

QUICK=0
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

PY=venv/bin/python
[ -x "$PY" ] || PY=python3

LOG=verify-apps.log
: > "$LOG"
FAILED=0

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

{
    echo "fink mcp_apps verification — $(date)"
    echo "branch: $(git branch --show-current)  head: $(git rev-parse --short HEAD)"
} | tee -a "$LOG"

# Collection first: surfaces import errors before anything executes. The two
# `data` packages make import resolution worth checking on its own.
run "$PY" -m pytest mcp_apps/tests/ --collect-only -q

if [ "$QUICK" -eq 1 ]; then
    run "$PY" -m pytest mcp_apps/tests/ -v --tb=short -m "not slow"
else
    run "$PY" -m pytest mcp_apps/tests/ -v --tb=short
fi

# The MCP wire contract: ui:// resource, mimeType, and the mandatory handshake.
# Not a pytest case because it needs the fastmcp in-memory client rather than
# the data layer.
run "$PY" mcp_apps/server.py --selftest

# Advisory only — never gates the exit code.
#
# This was originally a `run git diff --quiet` and it was wrong twice. It
# treated any uncommitted edit under mcp/ as a test failure, which fired on a
# README banner and would fire on legitimate work someone is doing on the
# legacy server. And the warning below could never print: `$?` read run()'s
# status, not git's, and run() always exits 0.
#
# Documentation churn under mcp/ is expected and fine. Uncommitted *code* is
# worth a look, but it is still not this suite's business to fail on — the
# guarantee that the legacy server still works is mcp/tests/verify.sh.
LEGACY_DIRTY=$(git diff --name-only -- mcp/data mcp/server.py mcp/visualization)
LEGACY_CODE=$(echo "$LEGACY_DIRTY" | grep -v '\.md$' | grep -v '^$')
if [ -n "$LEGACY_CODE" ]; then
    {
        echo ""
        echo "ℹ️  uncommitted CODE under mcp/ — the fork was meant to leave it alone:"
        echo "$LEGACY_CODE" | sed 's/^/     /'
        echo "   Run ./mcp/tests/verify.sh to confirm Open WebUI still works."
    } | tee -a "$LOG"
elif [ -n "$LEGACY_DIRTY" ]; then
    echo "" | tee -a "$LOG"
    echo "ℹ️  uncommitted docs under mcp/ (expected): $(echo "$LEGACY_DIRTY" | tr '\n' ' ')" \
        | tee -a "$LOG"
fi

echo "" | tee -a "$LOG"
if [ "$FAILED" -eq 0 ]; then
    echo "✅ Done — all green. Full output in $LOG" | tee -a "$LOG"
else
    echo "❌ Done — FAILURES present. Full output in $LOG" | tee -a "$LOG"
fi
exit "$FAILED"
