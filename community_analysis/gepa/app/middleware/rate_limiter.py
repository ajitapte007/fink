"""In-memory sliding-window rate limiter middleware."""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.utils.logging_config import get_logger

logger = get_logger("middleware.rate_limiter")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window counter per client IP (or API key)."""

    def __init__(self, app):
        super().__init__(app)
        # key → list of request timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _client_key(self, request: Request) -> str:
        """Identify the client by API key or IP."""
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key}"
        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ):
        settings = get_settings()

        if settings.RATE_LIMIT_RPM <= 0:
            return await call_next(request)

        key = self._client_key(request)
        now = time.time()
        window = 60.0  # 1 minute

        # Prune old timestamps
        self._requests[key] = [
            ts for ts in self._requests[key] if now - ts < window
        ]

        if len(self._requests[key]) >= settings.RATE_LIMIT_RPM:
            logger.warning(f"Rate limit hit for {key}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded ({settings.RATE_LIMIT_RPM} requests/min).",
                    "error_code": "RATE_LIMITED",
                },
            )

        self._requests[key].append(now)
        return await call_next(request)
