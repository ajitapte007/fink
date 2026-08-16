#!/bin/bash
# Packaging verification: build the wheel and prove it works with no repo.
#
# Companion to verify.sh, not a replacement. That one imports mcp_apps FROM THE
# REPO and proves the code is correct; it is structurally blind to packaging.
# A package-data glob that matches nothing keeps verify.sh green, produces no
# warning at build time, installs cleanly, and fails at a user's machine as
# "every ticker says Could not scan".
#
# Three layers, and each can only see its own:
#
#   1. verify.sh          the source is correct
#   2. wheel contents     the right files got in
#   3. clean install      it is genuinely self-contained
#
#   ./mcp_apps/tests/verify-package.sh
#
# Output goes to verify-package.log at the repo root (gitignored).
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1
REPO=$(pwd)

# Absolute, deliberately. Layer 3 does `cd /tmp` so the install check cannot
# accidentally import from the repo — a relative log path would follow it there
# and split the output across two files, with the half that matters in /tmp.
LOG="$REPO/verify-package.log"
: > "$LOG"
FAILED=0

say()  { echo "$*" | tee -a "$LOG"; }
head_() {
    say ""
    say "════════════════════════════════════════════════════════"
    say "▶ $*"
    say "════════════════════════════════════════════════════════"
}
run() {
    head_ "$*"
    "$@" >> "$LOG" 2>&1
    local rc=$?
    [ $rc -ne 0 ] && FAILED=1
    say "── exit code: $rc ──"
    return $rc
}
# For assertions rather than commands: prints a one-line verdict and records it.
check() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        printf '  %-48s ok\n' "$label" | tee -a "$LOG"
    else
        printf '  %-48s *** FAIL ***\n' "$label" | tee -a "$LOG"
        FAILED=1
    fi
}

# The interpreter matters more than it looks. `python3 -m venv` on macOS picks
# up Apple's bundled 3.9, and fastmcp requires >=3.10 — so pip reports
# "No matching distribution found for fastmcp", which says nothing about the
# real problem. Use the same interpreter the repo venv was built on.
PY="$REPO/venv/bin/python"
[ -x "$PY" ] || PY=python3

{
    echo "fink packaging verification — $(date)"
    echo "branch: $(git branch --show-current)  head: $(git rev-parse --short HEAD)"
    echo "python: $("$PY" -V 2>&1)"
} | tee -a "$LOG"

# ─────────────────────────────────────────────── layer 1: the source is correct
#
# Note where the detail goes. verify.sh writes its pytest output to its own
# verify-apps.log and only tees headers to stdout, so what lands here is a
# summary. On failure, verify-apps.log is the file with the traceback in it.
run ./mcp_apps/tests/verify.sh
if [ "$FAILED" -ne 0 ]; then
    say ""
    say "❌ verify.sh failed — stopping before the build."
    say "   Packaging a known-broken tree only produces a broken wheel."
    say "   Test detail is in verify-apps.log, not this file."
    exit 1
fi

# Both invocations. The suite imports the module, so it only ever exercises the
# package path — script mode is what Claude Desktop's config uses and is the
# thing deleting _bootstrap could have broken.
run "$PY" mcp_apps/server.py --selftest
run "$PY" -m mcp_apps.server --selftest

# ────────────────────────────────────────────────── layer 2: build and look in
run rm -rf dist build
run "$PY" -m build --wheel

