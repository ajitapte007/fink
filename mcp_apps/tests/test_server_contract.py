"""The MCP wire contract and the view's invariants.

Split by what each layer can prove. The pure builders (`ui_view`, `app_only`,
`view_csp`, `view_html`) and the view source are checkable anywhere, so they
live here. The end-to-end `tools/list` payload needs a real fastmcp client and
is skipped where fastmcp is absent — `server.py --selftest` covers it, and
`mcp_apps/tests/verify.sh` runs that.

Most of these encode something that already went wrong once. Phase 2 spent
hours on a panel that never appeared because the view had no `App.connect()`
call: the host fetched the resource, got valid HTML, and held the iframe hidden
forever waiting for a readiness signal. A successful `resources/read` followed
by silence is the log signature, and there is no such thing as a static MCP App
panel.
"""
from __future__ import annotations

import importlib.util
import sys
import types

import pytest


FASTMCP_IS_STUBBED = False


def _have_real_fastmcp() -> bool:
    """True only when the genuine package is importable.

    Cannot use `find_spec` after stubbing: the stub is a bare ModuleType with
    no __spec__, and find_spec raises ValueError rather than returning None for
    an already-imported module in that state.
    """
    mod = sys.modules.get("fastmcp")
    if mod is not None:
        return not getattr(mod, "_fink_stub", False)
    try:
        return importlib.util.find_spec("fastmcp") is not None
    except (ImportError, ValueError):
        return False


def _load_server():
    """Import server.py with fastmcp stubbed if it is not installed.

    The decorators only need to return the function unchanged for the module to
    import and its pure functions to be exercised.
    """
    global FASTMCP_IS_STUBBED
    if not _have_real_fastmcp():
        class _FakeMCP:
            def __init__(self, name):
                self.name = name

            def tool(self, **_kw):
                return lambda f: f

            def resource(self, *_a, **_kw):
                return lambda f: f

        fake = types.ModuleType("fastmcp")
        fake.FastMCP = _FakeMCP
        fake._fink_stub = True
        sys.modules["fastmcp"] = fake
        FASTMCP_IS_STUBBED = True

    spec = importlib.util.spec_from_file_location(
        "fink_server",
        __import__("pathlib").Path(__file__).resolve().parents[1] / "server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fink_server"] = mod
    spec.loader.exec_module(mod)
    return mod


srv = _load_server()


# --------------------------------------------------------------- _meta shapes
def test_ui_view_carries_both_the_current_and_legacy_keys():
    """`ui.resourceUri` is the spec key; `ui/resourceUri` is what ext-apps'
    registerAppTool emits. Sending both costs nothing and covers older hosts."""
    meta = srv.ui_view("ui://fink/x")
    assert meta["ui"]["resourceUri"] == "ui://fink/x"
    assert meta["ui/resourceUri"] == "ui://fink/x"


def test_app_only_hides_a_tool_from_the_model():
    assert srv.app_only()["ui"]["visibility"] == ["app"]


def test_view_csp_declares_the_sdk_origin():
    """Without this the sandbox blocks the ext-apps import and the view never
    connects — which looks identical to the view not existing."""
    assert srv.EXT_APPS_ORIGIN in srv.view_csp(srv.EXT_APPS_ORIGIN)["ui"]["csp"]["resourceDomains"]
    assert srv.EXT_APPS.startswith(srv.EXT_APPS_ORIGIN)


# ------------------------------------------------------------ view invariants
def test_every_view_performs_the_handshake():
    """The single most expensive lesson of phase 2."""
    html = srv.scan_view()
    assert "app.connect()" in html, (
        "scan_view never calls App.connect() — the host will fetch it, "
        "receive valid HTML, and hold the iframe hidden forever")


def test_every_view_imports_the_sdk_from_the_declared_origin():
    html = srv.scan_view()
    assert srv.EXT_APPS in html


