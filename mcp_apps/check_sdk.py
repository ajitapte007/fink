#!/usr/bin/env python3
"""Phase 0 — decide which SDK mcp_apps/server.py is built on.

MCP Apps needs two things the plain tool API does not provide:

  1. `_meta.ui.resourceUri` on a tool   -> links the tool to its ui:// view
  2. `_meta.ui.visibility = ["app"]`    -> hides a tool from the model
  3. a resource with mimeType "text/html;profile=mcp-app"

Two SDKs are installed and pinned in mcp/requirements.txt:

  A) fastmcp 3.4.4              standalone; what mcp/server.py already uses
  B) mcp 1.28.1                 official SDK, mcp.server.fastmcp

This does NOT just inspect signatures. A `**kwargs` signature would accept
`meta=` and silently discard it. So it registers a real tool and a real
resource, then reads them back out of the server and checks the metadata
actually survived.

    cd ~/.gemini/antigravity/scratch/fink
    venv/bin/python mcp_apps/check_sdk.py
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import traceback

RESOURCE_URI = "ui://fink/probe"
MIME = "text/html;profile=mcp-app"
TOOL_META = {"ui": {"resourceUri": RESOURCE_URI}, "ui/resourceUri": RESOURCE_URI}
HIDDEN_META = {"ui": {"visibility": ["app"]}}


def _sig(fn) -> str:
    try:
        return str(inspect.signature(fn))
    except (TypeError, ValueError):
        return "<unavailable>"


def _accepts_meta(fn) -> str:
    """'yes' | 'via **kwargs' | 'no'"""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return "unknown"
    if "meta" in params:
        return "yes"
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return "via **kwargs"
    return "no"


async def _list_tools(server) -> list:
    """Tool listing moved around across versions; try the known accessors."""
    for attr in ("list_tools", "get_tools"):
        fn = getattr(server, attr, None)
        if fn is None:
            continue
        try:
            out = fn()
            if inspect.isawaitable(out):
                out = await out
            return list(out.values()) if isinstance(out, dict) else list(out)
        except Exception:
            continue
    mgr = getattr(server, "_tool_manager", None)
    if mgr is not None:
        for attr in ("list_tools", "get_tools"):
            fn = getattr(mgr, attr, None)
            if fn is None:
                continue
            try:
                out = fn()
                if inspect.isawaitable(out):
                    out = await out
                return list(out.values()) if isinstance(out, dict) else list(out)
            except Exception:
                continue
    return []


async def _list_resources(server) -> list:
    for attr in ("list_resources", "get_resources"):
        fn = getattr(server, attr, None)
        if fn is None:
            continue
        try:
            out = fn()
            if inspect.isawaitable(out):
                out = await out
            return list(out.values()) if isinstance(out, dict) else list(out)
        except Exception:
            continue
    mgr = getattr(server, "_resource_manager", None)
    if mgr is not None:
        for attr in ("list_resources", "get_resources"):
            fn = getattr(mgr, attr, None)
            if fn is None:
                continue
            try:
                out = fn()
                if inspect.isawaitable(out):
                    out = await out
                return list(out.values()) if isinstance(out, dict) else list(out)
            except Exception:
                continue
    return []


def _read_meta(obj):
    """Tool metadata lands on `meta` or `_meta` depending on SDK and version."""
    for attr in ("meta", "_meta"):
        v = getattr(obj, attr, None)
        if v:
            return v
    dump = getattr(obj, "model_dump", None)
    if dump:
        try:
            d = dump(by_alias=True)
            return d.get("_meta") or d.get("meta")
        except Exception:
            pass
    return None


def _name_of(obj):
    return getattr(obj, "name", None) or getattr(obj, "uri", None) or repr(obj)


async def probe(label: str, make_server) -> dict:
    result = {"label": label, "ok": False, "notes": []}
    try:
        server, tool_dec, res_dec, version = make_server()
    except Exception as e:
        result["notes"].append(f"could not construct: {type(e).__name__}: {e}")
        return result

    result["version"] = version
    result["tool_sig"] = _sig(tool_dec)
    result["resource_sig"] = _sig(res_dec)
    result["tool_meta_param"] = _accepts_meta(tool_dec)
    result["resource_meta_param"] = _accepts_meta(res_dec)

    # --- register a visible tool carrying ui.resourceUri -------------------
    try:
        @tool_dec(meta=TOOL_META)
        def probe_visible(ticker: str = "AMZN") -> dict:
            """Probe tool with a ui:// resource link."""
            return {"ticker": ticker}
        result["notes"].append("registered visible tool with meta=")
    except Exception as e:
        result["notes"].append(f"tool(meta=) raised: {type(e).__name__}: {e}")

    # --- register an app-only tool ----------------------------------------
    try:
        @tool_dec(meta=HIDDEN_META)
        def probe_hidden(ticker: str = "AMZN") -> dict:
            """Probe tool that should be hidden from the model."""
            return {"ticker": ticker}
        result["notes"].append("registered app-only tool with meta=")
    except Exception as e:
        result["notes"].append(f"hidden tool(meta=) raised: {type(e).__name__}: {e}")

    # --- register the ui:// resource --------------------------------------
    for kwargs in ({"mime_type": MIME}, {"mimeType": MIME}, {}):
        try:
            @res_dec(RESOURCE_URI, **kwargs)
            def probe_resource() -> str:
                return "<h1>hello</h1>"
            result["resource_kwarg"] = next(iter(kwargs), "(none accepted)")
            result["notes"].append(f"registered resource with {kwargs or 'no mime kwarg'}")
            break
        except Exception as e:
            result["notes"].append(f"resource({kwargs}) raised: {type(e).__name__}: {e}")
    else:
        result["resource_kwarg"] = None

    # --- read it back: did the metadata survive? --------------------------
    tools = await _list_tools(server)
    result["tools_found"] = [_name_of(t) for t in tools]
    for t in tools:
        n = _name_of(t)
        m = _read_meta(t)
        if n == "probe_visible":
            result["visible_meta"] = m
            result["resourceUri_survived"] = bool(
                m and (m.get("ui", {}) or {}).get("resourceUri") == RESOURCE_URI)
        if n == "probe_hidden":
            result["hidden_meta"] = m
            result["visibility_survived"] = bool(
                m and (m.get("ui", {}) or {}).get("visibility") == ["app"])

    resources = await _list_resources(server)
    result["resources_found"] = [str(_name_of(r)) for r in resources]
    for r in resources:
        if RESOURCE_URI in str(_name_of(r)):
            mt = getattr(r, "mime_type", None) or getattr(r, "mimeType", None)
            result["resource_mime"] = mt
            result["mime_survived"] = mt == MIME

    result["ok"] = bool(result.get("resourceUri_survived"))
    return result


