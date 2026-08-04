"""Import-path setup. Import this first from every module in mcp_apps.

Puts `mcp/` on sys.path so sibling imports resolve — `from data.cache_orchestrator
import …`, `from metrics_registry import …` — exactly as mcp/server.py,
mcp/visualization/visualization_tool.py and mcp/tests/conftest.py already do.

This used to also need to evict a shadowed `mcp` package: mcp/__init__.py made
the directory a regular package named `mcp`, which beat the pip SDK whenever the
repo root was on sys.path. That file was deleted 2026-08-03, so `mcp/` is now a
namespace portion and the real package wins from any position. Nothing here has
to defend against it.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEGACY_MCP = REPO_ROOT / "mcp"

if str(LEGACY_MCP) not in sys.path:
    sys.path.insert(0, str(LEGACY_MCP))
