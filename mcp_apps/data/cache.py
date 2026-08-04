"""SQLite read-through cache. Source-agnostic by design.

Split out of `fetch_utils.py` during the phase 3 fork. Nothing here knows what
Alpha Vantage is: the schema is (symbol, function) → blob, and "function" is
whatever string the vendor layer wants to key on. When EDGAR lands it uses this
table too.

This package owns its own database. The legacy `mcp/` server has its own, and
the two are independent — which is what lets `mcp_apps` be packaged (uvx, a
container) without depending on a path outside itself. Sharing one file is
still possible by pointing both at ALPHAVANTAGE_CACHE_DB, but it is an explicit
choice rather than something path resolution arranges behind your back.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from .config import log_info

DEFAULT_DB_NAME = "alphavantage_cache.db"


def get_db_path() -> Path:
    """Resolve the cache database.

    1. $ALPHAVANTAGE_CACHE_DB, if set — tests, deployment, or deliberately
       sharing one file with the legacy server
    2. next to this module

    The legacy version had a third rule between these two: probe
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
    return Path(env) if env else Path(__file__).parent / DEFAULT_DB_NAME


def init_db():
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
