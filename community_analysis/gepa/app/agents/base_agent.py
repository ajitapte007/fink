"""Base agent class with shared LLM-calling logic."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.schemas import AgentOutput, FinancialData
from app.services.llm_service import call_llm_structured
from app.prompts.agent_prompts import build_agent_user_prompt
from app.utils.logging_config import get_logger
from app.utils.validation import create_fallback_agent_output

logger = get_logger("agents.base")


class BaseAgent(ABC):
    """Abstract base for bull / bear / neutral analyst agents."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def stance(self) -> str: ...

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @property
    def model(self) -> str | None:
        """Override to force a specific model; None → use default agent model."""
        return None

    async def analyze(self, data: FinancialData) -> AgentOutput:
        """Run analysis and return validated output (or fallback)."""
        logger.info(f"{self.name} agent starting analysis for {data.ticker}")

        user_prompt = build_agent_user_prompt(
            data.model_dump_json(indent=2)
        )

        try:
            result = await call_llm_structured(
                user_prompt=user_prompt,
                system_prompt=self.system_prompt,
                response_model=AgentOutput,
                model=self.model,
            )
            # Ensure agent metadata is correct
            result.agent = self.name
            result.stance = self.stance
            logger.info(
                f"{self.name} agent completed — confidence={result.confidence}"
            )
            return result

        except ValueError as exc:
            logger.error(f"{self.name} agent failed: {exc} — returning fallback")
            fallback_data = create_fallback_agent_output(self.name, self.stance)
            return AgentOutput.model_validate(fallback_data)
