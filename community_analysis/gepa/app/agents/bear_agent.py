"""Bear (skeptical) analyst agent."""

from app.agents.base_agent import BaseAgent
from app.prompts.agent_prompts import BEAR_SYSTEM_PROMPT


class BearAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "Bear Analyst"

    @property
    def stance(self) -> str:
        return "bearish"

    @property
    def system_prompt(self) -> str:
        return BEAR_SYSTEM_PROMPT
