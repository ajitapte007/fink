"""Pins the three `__file__`-relative paths the phase 3 split moved.

These are the part of the migration existing coverage was blind to. Function
signatures did not change and no caller changed, so every ported test kept
passing — but `CACHE_DIR`, its duplicate inside `available_seed_tickers`, and
the `get_db_path` fallback all resolve relative to the module that holds them,
and all three moved to different directories.

`mcp/tests/test_cache_flow.py` calls `get_db_path()` and uses whatever it
returns without asserting where it points, so a silently relocated database
would have passed there too.
"""
from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest

from mcp_apps.data import cache
from mcp_apps.data.alphavantage import fetch

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_cache_dir_sits_inside_the_alphavantage_package():
    """The corpus must live beside fetch.py, not where it used to.

    Before the split, `CACHE_DIR` resolved to `mcp/data/local_av_cache`. After,
    fetch.py lives one level deeper, so the corpus had to move with it. Get this
    wrong and the failure is quiet in the worst way: `get_local_json_cache`
    returns None for every ticker, seed mode raises OfflineDataUnavailable, and
    the message blames the ticker rather than the path.
    """
    assert fetch.CACHE_DIR == DATA_DIR / "alphavantage" / "local_av_cache"
    assert fetch.CACHE_DIR.is_dir(), f"{fetch.CACHE_DIR} does not exist"


def test_available_seed_tickers_agrees_with_the_files_on_disk():
    """The duplicated-path bug, made unrepeatable.

    `available_seed_tickers` used to rebuild `Path(__file__).parent /
    "local_av_cache"` inline instead of reading CACHE_DIR — the same path
    written twice. Move one and not the other and this function returns an empty
    set while `get_local_json_cache` keeps working, so seed mode reports "not in
    the corpus" for tickers that are sitting right there.
    """
    on_disk = {p.stem.upper() for p in fetch.CACHE_DIR.glob("*.json")}
    assert fetch.available_seed_tickers() == on_disk
    assert on_disk >= {"AAPL", "AMZN", "COST", "GOOGL", "NEE", "PG", "UNH", "WMT"}


def test_db_path_honours_the_env_var_at_call_time(tmp_path, monkeypatch):
    """The resolution order's first rule, and the reason it is not a constant.

    `ALPHAVANTAGE_CACHE_DB` used to be read into a module-level constant at
    import time, which froze it to whatever was set when the first importer ran.
    A fixture that set the variable afterwards got the stale value and quietly
    used the developer's real cache — the exact failure this suite's conftest
    would otherwise hit.
    """
    target = tmp_path / "somewhere-else.db"
    monkeypatch.setenv("ALPHAVANTAGE_CACHE_DB", str(target))
    assert cache.get_db_path() == target

    monkeypatch.setenv("ALPHAVANTAGE_CACHE_DB", str(tmp_path / "second.db"))
    assert cache.get_db_path() == tmp_path / "second.db", (
        "get_db_path cached the env var instead of re-reading it")


def test_db_path_falls_back_beside_the_cache_module(monkeypatch):
    """With no env var, this package owns a database inside itself.

    Self-containment is the property that makes `mcp_apps` packageable, and it
    is the reason the legacy `/app/backend/data` probe was removed: that path
    only exists inside the Open WebUI container, which this server never runs
    in.
    """
    monkeypatch.delenv("ALPHAVANTAGE_CACHE_DB", raising=False)
    resolved = cache.get_db_path()
    assert resolved == DATA_DIR / "alphavantage_cache.db"
    assert DATA_DIR in resolved.parents, (
        "the default cache must live inside the package, or mcp_apps cannot be "
        "shipped as a self-contained unit")


def test_db_path_does_not_touch_the_filesystem_to_decide(monkeypatch, tmp_path):
    """Resolution is a pure function of the environment.

    The removed container probe ran `mkdir` and an sqlite `connect` on every
    call just to pick a path — and `get_db_cache`/`set_db_cache` resolve afresh
    each time, 12 times to load a single ticker. Beyond the waste, a resolver
    with side effects is one that can fail for reasons unrelated to its answer.
    """
    import os

    monkeypatch.delenv("ALPHAVANTAGE_CACHE_DB", raising=False)
    before = set(os.listdir(tmp_path))
    monkeypatch.chdir(tmp_path)
    for _ in range(5):
        cache.get_db_path()
    assert set(os.listdir(tmp_path)) == before, (
        "get_db_path created something on disk; it should only read env")


def test_sharing_with_the_legacy_server_is_opt_in(tmp_path, monkeypatch):
    """Both servers can share one file, but only when told to.

    The fork owns its own cache by default so it stays self-contained. Pointing
    both at one path is still supported — that is what the env var is for — and
    it is the only way to get sharing, rather than something path resolution
    arranges implicitly.
    """
    shared = tmp_path / "shared.db"
    monkeypatch.setenv("ALPHAVANTAGE_CACHE_DB", str(shared))
    assert cache.get_db_path() == shared
    monkeypatch.delenv("ALPHAVANTAGE_CACHE_DB")
    assert cache.get_db_path() != shared


def test_init_db_creates_a_usable_schema(tmp_path, monkeypatch):
    """init_db runs at import; prove the table it makes is the one queried."""
    monkeypatch.setenv("ALPHAVANTAGE_CACHE_DB", str(tmp_path / "fresh.db"))
    cache.init_db()
    con = sqlite3.connect(str(cache.get_db_path()))
    cols = {r[1] for r in con.execute("PRAGMA table_info('av_cache')")}
    con.close()
    assert cols == {"symbol", "function", "data", "timestamp",
                    "expires_at", "source", "is_corrupt"}


def test_import_direction_is_one_way():
    """`alphavantage/` may import upward; the package above must not import down.

    The split is only worth anything if the dependency arrow stays pointed one
    way. If `cache.py` or `config.py` ever reaches into the vendor package, the
    'source-agnostic' claim is false and adding EDGAR means untangling it.
    """
    for modname in ("mcp_apps.data.cache", "mcp_apps.data.config",
                    "mcp_apps.data.prices"):
        src = Path(importlib.import_module(modname).__file__).read_text()
        assert "alphavantage" not in src.replace("alphavantage_cache.db", ""), (
            f"{modname} references the alphavantage package — the split's "
            f"import direction has been violated")