def test_scan_view_registers_a_result_handler_and_replays_buffered_results():
    """The race that produces a blank panel intermittently.

    `view_html` assigns `ontoolresult` before `connect()`, but the view's own
    script runs after it. A result delivered during the handshake therefore
    arrives before `__finkOnToolResult` exists. The buffer plus replay closes
    it; without the replay the panel is blank whenever the host is quick and
    fine when it is slow.
    """
    html = srv.scan_view()
    assert "__finkOnToolResult" in html
    assert "__finkLastResult" in html
    assert html.index("window.__finkLastResult = result") < html.index("app.connect()"), (
        "the buffer must be installed before connect(), or it cannot catch "
        "a result delivered during the handshake")


def test_scan_view_distinguishes_declined_clean_and_empty():
    """Collapsing these is how a scanner loses trust.

    "Declined" (out of scope), "clean" (checks ran, nothing found) and an error
    all render as zero findings. A view that only checks `findings.length`
    tells the user their insurer looks healthy.
    """
    html = srv.scan_view()
    for token in ("r.declined", "r.insufficient", "r.error", "Nothing unusual"):
        assert token in html, f"scan view does not handle {token}"


def test_scan_view_escapes_interpolated_content():
    """Findings carry company names and AV industry strings straight from a
    third-party API into innerHTML."""
    html = srv.scan_view()
    assert "const esc =" in html
    assert "esc(f.headline)" in html and "esc(r.name)" in html


def _js(html: str) -> str:
    """The view's code with // comments stripped.

    Comments here quote the very API shapes the tests below forbid or require,
    so matching prose instead of code makes a test fail for reasons unrelated
    to what it protects.
    """
    return "\n".join(line.split("//")[0] for line in html.splitlines())


def test_send_message_uses_the_shape_the_sdk_declares():
    """Regression: a malformed request took down the MCP connection.

    The first version called `app.sendMessage({content: text})`. The declared
    signature is `sendMessage(params: McpUiMessageRequest["params"])`, and the
    SDK's own example is:

        app.sendMessage({ role: "user", content: [{ type: "text", text }] })

    `role` is required and `content` is an array of typed blocks. Sending the
    wrong shape over a live JSON-RPC channel is a protocol violation rather
    than a no-op, and the host responded by dropping the connection — the panel
    collapsed with "unable to reach fink-apps", which reads like a server crash
    and was not one.
    """
    code = _js(srv.scan_view())
    assert "app.sendMessage(" in code, "the click no longer asks anything"
    call = code[code.index("app.sendMessage("):][:220]
    assert 'role: "user"' in call, "sendMessage requires a role"
    assert 'type: "text"' in call, "content must be an array of typed blocks"
    assert "content: [" in call, "content is an array, not a string"


def test_send_message_result_is_checked_not_just_awaited():
    """A host may decline a message without throwing.

    `sendMessage` resolves to `{ isError?: boolean }`. Awaiting it without
    reading that flag means a silently rejected question looks successful.
    """
    code = _js(srv.scan_view())
    assert "isError" in code[code.index("app.sendMessage("):][:400]


def test_no_unverified_host_methods_are_invoked():
    """Everything called on `app` must exist on the ext-apps 1.7.0 App class.

    Enumerated from the SDK type declarations. `notifySizeChanged` is the
    cautionary case: it never existed, optional chaining hid that for three
    phases, and the panel simply never reported its height.
    """
    real = {
        "connect", "callServerTool", "readServerResource", "listServerResources",
        "sendMessage", "sendLog", "sendSizeChanged", "sendToolListChanged",
        "sendOpenLink", "openLink", "createSamplingMessage", "updateModelContext",
        "requestDisplayMode", "requestTeardown", "getHostCapabilities",
        "getHostContext", "getHostVersion", "registerTool", "close",
        "addEventListener", "removeEventListener",
        # assignable on* handler properties
        "ontoolresult", "ontoolinput", "ontoolinputpartial", "ontoolcancelled",
        "onhostcontextchanged", "onteardown", "oncalltool", "onlisttools",
    }
    import re
    called = set(re.findall(r"app\??\.(\w+)", _js(srv.scan_view())))
    unknown = called - real
    assert not unknown, (
        f"{sorted(unknown)} do not exist on ext-apps App — optional chaining "
        f"will make them silently no-op rather than raise")


