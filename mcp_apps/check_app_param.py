#!/usr/bin/env python3
"""Phase 0b — investigate fastmcp's native `app=` parameter.

check_sdk.py showed both SDKs preserve a hand-written meta= dict, and that
fastmcp 3.4.4 additionally exposes:

    tool(..., app: 'AppConfig | dict[str, Any] | bool | None' = None, ...)
    resource(..., app: 'AppConfig | dict[str, Any] | bool | None' = None, ...)

That looks like purpose-built MCP Apps support. If so we should use it instead
of hand-rolling _meta, and it may also explain why the probe reported the
resource mimeType as None -- the earlier check read attributes off the registry
object, not off the wire.

This script does two things the first one did not:

  1. introspects AppConfig to see what it actually accepts
  2. uses fastmcp's in-memory Client to make REAL tools/list, resources/list
     and resources/read calls, so we see the wire payload the host will see

    cd ~/.gemini/antigravity/scratch/fink
    venv/bin/python mcp_apps/check_app_param.py
"""
from __future__ import annotations

import asyncio
import inspect
import json
import traceback

URI = "ui://fink/probe"
MIME = "text/html;profile=mcp-app"
HTML = "<h1>hello</h1>"


def hr(t=""):
    print(f"\n{'=' * 72}")
    if t:
        print(t)
        print("=" * 72)


def find_appconfig():
    """AppConfig moved around across fastmcp versions; look in the likely spots."""
    import fastmcp
    for path in ("AppConfig",):
        if hasattr(fastmcp, path):
            return getattr(fastmcp, path), f"fastmcp.{path}"
    for mod in ("fastmcp.server", "fastmcp.tools", "fastmcp.resources",
                "fastmcp.server.app", "fastmcp.utilities.types",
                "fastmcp.tools.tool", "fastmcp.resources.resource"):
        try:
            m = __import__(mod, fromlist=["AppConfig"])
        except Exception:
            continue
        if hasattr(m, "AppConfig"):
            return getattr(m, "AppConfig"), f"{mod}.AppConfig"
    return None, None


def describe_appconfig():
    hr("1. AppConfig")
    cls, where = find_appconfig()
    if cls is None:
        print("  not found by import; inspecting the annotation instead")
        import fastmcp
        ann = inspect.signature(fastmcp.FastMCP.tool).parameters["app"].annotation
        print(f"  tool(app=) annotation: {ann}")
        return None
    print(f"  found at: {where}")
    print(f"  {cls}")
    if hasattr(cls, "model_fields"):                      # pydantic
        for name, f in cls.model_fields.items():
            print(f"    {name:24} {f.annotation}   default={f.default!r}")
    else:
        print(f"    signature: {inspect.signature(cls)}")
    doc = inspect.getdoc(cls)
    if doc:
        print("  docstring:")
        for line in doc.splitlines()[:12]:
            print(f"    {line}")
    return cls


def build_variants():
    """Register the same view four ways so we can compare the wire output."""
    import fastmcp
    s = fastmcp.FastMCP("probe")

    # A: hand-written _meta, what the plan currently assumes
    @s.tool(meta={"ui": {"resourceUri": URI}, "ui/resourceUri": URI})
    def tool_handmeta(ticker: str = "AMZN") -> dict:
        """Hand-written _meta."""
        return {"ticker": ticker}

    # B: native app= with the resource uri
    try:
        @s.tool(app={"resourceUri": URI})
        def tool_appdict(ticker: str = "AMZN") -> dict:
            """app= as a dict."""
            return {"ticker": ticker}
    except Exception as e:
        print(f"  tool(app=dict) raised: {type(e).__name__}: {e}")

    # C: app=True, whatever that defaults to
    try:
        @s.tool(app=True)
        def tool_apptrue(ticker: str = "AMZN") -> dict:
            """app=True."""
            return {"ticker": ticker}
    except Exception as e:
        print(f"  tool(app=True) raised: {type(e).__name__}: {e}")

    # D: hidden tool, hand-written
    @s.tool(meta={"ui": {"visibility": ["app"]}})
    def tool_hidden(ticker: str = "AMZN") -> dict:
        """Should be hidden from the model."""
        return {"ticker": ticker}

    # resources: mime_type only vs mime_type + app=
    @s.resource(URI, mime_type=MIME)
    def res_mimeonly() -> str:
        return HTML

    try:
        @s.resource(URI + "-app", mime_type=MIME, app=True)
        def res_withapp() -> str:
            return HTML
    except Exception as e:
        print(f"  resource(app=True) raised: {type(e).__name__}: {e}")

    return s


async def wire_check(server):
    """Use the in-memory Client so we see exactly what a host would receive."""
    hr("2. WIRE PAYLOAD (in-memory client -> real list/read calls)")
    try:
        from fastmcp import Client
    except ImportError:
        print("  fastmcp.Client not available; skipping")
        return

    async with Client(server) as c:
        tools = await c.list_tools()
        print(f"\n  tools/list returned {len(tools)}:")
        for t in tools:
            meta = getattr(t, "meta", None) or getattr(t, "_meta", None)
            try:
                d = t.model_dump(by_alias=True)
                meta = d.get("_meta", meta)
            except Exception:
                pass
            print(f"    {t.name:18} _meta={json.dumps(meta, default=str)}")

        resources = await c.list_resources()
        print(f"\n  resources/list returned {len(resources)}:")
        for r in resources:
            mt = getattr(r, "mimeType", None) or getattr(r, "mime_type", None)
            meta = getattr(r, "meta", None) or getattr(r, "_meta", None)
            try:
                d = r.model_dump(by_alias=True)
                mt = d.get("mimeType", mt)
                meta = d.get("_meta", meta)
            except Exception:
                pass
            print(f"    {str(r.uri):24} mimeType={mt!r}")
            if meta:
                print(f"      _meta={json.dumps(meta, default=str)}")

        print(f"\n  resources/read {URI}:")
        try:
            content = await c.read_resource(URI)
            for item in content:
                mt = getattr(item, "mimeType", None) or getattr(item, "mime_type", None)
                text = getattr(item, "text", None)
                print(f"    mimeType={mt!r}")
                print(f"    text={text!r}")
                if mt == MIME:
                    print("    -> MIME SURVIVED ON THE WIRE. This is what matters.")
                else:
                    print(f"    -> mimeType is {mt!r}, not {MIME!r}")
        except Exception as e:
            print(f"    read failed: {type(e).__name__}: {e}")


async def main() -> int:
    import fastmcp
    print(f"fastmcp {getattr(fastmcp, '__version__', '?')}")
    describe_appconfig()

    hr("registering variants")
    try:
        server = build_variants()
    except Exception:
        traceback.print_exc()
        return 1

    await wire_check(server)

    hr("WHAT TO LOOK FOR")
    print("""  1. Does resources/read return mimeType 'text/html;profile=mcp-app'?
     If yes, the earlier FAIL was my probe reading the registry object
     rather than the wire, and nothing needs fixing.

  2. Does tool_appdict / tool_apptrue produce the same _meta shape as
     tool_handmeta? If the SDK emits a richer or differently-keyed _meta,
     prefer app= and drop the hand-written dicts from the plan.

  3. Does tool_hidden's _meta carry visibility=['app'] on the wire?
     That is what makes get_metric_series invisible to the model.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