WHL=$(ls dist/*.whl 2>/dev/null | head -1)
if [ -z "$WHL" ]; then
    say ""
    say "❌ no wheel produced — nothing further can be checked."
    exit 1
fi
say ""
say "built: $WHL"

head_ "wheel contents"
"$PY" - "$WHL" >> "$LOG" 2>&1 <<'PY'
import sys, zipfile, pathlib
z = zipfile.ZipFile(sys.argv[1]); names = z.namelist()
print(f"{len(names)} entries, "
      f"{sum(i.file_size for i in z.infolist())/1e6:.1f} MB uncompressed\n")
for n in sorted(names): print("   ", n)
print("\n--- METADATA ---")
meta = z.read([n for n in names if n.endswith('METADATA')][0]).decode()
for line in meta.splitlines():
    if line.startswith(('Name:', 'Version:', 'Requires-Python:', 'Requires-Dist:',
                        'License')):
        print("   ", line)
print("\n--- entry_points.txt ---")
print(z.read([n for n in names if n.endswith('entry_points.txt')][0]).decode())
print("--- WHEEL ---")
print(z.read([n for n in names if n.endswith('WHEEL')][0]).decode())
PY
say "── exit code: $? ──"

head_ "wheel contents — assertions"
"$PY" - "$WHL" 2>&1 <<'PY' | tee -a "$LOG"
import sys, zipfile, pathlib
names = zipfile.ZipFile(sys.argv[1]).namelist()
corpus = sorted(pathlib.Path(n).stem for n in names
                if 'local_av_cache/' in n and n.endswith('.json'))
mds = [n for n in names if n.endswith('.md')]
checks = [
    ("nine seed corpus JSONs",      len(corpus) == 9, " ".join(corpus)),
    ("no .db (developer's cache)",  not [n for n in names if n.endswith('.db')], ""),
    ("no tests/",                   not [n for n in names if 'mcp_apps/tests' in n], ""),
    ("no __pycache__",              not [n for n in names if '__pycache__' in n], ""),
    ("no sibling projects",         not [n for n in names if n.split('/')[0] in
        ('agent', 'gepa', 'mcp', 'open_webui', 'community_analysis')], ""),
    ("no _bootstrap.py",            not [n for n in names if '_bootstrap' in n], ""),
    ("only the user README ships",  mds == ['mcp_apps/README.md'], " ".join(mds)),
    ("tag is py3-none-any",         sys.argv[1].endswith('-py3-none-any.whl'), ""),
]
bad = 0
for label, ok, extra in checks:
    print(f"  {label:<48} {'ok' if ok else '*** FAIL ***'}  {extra}")
    bad += not ok
sys.exit(1 if bad else 0)
PY
[ "${PIPESTATUS[0]}" -ne 0 ] && FAILED=1

# verify.sh again: the wheel-dependent tests skipped the first time round,
# because dist/ did not exist yet. This is the run where they execute.
run ./mcp_apps/tests/verify.sh

# ──────────────────────────────────── layer 3: install with no repo in sight
VENV=$(mktemp -d)/fink-verify
head_ "clean venv at $VENV"
run "$PY" -m venv "$VENV"
run "$VENV/bin/pip" install -U pip
run "$VENV/bin/pip" install "$REPO/$WHL"

# `cd /tmp` is load-bearing, not tidiness. Run these from inside the repo and
# Python finds mcp_apps/ on the path whether or not the install worked, so the
# check passes for the wrong reason. From here, anything that runs came out of
# the wheel.
cd /tmp || exit 1

run "$VENV/bin/fink-scan" GOOGL
run "$VENV/bin/fink-apps" --selftest

head_ "runtime state landed outside the package"
DB_IN_PKG=$(find "$VENV" -name '*.db' 2>/dev/null)
if [ -n "$DB_IN_PKG" ]; then
    say "  *** FAIL *** cache written inside the installed package:"
    echo "$DB_IN_PKG" | sed 's/^/      /' | tee -a "$LOG"
    FAILED=1
else
    say "  no .db anywhere under site-packages               ok"
fi
"$VENV/bin/python" - 2>&1 <<'PY' | tee -a "$LOG"
import sys
from pathlib import Path

from mcp_apps.data import cache

db = cache.get_db_path().resolve()
pkg = Path(cache.__file__).resolve().parent
bad = 0
print(f"  resolved cache path: {db}")
for label, ok in (("outside the installed package", pkg not in db.parents),
                  ("data directory exists",         db.parent.is_dir()),
                  ("expected filename",             db.name == cache.DEFAULT_DB_NAME)):
    print(f"  {label:<48} {'ok' if ok else '*** FAIL ***'}")
    bad += not ok
sys.exit(1 if bad else 0)
PY
[ "${PIPESTATUS[0]}" -ne 0 ] && FAILED=1

cd "$REPO" || exit 1
rm -rf "$(dirname "$VENV")"

say ""
if [ "$FAILED" -eq 0 ]; then
    say "✅ Packaging verified — source, wheel contents, and a clean install."
    say "   This file: $LOG"
    say "   Test detail: verify-apps.log (from the second verify.sh run, where"
    say "   the wheel-dependent tests execute rather than skip)"
else
    say "❌ FAILURES present."
    say "   This file: $LOG   ·   test detail: verify-apps.log"
fi
exit "$FAILED"
