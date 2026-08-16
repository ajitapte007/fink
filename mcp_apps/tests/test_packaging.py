"""Packaging breaks quietly, and at other people's machines.

Two classes of failure live here. The first is drift between things that must
agree and have no reason to — the version in `__init__.py`, the version the
panel reports to the host, the dependency list, the package list. The second is
the wheel's *contents*, which nothing warns about: a `package-data` glob that
matches nothing produces no error, the build succeeds, the wheel installs, and
the failure surfaces at a user's machine as "every ticker says Could not scan".

The wheel-contents tests skip when `dist/` is absent rather than failing on a
dev machine that has not built one. The release script builds first, so they
are not skipped where it matters.
"""
from __future__ import annotations

import glob
import re
import zipfile
from pathlib import Path

import pytest

try:                                    # tomllib landed in 3.11
    import tomllib                      # and the declared floor is 3.10
except ModuleNotFoundError:             # ...so it is genuinely optional here
    tomllib = None

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
SERVER_SRC = (REPO / "mcp_apps" / "server.py").read_text()


def _code(src: str) -> str:
    """Source with comments and the module docstring removed.

    Both of those *describe* the things the tests below forbid — the docstring
    records that the FINK_SDK branch was removed, the comments explain why
    `_bootstrap` went. Matching raw text makes a test fail on its own
    documentation, which is a mistake this repo has made before and which
    reads as a real regression for as long as it takes to find.
    """
    parts = src.split('"""', 2)
    body = parts[2] if len(parts) == 3 else src        # drop the docstring
    return "\n".join(line.split("#")[0] for line in body.splitlines())


SERVER_CODE = _code(SERVER_SRC)


@pytest.fixture(scope="module")
def cfg() -> dict:
    assert PYPROJECT.exists(), "pyproject.toml is missing — the wheel cannot build"
    if tomllib is None:
        pytest.skip("needs tomllib (3.11+); the package itself supports 3.10")
    return tomllib.loads(PYPROJECT.read_text())


def _wheel() -> Path:
    hits = sorted(glob.glob(str(REPO / "dist" / "*.whl")))
    if not hits:
        pytest.skip("no wheel built; run `python -m build --wheel`")
    return Path(hits[-1])


# ------------------------------------------------------------------ the source
def test_version_is_single_sourced():
    """Two hand-maintained copies drift the first time one is bumped.

    The panel reporting a different version from the one installed is the kind
    of wrong that makes a bug report actively misleading.
    """
    from mcp_apps import __version__

    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__
    assert '"0.1.0"' not in SERVER_SRC, (
        "server.py has re-hardcoded a version literal; it must interpolate "
        "__version__ so the panel cannot disagree with the install")
    assert "{__version__}" in SERVER_SRC


