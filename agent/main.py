import uvicorn
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import ChatRequest, SynthesisRequest, PlanResponse, OverviewDataResponse, HistoricalDataResponse, ChatSynthesisResponse
from coordinator import get_plan, get_overview_data, get_synthesis
from alphavantage.fetch_utils import get_all_data_for_ticker
from alphavantage.process_utils import get_aligned_historical_data

app = FastAPI(title="Fink Agentic Workspace API")

# Allow React UI to talk to the backend on localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/plan", response_model=PlanResponse)
async def plan_endpoint(request: ChatRequest):
    try:
        return get_plan(request.ticker, request.message, request.force_refresh)
    except Exception as e:
        raise e

@app.post("/api/data/overview", response_model=OverviewDataResponse)
async def overview_endpoint(request: ChatRequest):
    try:
        return get_overview_data(request.ticker)
    except Exception as e:
        raise e

@app.post("/api/data/historical", response_model=HistoricalDataResponse)
async def historical_endpoint(request: ChatRequest):
    try:
        # Programmatic endpoint, skips LLM
        raw_cache = get_all_data_for_ticker(request.ticker)
        return HistoricalDataResponse(historical_chart_data=get_aligned_historical_data(raw_cache))
    except Exception as e:
        raise e

@app.post("/api/chat/reply", response_model=ChatSynthesisResponse)
async def chat_reply_endpoint(request: SynthesisRequest):
    try:
        return get_synthesis(request.ticker, request.message)
    except Exception as e:
        raise e

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
