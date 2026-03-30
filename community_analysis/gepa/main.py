"""
GEPA — Generative Equity Portfolio Analyzer
Multi-Agent AI Stock Analysis Platform
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.middleware.auth import APIKeyMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware
from app.routes.analysis import router as analysis_router
from app.utils.logging_config import setup_logging, get_logger

# ── Bootstrap logging ──────────────────────────────────────────────
setup_logging()
logger = get_logger("main")

# ── FastAPI app ────────────────────────────────────────────────────
app = FastAPI(
    title="GEPA — Generative Equity Portfolio Analyzer",
    description=(
        "AI-powered multi-agent stock analysis platform. "
        "Simulates an institutional investment committee with "
        "Bull, Bear, Neutral analysts and a Moderator."
    ),
    version="1.0.0",
)

# ── Middleware (order matters: last added = first executed) ─────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(APIKeyMiddleware)

# ── Routes ─────────────────────────────────────────────────────────
app.include_router(analysis_router)


# ── Startup / Shutdown events ──────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    settings = get_settings()
    logger.info("GEPA server starting")
    logger.info(f"Agent model     : {settings.AGENT_MODEL}")
    logger.info(f"Moderator model : {settings.MODERATOR_MODEL}")
    if not settings.GROQ_API_KEY:
        logger.warning("⚠️  GROQ_API_KEY is not set — LLM calls will fail!")
    if not settings.API_KEY:
        logger.info("API key auth disabled (no API_KEY configured)")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("GEPA server shutting down")
