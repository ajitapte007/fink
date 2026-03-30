"""Cross-examination engine — agents critique each other's outputs."""

from __future__ import annotations

import asyncio

from app.models.schemas import AgentOutput, CrossExamResult, FinancialData
from app.services.llm_service import call_llm_structured
from app.prompts.agent_prompts import (
    CROSS_EXAM_SYSTEM_PROMPT,
    build_cross_exam_user_prompt,
)
from app.utils.logging_config import get_logger
from app.utils.validation import create_fallback_cross_exam

logger = get_logger("agents.cross_examiner")


async def _single_cross_exam(
    reviewer: AgentOutput,
    target: AgentOutput,
    financial_data_json: str,
) -> CrossExamResult:
    """Run one cross-examination: reviewer critiques target."""
    logger.info(f"Cross-exam: {reviewer.agent} → {target.agent}")

    user_prompt = build_cross_exam_user_prompt(
        reviewer_output_json=reviewer.model_dump_json(indent=2),
        target_output_json=target.model_dump_json(indent=2),
        financial_data_json=financial_data_json,
    )

    try:
        result = await call_llm_structured(
            user_prompt=user_prompt,
            system_prompt=CROSS_EXAM_SYSTEM_PROMPT,
            response_model=CrossExamResult,
        )
        result.reviewer = reviewer.agent
        result.target = target.agent
        return result

    except ValueError as exc:
        logger.error(f"Cross-exam {reviewer.agent}→{target.agent} failed: {exc}")
        fallback = create_fallback_cross_exam(reviewer.agent, target.agent)
        return CrossExamResult.model_validate(fallback)


async def run_cross_examination(
    bull: AgentOutput,
    bear: AgentOutput,
    neutral: AgentOutput,
    data: FinancialData,
) -> list[CrossExamResult]:
    """
    Run all 6 cross-examinations in parallel:
      bull→bear, bull→neutral,
      bear→bull, bear→neutral,
      neutral→bull, neutral→bear
    """
    financial_json = data.model_dump_json(indent=2)

    pairs = [
        (bull, bear),
        (bull, neutral),
        (bear, bull),
        (bear, neutral),
        (neutral, bull),
        (neutral, bear),
    ]

    tasks = [
        _single_cross_exam(reviewer, target, financial_json)
        for reviewer, target in pairs
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert any unexpected exceptions to fallbacks
    clean_results: list[CrossExamResult] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            reviewer_name = pairs[i][0].agent
            target_name = pairs[i][1].agent
            logger.error(f"Unexpected cross-exam error: {r}")
            fallback = create_fallback_cross_exam(reviewer_name, target_name)
            clean_results.append(CrossExamResult.model_validate(fallback))
        else:
            clean_results.append(r)

    return clean_results
