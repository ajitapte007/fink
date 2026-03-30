"""Neutral (quantitative) analyst agent."""

from app.agents.base_agent import BaseAgent
from app.prompts.agent_prompts import NEUTRAL_SYSTEM_PROMPT


class NeutralAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Neutral Analyst"

    @property
    def stance(self) -> str:
        return "neutral"

    @property
    def system_prompt(self) -> str:
        return NEUTRAL_SYSTEM_PROMPT