def test_click_handlers_cannot_take_the_panel_down():
    """An exception escaping a click handler kills the view.

    Checked per handler rather than once: it is the handler that gains a new
    failure mode when it grows, and a single global assertion would pass on
    the strength of whichever one happened to be guarded.
    """
    code = _js(srv.scan_view())
    for selector in ('[data-act="chart"]', '[data-act="ask"]'):
        i = code.index("querySelector('" + selector + "')")
        body = code[i:i + 700]
        assert "try {" in body and "catch" in body, (
            f"the {selector} handler can throw into the host")


# ------------------------------------------------------------- payload shape
def test_scan_payload_carries_every_field_the_view_reads():
    """Keeps the tool and the view from drifting apart silently — a missing key
    renders as `undefined` in the panel rather than raising."""
    payload = srv.scan_fundamentals("GOOGL")
    for key in ("ticker", "name", "sector", "industry", "businessModel",
                "quarters", "checksRun", "declined", "insufficient",
                "clusters", "skips"):
        assert key in payload, f"payload missing {key!r}, which the view reads"

    assert payload["clusters"], "GOOGL should produce clusters"
    for f in payload["clusters"]:
        for key in ("id", "headline", "direction", "score", "signal",
                    "severity", "checks", "detail", "benign", "followUp"):
            assert key in f, f"finding missing {key!r}"
        assert f["direction"] in ("risk", "opportunity")
        assert 0 <= f["signal"] <= 10
        assert f["followUp"], "a finding with no follow-up cannot be clicked"


def test_scan_payload_is_json_serialisable():
    """It crosses a postMessage boundary. A dataclass or a set would be dropped
    by the host with no error visible to either side."""
    import json
    json.loads(json.dumps(srv.scan_fundamentals("AMZN")))


def test_unknown_ticker_returns_an_error_not_an_exception():
    """An MCP tool that raises gives the model a stack trace to relay."""
    out = srv.scan_fundamentals("NOTATICKER123")
    assert out["error"]
    assert out["clusters"] == []


def test_declined_company_is_not_reported_as_clean():
    out = srv.scan_fundamentals("UNH")
    assert out["declined"] is True
    assert out["clusters"] == []
    assert out["checksRun"] == 0


# --------------------------------------------------------------- wire, if any
fastmcp_required = pytest.mark.skipif(
    FASTMCP_IS_STUBBED,
    reason="fastmcp not installed; server.py --selftest covers the wire")


@fastmcp_required
@pytest.mark.slow
def test_tools_list_carries_the_ui_metadata():
    import asyncio

    from fastmcp import Client

    async def probe():
        async with Client(srv.mcp) as c:
            tools = {t.name: (t.model_dump(by_alias=True).get("_meta") or {})
                     for t in await c.list_tools()}
            resources = {str(r.uri): (getattr(r, "mimeType", None)
                                      or getattr(r, "mime_type", None))
                         for r in await c.list_resources()}
            return tools, resources

    tools, resources = asyncio.run(probe())

    assert tools["scan_fundamentals"]["ui"]["resourceUri"] == srv.SCAN_URI
    assert tools["fink_scan_payload"]["ui"]["visibility"] == ["app"]
    assert resources[srv.SCAN_URI] == srv.APP_MIME


# --------------------------------------------------------- phase 7: the chart
def test_metric_series_is_app_only():
    """A metric series must never reach model context.

    A scan is a few KB and belongs there — the model needs the findings to
    answer follow-ups. A series is hundreds of KB of dated numbers the model
    can do nothing with, and would pay for on every subsequent turn.
    """
    from mcp_apps import server as s
    import inspect
    src = inspect.getsource(s)
    decl = src[src.index("def fink_metric_series") - 200:src.index("def fink_metric_series")]
    assert "app_only()" in decl


def test_metric_series_returns_dated_values_and_display_config():
    out = srv.fink_metric_series("GOOGL", ["revenue", "gross_margin"], 2020, 2024)
    assert out["ticker"] == "GOOGL"
    assert out["series"]["revenue"], "no revenue points"
    for date in list(out["series"]["revenue"])[:5]:
        assert len(date) == 10 and date[4] == "-"
    # Labels and colours travel with the data so the view holds no copy of the
    # registry — one place to change a label, not two.
    assert out["config"]["revenue"]["label"]
    assert out["config"]["revenue"]["color"].startswith("#")


