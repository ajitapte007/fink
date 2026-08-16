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

  6. Standalone fastmcp and the official SDK behave identically here — tested
     on the wire in phase 0. fastmcp is the only one now: the FINK_SDK=official
     branch was removed in phase 10a rather than carry a second dependency and
     a code path nothing exercises.

Phase 3 added the data layer; phases 4-6 the scan tool, its view, and
the click-to-ask loop. app.callServerTool() is proven.

    venv/bin/python mcp_apps/server.py --selftest   # wire payload, no Claude
    venv/bin/python mcp_apps/server.py --stdio      # for Claude Desktop
"""
from __future__ import annotations

# Run as a script (`python mcp_apps/server.py`) and there is no package
# context, so `mcp_apps` is not importable until the repo root is on sys.path.
# Claude Desktop's config uses exactly that form, so this cannot be dropped
# until every caller runs the installed console script instead.
#
# This used to import _bootstrap, which additionally put the legacy `mcp/`
# directory on sys.path for sibling imports. Phase 3 ended those, and once
# installed `site-packages/mcp_apps/../mcp` is the pip MCP SDK — inserting it
# at sys.path[0] would shadow the package `from fastmcp import ...` resolves
# through. Deleted with _bootstrap.py.
if __package__ in (None, ""):
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import argparse
import asyncio
import json
import os
import sys

# Absolute, not relative: this module is imported both as `mcp_apps.server`
# and executed as a script, and the sys.path guard above makes the absolute
# form work in either case.
from mcp_apps import __commit__, __version__

SERVER_NAME = "fink-apps"
APP_MIME = "text/html;profile=mcp-app"
SCAN_URI = "ui://fink/scan"
CHART_URI = "ui://fink/chart"

# The ext-apps guest SDK. Loaded from unpkg for now; phase 7 vendors it
# alongside Chart.js so the view has no network dependency inside the sandbox.
EXT_APPS = "https://unpkg.com/@modelcontextprotocol/ext-apps@1.7.0/app-with-deps"
EXT_APPS_ORIGIN = "https://unpkg.com"

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
      app = new mod.App({{ name: "fink", version: "{__version__}" }});
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
# Chart rendering, shared by every view that draws one.
#
# Kept as strings spliced into each view rather than a second ui:// resource:
# a view is a single self-contained document, so anything two views both need
# is either duplicated or hoisted. Duplicated chart code would drift, and the
# transforms are exactly the sort of thing that gets fixed in one copy.
# --------------------------------------------------------------------------
CHART_CSS = """  .chartwrap { margin-top: 10px; display: none; }
  .chartwrap.open { display: block; }
  .xf { display: flex; gap: 5px; margin-bottom: 7px; flex-wrap: wrap;
        align-items: center; }
  .xf span { font-size: 10.5px; opacity: .5; margin-right: 2px; }
  .xf button { font: inherit; font-size: 10.5px; padding: 2px 8px;
               border-radius: 5px; cursor: pointer; color: inherit;
               background: transparent;
               border: 1px solid rgba(127,127,127,.36); }
  .xf button:hover { background: rgba(127,127,127,.12); }
  .xf button.on { background: rgba(127,127,127,.22);
                  border-color: rgba(127,127,127,.6); }
  .xf button[disabled] { opacity: .32; cursor: default; }
  .chartwrap canvas { width: 100%; max-height: 260px; }
  .chartnote { font-size: 10.5px; opacity: .5; margin-top: 5px; }
