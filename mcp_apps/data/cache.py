"""SQLite read-through cache. Source-agnostic by design.

Split out of `fetch_utils.py` during the phase 3 fork. Nothing here knows what
Alpha Vantage is: the schema is (symbol, function) → blob, and "function" is
whatever string the vendor layer wants to key on. When EDGAR lands it uses this
table too.

This package owns its own database, in a per-user data directory — never
inside the package itself. See `get_db_path` for why that distinction is
load-bearing once the code is installed rather than cloned.

The legacy `mcp/` server has its own, and the two are independent — which is
what lets `mcp_apps` be packaged (uvx, a container) without depending on a path
outside itself. Sharing one file is still possible by pointing both at
ALPHAVANTAGE_CACHE_DB, but it is an explicit choice rather than something path
resolution arranges behind your back.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from .config import log_info

DEFAULT_DB_NAME = "alphavantage_cache.db"
APP_DIR_NAME = "fink"

# Set by init_db only when the per-user data directory cannot be created. Kept
# as module state so `get_db_path` can stay side-effect free while still
# reporting where the database actually ended up.
_fallback_dir: Path | None = None


def default_data_dir() -> Path:
    """Where this package keeps its own state, per-user and per-platform.

    Deliberately *data*, not *cache*, even though the file is named one. On
    macOS `~/Library/Caches` and on Linux `$XDG_CACHE_HOME` are both places the
    system may purge without asking. Rebuilding this file costs 5 Alpha Vantage
    calls per ticker against a free tier of 25 a day, so a purge is not a
    transparent slowdown — it is a day of not being able to scan.

    Hand-rolled rather than depending on `platformdirs`. Three branches of
    `os.environ` lookups against a package that currently declares three
    runtime dependencies total; a fourth would need to earn more than this.
    """
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    return Path(os.getenv("XDG_DATA_HOME") or home / ".local" / "share") / APP_DIR_NAME


def get_db_path() -> Path:
    """Resolve the cache database.

    1. $ALPHAVANTAGE_CACHE_DB, if set — tests, deployment, or deliberately
       sharing one file with the legacy server
    2. a per-user data directory (`default_data_dir`)
    3. a temp directory, but only if `init_db` already found rule 2 unwritable

    Pure: reads the environment and module state, touches no filesystem. The
    directory is created by `init_db`, which runs once at import; see there for
    why that separation matters.

    **Rule 2 used to be "next to this module", and that was a packaging bug.**
    In a clone it resolves to the project directory and is fine. Installed, it
    resolves *inside site-packages* — runtime state written into installed
    code. Three ways that bites: site-packages is read-only in managed and
    containerised environments, so every scan fails on write; an uninstall
    leaves an orphan file the package manager did not create; and `uvx`, the
    documented install path, runs from an ephemeral environment under
    `~/.cache/uv`, so the accumulated cache can vanish whenever uv rebuilds it.
    That last one is quiet and expensive, since re-fetching costs quota.

    The test suite could not have caught it: `verify.sh` sets
    ALPHAVANTAGE_CACHE_DB to a temp file per run — correct for tests, and it
    means rule 2 was never exercised until the wheel was installed and run.

    The legacy version had another rule between 1 and 2: probe
    `/app/backend/data/` and use it if writable. That path only exists inside
    the Open WebUI container, and this package never runs there — it is a stdio
    server launched by the MCP host. So the probe could not succeed, and since
    `get_db_cache` and `set_db_cache` each resolve the path afresh (12 times to
    load one ticker), every one of those calls attempted a mkdir and an sqlite
    connect against a directory that cannot exist before falling through.

    The env var is read *here* rather than at import time. It used to be a
    module-level constant, which meant the value was frozen by whichever module
    imported first: a test that set the variable in a fixture got the stale path
    and silently used the developer's real cache. Reading at call time costs one
    getenv per query and makes monkeypatching work.
    """
    env = os.getenv("ALPHAVANTAGE_CACHE_DB")
    if env:
        return Path(env)
    return (_fallback_dir or default_data_dir()) / DEFAULT_DB_NAME


def init_db():
    """Create the table, and the directory it lives in.

    Directory creation belongs *here*, not in `get_db_path`. Resolution has to
    stay a pure function of the environment: `get_db_cache` and `set_db_cache`
    each resolve afresh, twelve times to load one ticker, and a resolver with
    side effects is one that can fail for reasons unrelated to its answer.
    That is the same objection that retired the `/app/backend/data` probe, and
    the first version of this change walked straight back into it.

    This runs once, at import.
    """
    global _fallback_dir

    parent = get_db_path().parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if os.getenv("ALPHAVANTAGE_CACHE_DB"):
            # An explicit path is honoured or it fails. Silently redirecting
            # somewhere else would be worse than the error: the caller asked
            # for a specific file, quite possibly to share one with mcp/.
            raise
        # Read-only or absent home — a container, a locked-down account.
        # Degrade to a temp file rather than die: the seed corpus still has to
        # be loaded into SQLite for a scan to work at all, so no database means
        # no scan. Said out loud, because a cache that stops persisting looks
        # from the outside like the network being slow.
        _fallback_dir = Path(tempfile.gettempdir()) / APP_DIR_NAME
        _fallback_dir.mkdir(parents=True, exist_ok=True)
        log_info(f"cannot write {parent} ({e}); "
                 f"caching to {_fallback_dir} for this session only")

    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS av_cache (
            symbol TEXT,
            function TEXT,
            data TEXT,
            timestamp REAL,
            expires_at REAL,
            source TEXT,
            is_corrupt INTEGER DEFAULT 0,
            PRIMARY KEY (symbol, function)
        )
        """
    )
    # Upgrade old databases if columns don't exist
    for col, decl in (("expires_at", "REAL"),
                      ("source", "TEXT"),
                      ("is_corrupt", "INTEGER DEFAULT 0")):
        try:
            cursor.execute(f"ALTER TABLE av_cache ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def get_db_cache(symbol: str, function: str) -> tuple:
    """Returns (data, timestamp, expires_at, source, is_corrupt) or None."""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data, timestamp, expires_at, source, is_corrupt FROM av_cache "
            "WHERE symbol = ? AND function = ?",
            (symbol.upper(), function.upper())
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            data_str, timestamp, expires_at, source, is_corrupt = row
            # Upgrade legacy entries if columns are empty
            if expires_at is None:
                expires_at = timestamp + 86400 * 7
            if source is None:
                source = "api"
            if is_corrupt is None:
                is_corrupt = 0
            return json.loads(data_str), timestamp, expires_at, source, is_corrupt
    except Exception as e:
        log_info(f"SQLite read cache error: {e}")
    return None


def set_db_cache(symbol: str, function: str, data: dict, timestamp: float,
                 expires_at: float, source: str, is_corrupt: int = 0):
    """Writes to SQLite cache."""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO av_cache
                (symbol, function, data, timestamp, expires_at, source, is_corrupt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (symbol.upper(), function.upper(), json.dumps(data), timestamp,
             expires_at, source, is_corrupt)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log_info(f"SQLite write cache error: {e}")


# Auto-initialize on import, as the original did. Callers reach for get_db_cache
# without ceremony and the table has to exist by then.
init_db()
