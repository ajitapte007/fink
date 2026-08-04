#!/usr/bin/env python3
"""Phase 0c — is FastMCPApp usable, or does Prefab lock us into declarative UI?

FastMCPApp's docstring says it binds "entry-point tools (@app.ui), backend
tools (@app.tool), and the Prefab renderer resource". The first two map exactly
onto what we want:

    @app.ui    -> scan_fundamentals, show_financial_dashboard   (model sees)
    @app.tool  -> get_metric_series                             (view only)

The open question is Prefab. Two possibilities:

  GOOD  Prefab is a thin HTML host - we hand it our own self-contained
        dashboard.html (Chart.js + chartUtils.js inlined) and it serves it
        at a ui:// URI. Then FastMCPApp saves us real work.

  BAD   Prefab is a declarative component renderer - we describe UI as a
        tree and it renders with its own widgets. That cannot run Chart.js
        or the 246 reused lines of chartUtils.js, so we ignore FastMCPApp
        and use plain FastMCP + meta= (proven working in check_app_param).

    cd ~/.gemini/antigravity/scratch/fink
    venv/bin/python mcp_apps/check_fastmcpapp.py
"""
from __future__ import annotations

import asyncio
import inspect
import json
import pkgutil
import traceback


def hr(t):
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


def show(label, obj, doclines=25):
    print(f"\n--- {label} ---")
    try:
        print(f"  signature: {inspect.signature(obj)}")
    except (TypeError, ValueError):
        pass
    doc = inspect.getdoc(obj)
    if doc:
        for line in doc.splitlines()[:doclines]:
            print(f"  {line}")


def main() -> int:
    import fastmcp
    from fastmcp import FastMCPApp
    print(f"fastmcp {getattr(fastmcp, '__version__', '?')}")

    hr("1. FastMCPApp surface")
    show("FastMCPApp.__init__", FastMCPApp.__init__)
    for name in ("ui", "tool", "resource", "prefab", "renderer", "html"):
        m = getattr(FastMCPApp, name, None)
        if m is not None:
            show(f"FastMCPApp.{name}", m)
    print("\n  public attrs:")
    print("   ", sorted(a for a in dir(FastMCPApp) if not a.startswith("_")))

    hr("2. What is Prefab?")
    try:
        import fastmcp.apps as apps_pkg
        print("  fastmcp.apps submodules:")
        for m in pkgutil.iter_modules(apps_pkg.__path__):
            print(f"    {m.name}")
    except Exception as e:
        print(f"  could not enumerate fastmcp.apps: {e}")

    prefab = None
    for path in ("fastmcp.apps.prefab", "fastmcp.apps.app", "fastmcp.prefab"):
        try:
            mod = __import__(path, fromlist=["*"])
        except Exception:
            continue
        names = [n for n in dir(mod) if "refab" in n or "ender" in n]
        if names:
            print(f"\n  {path} exports: {names}")
            for n in names:
                obj = getattr(mod, n)
                if inspect.isclass(obj) or inspect.isfunction(obj):
                    show(f"{path}.{n}", obj, doclines=30)
                    if prefab is None:
                        prefab = obj

    hr("3. THE DECIDING QUESTION: can we supply raw HTML?")
    print("""  Looking for a parameter like html=, template=, content=, src=,
  or a file path on either FastMCPApp.__init__ or @app.ui. If UI is
  described as a component tree instead, Chart.js cannot run.""")

    hits = []
    for label, fn in (("FastMCPApp.__init__", FastMCPApp.__init__),
                      ("FastMCPApp.ui", getattr(FastMCPApp, "ui", None))):
        if fn is None:
            continue
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            continue
        for p in params.values():
            if any(k in p.name.lower() for k in
                   ("html", "template", "content", "src", "file", "path",
                    "view", "render", "prefab", "asset", "static")):
                hits.append(f"{label}({p.name}: {p.annotation})")
    if hits:
        print("\n  candidate parameters found:")
        for h in hits:
            print(f"    {h}")
    else:
        print("\n  no obvious raw-HTML parameter on __init__ or ui()")

    hr("4. Live attempt: register a ui:// serving our own HTML")
    try:
        app = FastMCPApp(name="probe")
        print(f"  constructed: {app!r}")
        for attr in ("prefab", "renderer", "resource_uri", "uri", "html"):
            if hasattr(app, attr):
                print(f"    app.{attr} = {getattr(app, attr)!r}")
    except Exception as e:
        print(f"  FastMCPApp(name=...) failed: {type(e).__name__}: {e}")
        try:
            app = FastMCPApp("probe")
            print(f"  constructed positionally: {app!r}")
        except Exception as e2:
            print(f"  positional also failed: {type(e2).__name__}: {e2}")
            traceback.print_exc()
            return 1

    hr("VERDICT — read this")
    print("""  If section 3 or 4 shows a way to hand FastMCPApp our own HTML
  string or file, use FastMCPApp: @app.ui / @app.tool is exactly the
  visible / app-only split we designed, and it handles resource
  registration for us.

  If Prefab only accepts a component tree or its own DSL, ignore
  FastMCPApp entirely. Plain FastMCP + meta= is already proven working
  (check_app_param.py: resourceUri, visibility and mimeType all survive
  on the wire) and it is the only path that can run Chart.js plus the
  246 reused lines of chartUtils.js.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
