import pytest
from unittest.mock import patch, MagicMock
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
    
    # Assert shares outstanding is 0.0 or sets eps to None
    assert pt.shares_outstanding == 0.0
    assert pt.eps is None
    
    # Ratios having eps/fcf or rev/shares divisor of zero should resolve to None
    assert pt.pe_ratio is None
    assert pt.ps_ratio is None
    assert pt.pfcf_ratio is None
    assert pt.pocf_ratio is None

@pytest.mark.asyncio
async def test_filter_metrics_tool_safeguards():
    # Test that invalid metrics list throws an error in filter_metrics_tool
    results = await mcp.call_tool("filter_metrics_tool", {
        "ticker": "AMZN",
        "metrics": ["invalid_metric_key_123"]
    })
    data = json.loads(results.content[0].text)
    assert "error" in data
    assert "Invalid metrics requested" in data["error"]

@pytest.mark.asyncio
@patch('google.genai.Client')
async def test_qa_tool_mocked(mock_genai_client):
    # Mock the return value of gemini client generate_content
    mock_client_instance = MagicMock()
    mock_genai_client.return_value = mock_client_instance
    mock_response = MagicMock()
    mock_response.text = "Analyst Report content goes here."
    mock_client_instance.models.generate_content.return_value = mock_response
    
    results = await mcp.call_tool("qa_tool", {
        "ticker": "AAPL",
        "financial_data": "{}",
        "question": "What is AAPL's moat?"
    })
    
    assert "Analyst Report content goes here." in results.content[0].text
