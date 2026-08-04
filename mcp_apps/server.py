#!/usr/bin/env python3
"""fink MCP Apps server.

PHASE 2 COMPLETE — a ui:// resource renders in Claude Desktop, the guest
completes the ui/initialize handshake, and the host delivers the tool result
into the iframe via ontoolresult.

What phase 2 established, by experiment rather than by reading docs:

  1. A VIEW MUST CALL App.connect() OR IT WILL NEVER DISPLAY.
     This is the whole reason the first attempt failed. The host fetches the
     resource, receives the HTML, and then holds the iframe hidden waiting for
     the guest to signal readiness. A view with no JavaScript never signals,
     so it never appears. The log signature is distinctive and worth
     remembering: a successful `resources/read` followed by silence.
     There is no such thing as a static MCP App panel.

  2. Resource URI naming is free. `ui://fink/hello` renders exactly as well as
     `ui://fink/hello.html`, despite every published example using a .html
     suffix. Bisected 2026-08-03.

  3. `visibility: ["model"]` on an entry-point tool is harmless. Also bisected;
     it was a suspect and is not.

  4. `visibility: ["app"]` IS honoured — fink_echo never appears in Claude's
     tool list. That makes the app-only data path viable: bulk series can go to
     the view without passing through the model's context.

  5. CSP `resourceDomains` is honoured — the unpkg import of the ext-apps SDK
     succeeds when declared, and the sandbox blocks it when not.

  6. Standalone fastmcp and the official SDK behave identically here. fastmcp
     is used because mcp/server.py already depends on it.

Still unproven, and the first thing phase 3 tests: app.callServerTool().

    venv/bin/python mcp_apps/server.py --selftest   # wire payload, no Claude
    venv/bin/python mcp_apps/server.py --stdio      # for Claude Desktop
"""
from __future__ import annotations

# Must precede any sibling import. Works both as `python -m mcp_apps.server`
# (package context, relative import) and `python mcp_apps/server.py` (no
# package context, so put the repo root on sys.path and import absolutely).
try:
    from . import _bootstrap  # noqa: F401
except ImportError:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from mcp_apps import _bootstrap  # noqa: F401

import argparse
import asyncio
import json
import os
import sys

SERVER_NAME = "fink-apps"
APP_MIME = "text/html;profile=mcp-app"
HELLO_URI = "ui://fink/hello"

# The ext-apps guest SDK. Loaded from unpkg for now; phase 7 vendors it
# alongside Chart.js so the view has no network dependency inside the sandbox.
EXT_APPS = "https://unpkg.com/@modelcontextprotocol/ext-apps@1.7.0/app-with-deps"
EXT_APPS_ORIGIN = "https://unpkg.com"

#   FINK_SDK=fastmcp   standalone fastmcp 3.4.4  (default, matches mcp/server.py)
#   FINK_SDK=official  mcp.server.fastmcp 1.28.1
SDK = os.getenv("FINK_SDK", "fastmcp").strip().lower()
if SDK == "official":
    from mcp.server.fastmcp import FastMCP
else:
    from fastmcp import FastMCP


# --------------------------------------------------------------------------
# _meta builders.
#
# fastmcp also offers `app={...}`, but it is thin sugar that nests the dict
# under "ui" and nothing more — `app=True` emits a bare `{"ui": true}`. Writing
# meta= directly also lets us carry the legacy `ui/resourceUri` key, which is
# what ext-apps' registerAppTool does. Verified on the wire by
# mcp_apps/check_app_param.py.
# --------------------------------------------------------------------------
def ui_view(uri: str) -> dict:
    """Tool metadata: this tool opens a ui:// view and is visible to the model."""
    return {
        "ui": {"resourceUri": uri, "visibility": ["model"]},
        "ui/resourceUri": uri,          # legacy key, older MCP-UI hosts
    }


def app_only() -> dict:
    """Tool metadata: hidden from the model, callable only from inside a view."""
    return {"ui": {"visibility": ["app"]}}


def view_csp(*origins: str) -> dict:
    """Resource metadata: origins the view is allowed to load from.

    Without this the sandbox CSP blocks the import and the view never connects,
    which looks identical to the view not existing.
    """
    return {"ui": {"csp": {"resourceDomains": list(origins)}}}


