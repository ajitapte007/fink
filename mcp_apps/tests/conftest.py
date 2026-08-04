"""Pytest configuration for the mcp_apps suite.

Deliberately not a copy of `mcp/tests/conftest.py`. Three differences, each for
a reason:

1. It puts the *repo root* on sys.path, not `mcp/`. Tests import
   `mcp_apps.data.…` by its full path. Both trees contain a package called
   `data`, and an unqualified `import data.x` would resolve by sys.path order —
   silently testing whichever tree happened to come first.

2. No FINK_STATIC_DIR. That exists in the legacy suite because rendering a
   chart writes `open_webui/static/{ticker}-data.json` into the working tree.
   Nothing here writes chart JSON.

3. The SQLite cache is redirected to a per-session temp file. The legacy suite
   shares the developer's real cache, so a stale row can make a test pass that
   should fail. Here every run starts empty and populates from the seed corpus,
   which is the only thing checked into git.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Force offline data before any module imports the fetch layer. Set here rather
# than in a wrapper script so it holds however pytest is invoked — a bare
# `pytest mcp_apps/tests/` must not reach AlphaVantage either.
#
# `mock_data=True` alone was never enough: it only *prefers* the seed corpus and
# falls through to the live API for tickers it doesn't have. Seed mode makes
# that a hard error.
os.environ["FINK_DATA_MODE"] = "seed"

# Isolate the cache. Must be set before `mcp_apps.data.cache` is imported,
# because that module calls init_db() at import time.
_TMP_DB = Path(tempfile.mkdtemp(prefix="fink-apps-cache-")) / "test_cache.db"
os.environ["ALPHAVANTAGE_CACHE_DB"] = str(_TMP_DB)

import pytest  # noqa: E402

SEED_TICKERS = ["AAPL", "AMZN", "COST", "GOOGL", "NEE", "PG", "UNH", "WMT"]


@pytest.fixture(autouse=True)
def no_live_quotes(monkeypatch):
    """Neutralise the Yahoo call for every test.

    `get_aligned_historical_data` appends a row dated *today* carrying the live
    quote. Left alone, half this suite would depend on the network and on the
    calendar: series lengths would differ between a laptop and CI, and any
    assertion about the last row would be checking today's market.

    Patched at the definition site (`data.prices`) because the import in
    `metrics.py` is function-local.
    """
    from mcp_apps.data import prices
    monkeypatch.setattr(prices, "get_latest_yahoo_price", lambda _t: None)


@pytest.fixture(scope="session")
def raw_cache():
    """{ticker: raw AV payloads}, fetched once for the whole session.

    Loading nine tickers costs a few seconds of JSON parsing; doing it per-test
    dominates the runtime of the suite.
    """
    from mcp_apps.data.cache_orchestrator import cache_ticker_data
    out = {}
    for t in SEED_TICKERS:
        res = cache_ticker_data(t)
        assert not res.get("error"), f"{t}: {res.get('error')}"
        out[t] = res["raw_cache"]
    return out


@pytest.fixture(scope="session")
def companies():
    """{ticker: engine.Company}, built once."""
    from mcp_apps.data import adapters
    return {t: adapters.load_company(t) for t in SEED_TICKERS}


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: exercises all seed tickers end to end")
