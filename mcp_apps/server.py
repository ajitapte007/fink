#!/usr/bin/env python3
"""fink MCP Apps server.

One tool reaches the model: `scan_fundamentals`, which runs the anomaly scan
and opens a panel of ranked findings. `fink_scan_payload` is app-only —
callable from inside that panel, invisible to the model.

What phase 2 established by experiment rather than by reading docs, and which
is still the reason this file is shaped the way it is:

  1. A VIEW MUST CALL App.connect() OR IT WILL NEVER DISPLAY.
     This is the whole reason the first attempt failed. The host fetches the
     resource, receives the HTML, and then holds the iframe hidden waiting for
     the guest to signal readiness. A view with no JavaScript never signals,
     so it never appears. The log signature is distinctive and worth
     remembering: a successful `resources/read` followed by silence.
     There is no such thing as a static MCP App panel.

  2. Resource URI naming is free. A bare `ui://fink/scan` renders exactly as
     well as `ui://fink/scan.html`, despite every published example using a
     .html suffix. Bisected 2026-08-03.

  3. `visibility: ["model"]` on an entry-point tool is harmless. Also bisected;
     it was a suspect and is not.

  4. `visibility: ["app"]` IS honoured — an app-only tool never appears in
     Claude's tool list. That makes the app-only data path viable: bulk series
     can go to the view without passing through the model's context.

  5. CSP `resourceDomains` is honoured — the unpkg import of the ext-apps SDK
     succeeds when declared, and the sandbox blocks it when not.

  6. Standalone fastmcp and the official SDK behave identically here. fastmcp
     is used because mcp/server.py already depends on it.

Phase 3 added the data layer; phases 4-6 the scan tool, its view, and
the click-to-ask loop. app.callServerTool() is proven.

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
SCAN_URI = "ui://fink/scan"

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
# what ext-apps' registerAppTool does. Verified on the wire during phase 0.
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
      // Buffer as well as dispatch. The view's own script runs after
      // connect() returns, so a result delivered during the handshake would
      // arrive before __finkOnToolResult exists and be dropped -- producing a
      // blank panel with a successful log, which is exactly the failure mode
      // that cost hours in phase 2. The view replays __finkLastResult on load.
      app.ontoolresult = (result) => {{
        status("tool result received");
        window.__finkLastResult = result;
        window.__finkOnToolResult?.(result);
      }};
      await app.connect();
      status("connected");
      window.__finkApp = app;
      // No manual resize call. `autoResize` defaults to true, so the App
      // already watches document.body with a ResizeObserver and emits
      // ui/notifications/size-changed itself. The method this used to call --
      // notifySizeChanged -- does not exist on App (it is sendSizeChanged),
      // and optional chaining meant it silently did nothing for three phases.
    }} catch (e) {{
      status("FAILED: " + (e && e.message ? e.message : String(e)));
    }}
    {script}
  </script>
</body>
</html>"""


# --------------------------------------------------------------------------
# Phase 5 — the findings view.
#
# Styling is inline and uses `color-scheme` plus CSS variables rather than
# hardcoded colours, because the panel renders inside the host's iframe and
# inherits neither its stylesheet nor its theme. A palette that looks right in
# light mode is unreadable in dark otherwise.
# --------------------------------------------------------------------------
SCAN_BODY = """
<style>
  #hdr { margin: 0 0 14px; }
  #ident { font-size: 12px; opacity: .68; margin-top: 2px; }
  #coverage { font-size: 11px; opacity: .55; margin-top: 6px; }
  .note { padding: 12px 14px; border-radius: 8px; font-size: 13px;
          background: rgba(127,127,127,.10); line-height: 1.5; }
  .note b { font-weight: 600; }
  .f { border: 1px solid rgba(127,127,127,.28); border-left-width: 3px;
       border-radius: 8px; padding: 11px 13px; margin-bottom: 9px;
       cursor: pointer; transition: background .12s, border-color .12s; }
  .f:hover { background: rgba(127,127,127,.09); }
  .f.risk { border-left-color: #dc2626; }
  .f.opportunity { border-left-color: #059669; }
  .f-top { display: flex; align-items: baseline; gap: 9px; }
  .tag { font-size: 9.5px; letter-spacing: .07em; font-weight: 700;
         padding: 2px 6px; border-radius: 4px; flex: none; }
  .tag.risk { background: rgba(220,38,38,.14); color: #dc2626; }
  .tag.opportunity { background: rgba(5,150,105,.14); color: #059669; }
  .headline { font-weight: 550; font-size: 13.5px; flex: 1; }
  .sig { font-size: 11px; opacity: .6; font-variant-numeric: tabular-nums;
         flex: none; }
  .detail { font-size: 12.5px; opacity: .85; margin: 7px 0 0; line-height: 1.5; }
  .meta { font-size: 11px; opacity: .5; margin-top: 7px; }
  details { margin-top: 7px; }
  summary { font-size: 11.5px; opacity: .62; cursor: pointer; }
  details ul { margin: 6px 0 0; padding-left: 18px; font-size: 12px;
               opacity: .78; line-height: 1.55; }
  .ask { font-size: 11.5px; margin-top: 8px; opacity: .72; }
  .ask b { font-weight: 600; }
  #disclaim { font-size: 10.5px; opacity: .42; margin-top: 14px;
              line-height: 1.5; }
</style>
<div id="hdr"></div>
<div id="body"></div>
<div id="disclaim"></div>
"""