def test_metric_series_honours_the_window():
    """The chartSpec window is what the check measured; ignoring it would show
    the reader a different period from the one the finding describes."""
    out = srv.fink_metric_series("GOOGL", ["revenue"], 2020, 2022)
    dates = sorted(out["series"]["revenue"])
    assert dates[0] >= "2020-01-01" and dates[-1] <= "2022-12-31"


def test_metric_series_reports_bad_input_rather_than_returning_empty():
    """An empty series and a rejected request render identically — a blank
    chart — unless the error survives to the view."""
    assert srv.fink_metric_series("GOOGL", ["not_a_metric"])["error"]
    assert srv.fink_metric_series("NOTATICKER123", ["revenue"])["error"]


def test_view_offers_two_distinct_calls_to_action():
    """Looking at evidence and asking the model are different intents.

    "See chart" answers "is this real?" without leaving the panel; "Ask"
    answers "what does it mean?" and needs the model. One click would force a
    guess about which the reader wanted.
    """
    html = srv.scan_view()
    assert 'data-act="chart"' in html and 'data-act="ask"' in html
    code = _js(html)
    assert "drawChart" in code and "askInChat" in code


def test_chart_fetches_its_data_without_the_model():
    """The whole context-cost argument, in one assertion."""
    code = _js(srv.scan_view())
    call = code[code.index("drawChart"):]
    assert "callServerTool" in call
    assert "fink_metric_series" in call


def test_chart_library_comes_from_an_origin_the_csp_permits():
    """Any other origin is blocked by the sandbox and the request silently
    fails — a chart that never draws, with nothing in the console."""
    code = _js(srv.scan_view())
    import re
    for url in re.findall(r'https://[^\s"\']+', code):
        assert url.startswith(srv.EXT_APPS_ORIGIN), (
            f"{url} is outside the declared resourceDomains")


def test_chart_aligns_every_series_on_one_axis():
    """Series have different coverage — a balance-sheet item may start later
    than revenue. Charting each against its own dates makes two lines look
    correlated when they are merely both rising.
    """
    code = _js(srv.scan_view())
    assert "new Set(Object.values(series)" in code, "no union of dates"
    assert "spanGaps" in code, "gaps would break the line instead of bridging it"


def test_buttons_stop_propagation():
    """The row still holds a <details> the reader can toggle.

    Without stopPropagation a button click bubbles to the row as well, so
    "See chart" opens the chart and collapses the row underneath it.

    Indexed off the *handler* — `querySelector('[data-act=...]')` — not the
    markup, which contains the same attribute and would make this assert
    against a template string.
    """
    code = _js(srv.scan_view())
    for selector in ('[data-act="chart"]', '[data-act="ask"]'):
        i = code.index("querySelector('" + selector + "')")
        assert "stopPropagation" in code[i:i + 300], (
            f"{selector} does not stop the click bubbling to the row")


# ------------------------------------------------- phase 8: chart transforms
def test_all_four_transform_toggles_are_offered():
    html = srv.scan_view()
    for xf in ("none", "normalize", "yoy", "pershare"):
        assert f'data-xf="{xf}"' in html, f"no {xf} control"


def test_normalize_collapses_to_one_axis():
    """The reason normalise exists.

    Dollars and rates cannot share an axis — a 1086bp ROIC collapse is a flat
    line beside revenue in the hundreds of billions — so the default chart uses
    two. But once every series is indexed to 100 they share a unit, and two
    axes with the same scale invite comparing positions that are not
    comparable. Indexing must therefore also drop the second axis.
    """
    code = _js(srv.scan_view())
    assert 'xf === "normalize" || xf === "yoy"' in code, "oneAxis not derived"
    assert "!oneAxis && right.has(id)" in code, "datasets still split by axis"
    assert "display: !oneAxis && right.size > 0" in code, "y1 still shown"


def test_normalize_divides_by_the_absolute_base():
    """A series starting negative would invert if divided by a signed base —
    a loss shrinking would render as a line going down."""
    code = _js(srv.scan_view())
    norm = code[code.index("normalize: (pts)"):][:520]
    assert "Math.abs(base)" in norm


