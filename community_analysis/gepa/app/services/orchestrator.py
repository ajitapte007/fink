"""4-phase pipeline orchestrator."""

from __future__ import annotations

import asyncio
import time

from app.agents.bull_agent import BullAgent
from app.agents.bear_agent import BearAgent
from app.agents.neutral_agent import NeutralAgent
from app.agents.cross_examiner import run_cross_examination
from app.agents.moderator import synthesize_report
from app.models.schemas import FinancialData, FinalReport
from app.services.data_extractor import fetch_stock_data
from app.services.demo_report import get_demo_report
from app.utils.logging_config import get_logger

logger = get_logger("orchestrator")


def _all_agents_failed(bull, bear, neutral) -> bool:
    """Check if all agents returned fallback/error responses."""
    return all(
        a.confidence == 0.0 and "could not be completed" in a.thesis.lower()
        for a in (bull, bear, neutral)
    )


async def run_analysis(ticker: str) -> FinalReport:
    """
    Execute the full 4-phase investment committee pipeline.

    Phase 1 — Data ingestion
    Phase 2 — Parallel agent analysis (bull, bear, neutral)
    Phase 3 — Cross-examination (6 parallel critiques)
    Phase 4 — Moderator synthesis → FinalReport

    Falls back to a demo report if all LLM calls fail (e.g. API quota exhausted).
    """
    t0 = time.perf_counter()

    # ── Phase 1: Data Ingestion ────────────────────────────
    logger.info(f"Phase 1 — Fetching data for {ticker}")
    data: FinancialData = await fetch_stock_data(ticker)
    logger.info(f"Phase 1 complete — {data.company_name} ({data.ticker})")

    # ── Phase 2: Parallel Agent Analysis ───────────────────
    logger.info("Phase 2 — Running bull / bear / neutral agents in parallel")
    bull_agent = BullAgent()
    bear_agent = BearAgent()
    neutral_agent = NeutralAgent()

    bull_result, bear_result, neutral_result = await asyncio.gather(
        bull_agent.analyze(data),
        bear_agent.analyze(data),
        neutral_agent.analyze(data),
    )
    logger.info("Phase 2 complete — all 3 agents finished")

    # ── Detect total LLM failure → Demo Mode ──────────────
    if _all_agents_failed(bull_result, bear_result, neutral_result):
        elapsed = time.perf_counter() - t0
        logger.warning(
            f"All agents returned fallback — API quota likely exhausted. "
            f"Returning DEMO report for {ticker} ({elapsed:.1f}s)"
        )
        return get_demo_report(ticker)

    # ── Phase 3: Cross-Examination ─────────────────────────
    logger.info("Phase 3 — Running cross-examination (6 pairs)")
    cross_exam_results = await run_cross_examination(
        bull=bull_result,
        bear=bear_result,
        neutral=neutral_result,
        data=data,
    )
    logger.info(f"Phase 3 complete — {len(cross_exam_results)} cross-exams done")

    # ── Phase 4: Moderator Synthesis ───────────────────────
    logger.info("Phase 4 — Moderator synthesizing final report")
    report = await synthesize_report(
        data=data,
        bull=bull_result,
        bear=bear_result,
        neutral=neutral_result,
        cross_exams=cross_exam_results,
    )

    elapsed = time.perf_counter() - t0
    logger.info(
        f"Pipeline complete for {ticker} in {elapsed:.1f}s"
    )

    return report

