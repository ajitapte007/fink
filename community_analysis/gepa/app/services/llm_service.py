"""Async LLM service wrapper using Groq (OpenAI-compatible API) with retry logic."""

from __future__ import annotations

import json
from typing import Type, TypeVar, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import get_settings
from app.utils.logging_config import get_logger
from app.utils.validation import extract_json_from_text

logger = get_logger("llm_service")

T = TypeVar("T", bound=BaseModel)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        # Using Groq's high-speed OpenAI-compatible API
        _client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )
    return _client


async def call_llm(
    user_prompt: str,
    system_prompt: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Make a single chat completion call via Groq. Returns the raw text content.
    """
    settings = get_settings()
    client = _get_client()

    model = model or settings.AGENT_MODEL
    temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE

    logger.info(f"LLM call  model={model}  temp={temperature}  prompt_len={len(user_prompt)}")

    response = await client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or ""

    usage = response.usage
    if usage:
        logger.info(
            f"Token usage  prompt={usage.prompt_tokens}  "
            f"completion={usage.completion_tokens}  total={usage.total_tokens}"
        )

    return content


async def call_llm_structured(
    user_prompt: str,
    system_prompt: str,
    response_model: Type[T],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> T:
    """
    Call LLM with automatic retry and Pydantic validation.

    Retries up to settings.LLM_MAX_RETRIES times on parse / validation errors.
    Raises ValueError if all retries are exhausted.
    """
    settings = get_settings()
    last_error: Optional[Exception] = None

    for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
        try:
            raw = await call_llm(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
            )

            json_str = extract_json_from_text(raw)
            data = json.loads(json_str)
            return response_model.model_validate(data)

        except (json.JSONDecodeError, ValueError, Exception) as exc:
            import asyncio
            import re
            
            last_error = exc
            error_str = str(exc)
            
            # Groq returns "Please try again in 12.96s."
            wait_time = 3.0
            if "Please try again in" in error_str:
                match = re.search(r"Please try again in ([0-9.]+)s", error_str)
                if match:
                    wait_time = float(match.group(1)) + 0.5

            logger.warning(
                f"Attempt {attempt}/{settings.LLM_MAX_RETRIES} failed: {exc}. Retrying in {wait_time}s..."
            )
            
            if attempt < settings.LLM_MAX_RETRIES:
                await asyncio.sleep(wait_time)
                # Bump temperature slightly to vary output
                temperature = min((temperature or settings.LLM_TEMPERATURE) + 0.1, 1.0)

    raise ValueError(
        f"All {settings.LLM_MAX_RETRIES} LLM retries exhausted. Last error: {last_error}"
    )