def test_yoy_is_twelve_monthly_points_not_four():
    """The series is monthly-aligned. A 4-point lag would be quarter-over-
    quarter wearing a year-over-year label."""
    code = _js(srv.scan_view())
    assert "pctChange(pts, 12)" in code


def test_yoy_is_sign_aware():
    """A loss narrowing from -100 to -50 is an improvement. Dividing by a
    signed base reports it as -50%, pointing the wrong way."""
    code = _js(srv.scan_view())
    assert "Math.abs(prev)" in code[code.index("function pctChange"):][:600]


def test_per_share_only_applies_where_it_means_something():
    """A margin per share is meaningless. Price already is per share. Market
    cap per share is the price again."""
    code = _js(srv.scan_view())
    rule = code[code.index("const PER_SHARE_OK"):][:260]
    assert 'UNIT[id] === "USD"' in rule
    assert 'id !== "price"' in rule
    assert 'id !== "market_cap"' in rule


def test_per_share_is_disabled_rather_than_silently_empty():
    """Clicking a control that produces nothing reads as a broken chart."""
    code = _js(srv.scan_view())
    assert "psBtn.disabled" in code
    assert "psBtn.title" in code, "a disabled control should say why"


def test_toggling_a_transform_repaints_without_refetching():
    """The view already holds the series. Refetching would spend a round trip
    recomputing what it has, and make a toggle feel slower than it is."""
    code = _js(srv.scan_view())
    handler = code[code.index("querySelectorAll(\"[data-xf]\")"):][:700]
    assert "paint(el)" in handler
    assert "callServerTool" not in handler, "a toggle should not hit the server"


def test_transform_note_states_which_view_is_active():
    """Indexed values look like nothing in particular unless labelled."""
    code = _js(srv.scan_view())
    assert "XF_LABEL[xf]" in code
    for xf in ("none", "normalize", "yoy", "pershare"):
        assert f"{xf}:" in code[code.index("const XF_LABEL"):][:400]


def test_shares_outstanding_does_not_draw_as_a_line_unless_asked():
    """It rides along for the per-share divisor. Drawn unasked it is a
    near-flat line in the billions that flattens everything else."""
    code = _js(srv.scan_view())
    assert 'id !== "shares_outstanding"' in code


# --------------------------------------- phase 8b: the standalone chart view
def test_chart_fundamentals_is_model_visible_and_opens_the_chart_view():
    """Entry point for following a thread the scan did not raise."""
    from mcp_apps import server as s
    assert s.ui_view(s.CHART_URI)["ui"]["resourceUri"] == s.CHART_URI


def test_chart_fundamentals_defaults_to_something_worth_looking_at():
    out = srv.chart_fundamentals("GOOGL")
    assert not out.get("error")
    spec = out["chartSpec"]
    assert spec["metrics"], "an empty default renders a blank panel"
    assert spec["startYear"] and spec["endYear"]
    assert spec["startYear"] < spec["endYear"]


def test_chart_fundamentals_accepts_an_explicit_window_and_metrics():
    out = srv.chart_fundamentals("GOOGL", ["roic", "gross_margin"], 2019, 2023)
    assert out["chartSpec"]["metrics"] == ["roic", "gross_margin"]
    assert out["chartSpec"]["startYear"] == 2019
    assert out["chartSpec"]["endYear"] == 2023
    # Both are rates, so both belong on the right axis.
    assert set(out["chartSpec"]["rightAxis"]) == {"roic", "gross_margin"}


def test_chart_fundamentals_names_the_valid_metrics_when_rejecting():
    """The model picks metric ids from a docstring. When it guesses wrong the
    error has to be enough to correct itself without another round trip."""
    out = srv.chart_fundamentals("GOOGL", ["ebitda_margin"])
    assert "unknown metrics" in out["error"]
    assert "gross_margin" in out["error"], "the error does not list valid ids"


def test_chart_fundamentals_reports_an_unavailable_ticker():
    assert srv.chart_fundamentals("NOTATICKER123")["error"]


