"""fink — conversational financial due diligence as an MCP App.

The single source of truth for the version. `pyproject.toml` reads
`__version__` through `[tool.setuptools.dynamic]`, and `server.py` reads it
rather than repeating it in the view's JS — so the version the panel reports to
the host is by construction the version that was installed.

`__commit__` exists because the distribution repo will hold no source (see
`phase10-PARKED-distribution.md`): a release tag there names a README commit,
not the code that shipped, so provenance has to travel inside the artifact. The
release script stamps it from `git rev-parse --short HEAD` immediately before
building and never commits the stamped value — a file cannot contain its own
SHA, so committing it would make this name the tagged commit's *parent*.

It stays "unknown" in git deliberately. A wheel built outside the release
script is then identifiable as such rather than quietly mislabelled.
"""
from __future__ import annotations

__version__ = "0.1.0"
__commit__ = "unknown"