"""

CHART_CORE = r"""    // Chart.js, loaded once and lazily -- nothing fetches it unless a chart is
    // actually asked for. The UMD bundle rather than the ESM entry: the ESM
    // build imports the bare specifier "chart.js", which a browser cannot
    // resolve without an import map. Same origin as the SDK, so the existing
    // CSP resourceDomains already permits it.
    let chartLib = null;
    function loadChartJs() {
      if (chartLib) return chartLib;
      chartLib = new Promise((resolve, reject) => {
        const el = document.createElement("script");
        el.src = "https://unpkg.com/chart.js@4.4.7/dist/chart.umd.js";
        el.onload = () => resolve(window.Chart);
        el.onerror = () => reject(new Error("Chart.js failed to load"));
        document.head.appendChild(el);
      });
      return chartLib;
    }

    const fmt = (v) => {
      const a = Math.abs(v);
      if (a >= 1e12) return (v / 1e12).toFixed(1) + "T";
      if (a >= 1e9)  return (v / 1e9).toFixed(1) + "B";
      if (a >= 1e6)  return (v / 1e6).toFixed(1) + "M";
      if (a >= 1e3)  return (v / 1e3).toFixed(1) + "K";
      return (Math.round(v * 100) / 100).toString();
    };

    // Transforms. Each takes {date: value} and returns the same shape, so the
    // drawing code below does not care which is active.
    //
    // "normalize" is the one that fixes a real readability problem rather than
    // adding a nicety. Absolute dollars and rates cannot share an axis -- a
    // 1086bp ROIC collapse is a flat line beside revenue in the hundreds of
    // billions -- so the default chart puts them on two, and two axes make
    // relative movement genuinely hard to compare. Indexing everything to 100
    // at the first point it exists puts every series back on one axis and
    // makes "which of these moved most" answerable at a glance.
    const UNIT = {};   // metric id -> unit, filled from the payload config

    function pctChange(pts, lagMonths) {
      const dates = Object.keys(pts).sort();
      const out = {};
      const idx = new Map(dates.map((d, i) => [d, i]));
      for (const d of dates) {
        const i = idx.get(d);
        if (i < lagMonths) continue;
        const prev = pts[dates[i - lagMonths]];
        const cur = pts[d];
        if (prev == null || cur == null || prev === 0) continue;
        // Sign-aware: a loss narrowing from -100 to -50 is an improvement, and
        // dividing by a negative base would report it as -50%.
        out[d] = ((cur - prev) / Math.abs(prev)) * 100;
      }
      return out;
    }

    const TRANSFORMS = {
      none: (pts) => pts,

      normalize: (pts) => {
        const dates = Object.keys(pts).sort();
        const base = dates.map((d) => pts[d]).find((v) => v != null && v !== 0);
        if (base == null) return {};
        const out = {};
        // Divide by |base| so a series starting negative still reads in the
        // right direction rather than inverting.
        for (const d of dates) if (pts[d] != null) out[d] = (pts[d] / Math.abs(base)) * 100;
        return out;
      },

      // 12 monthly points back. The series is monthly-aligned, so this is a
      // true year-over-year rather than a quarter-over-quarter mislabelled.
      yoy: (pts) => pctChange(pts, 12),

      pershare: (pts, id, shares) => {
        // Price is already a per-share quantity. Dividing it again is wrong
        // and dropping it is worse -- it is the context line every other
        // series is read against, so it passes through untouched.
        if (PER_SHARE_PASSTHROUGH(id)) return pts;
        if (!shares || !PER_SHARE_OK(id)) return null;   // null = not applicable
        const out = {};
        for (const [d, v] of Object.entries(pts)) {
          const sh = shares[d];
          if (v != null && sh) out[d] = v / sh;
        }
        return out;
      },
    };

    // Per share only means something for an absolute the company earns or
    // spends. A margin per share is meaningless; price already is per share;
    // market cap per share is just the price again.
    const PER_SHARE_OK = (id) =>
      UNIT[id] === "USD" && id !== "price" && id !== "market_cap";

    // Already per share, so it is charted as-is rather than divided or dropped.
    const PER_SHARE_PASSTHROUGH = (id) => id === "price";

    // Legend entries have to describe what is *plotted*, not what the metric
    // is underneath. Under "indexed to 100" a revenue line is no longer in
    // dollars, and saying so would be wrong; under YoY everything is a percent
    // regardless of its source unit. The axis side is only shown when there
    // are two axes — naming a side when there is only one is noise.
    const UNIT_SHORT = { USD: "$", percent: "%", ratio: "×", count: "shares" };

    function seriesLabel(id, cfg, xf, oneAxis, onRight) {
      const base = cfg[id]?.label ?? id;
      let unit;
      if (xf === "normalize")      unit = "indexed";
      else if (xf === "yoy")       unit = "% YoY";
      else if (xf === "pershare")  unit = PER_SHARE_PASSTHROUGH(id)
                                        ? UNIT_SHORT[UNIT[id]] ?? ""
                                        : "$/share";
      else                         unit = UNIT_SHORT[UNIT[id]] ?? "";
      const side = oneAxis ? "" : (onRight ? "right" : "left");
      const bits = [unit, side].filter(Boolean);
      return bits.length ? `${base} (${bits.join(", ")})` : base;
    }

    const XF_LABEL = {
      none: "actual values",
      normalize: "indexed to 100 at the first point — one axis, relative movement",
      yoy: "year-over-year change, percent",
      pershare: "per share",
    };

    async function drawChart(el, ticker, spec) {
      const wrap = el.querySelector(".chartwrap");
      const note = wrap.querySelector(".chartnote");
      spec = spec || {};
      note.textContent = "loading…";
      wrap.classList.add("open");

      let Chart, payload;
      try {
        Chart = await loadChartJs();
        // Straight to the server, bypassing the model. The series is hundreds
        // of KB; routing it through the conversation would cost that on every
        // subsequent turn for data the model cannot use.
        const r = await app.callServerTool({
          name: "fink_metric_series",
          arguments: {
            ticker,
            // shares_outstanding is appended by load_series regardless, and the
            // per-share transform needs it. It is filtered out of the drawn
            // lines unless explicitly requested.
            metrics: spec.metrics,
            start_year: spec.startYear,
            end_year: spec.endYear,
          },
        });
        payload = r?.structuredContent
               ?? JSON.parse(r?.content?.[0]?.text ?? "{}");
      } catch (e) {
        note.textContent = "could not load the chart: " + (e?.message ?? e);
        return;
      }
      if (payload.error) { note.textContent = payload.error; return; }

      el.__payload = payload;
      el.__spec = spec;
      paint(el);
    }

    function paint(el) {
      const payload = el.__payload || {};
      const spec = el.__spec || {};
      const wrap = el.querySelector(".chartwrap");
      const note = wrap.querySelector(".chartnote");
      const xf = el.__xf || "none";

      const cfg = payload.config || {};
      for (const [id, c] of Object.entries(cfg)) UNIT[id] = c.unit;

      // shares_outstanding rides along for per-share but is not itself a line.
      const shares = payload.series?.shares_outstanding;
      const series = Object.fromEntries(
        Object.entries(payload.series || {})
          .filter(([id]) => id !== "shares_outstanding"
                            || (spec.metrics || []).includes("shares_outstanding")));

      const right = new Set(spec.rightAxis || []);

      // One x-axis for every series: the union of dates, sorted. Charting each
      // series against its own dates silently misaligns them, which is the
      // failure that makes two lines look correlated when they are not.
      const dates = [...new Set(Object.values(series)
        .flatMap((pts) => Object.keys(pts)))].sort();

      // Under normalize and yoy every series shares a unit, so the split axis
      // stops being useful and actively hurts: two axes with the same scale
      // invite the reader to compare positions that are not comparable.
      const oneAxis = xf === "normalize" || xf === "yoy";
      const skipped = [];

      const datasets = Object.entries(series)
        .map(([id, raw]) => {
          const pts = TRANSFORMS[xf](raw, id, shares);
          if (pts === null) { skipped.push(cfg[id]?.label ?? id); return null; }  // plain name
          return [id, pts];
        })
        .filter((x) => x && Object.keys(x[1]).length)
        .map(([id, pts]) => ({
          // Carried so the tooltip can find its unit. Indexing back into
          // Object.keys(series) by datasetIndex looks equivalent and is not:
          // datasets are filtered when a series is empty or per-share skips
          // it, so the two lists drift apart and tooltips take the wrong unit.
          finkId: id,
          label: seriesLabel(id, cfg, xf, oneAxis, right.has(id)),
          data: dates.map((d) => (d in pts ? pts[d] : null)),
          borderColor: cfg[id]?.color ?? "#888",
          backgroundColor: "transparent",
          yAxisID: (!oneAxis && right.has(id)) ? "y1" : "y",
          borderWidth: 1.6,
          pointRadius: 0,
          spanGaps: true,
          tension: 0.15,
        }));

      if (!datasets.length) {
        note.textContent = skipped.length
          ? "per share does not apply to any series here"
          : "no data for this window";
        el.__chart?.destroy(); el.__chart = null;
        return;
      }

      const canvas = wrap.querySelector("canvas");
      el.__chart?.destroy();
      el.__chart = new Chart(canvas, {
        type: "line",
        data: { labels: dates, datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { labels: { boxWidth: 10, font: { size: 10 } } },
            tooltip: { callbacks: {
              label: (c) => {
                if (c.parsed.y == null) return c.dataset.label + ": n/a";
                const pct = UNIT[c.dataset.finkId] === "percent";
                const v = fmt(c.parsed.y);
                return c.dataset.label + ": " +
                       (xf === "yoy" ? (c.parsed.y > 0 ? "+" : "") + v + "%"
                        : xf === "normalize" ? v
                        : pct ? v + "%" : v);
              } } },
          },
          scales: {
            x: { ticks: { maxTicksLimit: 8, font: { size: 9 } },
                 grid: { display: false } },
            y: { position: "left", ticks: { callback: fmt, font: { size: 9 } },
                 grid: { color: "rgba(127,127,127,.14)" } },
            y1: { position: "right", display: !oneAxis && right.size > 0,
                  ticks: { font: { size: 9 } }, grid: { display: false } },
          },
        },
      });
      const psBtn = el.querySelector('[data-xf="pershare"]');
      if (psBtn) {
        const anyOk = Object.keys(series).some(PER_SHARE_OK) && !!shares;
        // price alone is not a reason to offer it: nothing would change.
        psBtn.disabled = !anyOk;
        psBtn.title = anyOk ? "" :
          "no absolute dollar series here — per share would be meaningless";
      }

      note.textContent = `${spec.startYear}–${spec.endYear} · ${XF_LABEL[xf]}` +
        (skipped.length ? ` · not applicable to ${skipped.join(", ")}` : "") +
        (oneAxis ? "" : " · right axis: rates and price");
    }