def test_pyproject_reads_the_version_from_the_package(cfg):
    assert cfg["project"]["dynamic"] == ["version"]
    assert cfg["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "mcp_apps.__version__"}


def test_commit_defaults_to_unknown_in_git():
    """A wheel built outside the release script must be identifiable as such.

    Defaulting to a plausible-looking SHA would make an unstamped build
    indistinguishable from a stamped one — worse than no provenance at all.
    """
    from mcp_apps import __commit__

    assert __commit__ == "unknown"


def test_the_official_sdk_branch_is_gone():
    """Phase 10a removed it. A reintroduction means an undeclared dependency:
    `mcp` is not in `dependencies`, so the branch would fail only at import,
    and only for whoever set the env var.

    Matched against `_code`, not the raw source — the module docstring records
    that the branch was removed, and naive matching fails on that sentence.
    """
    assert "FINK_SDK" not in SERVER_CODE
    assert "from mcp.server" not in SERVER_CODE
    assert "from fastmcp import FastMCP" in SERVER_CODE


def test_bootstrap_is_gone_but_script_mode_survives():
    """The trap in deleting `_bootstrap`.

    The old block did two jobs: put `mcp/` on sys.path (dead) and put the repo
    root on sys.path (load-bearing). The second is what makes
    `python mcp_apps/server.py` work with no package context — which is what
    Claude Desktop's config does. Removing it yields ModuleNotFoundError at
    startup, and Claude Desktop reports a server that failed to start as
    nothing at all.

    The rest of the suite cannot catch this: it imports the module, so it only
    ever exercises the package path.
    """
    assert not (REPO / "mcp_apps" / "_bootstrap.py").exists()
    assert "_bootstrap" not in SERVER_CODE, "_bootstrap is still imported"
    assert '__package__ in (None, "")' in SERVER_CODE, (
        "the script-mode sys.path guard is gone; "
        "`python mcp_apps/server.py` will not start")


def test_declared_dependencies_match_what_is_imported(cfg):
    """An undeclared dependency installs fine and fails at first import."""
    declared = {re.split(r"[><=!\[]", d)[0].strip().lower()
                for d in cfg["project"]["dependencies"]}
    assert declared == {"fastmcp", "pydantic", "requests"}, declared

    src = "\n".join(p.read_text() for p in (REPO / "mcp_apps").rglob("*.py")
                    if "tests" not in p.parts)
    for pkg in declared:
        assert re.search(rf"^\s*(from|import)\s+{pkg}\b", src, re.M), \
            f"{pkg} is declared but never imported"


def test_every_console_script_target_exists(cfg):
    """A rename breaks the entry point silently — the wheel builds, installs,
    and the command dies with AttributeError at a user's machine."""
    import importlib

    for name, target in cfg["project"]["scripts"].items():
        mod_name, _, fn = target.partition(":")
        mod = importlib.import_module(mod_name)
        assert callable(getattr(mod, fn, None)), f"{name} -> {target} is not callable"


def test_package_list_excludes_the_siblings_and_the_tests(cfg):
    pkgs = set(cfg["tool"]["setuptools"]["packages"])
    assert pkgs == {"mcp_apps", "mcp_apps.data",
                    "mcp_apps.data.alphavantage", "mcp_apps.engine"}
    assert "mcp_apps.tests" not in pkgs


def test_the_readme_and_pyproject_agree_on_the_python_floor(cfg):
    """They had drifted: pyproject said 3.10, the README said 3.11+.

    Neither was wrong about the code — nothing here uses a 3.11 feature — but a
    README stricter than the metadata turns away users pip would have accepted,
    and a README looser than the metadata sends them into an install failure.
    """
    floor = cfg["project"]["requires-python"].lstrip(">=").strip()
    readme = (REPO / "mcp_apps" / "README.md").read_text()
    assert f"Python {floor}" in readme, (
        f"pyproject requires >={floor}; the README does not say so")


def test_package_data_globs_are_narrow(cfg):
    """The failure this file exists for.

    `mcp_apps/data/alphavantage_cache.db` is on disk. It is gitignored, so it
    never reached git — but a `*` glob would sweep it into the wheel and ship
    the developer's own fetch history to every user. Same for STATE.md under a
    `*.md` glob.
    """
    data = cfg["tool"]["setuptools"]["package-data"]
    assert data["mcp_apps.data.alphavantage"] == ["local_av_cache/*.json"]
    assert data["mcp_apps"] == ["README.md"]


# ------------------------------------------------------------------- the wheel
def test_the_cache_never_defaults_inside_the_package(monkeypatch):
    """Found by installing the wheel, not by any test — which is the point.

    `verify.sh` sets ALPHAVANTAGE_CACHE_DB to a temp file, so the default
    branch was never exercised until the package was installed and run from
    /tmp. It resolved to site-packages: runtime state written into installed
    code, which fails outright where site-packages is read-only and silently
    loses the cache under uvx's ephemeral environments.
    """
    from mcp_apps.data import cache

    monkeypatch.delenv("ALPHAVANTAGE_CACHE_DB", raising=False)
    db = cache.get_db_path().resolve()
    pkg = Path(cache.__file__).resolve().parent

    assert pkg not in db.parents, (
        f"cache defaults to {db}, which is inside the installed package")
    assert db.name == cache.DEFAULT_DB_NAME
    assert db.parent.is_dir(), "the data directory was not created"


def test_the_env_var_still_wins(monkeypatch, tmp_path):
    """The override is what lets tests isolate and lets a user share one file
    with the legacy server. It must beat the new default."""
    from mcp_apps.data import cache

    target = tmp_path / "explicit.db"
    monkeypatch.setenv("ALPHAVANTAGE_CACHE_DB", str(target))
    assert cache.get_db_path() == target


def test_wheel_is_pure_python():
    """py3-none-any is three claims: any Python 3, no compiled extension, any
    OS. One file covers macOS, Windows and Linux; losing it means a matrix."""
    assert _wheel().name.endswith("-py3-none-any.whl"), _wheel().name


def test_wheel_filename_matches_the_package_version():
    from mcp_apps import __version__

    assert f"-{__version__}-" in _wheel().name


def test_wheel_carries_the_whole_seed_corpus():
    """A glob that matched nothing gives a wheel that installs and then fails
    on every ticker."""
    from mcp_apps.data.alphavantage.fetch import available_seed_tickers

    names = zipfile.ZipFile(_wheel()).namelist()
    shipped = {Path(n).stem for n in names if "local_av_cache/" in n
               and n.endswith(".json")}
    assert shipped == available_seed_tickers(), (
        f"corpus in wheel: {sorted(shipped)}")


@pytest.mark.parametrize("pattern,why", [
    (".db", "the developer's local AlphaVantage cache"),
    ("mcp_apps/tests/", "a suite whose fixtures assume the repo layout"),
    ("__pycache__", "stale bytecode travelling with the source"),
    ("agent/", "an unrelated sibling project"),
    ("open_webui/", "an unrelated sibling project"),
])
def test_wheel_omits(pattern, why):
    hits = [n for n in zipfile.ZipFile(_wheel()).namelist() if pattern in n]
    assert not hits, f"wheel ships {why}: {hits[:5]}"


def test_the_only_markdown_in_the_wheel_is_the_user_readme():
    """Stated as a whitelist on purpose.

    A test asserting "no STATE.md" protects the file it names. This one
    protects documents that do not exist yet — which is the real failure mode,
    since the leak will come from a doc written months from now and swept in by
    a glob nobody re-read.
    """
    mds = [n for n in zipfile.ZipFile(_wheel()).namelist()
           if n.endswith(".md") and not n.startswith("fink_apps-")]
    assert mds == ["mcp_apps/README.md"], mds
