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


def test_click_handler_cannot_take_the_panel_down():
    """An exception escaping the click handler kills the view."""
    html = srv.scan_view()
    click = html[html.index('addEventListener("click"'):]
    assert "try {" in click[:400] and "catch" in click[:400]


# ------------------------------------------------------------- payload shape
def test_scan_payload_carries_every_field_the_view_reads():
    """Keeps the tool and the view from drifting apart silently — a missing key
    renders as `undefined` in the panel rather than raising."""
    payload = srv.scan_fundamentals("GOOGL")
    for key in ("ticker", "name", "sector", "industry", "businessModel",
                "quarters", "checksRun", "declined", "insufficient",
                "findings", "skips"):
        assert key in payload, f"payload missing {key!r}, which the view reads"

    assert payload["findings"], "GOOGL should produce findings"
    for f in payload["findings"]:
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
    assert out["findings"] == []


def test_declined_company_is_not_reported_as_clean():
    out = srv.scan_fundamentals("UNH")
    assert out["declined"] is True
    assert out["findings"] == []
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
