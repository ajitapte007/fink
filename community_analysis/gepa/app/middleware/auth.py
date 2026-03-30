"""Simple API key authentication middleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.utils.logging_config import get_logger

logger = get_logger("middleware.auth")

# Paths that skip authentication
_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests missing a valid X-API-Key header."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ):
        settings = get_settings()

        # Skip auth if no API key is configured or path is public
        if not settings.API_KEY or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if api_key != settings.API_KEY:
            logger.warning(f"Auth failed from {request.client.host if request.client else 'unknown'}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key.", "error_code": "UNAUTHORIZED"},
            )

        return await call_next(request)
