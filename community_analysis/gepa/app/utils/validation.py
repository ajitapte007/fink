"""JSON parsing and validation utilities for LLM outputs."""

from __future__ import annotations

import json
import re
from typing import TypeVar, Type

from pydantic import BaseModel, ValidationError

from app.utils.logging_config import get_logger

logger = get_logger("validation")

T = TypeVar("T", bound=BaseModel)


def extract_json_from_text(text: str) -> str:
    """Extract the first JSON object or array from possibly messy LLM output."""

    # Try to find JSON inside markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if fence_match:
        return fence_match.group(1).strip()

    # Try to find a top-level JSON object
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        return brace_match.group(0).strip()

    # Try to find a top-level JSON array
    bracket_match = re.search(r"\[[\s\S]*\]", text)
    if bracket_match:
        return bracket_match.group(0).strip()

    # Return as-is and let the caller handle the parse error
    return text.strip()


def parse_llm_json(raw_text: str, model_class: Type[T]) -> T:
    """
    Extract JSON from LLM text and validate against a Pydantic model.

    Raises ValueError if extraction or validation fails.
    """
    json_str = extract_json_from_text(raw_text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.error(f"JSON decode failed: {exc}  |  raw={raw_text[:200]}")
        raise ValueError(f"Invalid JSON from LLM: {exc}") from exc

    try:
        return model_class.model_validate(data)
    except ValidationError as exc:
        logger.error(f"Pydantic validation failed: {exc}")
        raise ValueError(f"Schema validation failed: {exc}") from exc


def create_fallback_agent_output(agent_name: str, stance: str) -> dict:
    """Return a safe default when all LLM retries are exhausted."""
    return {
        "agent": agent_name,
        "stance": stance,
        "thesis": "Analysis could not be completed due to LLM processing errors.",
        "key_points": ["Unable to generate analysis — fallback response."],
        "risks": ["Analysis unavailable — treat all conclusions with caution."],
        "opportunities": [],
        "data_references": [],
        "confidence": 0.0,
    }


def create_fallback_cross_exam(reviewer: str, target: str) -> dict:
    """Return a safe default cross-examination result."""
    return {
        "reviewer": reviewer,
        "target": target,
        "critiques": ["Cross-examination could not be completed."],
        "agreements": [],
        "bias_flags": [],
        "missing_considerations": [],
        "severity": "low",
    }