SCAN_SCRIPT = r"""
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
      c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

    // Phase 6. Verified against the ext-apps 1.7.0 type declarations rather
    // than guessed -- the first attempt called app.sendMessage({content: text})
    // and the host dropped the whole connection, because `role` is required
    // and `content` is an array of typed blocks, not a string. A malformed
    // request on a live JSON-RPC channel is a protocol violation, not a
    // no-op that falls through to the next thing you try.
    //
    //   sendMessage(params: McpUiMessageRequest["params"], options?)
    //   { role: "user", content: [{ type: "text", text: "..." }] }
    //
    // Returns { isError?: boolean }: a host may *reject* the message without
    // throwing, so the result has to be checked as well as awaited.
    async function askInChat(text) {
      if (typeof app?.sendMessage !== "function") {
        status("this host cannot accept messages from a panel");
        return;
      }
      try {
        const res = await app.sendMessage({
          role: "user",
          content: [{ type: "text", text }],
        });
        // Claude Desktop stages the text in the composer rather than sending
        // it outright -- the host has discretion here, and letting the user
        // edit before committing is the better default. Say "ready to send"
        // rather than "asked", because nothing has been asked yet.
        status(res?.isError ? "the host declined that question"
                            : "question ready to send in the chat box");
      } catch (e) {
        status("could not ask: " + (e?.message ?? e));
      }
    }

    function renderFinding(f) {
      const dir = f.direction === "risk" ? "risk" : "opportunity";
      const benign = (f.benign || []).length
        ? `<details><summary>Innocent explanations to rule out first</summary>
             <ul>${f.benign.map(b => `<li>${esc(b)}</li>`).join("")}</ul>
           </details>` : "";
      return `
        <div class="f ${dir}" data-q="${esc(f.followUp)}">
          <div class="f-top">
            <span class="tag ${dir}">${dir.toUpperCase()}</span>
            <span class="headline">${esc(f.headline)}</span>
            <span class="sig">${f.signal}/10 &middot; ${esc(f.severity)}</span>
          </div>
          ${(f.detail || []).map(d => `<p class="detail">${esc(d)}</p>`).join("")}
          <div class="meta">checks: ${(f.checks || []).map(esc).join(", ")}</div>
          ${benign}
          <div class="ask"><b>Ask:</b> ${esc(f.followUp)}</div>
        </div>`;
    }

    function render(r) {
      const hdr = document.getElementById("hdr");
      const body = document.getElementById("body");
      const disclaim = document.getElementById("disclaim");
      if (!r || !r.ticker) return;

      hdr.innerHTML =
        `<h1 style="margin:0;font-size:17px;font-weight:600">
           ${esc(r.ticker)} &mdash; ${esc(r.name)}</h1>
         <div id="ident">${esc(r.sector)} &middot; ${esc(r.industry)}
           &middot; classified <code>${esc(r.businessModel)}</code></div>
         <div id="coverage">${r.quarters} quarters &middot;
           ${r.checksRun} checks ran</div>`;

      if (r.error) {
        body.innerHTML = `<div class="note"><b>Could not scan.</b><br>${esc(r.error)}</div>`;
      } else if (r.declined) {
        const why = (r.skips && r.skips[0]) ? r.skips[0].reason : "out of scope";
        body.innerHTML = `<div class="note"><b>Declined.</b> ${esc(why)}<br><br>
          Refusing to answer is the answer here &mdash; approximating the
          missing denominators would produce confident nonsense.</div>`;
      } else if (r.insufficient) {
        body.innerHTML = `<div class="note"><b>Not enough history.</b>
          Fewer than 12 usable quarters, so no check could run.</div>`;
      } else if (!r.findings || !r.findings.length) {
        body.innerHTML = `<div class="note"><b>Nothing unusual.</b>
          ${r.checksRun} checks ran and none cleared the significance floor.
          That is a result, not an empty state.</div>`;
      } else {
        body.innerHTML = r.findings.map(renderFinding).join("");
        body.querySelectorAll(".f").forEach(el => {
          el.addEventListener("click", (ev) => {
            if (ev.target.closest("summary, details")) return;  // let it toggle
            // Never let a click surface an exception to the host.
            try { askInChat(el.dataset.q); }
            catch (e) { status("click handler failed: " + (e?.message ?? e)); }
          });
        });
      }

      disclaim.textContent =
        "Every number is computed from Alpha Vantage quarterly statements. " +
        "Thresholds are relative to this company's own history. " +
        "Statistically unusual is not the same as wrong. Not investment advice.";

    }

    window.__finkOnToolResult = (result) => {
      // The host hands back the MCP envelope, not the bare dict. phase 2
      // established the shape: prefer structuredContent, fall back to parsing
      // the text block.
      let data = result?.structuredContent;
      if (!data && result?.content?.[0]?.text) {
        try { data = JSON.parse(result.content[0].text); } catch (e) {}
      }
      if (data) render(data);
    };

    // Replay anything that landed during the handshake, before this handler
    // was assigned. Without this the panel is blank whenever the host is
    // quick, and intermittently fine when it is not -- the worst kind of bug.
    if (window.__finkLastResult) {
      window.__finkOnToolResult(window.__finkLastResult);
    }
"""


