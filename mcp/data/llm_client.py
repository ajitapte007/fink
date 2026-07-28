"""
Centralized LLM client abstraction.

Provides a unified interface for querying LLMs, currently backed by OpenAI.
Switch providers by implementing a new LLMClient subclass and updating the factory.
"""
import os
import json
from abc import ABC, abstractmethod
from typing import Optional

from openai import OpenAI

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")


class LLMClient(ABC):
    """Abstract interface for LLM querying."""

    @abstractmethod
    def query_json(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.0) -> dict:
        """Send a prompt and parse a JSON response."""

    @abstractmethod
    def query_text(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.2) -> str:
        """Send a prompt and return raw text response."""

    @abstractmethod
    def query_json_with_search(self, system_prompt: str, user_prompt: str,
                               temperature: float = 0.0) -> dict:
        """Send a prompt with web search grounding, return parsed JSON."""


class OpenAIClient(LLMClient):
    """OpenAI-backed implementation using the user's OPENAI_API_KEY.

    Uses Chat Completions API for plain queries and the Responses API
    for search-grounded queries (web_search tool).
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def query_json(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.0) -> dict:
        """Plain JSON query via Chat Completions API."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=temperature
        )
        return json.loads(response.choices[0].message.content)

    def query_text(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.2) -> str:
        """Plain text query via Chat Completions API."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature
        )
        return response.choices[0].message.content

    def query_json_with_search(self, system_prompt: str, user_prompt: str,
                               temperature: float = 0.0) -> dict:
        """JSON query with web search grounding via Responses API.

        Uses OpenAI's built-in web_search tool so the model can
        autonomously search for 10-K filing data before responding.
        """
        combined_input = f"{system_prompt}\n\n{user_prompt}"
        response = self.client.responses.create(
            model=self.model,
            tools=[{"type": "web_search"}],
            input=combined_input,
            temperature=temperature
        )
        return json.loads(response.output_text)


def get_llm_client(model: Optional[str] = None) -> LLMClient:
    """Factory function — returns the active LLM client.

    Switch provider here when migrating to Gemini or local models.
    """
    return OpenAIClient(model=model or DEFAULT_MODEL)
