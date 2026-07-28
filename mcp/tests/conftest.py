"""Pytest configuration for the mcp/ test suite.

Puts `mcp/` on sys.path so test modules can `import data.*`, `import visualization.*`,
and `import metrics_registry` regardless of the directory pytest is invoked from.

Previously each test file hand-rolled its own sys.path.insert, and four of them
never did — so the suite could only be run file-by-file or with PYTHONPATH set
externally. Those per-file inserts are now redundant but harmless.

Note this cannot be a root-level pytest.ini: the repository also contains the
independent `agent/` and `community_analysis/` sub-projects, which have their own
layouts and should not inherit this path configuration.
"""
import os
import sys
from pathlib import Path

MCP_DIR = Path(__file__).parent.parent.resolve()
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

# Force offline data for the whole suite, before any module imports fetch_utils.
# Set here rather than in a wrapper script so it holds however pytest is invoked — a
# bare `pytest mcp/tests/` must not reach AlphaVantage either.
#
# `mock_data=True` alone was never enough: it only *prefers* the seed corpus and falls
# through to the live API for tickers it doesn't have. Seed mode makes that a hard error.
os.environ.setdefault("FINK_DATA_MODE", "seed")


def pytest_configure(config):
    """Register custom marks used across the suite."""
    config.addinivalue_line(
        "markers", "e2e: end-to-end test requiring the Open WebUI container to be running"
    )
    config.addinivalue_line(
        "markers", "network: test that makes live network calls (MCP server or external API)"
    )