# --------------------------------------------------------------------------
def view_html(title: str, body: str, script: str = "") -> str:
    """Wrap markup in a document that performs the mandatory host handshake.

    Every view goes through here. The handshake is not optional decoration —
    see point 1 in the module docstring.
    """
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="color-scheme" content="light dark">
<style>
  html, body {{ margin:0; padding:0; background:transparent; }}
  body {{ font: 14px/1.5 ui-sans-serif, -apple-system, system-ui, sans-serif;
         color:#1a1a1a; padding:20px 22px; }}
  @media (prefers-color-scheme: dark) {{ body {{ color:#ededed; }} }}
  h1 {{ font-size:17px; font-weight:500; margin:0 0 10px; }}
  #fink-status {{ font-size:12px; padding:6px 10px; border-radius:6px;
                 background:rgba(127,127,127,.15); margin:10px 0; }}
  code {{ font:11px ui-monospace, Menlo, monospace; }}
</style>
</head>
<body>
  <h1>{title}</h1>
  <div id="fink-status">connecting&hellip;</div>
  {body}
  <script type="module">
    const status = (t) => {{
      const el = document.getElementById("fink-status");
      if (el) el.textContent = t;
    }};
    let app = null;
    try {{
      const mod = await import("{EXT_APPS}");
      app = new mod.App({{ name: "fink", version: "0.1.0" }});
      app.ontoolresult = (result) => {{
        status("tool result received");
        window.__finkOnToolResult?.(result);
      }};
      await app.connect();
      status("connected");
      window.__finkApp = app;
      app.notifySizeChanged?.({{ height: document.body.scrollHeight, width: 0 }});
    }} catch (e) {{
      status("FAILED: " + (e && e.message ? e.message : String(e)));
    }}
    {script}
  </script>
</body>
</html>"""


mcp = FastMCP(SERVER_NAME)


@mcp.tool(meta=ui_view(HELLO_URI))
def fink_hello(note: str = "phase 2") -> dict:
    """Render the fink MCP Apps smoke-test panel. Takes no real input."""
    return {
        "note": note,
        "summary": "fink phase 2 probe — handshake and tool-result delivery.",
    }


@mcp.tool(meta=app_only())
def fink_echo(payload: str = "ping") -> dict:
    """Not for the model. Confirms visibility=["app"] hides a tool: this does
    not appear in Claude's tool list, and phase 3 will call it from the view
    via callServerTool."""
    return {"echo": payload}


@mcp.resource(HELLO_URI, mime_type=APP_MIME, meta=view_csp(EXT_APPS_ORIGIN))
def hello_view() -> str:
    """Phase 2 smoke test: handshake, tool result, and a callServerTool button
    that phase 3 will build on."""
    return view_html(
        "fink MCP App",
        """<div>Handshake and tool-result delivery confirmed.</div>
           <p><button id="echo">call fink_echo (app-only tool)</button></p>
           <pre id="out" style="font-size:11px"></pre>""",
        script="""
      document.getElementById("echo")?.addEventListener("click", async () => {
        const out = document.getElementById("out");
        if (!app) { out.textContent = "not connected"; return; }
        try {
          const r = await app.callServerTool(
            { name: "fink_echo", arguments: { payload: "from the view" } });
          out.textContent = "callServerTool OK: " + JSON.stringify(r);
        } catch (e) {
          out.textContent = "callServerTool FAILED: " + (e?.message ?? e);
        }
      });""")


# --------------------------------------------------------------------------
async def selftest() -> int:
    """In-memory round trip: exactly the payload a host receives."""
    if SDK == "official":
        print("selftest uses fastmcp's in-memory Client; rerun without FINK_SDK.")
        return 0
    from fastmcp import Client

    ok = True
    async with Client(mcp) as c:
        tools = await c.list_tools()
        print(f"tools/list -> {len(tools)}")
        meta_by_name = {}
        for t in tools:
            m = getattr(t, "meta", None) or getattr(t, "_meta", None)
            try:
                m = t.model_dump(by_alias=True).get("_meta", m)
            except Exception:
                pass
            meta_by_name[t.name] = m or {}
            print(f"  {t.name:12} {json.dumps(m, default=str)}")

        if meta_by_name.get("fink_hello", {}).get("ui", {}).get(
                "resourceUri") != HELLO_URI:
            print("  FAIL fink_hello missing ui.resourceUri")
            ok = False
        if meta_by_name.get("fink_echo", {}).get("ui", {}).get(
                "visibility") != ["app"]:
            print("  FAIL fink_echo missing ui.visibility=['app']")
            ok = False

        for r in await c.list_resources():
            mt = getattr(r, "mimeType", None) or getattr(r, "mime_type", None)
            print(f"\nresources/list  {str(r.uri):20} mimeType={mt!r}")

        for item in await c.read_resource(HELLO_URI):
            mt = getattr(item, "mimeType", None) or getattr(item, "mime_type", None)
            text = getattr(item, "text", "") or ""
            print(f"resources/read  mimeType={mt!r}  {len(text)} bytes")
            if mt != APP_MIME:
                print(f"  FAIL expected {APP_MIME!r}")
                ok = False
            if "App.connect" not in text and "app.connect" not in text:
                print("  FAIL view does not perform the handshake — it will "
                      "never render. See point 1 in the module docstring.")
                ok = False

    print("\n" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stdio", action="store_true", help="stdio (Claude Desktop)")
    ap.add_argument("--http", action="store_true", help="HTTP transport")
    ap.add_argument("--port", type=int, default=3110)
    ap.add_argument("--selftest", action="store_true",
                    help="print the wire payload and exit")
    args = ap.parse_args()

    if args.selftest:
        return asyncio.run(selftest())
    print(f"[fink-apps] SDK={SDK}", file=sys.stderr)
    if args.http:
        mcp.run(transport="http", port=args.port)
        return 0
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