def build_fastmcp():
    import fastmcp
    s = fastmcp.FastMCP("probe")
    return s, s.tool, s.resource, getattr(fastmcp, "__version__", "?")


def build_official():
    from mcp.server.fastmcp import FastMCP
    import mcp as mcp_pkg
    s = FastMCP("probe")
    return s, s.tool, s.resource, getattr(mcp_pkg, "__version__", "?")


def render(r: dict) -> None:
    print(f"\n{'=' * 72}\n{r['label']}   version={r.get('version','?')}\n{'=' * 72}")
    print(f"  tool()      {r.get('tool_sig','-')}")
    print(f"  resource()  {r.get('resource_sig','-')}")
    print(f"  meta= param on tool:     {r.get('tool_meta_param','-')}")
    print(f"  meta= param on resource: {r.get('resource_meta_param','-')}")
    print(f"  resource mime kwarg:     {r.get('resource_kwarg','-')}")
    print()
    print(f"  BEHAVIOUR (what actually survived registration)")
    print(f"    _meta.ui.resourceUri      {'PASS' if r.get('resourceUri_survived') else 'FAIL'}")
    print(f"    _meta.ui.visibility       {'PASS' if r.get('visibility_survived') else 'FAIL'}")
    print(f"    resource mimeType         {'PASS' if r.get('mime_survived') else 'FAIL'}"
          f"   (got {r.get('resource_mime')!r})")
    print()
    print(f"  tools registered:     {r.get('tools_found', [])}")
    print(f"  resources registered: {r.get('resources_found', [])}")
    if r.get("visible_meta") is not None:
        print(f"  visible tool _meta:   {json.dumps(r['visible_meta'], default=str)}")
    if r.get("notes"):
        print("  notes:")
        for n in r["notes"]:
            print(f"    - {n}")


async def main() -> int:
    try:
        import mcp as mcp_pkg
        origin = getattr(mcp_pkg, "__file__", None) or (
            "namespace: " + str(list(getattr(mcp_pkg, "__path__", []))))
        print(f"import mcp -> {origin}")
        if "site-packages" not in str(origin):
            print("  WARNING: that is not the SDK. Either mcp/__init__.py came")
            print("  back, or the SDK is not installed in this interpreter.")
    except ImportError:
        print("import mcp -> NOT FOUND (SDK not installed in this interpreter)")

    results = []
    for label, builder in (("A) fastmcp (standalone)", build_fastmcp),
                           ("B) mcp.server.fastmcp (official SDK)", build_official)):
        try:
            results.append(await probe(label, builder))
        except Exception:
            print(f"\n{label}: probe crashed")
            traceback.print_exc()
            results.append({"label": label, "ok": False, "notes": ["crashed"]})

    for r in results:
        render(r)

    print(f"\n{'=' * 72}\nVERDICT\n{'=' * 72}")
    winners = [r for r in results if r.get("ok")]
    if not winners:
        print("  Neither SDK preserved _meta.ui.resourceUri.")
        print("  -> Fall back to mcp.server.lowlevel.Server and hand-build")
        print("     list_tools()/list_resources() with _meta in the dicts.")
        print("     Plan section 1, third row of the decision table.")
        return 1
    if any("fastmcp (standalone)" in r["label"] for r in winners):
        print("  USE: fastmcp (standalone).")
        print("  Same SDK as mcp/server.py, no name collision, one less variable.")
    else:
        print("  USE: mcp.server.fastmcp (official SDK).")
        print("  Standalone fastmcp did not preserve the metadata.")
    for r in winners:
        if not r.get("visibility_survived"):
            print(f"  NOTE ({r['label']}): visibility=['app'] did NOT survive.")
            print("    get_metric_series will be model-visible. Harmless for the")
            print("    prototype, but the bulk series will reach the model.")
        if not r.get("mime_survived"):
            print(f"  NOTE ({r['label']}): resource mimeType did not stick as")
            print(f"    '{MIME}'. The host may not treat it as an MCP App.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
