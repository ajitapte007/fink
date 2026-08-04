"""fink data layer — forked from mcp/data in phase 3.

Layout:
    config.py        FINK_DATA_MODE, logging, OfflineDataUnavailable
    cache.py         SQLite read-through cache, source-agnostic
    prices.py        live quote lookup (Yahoo)
    alphavantage/    the AV client, its five endpoints, and the seed corpus
    metrics.py       composite metrics aligned to the monthly price series
    identity.py      display strings for panel headers
    models.py        pydantic schemas
    adapters.py      the only coupling point to mcp_apps.engine

Import direction is downward: alphavantage/ imports cache and config, never
the reverse. See mcp_apps/data/README.md for the migration policy.
"""