mcp = FastMCP(SERVER_NAME)


# --------------------------------------------------------------------------
# Phase 4 — the scan.
#
# `adapters` and `engine` are imported lazily inside the tool rather than at
# module scope. Importing them pulls in the whole data layer and runs
# `cache.init_db()`, which touches the filesystem — and `--selftest` should be
# able to check the wire contract without any of that happening.
# --------------------------------------------------------------------------
def _scan_payload(ticker: str) -> dict:
    """Run a scan and shape it for both the model and the view.

    Deliberately the same payload for both. An earlier sketch had the tool
    return a trimmed summary to the model and the view fetch the full version
    over `callServerTool`, to keep bulk data out of model context. That is the
    right instinct for the *chart* — a metric series is hundreds of KB — and
    wrong here: a scan is a few KB, and the model needs the findings to answer
    the follow-up question the user is about to click on. Splitting them would
    mean the panel knew things the model could not discuss.
    """
    from mcp_apps.scan_cli import scan_one
    return scan_one(ticker)


@mcp.tool(meta=ui_view(SCAN_URI))
def scan_fundamentals(ticker: str) -> dict:
    """Scan a company's fundamentals for statistically unusual movements.

    Runs eight deterministic checks over Alpha Vantage quarterly statements and
    returns ranked risk and opportunity findings, each with the innocent
    explanations to rule out first. Thresholds are relative to the company's own
    trailing history, never absolute. Financials, insurers and REITs are
    declined rather than approximated.

    Returning nothing is a real result: it means the checks ran and found
    nothing unusual.
    """
    from mcp_apps.data.adapters import TickerUnavailable
    try:
        return _scan_payload(ticker)
    except TickerUnavailable as e:
        return {"ticker": ticker.upper(), "error": str(e), "findings": []}


@mcp.tool(meta=app_only())
def fink_scan_payload(ticker: str) -> dict:
    """Not for the model. Lets the panel re-run a scan without a round trip
    through the conversation — used when the view re-renders for a new ticker."""
    return scan_fundamentals(ticker)


@mcp.resource(SCAN_URI, mime_type=APP_MIME, meta=view_csp(EXT_APPS_ORIGIN))
def scan_view() -> str:
    """The findings list.

    Renders whatever `ontoolresult` delivers. Three states worth distinguishing,
    because collapsing them is how a scanner loses trust:

      declined     — out of scope, and saying so is the honest answer
      clean        — the checks ran and found nothing
      findings     — ranked, with benign explanations attached

    "Clean" and "declined" look identical if you only check `findings.length`,
    and an empty list from a company nobody scanned looks the same again.
    """
    return view_html("fink — fundamentals scan", SCAN_BODY, script=SCAN_SCRIPT)


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

        if meta_by_name.get("scan_fundamentals", {}).get("ui", {}).get(
                "resourceUri") != SCAN_URI:
            print(f"  FAIL scan_fundamentals missing ui.resourceUri={SCAN_URI}")
            ok = False
        for name in ("fink_scan_payload",):
            if meta_by_name.get(name, {}).get("ui", {}).get("visibility") != ["app"]:
                print(f"  FAIL {name} missing ui.visibility=['app']")
                ok = False

        for r in await c.list_resources():
            mt = getattr(r, "mimeType", None) or getattr(r, "mime_type", None)
            print(f"\nresources/list  {str(r.uri):20} mimeType={mt!r}")

        for uri in (SCAN_URI,):
            for item in await c.read_resource(uri):
                mt = (getattr(item, "mimeType", None)
                      or getattr(item, "mime_type", None))
                text = getattr(item, "text", "") or ""
                print(f"resources/read  {uri:16} mimeType={mt!r}  {len(text)} bytes")
                if mt != APP_MIME:
                    print(f"  FAIL expected {APP_MIME!r}")
                    ok = False
                if "App.connect" not in text and "app.connect" not in text:
                    print("  FAIL view does not perform the handshake — it will "
                          "never render. See point 1 in the module docstring.")
                    ok = False
                # A view that never registers a result handler renders an empty
                # shell: it connects, the host shows it, and nothing appears.
                if uri == SCAN_URI and "__finkOnToolResult" not in text:
                    print("  FAIL scan view has no tool-result handler")
                    ok = False
                if uri == SCAN_URI and "__finkLastResult" not in text:
                    print("  FAIL scan view does not replay a buffered result — "
                          "it will render blank when the host is quick")
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