"""


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
  .cta { display: flex; gap: 8px; margin-top: 10px; }
  .cta button { font: inherit; font-size: 11.5px; padding: 4px 11px;
                border-radius: 6px; cursor: pointer; color: inherit;
                background: transparent;
                border: 1px solid rgba(127,127,127,.42); }
  .cta button:hover { background: rgba(127,127,127,.13); }
  .cta button[disabled] { opacity: .5; cursor: default; }
${CHART_CSS}
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

    ${CHART_CORE}

    function renderCluster(f) {
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
          <div class="cta">
            <button data-act="chart">See chart</button>
            <button data-act="ask">Ask about this</button>
          </div>
          <div class="chartwrap">
            <div class="xf"><span>view</span>
              <button data-xf="none" class="on">Actual</button>
              <button data-xf="normalize">Indexed to 100</button>
              <button data-xf="yoy">YoY growth</button>
              <button data-xf="pershare">Per share</button>
            </div>
            <canvas></canvas>
            <div class="chartnote"></div>
          </div>
        </div>`;
    }

    let current = {};

    function render(r) {
      current = r || {};
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
      } else if (!r.clusters || !r.clusters.length) {
        body.innerHTML = `<div class="note"><b>Nothing unusual.</b>
          ${r.checksRun} checks ran and none cleared the significance floor.
          That is a result, not an empty state.</div>`;
      } else {
        body.innerHTML = r.clusters.map(renderCluster).join("");
        body.querySelectorAll(".f").forEach((el, i) => {
          const f = r.clusters[i];
          // Two calls to action, because looking at the evidence and asking
          // the model about it are different intents. "See chart" stays inside
          // the panel and answers "is this real?". "Ask" brings the model in
          // for "what does it mean?". Collapsing them into one click forces a
          // guess about which the reader wanted.
          el.querySelector('[data-act="chart"]')?.addEventListener("click", async (ev) => {
            ev.stopPropagation();
            const btn = ev.currentTarget;
            const wrap = el.querySelector(".chartwrap");
            if (wrap.classList.contains("open")) {
              wrap.classList.remove("open");
              btn.textContent = "See chart";
              return;
            }
            btn.disabled = true;
            try { await drawChart(el, current.ticker, f.chartSpec); btn.textContent = "Hide chart"; }
            catch (e) { status("chart failed: " + (e?.message ?? e)); }
            finally { btn.disabled = false; }
          });
          // Transform toggles repaint from el.__payload. Refetching would
          // spend a round trip to recompute something the view already holds,
          // and would make a toggle feel slower than it is.
          el.querySelectorAll("[data-xf]").forEach((btn) => {
            btn.addEventListener("click", (ev) => {
              ev.stopPropagation();
              const want = btn.dataset.xf;
              el.__xf = want;
              el.querySelectorAll("[data-xf]").forEach(
                (b) => b.classList.toggle("on", b === btn));
              try { paint(el); }
              catch (e) { status("could not redraw: " + (e?.message ?? e)); }
            });
          });

          el.querySelector('[data-act="ask"]')?.addEventListener("click", (ev) => {
            ev.stopPropagation();
            try { askInChat(f.followUp); }
            catch (e) { status("could not ask: " + (e?.message ?? e)); }
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

    Deliberately the same payload for both, with one exception. An earlier
    sketch had the tool return a trimmed summary to the model and the view
    fetch the full version over `callServerTool`, to keep bulk data out of
    model context. That is the right instinct for the *chart* — a metric series
    is hundreds of KB — and wrong here: a scan is a few KB, and the model needs
    the clusters to answer the follow-up question the user is about to click
    on. Splitting them would mean the panel knew things the model could not
    discuss.

    The exception is `guidance`: instructions on how to narrate the result,
    which are for the model and meaningless to the view.
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
        return {"ticker": ticker.upper(), "error": str(e), "clusters": []}


@mcp.tool(meta=app_only())
def fink_scan_payload(ticker: str) -> dict:
    """Not for the model. Lets the panel re-run a scan without a round trip
    through the conversation — used when the view re-renders for a new ticker."""
    return scan_fundamentals(ticker)


@mcp.tool(meta=app_only())
def fink_metric_series(ticker: str, metrics: list[str] | None = None,
                       start_year: int | None = None,
                       end_year: int | None = None) -> dict:
    """Not for the model. Aligned monthly series for the chart.

    This is the tool the app-only path was built for. A scan is a few KB and
    belongs in model context; a metric series is hundreds of KB of dated
    numbers that the model can do nothing useful with and would pay for on
    every subsequent turn. The panel calls this directly over `callServerTool`,
    so the data reaches the chart without ever entering the conversation.

    Returns {metric_id: {date: value}} plus the labels and colours the chart
    needs, so the view does not carry its own copy of the registry.
    """
    from mcp_apps.data import adapters
    from mcp_apps.data.adapters import TickerUnavailable
    from mcp_apps.data.metrics_registry import METRICS_REGISTRY

    try:
        series = adapters.load_series(ticker, metrics)
    except TickerUnavailable as e:
        return {"ticker": ticker.upper(), "error": str(e), "series": {}}
    except ValueError as e:
        return {"ticker": ticker.upper(), "error": str(e), "series": {}}

    if start_year or end_year:
        lo = f"{start_year}-01-01" if start_year else ""
        hi = f"{end_year}-12-31" if end_year else "9999"
        series = {m: {d: v for d, v in pts.items() if lo <= d <= hi}
                  for m, pts in series.items()}

    by_id = {m["id"]: m for m in METRICS_REGISTRY}
    return {
        "ticker": ticker.upper(),
        "series": series,
        "config": {m: {"label": by_id[m]["label"],
                       "unit": by_id[m]["unit"],
                       "color": by_id[m].get("color", "#888")}
                   for m in series if m in by_id},
    }


@mcp.tool(meta=ui_view(CHART_URI))
def chart_fundamentals(ticker: str, metrics: list[str] | None = None,
                       start_year: int | None = None,
                       end_year: int | None = None) -> dict:
    """Chart a company's fundamentals over time, with no scan involved.

    For following a thread the scan did not raise — "show me GOOGL's margins
    and ROIC since 2015", or charting a metric a finding mentioned in passing.
    The panel offers the same views as a finding's chart: actual, indexed to
    100, year-over-year, and per share.

    Omitting `metrics` charts revenue, operating margin and price. Valid
    metric ids come back in the error when an unknown one is passed.
    """
    from mcp_apps.chartspec import DEFAULT_YEARS
    from mcp_apps.data import adapters
    from mcp_apps.data.adapters import TickerUnavailable
    from mcp_apps.data.metrics_registry import DEFAULT_CHART_METRICS, VALID_METRIC_KEYS

    wanted = list(metrics) if metrics else list(DEFAULT_CHART_METRICS)
    unknown = [m for m in wanted if m not in VALID_METRIC_KEYS]
    if unknown:
        return {"ticker": ticker.upper(),
                "error": f"unknown metrics {unknown}. Valid: "
                         f"{sorted(VALID_METRIC_KEYS)}"}

    try:
        ident = adapters.load_identity(ticker)
    except TickerUnavailable as e:
        return {"ticker": ticker.upper(), "error": str(e)}

    # Default window mirrors a finding's: long enough to cover the trailing
    # period the checks score against, with context before it.
    if not end_year or not start_year:
        series = adapters.load_series(ticker, ["price"])
        dates = sorted(series.get("price", {}))
        if dates:
            end_year = end_year or int(dates[-1][:4])
            start_year = start_year or max(int(dates[0][:4]),
                                           end_year - DEFAULT_YEARS)

    return {
        "ticker": ident["ticker"],
        "name": ident.get("name") or ticker.upper(),
        "sector": ident.get("sector", ""),
        "industry": ident.get("industry", ""),
        "businessModel": ident.get("business_model", ""),
        "chartSpec": {
            "metrics": wanted,
            "startYear": start_year,
            "endYear": end_year,
            "rightAxis": [m for m in wanted
                          if m.endswith("_margin")
                          or m in ("roic", "roa", "roe", "price",
                                   "dividend_yield")],
        },
        "summary": f"{ident['ticker']}: {', '.join(wanted)} "
                   f"{start_year}-{end_year}.",
    }


CHART_BODY = """
<style>
  #hdr { margin: 0 0 12px; }
  #ident { font-size: 12px; opacity: .68; margin-top: 2px; }
