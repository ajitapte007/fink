"""API routes for stock analysis."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import AnalyzeRequest, FinalReport, ErrorResponse
from app.services.orchestrator import run_analysis
from app.services.debate_orchestrator import run_live_debate_stream
from app.utils.logging_config import get_logger

logger = get_logger("routes.analysis")

router = APIRouter()


@router.post(
    "/analyze-stock",
    response_model=FinalReport,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Analyze a stock using the multi-agent investment committee",
    description=(
        "Runs a 4-phase pipeline: data ingestion, parallel bull/bear/neutral "
        "analysis, cross-examination, and moderator synthesis. Returns a "
        "comprehensive investment report."
    ),
)
async def analyze_stock(request: AnalyzeRequest) -> FinalReport:
    ticker = request.ticker.strip().upper()

    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker symbol is required.")

    logger.info(f"Received analysis request for {ticker}")

    try:
        report = await run_analysis(ticker)
        return report

    except ValueError as exc:
        logger.error(f"Analysis failed for {ticker}: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception as exc:
        logger.error(f"Unexpected error analysing {ticker}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error during analysis: {type(exc).__name__}",
        )


@router.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "gepa"}


@router.post("/live-debate/stream")
async def stream_debate(request: AnalyzeRequest):
    """
    Run a real-time, multi-turn LLM debate on the given stock.
    Returns a Server-Sent Events (SSE) stream of `DebateMessage` JSONs.
    """
    ticker = request.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker symbol is required.")
        
    logger.info(f"Received live debate request for {ticker}")
    return StreamingResponse(
        run_live_debate_stream(ticker, rounds=2),
        media_type="text/event-stream"
    )
