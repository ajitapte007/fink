import pytest
from data.process_utils import get_aligned_historical_data
from server import mcp
import json

def test_alignment_edge_cases():
    # Mock data structure representing empty/zero/missing values
    raw_cache = {
        "TIME_SERIES_MONTHLY_ADJUSTED": {
            "Monthly Adjusted Time Series": {
                "2023-12-31": {"5. adjusted close": "150.0"},
                "2023-11-30": {"5. adjusted close": "145.0"}
            }
        },
        "INCOME_STATEMENT": {
            "annualReports": [
                {
                    "fiscalDateEnding": "2023-12-31",
                    "totalRevenue": "0.0",  # Zero revenue to trigger margins protection
                    "operatingIncome": "1000.0",
                    "netIncome": "500.0",
                    "costOfRevenue": "0.0",
                    "researchAndDevelopment": "200.0",
                    "sellingGeneralAndAdministrative": "300.0"
                }
            ],
            "quarterlyReports": []
        },
        "BALANCE_SHEET": {
            "annualReports": [
                {
                    "fiscalDateEnding": "2023-12-31",
                    "commonStockSharesOutstanding": "0",  # Zero shares to trigger per-share protection
                    "cashAndCashEquivalentsAtCarryingValue": "500.0",
                    "longTermDebt": "200.0",
                    "shortTermDebt": "100.0"
                }
            ],
            "quarterlyReports": []
        },
        "CASH_FLOW": {
            "annualReports": [
                {
                    "fiscalDateEnding": "2023-12-31",
                    "operatingCashflow": "600.0",
                    "capitalExpenditures": "100.0",
                    "stockBasedCompensation": "50.0",
                    "paymentsForRepurchaseOfCommonStock": "25.0"
                }
            ],
            "quarterlyReports": []
        }
    }
    
    aligned = get_aligned_historical_data(raw_cache)
    # Filter for the smoothed point or final points
    assert len(aligned) > 0
    pt = aligned[0]
    
    # Assert safeguards triggered: zero/missing revenue sets margin metrics to None
    assert pt.operating_margin is None
    assert pt.profit_margin is None
    assert pt.gross_margin is None
    
    # Zero shares outstanding must not blow up per-share derivations
    assert pt.shares_outstanding == 0.0

    # Ratios with a zero divisor (earnings, revenue, cash flow) should resolve to None
    assert pt.pe_ratio is None
    assert pt.ps_ratio is None
    assert pt.pfcf_ratio is None
    assert pt.pocf_ratio is None

@pytest.mark.asyncio
async def test_compute_metrics_invalid_metric_safeguard():
    """An unknown metric key returns a structured error listing the allowed keys."""
    results = await mcp.call_tool("compute_metrics", {
        "ticker": "AMZN",
        "metrics": ["invalid_metric_key_123"]
    })
    data = json.loads(results.content[0].text)
    assert "error" in data
    assert "Invalid metrics" in data["error"]
    assert "invalid_metric_key_123" in data["error"]


@pytest.mark.asyncio
async def test_compute_metrics_empty_metrics_returns_all():
    """Omitting `metrics` should return the full registry, not an empty result."""
    results = await mcp.call_tool("compute_metrics", {
        "ticker": "AMZN", "start_year": 2022, "end_year": 2023
    })
    data = json.loads(results.content[0].text)
    assert "error" not in data
    assert len(data["data"]) > 0

    all_keys = {k for pt in data["data"] for k in pt}
    # A spread across categories, not just one statement
    assert "revenue" in all_keys
    assert "price" in all_keys


def test_alignment_handles_empty_cache():
    """Aligning an empty cache should not raise."""
    try:
        aligned = get_aligned_historical_data({})
    except Exception as e:
        pytest.fail(f"get_aligned_historical_data({{}}) raised {type(e).__name__}: {e}")
    assert aligned == [] or len(aligned) == 0


# ─── Timeframe resolution ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_end_year_defaults_to_current_year():
    """An omitted end_year resolves server-side to the current year.

    The LLM derives relative ranges ("last 10 years") from the date in its system
    prompt and gets it wrong often enough to matter — observed emitting end_year=2025
    while the prompt correctly stated July 2026. Resolving server-side makes the upper
    bound deterministic regardless of model drift.
    """
    from datetime import datetime
    current_year = datetime.now().year

    results = await mcp.call_tool("compute_metrics", {
        "ticker": "AMZN", "metrics": ["revenue"], "start_year": current_year - 9
    })
    data = json.loads(results.content[0].text)
    assert data["timeframe"]["end_year"] == current_year, \
        f"expected end_year to default to {current_year}, got {data['timeframe']['end_year']}"


@pytest.mark.asyncio
async def test_explicit_end_year_is_respected():
    """An explicit end_year must not be overwritten by the default."""
    results = await mcp.call_tool("compute_metrics", {
        "ticker": "AMZN", "metrics": ["revenue"], "start_year": 2018, "end_year": 2020
    })
    data = json.loads(results.content[0].text)
    assert data["timeframe"]["end_year"] == 2020
    for pt in data["data"]:
        assert int(pt["date"].split("-")[0]) <= 2020


def test_system_prompt_uses_dynamic_date_variable():
    """The seeded system prompt must not bake a literal date at provisioning time.

    It previously used an f-string evaluated during setup, so the model's notion of
    "today" froze on the deploy date. Open WebUI substitutes {{CURRENT_DATE}} per
    request, so the tokens must survive into the stored prompt verbatim.
    """
    from datetime import date
    from system_prompt import build_system_prompt

    prompt = build_system_prompt("visualize_native", "compute_metrics_native")

    assert "{{CURRENT_DATE}}" in prompt, "prompt lost its {{CURRENT_DATE}} token"
    assert "{{CURRENT_WEEKDAY}}" in prompt, "prompt lost its {{CURRENT_WEEKDAY}} token"
    # A resolved date anywhere means someone re-baked it at build time.
    assert str(date.today().year) not in prompt.split("## Available Tools")[0], \
        "system prompt bakes a static date instead of using the template variable"


def test_system_prompt_template_vars_render():
    """render_template_vars must resolve the tokens the way Open WebUI does."""
    from datetime import date
    from system_prompt import build_system_prompt, render_template_vars

    rendered = render_template_vars(
        build_system_prompt("visualize_native", "compute_metrics_native"),
        today=date(2026, 7, 28),
    )
    assert "2026-07-28" in rendered
    assert "Tuesday" in rendered
    assert "{{" not in rendered.split("## Available Tools")[0], \
        "unresolved template tokens remain after rendering"


def test_system_prompt_covers_both_tools_for_timeframes():
    """The Timeframes rule must be shared, not buried under the chart intent.

    compute_metrics takes start_year/end_year too, so a data-path question like
    "revenues over the last 10 years" needs the same guidance.
    """
    from system_prompt import build_system_prompt

    prompt = build_system_prompt("visualize_native", "compute_metrics_native")
    timeframes = prompt.split("## Timeframes")[1].split("## Query Intent")[0]

    assert "Last N years" in timeframes
    assert "both" in timeframes.lower(), "Timeframes section should state it covers both tools"
    # It must appear before intent classification, so it applies to every intent.
    assert prompt.index("## Timeframes") < prompt.index("### Intent A")
