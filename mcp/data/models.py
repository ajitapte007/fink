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

VALID_METRIC_KEYS = [
    "price",
    "revenue",
    "cost_of_goods_sold",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "selling_general_admin",
    "research_development",
    "stock_based_compensation",
    "share_repurchase",
    "cash_and_equivalents",
    "total_debt",
    "market_cap",
    "enterprise_value",
    "pe_ratio",
    "ps_ratio",
    "pfcf_ratio",
    "pocf_ratio",
    "shares_outstanding",
    "dividends",
    "dividend_yield",
    "payout_ratio_fcf",
    "payout_ratio_ocf",
    "roic",
    "operating_margin",
    "profit_margin",
    "gross_margin",
    "roa",
    "roe",
    "ebitda",
    "ev_ebitda"
]

class ChartDataPoint(BaseModel):
    date: str
    price: float
    revenue: Optional[float] = Field(None, description="Aligned Revenue value")
    cost_of_goods_sold: Optional[float] = Field(None, description="Aligned Cost of Goods Sold")
    operating_income: Optional[float] = Field(None, description="Aligned Operating Income value")
    net_income: Optional[float] = Field(None, description="Aligned Net Income value")
    free_cash_flow: Optional[float] = Field(None, description="Aligned Free Cash Flow value")
    roic: Optional[float] = Field(None, description="Aligned ROIC value")
    
    # Expanded Metrics
    eps: Optional[float] = Field(None, description="Aligned EPS value")
    capex: Optional[float] = Field(None, description="Aligned Capital Expenditures value")
    operating_cash_flow: Optional[float] = Field(None, description="Aligned Operating Cash Flow value")
    pe_ratio: Optional[float] = Field(None, description="Aligned P/E Ratio")
    ps_ratio: Optional[float] = Field(None, description="Aligned P/S Ratio")
    pfcf_ratio: Optional[float] = Field(None, description="Aligned P/FCF Ratio")
    pocf_ratio: Optional[float] = Field(None, description="Aligned P/OCF Ratio")
    shares_outstanding: Optional[float] = Field(None, description="Aligned Shares Outstanding")
    dividends: Optional[float] = Field(None, description="Aligned TTM Dividends Paid")
    dividend_yield: Optional[float] = Field(None, description="Aligned Dividend Yield TTM")
    payout_ratio_fcf: Optional[float] = Field(None, description="Aligned Payout Ratio (FCF)")
    payout_ratio_ocf: Optional[float] = Field(None, description="Aligned Payout Ratio (OCF)")
    
    # New metrics
    selling_general_admin: Optional[float] = Field(None, description="Aligned Selling, General and Administrative value")
    research_development: Optional[float] = Field(None, description="Aligned Research and Development value")
    stock_based_compensation: Optional[float] = Field(None, description="Aligned Stock-Based Compensation value")
    share_repurchase: Optional[float] = Field(None, description="Aligned Payments for Share Repurchases")
    cash_and_equivalents: Optional[float] = Field(None, description="Aligned Cash and Cash Equivalents")
    total_debt: Optional[float] = Field(None, description="Aligned Total Debt")
    market_cap: Optional[float] = Field(None, description="Aligned Market Capitalization")
    enterprise_value: Optional[float] = Field(None, description="Aligned Enterprise Value")
    operating_margin: Optional[float] = Field(None, description="Aligned Operating Margin (%)")
    profit_margin: Optional[float] = Field(None, description="Aligned Net Profit Margin (%)")
    gross_margin: Optional[float] = Field(None, description="Aligned Gross Profit Margin (%)")
    roa: Optional[float] = Field(None, description="Aligned ROA value")
    roe: Optional[float] = Field(None, description="Aligned ROE value")
    ebitda: Optional[float] = Field(None, description="Aligned EBITDA value")
    ev_ebitda: Optional[float] = Field(None, description="Aligned EV/EBITDA ratio")


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
