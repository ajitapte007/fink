"""Moderator agent — synthesizes all analyses into a final verdict."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.config import get_settings
from app.models.schemas import (
    AgentOutput,
    CrossExamResult,
    FinancialData,
    FinalReport,
)
from app.services.llm_service import call_llm
from app.prompts.agent_prompts import (
    MODERATOR_SYSTEM_PROMPT,
    build_moderator_user_prompt,
)
from app.utils.logging_config import get_logger
from app.utils.validation import extract_json_from_text

logger = get_logger("agents.moderator")


async def synthesize_report(
    data: FinancialData,
    bull: AgentOutput,
    bear: AgentOutput,
    neutral: AgentOutput,
    cross_exams: list[CrossExamResult],
) -> FinalReport:
    """
    Run the moderator against all inputs and assemble the FinalReport.

    Uses the high-quality model (MODERATOR_MODEL).
    """
    settings = get_settings()

    cross_exam_dicts = [ce.model_dump() for ce in cross_exams]

    user_prompt = build_moderator_user_prompt(
        financial_data_json=data.model_dump_json(indent=2),
        bull_json=bull.model_dump_json(indent=2),
        bear_json=bear.model_dump_json(indent=2),
        neutral_json=neutral.model_dump_json(indent=2),
        cross_exam_json=json.dumps(cross_exam_dicts, indent=2),
    )

    last_error = None
    for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
        try:
            raw = await call_llm(
                user_prompt=user_prompt,
                system_prompt=MODERATOR_SYSTEM_PROMPT,
                model=settings.MODERATOR_MODEL,
                temperature=0.2,
            )

            parsed = json.loads(extract_json_from_text(raw))

            report = FinalReport(
                ticker=data.ticker,
                company_name=data.company_name,
                analysis_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                executive_summary=parsed.get("executive_summary", ""),
                bull_case=bull,
                bear_case=bear,
                neutral_case=neutral,
                cross_examination_results=cross_exams,
                moderator_commentary=parsed.get("moderator_commentary", ""),
                key_catalysts=parsed.get("key_catalysts", []),
                primary_risks=parsed.get("primary_risks", []),
            )

            logger.info("Moderator synthesis complete (objective analysis)")
            return report

        except Exception as exc:
            last_error = exc
            logger.warning(
                f"Moderator attempt {attempt}/{settings.LLM_MAX_RETRIES} failed: {exc}"
            )

    # All retries failed — build a minimal report
    logger.error(f"Moderator exhausted retries — returning minimal report: {last_error}")
    return FinalReport(
        ticker=data.ticker,
        company_name=data.company_name,
        analysis_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        executive_summary="Moderator synthesis could not be completed.",
        bull_case=bull,
        bear_case=bear,
        neutral_case=neutral,
        cross_examination_results=cross_exams,
        moderator_commentary="All moderator retries exhausted.",
        key_catalysts=[],
        primary_risks=["Moderator analysis failed — exercise caution."],
    )