def test_both_views_share_one_chart_implementation():
    """Two copies of the transforms would drift, and the transforms are
    precisely the sort of thing that gets fixed in one place only."""
    scan, chart = _js(srv.scan_view()), _js(srv.chart_view())
    for token in ("const TRANSFORMS", "function pctChange",
                  "const PER_SHARE_OK", "function drawChart", "function paint"):
        assert token in scan, f"scan view lost {token}"
        assert token in chart, f"chart view lost {token}"


def test_chart_view_performs_the_handshake_and_replays_buffered_results():
    """Same two invariants as the scan view; a second view is a second chance
    to get them wrong."""
    html = srv.chart_view()
    assert "app.connect()" in html
    assert "__finkOnToolResult" in html and "__finkLastResult" in html
    assert html.index("window.__finkLastResult = result") < html.index("app.connect()")


def test_chart_view_offers_the_same_transforms():
    html = srv.chart_view()
    for xf in ("none", "normalize", "yoy", "pershare"):
        assert f'data-xf="{xf}"' in html


def test_chart_view_escapes_interpolated_content():
    code = _js(srv.chart_view())
    assert "esc(r.ticker)" in code and "esc(r.name" in code


def test_chart_view_loads_only_from_permitted_origins():
    import re
    for url in re.findall(r'https://[^\s"\']+', _js(srv.chart_view())):
        assert url.startswith(srv.EXT_APPS_ORIGIN)


# ------------------------------------------------- phase 8c: legend labelling
def test_legend_states_the_unit_and_the_axis_side():
    """Two axes are unreadable without saying which line is on which.

    A legend reading "Revenue" and "ROIC" leaves the reader to infer that one
    is in dollars on the left and the other a percent on the right — from a
    colour.
    """
    code = _js(srv.scan_view())
    assert "function seriesLabel" in code
    fn = code[code.index("function seriesLabel"):][:700]
    assert "onRight" in fn and '"right"' in fn and '"left"' in fn
    assert "UNIT_SHORT[UNIT[id]]" in fn


def test_legend_describes_what_is_plotted_not_the_underlying_metric():
    """Under "indexed to 100" a revenue line is no longer in dollars, and
    under YoY everything is a percent whatever its source unit. Labelling
    either with the metric's own unit would be a lie."""
    fn = _js(srv.scan_view())
    fn = fn[fn.index("function seriesLabel"):][:700]
    assert '"indexed"' in fn
    assert '"% YoY"' in fn
    assert '"$/share"' in fn


def test_legend_omits_the_axis_side_when_there_is_only_one_axis():
    """Naming a side when there is nothing to distinguish it from is noise."""
    fn = _js(srv.scan_view())
    fn = fn[fn.index("function seriesLabel"):][:700]
    assert "oneAxis ? \"\"" in fn


def test_tooltip_finds_its_unit_by_id_not_by_position():
    """Regression guard on a bug written and caught in the same edit.

    Datasets are filtered — an empty series is dropped, and per-share skips
    anything that is not an absolute — so dataset order stops matching the
    series dict. Indexing by datasetIndex silently takes a neighbouring
    series' unit.
    """
    code = _js(srv.scan_view())
    assert "finkId: id" in code, "datasets do not carry their metric id"
    assert "UNIT[c.dataset.finkId]" in code
    assert "Object.keys(series)[c.datasetIndex]" not in code, (
        "tooltip is back to positional lookup, which drifts when datasets "
        "are filtered")


def test_both_views_label_legends_the_same_way():
    for view in (srv.scan_view(), srv.chart_view()):
        assert "function seriesLabel" in _js(view)


def test_price_survives_the_per_share_view_unchanged():
    """Price is already per share.

    Dividing it by the share count again is arithmetically wrong; dropping it
    as "not applicable" is worse, because it is the context line every other
    series is read against. It passes through and keeps its own unit.
    """
    code = _js(srv.scan_view())
    assert "const PER_SHARE_PASSTHROUGH" in code
    ps = code[code.index("pershare: (pts, id, shares)"):][:420]
    assert "PER_SHARE_PASSTHROUGH(id)) return pts;" in ps, (
        "price is either divided twice or dropped from the chart")
    # ...and is not mislabelled "$/share" when it passes through.
    fn = code[code.index("function seriesLabel"):][:800]
    assert "PER_SHARE_PASSTHROUGH(id)" in fn
