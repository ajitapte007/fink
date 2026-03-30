"""Bull (optimistic) analyst agent."""

from app.agents.base_agent import BaseAgent
from app.prompts.agent_prompts import BULL_SYSTEM_PROMPT


class BullAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Bull Analyst"

    @property
    def stance(self) -> str:
        return "bullish"

    @property
    def system_prompt(self) -> str:
        return BULL_SYSTEM_PROMPT