${CHART_CSS}
  .chartwrap { display: block; }
  .note { padding: 12px 14px; border-radius: 8px; font-size: 13px;
          background: rgba(127,127,127,.10); line-height: 1.5; }
  #disclaim { font-size: 10.5px; opacity: .42; margin-top: 12px; line-height: 1.5; }
</style>
<div id="hdr"></div>
<div id="host">
  <div class="chartwrap">
    <div class="xf"><span>view</span>
      <button data-xf="none" class="on">Actual</button>
      <button data-xf="normalize">Indexed to 100</button>
      <button data-xf="yoy">YoY growth</button>
      <button data-xf="pershare">Per share</button>
    </div>
    <canvas></canvas>
    <div class="chartnote"></div>
  </div>
</div>
<div id="disclaim"></div>
"""

CHART_SCRIPT = r"""
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
      c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

    ${CHART_CORE}

    const host = document.getElementById("host");

    async function renderChartPanel(r) {
      const hdr = document.getElementById("hdr");
      if (!r || !r.ticker) return;

      hdr.innerHTML =
        `<h1 style="margin:0;font-size:17px;font-weight:600">
           ${esc(r.ticker)} &mdash; ${esc(r.name ?? "")}</h1>
         <div id="ident">${esc(r.sector ?? "")}
           ${r.industry ? "&middot; " + esc(r.industry) : ""}</div>`;

      if (r.error) {
        host.innerHTML = `<div class="note">${esc(r.error)}</div>`;
        return;
      }

      host.querySelectorAll("[data-xf]").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          host.__xf = btn.dataset.xf;
          host.querySelectorAll("[data-xf]").forEach(
            (b) => b.classList.toggle("on", b === btn));
          try { paint(host); }
          catch (e) { status("could not redraw: " + (e?.message ?? e)); }
        });
      });

      try { await drawChart(host, r.ticker, r.chartSpec); }
      catch (e) { status("chart failed: " + (e?.message ?? e)); }

      document.getElementById("disclaim").textContent =
        "Alpha Vantage quarterly statements, aligned to monthly prices. " +
        "Not investment advice.";
    }

    window.__finkOnToolResult = (result) => {
      let data = result?.structuredContent;
      if (!data && result?.content?.[0]?.text) {
        try { data = JSON.parse(result.content[0].text); } catch (e) {}
      }
      if (data) renderChartPanel(data);
    };

    if (window.__finkLastResult) {
      window.__finkOnToolResult(window.__finkLastResult);
    }
