from pydantic import BaseModel, Field
from typing import List, Optional

class IronTriangleScores(BaseModel):
    Fundamentals: float = Field(..., description="Score 1-10 for underlying business fundamentals (ROIC, margins, etc.)")
    Valuation: float = Field(..., description="Score 1-10 for valuation multiples mapping (P/E, FCF yield)")
    SentimentMomentum: float = Field(..., description="Score 1-10 for institutional and momentum velocity")

class MetricItem(BaseModel):
    label: str
    value: str

class DrilldownMatrix(BaseModel):
    Fundamentals: List[MetricItem] = Field(..., description="Must contain ROIC, Debt/Leverage, and Profit margins")
    Valuation: List[MetricItem] = Field(..., description="Must contain the most applicable valuation ratios for this sector")
    SentimentMomentum: List[MetricItem] = Field(..., description="Must contain TTM/30-day price change, RSI, 50 SMA positioning, or volume trajectory")

class CorporateIdentity(BaseModel):
    ticker: str
    last_closing_price: str
    market_cap: str
    sector: str
    industry: str
    country: str = "US"
    last_refreshed: str = "Unknown"

class UIState(BaseModel):
    active_tab: str = Field(..., description="Target UI tab: 'overview' or 'historical'")
    selected_historical_metrics: List[str] = Field(
        default=[], 
        description="List of metrics to pre-check in the UI, e.g. ['Revenue', 'Operating Income']"
    )
    start_date: Optional[str] = Field(None, description="Recommended start date filter, e.g. '2018-01-01'")
    end_date: Optional[str] = Field(None, description="Recommended end date filter, e.g. '2022-12-31'")

from .metrics_registry import VALID_METRIC_KEYS

class ChartDataPoint(BaseModel):
    """Historical data point with all available financial metrics.
    Fields are kept in sync with METRICS_REGISTRY — see metrics_registry.py.
    """
    date: str
    price: float

    # Aggregates
    revenue: Optional[float] = Field(None, description="Total revenue, TTM-aligned")
    cost_of_goods_sold: Optional[float] = Field(None, description="Cost of goods sold")
    operating_income: Optional[float] = Field(None, description="Operating income (EBIT)")
    net_income: Optional[float] = Field(None, description="Net income after taxes")
    operating_cash_flow: Optional[float] = Field(None, description="Cash flow from operations")
    capex: Optional[float] = Field(None, description="Capital expenditures")
    free_cash_flow: Optional[float] = Field(None, description="Free cash flow (OCF minus CapEx)")
    selling_general_admin: Optional[float] = Field(None, description="SG&A expenses")
    research_development: Optional[float] = Field(None, description="R&D expenses")
    stock_based_compensation: Optional[float] = Field(None, description="Stock-based compensation expense")
    share_repurchase: Optional[float] = Field(None, description="Payments for share repurchases")
    cash_and_equivalents: Optional[float] = Field(None, description="Cash and cash equivalents")
    total_debt: Optional[float] = Field(None, description="Total debt")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    enterprise_value: Optional[float] = Field(None, description="Enterprise value")
    ebitda: Optional[float] = Field(None, description="EBITDA")

    # Valuation Ratios
    pe_ratio: Optional[float] = Field(None, description="P/E ratio (TTM)")
    ps_ratio: Optional[float] = Field(None, description="P/S ratio (TTM)")
    pfcf_ratio: Optional[float] = Field(None, description="P/FCF ratio")
    pocf_ratio: Optional[float] = Field(None, description="P/OCF ratio")
    ev_ebitda: Optional[float] = Field(None, description="EV/EBITDA ratio")

    # Shareholder Return
    shares_outstanding: Optional[float] = Field(None, description="Total shares outstanding")
    dividends: Optional[float] = Field(None, description="TTM dividends paid")
    dividend_yield: Optional[float] = Field(None, description="Dividend yield (TTM)")
    payout_ratio_fcf: Optional[float] = Field(None, description="Payout ratio (FCF %)")
    payout_ratio_ocf: Optional[float] = Field(None, description="Payout ratio (OCF %)")

    # Performance & Efficiency
    roic: Optional[float] = Field(None, description="Return on invested capital")
    operating_margin: Optional[float] = Field(None, description="Operating margin (%)")
    profit_margin: Optional[float] = Field(None, description="Net profit margin (%)")
    gross_margin: Optional[float] = Field(None, description="Gross margin (%)")
    roa: Optional[float] = Field(None, description="Return on assets (%)")
    roe: Optional[float] = Field(None, description="Return on equity (%)")

    # Balance Sheet & Working Capital — added in the phase 3 fork.
    # Charting surface for the working-capital and capital-intensity findings.
    # `depreciation_amortization` comes off the cash flow statement and is
    # normalised to a magnitude, matching how `capex` is already handled: AV
    # reports both inconsistently as positive or negative, and a sign flip would
    # silently invert the capex/D&A ratio rather than raise.
    total_assets: Optional[float] = Field(None, description="Total assets")
    current_liabilities: Optional[float] = Field(None, description="Total current liabilities")
    receivables: Optional[float] = Field(None, description="Current net receivables")
    inventory: Optional[float] = Field(None, description="Inventory")
    payables: Optional[float] = Field(None, description="Current accounts payable")
    depreciation_amortization: Optional[float] = Field(None, description="Depreciation, depletion and amortization")


# LLM Generation Schemas
class PlanLLMOutput(BaseModel):
    ui_state: UIState
    agent_pathway: List[str] = Field(..., description="Ordered list of agents that serviced this query")

class OverviewLLMOutput(BaseModel):
    iron_triangle_scores: IronTriangleScores
    drilldown_matrix: DrilldownMatrix

class SynthesisLLMOutput(BaseModel):
    synthesis_summary: str = Field(..., description="Synthesis detailing position in sector/moat, recent sentiment catalysts, and what the stock is pricing in. If historical, answer the question directly using exact numbers and dates.")

# API Request Schemas
class ChatRequest(BaseModel):
    ticker: str
    message: str
    force_refresh: bool = False

class SynthesisRequest(BaseModel):
    ticker: str
    message: str
    active_tab: str

# API Response Schemas
class PlanResponse(BaseModel):
    ui_state: UIState
    agent_pathway: List[str]
    corporate_identity: CorporateIdentity

class OverviewDataResponse(BaseModel):
    iron_triangle_scores: IronTriangleScores
    drilldown_matrix: DrilldownMatrix
    synthesis_summary: str

class HistoricalDataResponse(BaseModel):
    historical_chart_data: List[ChartDataPoint]

class ChatSynthesisResponse(BaseModel):
    synthesis_summary: str
