"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration — sourced from .env or OS environment."""

    # ── Groq ──────────────────────────────────────────
    GROQ_API_KEY: str = ""

    # ── Model routing ──────────────────────────────
    AGENT_MODEL: str = "llama-3.1-8b-instant"
    MODERATOR_MODEL: str = "llama-3.3-70b-versatile"

    # ── Auth ───────────────────────────────────────
    API_KEY: str = ""

    # ── Rate limiting ──────────────────────────────
    RATE_LIMIT_RPM: int = 10

    # ── Cache ──────────────────────────────────────
    CACHE_TTL_SECONDS: int = 900  # 15 minutes

    # ── LLM behaviour ─────────────────────────────
    LLM_MAX_RETRIES: int = 3
    LLM_TEMPERATURE: float = 0.3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