"""


@mcp.resource(CHART_URI, mime_type=APP_MIME, meta=view_csp(EXT_APPS_ORIGIN))
def chart_view() -> str:
    """A standalone chart, sharing every line of its rendering with the scan
    panel's inline charts — same transforms, same axis rules, same fetch."""
    return view_html("fink — fundamentals",
                     CHART_BODY.replace("${CHART_CSS}", CHART_CSS),
                     script=CHART_SCRIPT.replace("${CHART_CORE}", CHART_CORE))


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
    return view_html("fink — fundamentals scan",
                     SCAN_BODY.replace("${CHART_CSS}", CHART_CSS),
                     script=SCAN_SCRIPT.replace("${CHART_CORE}", CHART_CORE))


# --------------------------------------------------------------------------
async def selftest() -> int:
    """In-memory round trip: exactly the payload a host receives."""
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

        for name, uri in (("scan_fundamentals", SCAN_URI),
                          ("chart_fundamentals", CHART_URI)):
            if meta_by_name.get(name, {}).get("ui", {}).get("resourceUri") != uri:
                print(f"  FAIL {name} missing ui.resourceUri={uri}")
                ok = False
        for name in ("fink_scan_payload",):
            if meta_by_name.get(name, {}).get("ui", {}).get("visibility") != ["app"]:
                print(f"  FAIL {name} missing ui.visibility=['app']")
                ok = False

        for r in await c.list_resources():
            mt = getattr(r, "mimeType", None) or getattr(r, "mime_type", None)
            print(f"\nresources/list  {str(r.uri):20} mimeType={mt!r}")

        for uri in (SCAN_URI, CHART_URI):
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
                if "__finkOnToolResult" not in text:
                    print(f"  FAIL {uri} has no tool-result handler")
                    ok = False
                if "__finkLastResult" not in text:
                    print(f"  FAIL {uri} does not replay a buffered result — "
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
    # Claude Desktop captures stderr to
    # ~/Library/Logs/Claude/mcp-server-fink-apps.log, so this identifies the
    # process that actually ran — not a healthy neighbour started by hand.
    print(f"[fink-apps] {__version__}+{__commit__} py{sys.version_info.major}."
          f"{sys.version_info.minor}.{sys.version_info.micro} "
          f"mode={os.getenv('FINK_DATA_MODE', 'unset')}", file=sys.stderr)
    if args.http:
        mcp.run(transport="http", port=args.port)
        return 0
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
