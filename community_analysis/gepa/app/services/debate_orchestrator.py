"""Live debate orchestrator using SSE streaming."""

from __future__ import annotations

import json
from typing import AsyncGenerator

from app.models.schemas import FinancialData, DebateMessage
from app.prompts.agent_prompts import (
    DEBATE_SYSTEM_PROMPT,
    BULL_SYSTEM_PROMPT,
    BEAR_SYSTEM_PROMPT,
    NEUTRAL_SYSTEM_PROMPT,
    build_debate_user_prompt,
)
from app.services.data_extractor import fetch_stock_data
from app.services.llm_service import call_llm_structured
from app.utils.logging_config import get_logger

logger = get_logger("debate_orchestrator")


# Parse out only the role description part from the static prompts
def _extract_role(prompt: str) -> str:
    """Extract just the role/approach part of the static system prompts."""
    # Split by common rules to just get the persona
    parts = prompt.split("STRICT RULES")
    return parts[0].strip()


BULL_ROLE = _extract_role(BULL_SYSTEM_PROMPT)
BEAR_ROLE = _extract_role(BEAR_SYSTEM_PROMPT)
NEUTRAL_ROLE = _extract_role(NEUTRAL_SYSTEM_PROMPT)

AGENTS = [
    {"name": "Bull Analyst", "role": BULL_ROLE},
    {"name": "Bear Analyst", "role": BEAR_ROLE},
    {"name": "Neutral Analyst", "role": NEUTRAL_ROLE},
]


async def run_live_debate_stream(ticker: str, rounds: int = 2) -> AsyncGenerator[str, None]:
    """
    Run a sequential debate between agents and yield SSE JSON strings.
    """
    logger.info(f"Starting live debate for {ticker}")

    # ── 1. Fetch Data ──────────────────────────────────────────────────
    try:
        data: FinancialData = await fetch_stock_data(ticker)
        data_json = data.model_dump_json(indent=2)
    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker}: {e}")
        error_msg = DebateMessage(
            speaker="System",
            message=f"Could not initialize debate: data pipeline failed [{e}]",
            confidence=0.0
        )
        yield f"data: {error_msg.model_dump_json()}\n\n"
        return

    # Notify frontend that data is ready
    system_msg = DebateMessage(
        speaker="System",
        message=f"Financial data for {data.company_name} loaded. The debate will now begin.",
        confidence=100.0,
    )
    yield f"data: {system_msg.model_dump_json()}\n\n"

    # ── 2. Debate Loop ─────────────────────────────────────────────────
    conversation_history = []
    
    total_turns = len(AGENTS) * rounds
    turn = 0

    for round_num in range(rounds):
        for agent in AGENTS:
            turn += 1
            logger.info(f"Debate Turn {turn}/{total_turns} — {agent['name']}")

            # Build prompts
            system_prompt = DEBATE_SYSTEM_PROMPT.format(agent_role_description=agent["role"])
            
            # Format conversation history
            if not conversation_history:
                history_text = "No conversation yet. You are the first speaker. Present your opening argument."
            else:
                history_text = "\n\n".join(
                    f"**{msg['speaker']}**: {msg['message']}"
                    for msg in conversation_history[-5:] # Keep last 5 messages for context
                )

            user_prompt = build_debate_user_prompt(
                financial_data_json=data_json,
                conversation_history_json=history_text,
            )

            # Call LLM
            try:
                response: DebateMessage = await call_llm_structured(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    response_model=DebateMessage,
                    # We can use the agent model for speed
                )
                
                # Enforce the correct speaker name just in case the LLM hallucinates it
                response.speaker = agent["name"]
                
                # Append to history
                conversation_history.append({
                    "speaker": response.speaker,
                    "message": response.message
                })

                # Yield SSE
                yield f"data: {response.model_dump_json()}\n\n"

            except Exception as e:
                logger.error(f"Agent {agent['name']} failed in debate: {e}")
                err_msg = DebateMessage(
                    speaker=agent["name"],
                    message=f"*Connection lost* (LLM Error: {e})",
                    confidence=0.0
                )
                conversation_history.append({
                    "speaker": err_msg.speaker,
                    "message": err_msg.message
                })
                yield f"data: {err_msg.model_dump_json()}\n\n"

    # ── 3. Conclusion ──────────────────────────────────────────────────
    closing_msg = DebateMessage(
        speaker="System",
        message="The debate has concluded.",
        confidence=100.0
    )
    yield f"data: {closing_msg.model_dump_json()}\n\n"
    logger.info(f"Live debate for {ticker} finished successfully")
