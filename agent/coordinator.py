import os
import json
import datetime
from google import genai
from google.genai import types
from models import (
    PlanLLMOutput, PlanResponse,
    OverviewLLMOutput, OverviewDataResponse,
    SynthesisLLMOutput, ChatSynthesisResponse
)
from alphavantage.fetch_utils import get_all_data_for_ticker
from alphavantage.process_utils import get_aligned_historical_data, get_corporate_identity

client = genai.Client()

_CACHE_MAP = {}

def get_or_create_cache(ticker: str, raw_cache: dict) -> str:
    if ticker in _CACHE_MAP:
        try:
            # Verify cache is still alive
            c = client.caches.get(name=_CACHE_MAP[ticker])
            return c.name
        except Exception:
            pass
            
    c = client.caches.create(
        model="gemini-2.5-flash",
        config=types.CreateCachedContentConfig(
            contents=[json.dumps(raw_cache)],
            ttl="3600s"
        )
    )
    _CACHE_MAP[ticker] = c.name
    return c.name

def get_plan(ticker: str, message: str) -> PlanResponse:
    raw_cache = get_all_data_for_ticker(ticker)
    
    # We only need the OVERVIEW portion for planning, no need to send the full 150k token cache
    # This makes the planner incredibly fast and cheap.
    planner_context = raw_cache.get("OVERVIEW", {})
    
    prompt = f"""
    You are the Coordinator Agent (Planner).
    The user is looking at the dashboard for ticker "{ticker}".
    The user's direct query is: "{message}"
    
    Determine if this is an "overview" query (e.g. general business, moat, fundamentals) 
    or a "historical" query (e.g. plot revenue, dividend history, EPS over time).
    
    If historical:
    - active_tab = "historical"
    - selected_historical_metrics = [List of specific metrics requested out of: 'Revenue', 'Operating Income', 'Net Income', 'EPS', 'Free Cash Flow', 'Operating Cash Flow', 'Capex', 'P/E', 'P/S', 'P/FCF', 'P/OCF', 'Shares Outstanding', 'Dividends (TTM)', 'Dividend Yield', 'Payout Ratio (FCF)', 'Payout Ratio (OCF)', 'ROIC']
    - agent_pathway = ["Coordinator Agent", "Historical Data Specialist"]
    
    If overview:
    - active_tab = "overview"
    - selected_historical_metrics = []
    - agent_pathway = ["Coordinator Agent", "Core Metric Specialists", "Sector Agent", "Stage Agent"]
    
    Return the exact payload adhering to the PlanLLMOutput JSON schema.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=PlanLLMOutput,
            temperature=0.0
        )
    )
    
    plan_out = PlanLLMOutput.model_validate_json(response.text)
    
    return PlanResponse(
        ui_state=plan_out.ui_state,
        agent_pathway=plan_out.agent_pathway,
        corporate_identity=get_corporate_identity(raw_cache)
    )

def get_overview_data(ticker: str) -> OverviewDataResponse:
    raw_cache = get_all_data_for_ticker(ticker)
    cache_name = get_or_create_cache(ticker, raw_cache)
    
    prompt = f"""
    You are the Sector and Stage Agents analyzing "{ticker}".
    Analyze the full financial data provided in the cached context.
    
    1. Provide Iron Triangle scores (1-10) for Fundamentals, Valuation, and SentimentMomentum.
    2. Provide a drilldown_matrix containing key metrics:
       - 'Fundamentals': ROIC, Debt/Leverage, and Profit margins.
       - 'Valuation': The 3 most applicable ratios for this company's sector.
       - 'SentimentMomentum': 30-day/TTM price change, RSI or 50 SMA relative position, volume trajectory.
    
    Return the exact final payload adhering to the OverviewLLMOutput JSON schema.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=OverviewLLMOutput,
            temperature=0.2,
            cached_content=cache_name
        )
    )
    
    overview_out = OverviewLLMOutput.model_validate_json(response.text)
    
    # Generate the synthesis summary specifically for the overview tab
    synthesis_prompt = f"Analyze '{ticker}' based on the cached context. Provide a sophisticated 1-paragraph summary detailing its position in the sector, its competitive moat, recent sentiment catalysts, and what expectations or growth rate the stock currently seems to be pricing in."
    synthesis_response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=synthesis_prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            cached_content=cache_name
        )
    )
    
    return OverviewDataResponse(
        iron_triangle_scores=overview_out.iron_triangle_scores,
        drilldown_matrix=overview_out.drilldown_matrix,
        synthesis_summary=synthesis_response.text
    )

def get_synthesis(ticker: str, message: str) -> ChatSynthesisResponse:
    raw_cache = get_all_data_for_ticker(ticker)
    cache_name = get_or_create_cache(ticker, raw_cache)
    
    prompt = f"""
    You are the Synthesis Specialist.
    The user is looking at the dashboard for ticker "{ticker}".
    The user's query is: "{message}"
    
    Using the cached financial history, provide an exact, precise written response to their question.
    Cite exact numbers, years, and dates when discussing historical trends.
    Do not generate markdown or code, just a clean conversational paragraph.
    
    Return the payload adhering to the SynthesisLLMOutput JSON schema.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=SynthesisLLMOutput,
            temperature=0.2,
            cached_content=cache_name
        )
    )
    
    synth_out = SynthesisLLMOutput.model_validate_json(response.text)
    
    return ChatSynthesisResponse(
        synthesis_summary=synth_out.synthesis_summary
    )
