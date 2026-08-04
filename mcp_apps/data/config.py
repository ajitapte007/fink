"""Process-wide data configuration. No vendor knows about this module's callers.

Split out of `fetch_utils.py` during the phase 3 fork. Everything here is
source-agnostic: it applies equally to Alpha Vantage, to SEC EDGAR when that
lands, and to anything after.
"""
from __future__ import annotations

import os
import sys


class OfflineDataUnavailable(RuntimeError):
    """Raised when seed mode is active and the requested data isn't available locally."""


def get_data_mode() -> str:
    """Where financial data may come from. Set via the FINK_DATA_MODE env var.

    "live" (default) — SQLite cache → seed JSON → AlphaVantage network.
    "seed"           — SQLite cache → seed JSON → raise. Never touches the network.

    Seed mode exists because `mock_data=True` was never sufficient to keep tests
    offline: it only *prefers* the seed corpus, and falls through to the live API for
    any ticker not in the seed corpus. That made the suite hit AlphaVantage for
    cases like INVALIDTICKER12345 — burning daily quota, writing junk rows into the
    shared cache, and making runtime depend on rate limiting (one run took 4m10s vs 42s).

    `mcp_apps/tests/conftest.py` forces "seed", so tests are offline however they're
    invoked. Production sets FINK_DATA_MODE=live in docker-compose.yml.

    Read at call time, not import time, so a test can change it with monkeypatch.
    """
    return os.getenv("FINK_DATA_MODE", "live").strip().lower()


def log_info(msg: str):
    """stderr, unbuffered. stdout belongs to the MCP stdio transport — anything
    written there corrupts the JSON-RPC stream and the host disconnects."""
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()
