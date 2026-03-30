"""Pre-built demo reports for when LLM APIs are unavailable."""

from app.models.schemas import (
    FinalReport, AgentOutput, CrossExamResult
)
from datetime import datetime, timezone


def get_demo_report(ticker: str) -> FinalReport:
    """Return a realistic pre-built investment report for demonstration."""

    ticker = ticker.upper()

    return FinalReport(
        ticker=ticker,
        company_name="Microsoft Corp" if ticker == "MSFT" else f"{ticker} Inc.",
        analysis_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        executive_summary=(
            f"{ticker} presents a compelling investment case driven by dominant cloud infrastructure (Azure), "
            f"aggressive AI monetization through Copilot integrations across the Office 365 suite, and "
            f"robust free cash flow generation exceeding $67B annually. The company's strategic positioning "
            f"in enterprise AI — bolstered by its deep OpenAI partnership — gives it a first-mover advantage "
            f"in the highest-growth segment of technology. However, elevated valuation multiples (PE ~35x) "
            f"and increasing regulatory scrutiny of AI and cloud market dominance warrant measured optimism."
        ),
        bull_case=AgentOutput(
            agent="Bull Analyst",
            stance="bullish",
            thesis=(
                f"{ticker} is the best-positioned mega-cap to capitalize on the generational AI wave. "
                f"Azure's AI revenue is accelerating, Copilot adoption is driving ARPU expansion across "
                f"365M+ commercial Office users, and the gaming division (Activision Blizzard) adds a "
                f"high-margin recurring revenue stream."
            ),
            key_points=[
                "Azure cloud revenue grew 29% YoY with AI services contributing 12 percentage points of growth",
                "Microsoft 365 Copilot is being adopted by 70% of Fortune 500 companies, driving $30/user/month premium",
                "Free cash flow of $67B provides massive runway for dividends, buybacks, and AI infrastructure investment",
                "Gaming segment (Activision Blizzard) adds $8.7B in annual revenue with 50%+ gross margins",
                "Operating margins expanded to 44%, highest among mega-cap tech peers",
            ],
            risks=[
                "Concentration risk in OpenAI partnership — dependency on a single AI provider",
                "Azure growth could decelerate as hyperscaler market matures",
                "Regulatory risk from EU Digital Markets Act and US antitrust scrutiny",
            ],
            opportunities=[
                "AI agent ecosystem could create entirely new revenue categories",
                "Copilot monetization only at 15% penetration — massive TAM runway",
                "LinkedIn AI features driving premium subscription growth",
            ],
            data_references=[
                "Azure revenue: $25.5B/quarter (29% YoY growth)",
                "Free Cash Flow: $67B TTM",
                "Operating Margin: 44%",
                "Market Cap: $3.01T",
                "Copilot users: 1.3M paid seats",
            ],
            confidence=0.82,
        ),
        bear_case=AgentOutput(
            agent="Bear Analyst",
            stance="bearish",
            thesis=(
                f"{ticker} trades at a significant premium that assumes flawless AI execution. "
                f"At 35x earnings, any slowdown in Azure growth or Copilot monetization disappointment "
                f"could trigger a meaningful multiple compression. The $13B annual OpenAI commitment "
                f"represents an enormous concentrated bet with uncertain ROI."
            ),
            key_points=[
                "PE ratio of 35.2x is 40% above the 10-year median — pricing in perfection",
                "OpenAI investment of $13B creates binary risk — partnership terms could change unfavorably",
                "Enterprise AI adoption is slower than marketed — many Copilot pilots not converting to paid",
                "Cloud infrastructure capex of $44B is accelerating, compressing near-term free cash flow yield",
                "Competition from AWS Bedrock and Google Cloud AI is intensifying on price and features",
            ],
            risks=[
                "Multiple compression risk if earnings growth decelerates below 15%",
                "Capex overshoot could reduce FCF by 15-20% in the next 2 years",
                "Antitrust action could force structural changes to bundling strategy",
            ],
            opportunities=[
                "Valuation correction could create better entry point at 28-30x PE",
                "Cost optimization cycle could improve margins even with capex growth",
            ],
            data_references=[
                "Forward PE: 31.4x (consensus estimates)",
                "Capex guidance: $44B for FY2025",
                "OpenAI committed investment: $13B",
                "PEG Ratio: 2.4x (above fair value threshold)",
                "Debt-to-Equity: 0.45",
            ],
            confidence=0.68,
        ),
        neutral_case=AgentOutput(
            agent="Neutral Analyst",
            stance="neutral",
            thesis=(
                f"{ticker}'s fundamentals are strong but the stock is fairly valued at current levels. "
                f"The risk/reward is balanced between genuine AI-driven growth acceleration and elevated "
                f"valuation multiples that leave limited margin of safety."
            ),
            key_points=[
                "Revenue growth of 18% YoY is robust but already reflected in forward estimates",
                "Profit margins at 36% are best-in-class and show operational excellence",
                "Analyst consensus price target of $450 implies ~12% upside — moderate, not exceptional",
                "Dividend yield of 0.76% with 10% annual growth provides income floor",
                "Beta of 0.89 suggests lower volatility than market — defensive quality characteristic",
            ],
            risks=[
                "Consensus estimates may be too optimistic on AI revenue contribution",
                "Currency headwinds could impact international revenue (55% of total)",
            ],
            opportunities=[
                "Any pullback to $370-380 range would offer attractive entry with better risk/reward",
                "Dividend growth trajectory supports long-term total return thesis",
            ],
            data_references=[
                "Revenue Growth: 18% YoY",
                "Net Income: $82B TTM",
                "Dividend Yield: 0.76%",
                "Beta: 0.89",
                "Analyst Target: $450 (12% upside)",
                "Total Revenue: $227B",
            ],
            confidence=0.75,
        ),
        cross_examination_results=[
            CrossExamResult(
                reviewer="Bull Analyst",
                target="Bear Analyst",
                critiques=[
                    "The Bear's PE premium argument ignores that MSFT deserves a premium due to "
                    "best-in-class margins, diversified revenue, and durable competitive moats. "
                    "Comparing to historical median PE ignores structural shift in business quality."
                ],
                agreements=["Capex acceleration is a valid near-term concern worth monitoring"],
                bias_flags=["Bear may be anchoring too heavily on valuation without weighing growth quality"],
                severity="medium",
            ),
            CrossExamResult(
                reviewer="Bear Analyst",
                target="Bull Analyst",
                critiques=[
                    "The Bull's 82% confidence is aggressively high given macro uncertainty. "
                    "The Copilot adoption figures cited (70% of F500) measure trials, not paid conversions. "
                    "Actual paid seat count of 1.3M vs 365M users suggests <1% conversion."
                ],
                agreements=["Azure's growth trajectory is genuinely impressive and market-leading"],
                bias_flags=["Bull may be conflating trial adoption with revenue-generating adoption"],
                severity="high",
            ),
            CrossExamResult(
                reviewer="Neutral Analyst",
                target="Bull Analyst",
                critiques=[
                    "The Bull thesis relies heavily on forward-looking AI revenue projections that "
                    "haven't yet materialized at scale. Current AI revenue contribution to Azure "
                    "is meaningful but not yet transformative to the overall P&L."
                ],
                agreements=["Azure cloud positioning is genuinely best-in-class among hyperscalers"],
                bias_flags=["Some data references mix trailing and forward metrics without clear distinction"],
                severity="medium",
            ),
            CrossExamResult(
                reviewer="Neutral Analyst",
                target="Bear Analyst",
                critiques=[
                    "The Bear's comparison of MSFT to historical PE median fails to account for "
                    "the structural improvement in business mix — shift from licenses to recurring "
                    "SaaS revenue fundamentally changes the appropriate valuation range."
                ],
                agreements=["Capex trajectory does warrant close monitoring for FCF impact"],
                bias_flags=["May be overweighting short-term capex pain vs long-term AI infrastructure value"],
                severity="medium",
            ),
            CrossExamResult(
                reviewer="Bull Analyst",
                target="Neutral Analyst",
                critiques=[
                    "The Neutral's 'fairly valued' conclusion is too conservative. The analyst "
                    "consensus target of $450 likely underestimates Copilot's revenue potential "
                    "over a 2-3 year horizon as enterprise adoption curves typically accelerate."
                ],
                agreements=["The defensive quality characteristics and dividend growth are valid points"],
                bias_flags=["Neutral may be anchoring too heavily on consensus estimates which lag reality"],
                severity="low",
            ),
            CrossExamResult(
                reviewer="Bear Analyst",
                target="Neutral Analyst",
                critiques=[
                    "The Neutral's characterization of 18% revenue growth as 'robust but reflected' "
                    "understates the risk that growth is peaking, not accelerating. If AI revenue "
                    "disappoints, the growth rate could decelerate to 12-14% quickly."
                ],
                agreements=["Dividend yield and low beta do provide defensive characteristics"],
                bias_flags=["Neutral may be underweighting downside scenario probability"],
                severity="medium",
            ),
        ],
        moderator_commentary=(
            f"After reviewing all three analyst perspectives and their cross-examinations, the committee "
            f"finds the strongest arguments on the Bull side — particularly Azure's AI-driven acceleration "
            f"and Copilot's enormous addressable market. However, the Bear raises valid concerns about "
            f"valuation multiples pricing in flawless execution. The Neutral's observation about limited "
            f"margin of safety at current prices is well-taken. On balance, {ticker} is a high-quality "
            f"compounder that investors should accumulate on pullbacks rather than chase at all-time highs."
        ),
        key_catalysts=[
            "Azure AI revenue crossing $10B annual run rate",
            "Microsoft 365 Copilot surpassing 5M paid seats",
            "FY2025 earnings beat with raised guidance",
            "Potential AI agent marketplace launch driving new revenue stream",
            "Activision Blizzard synergies exceeding integration targets",
        ],
        primary_risks=[
            "OpenAI partnership disruption or renegotiation of terms",
            "Cloud infrastructure capex significantly exceeding $50B without proportional revenue growth",
            "EU regulatory action forcing unbundling of Teams/Copilot from Office 365",
            "Macro-driven enterprise spending slowdown affecting cloud and SaaS budgets",
            "Competitive pressure from AWS and Google Cloud on AI model pricing",
        ],
        disclaimer=(
            "⚠️ DEMO MODE — This is a pre-built demonstration report generated without live AI agents. "
            "It uses representative data to showcase the platform's capabilities. "
            "When your API key has available credits, the system will generate live AI-powered analysis. "
            "This does not constitute investment advice."
        ),
    )
