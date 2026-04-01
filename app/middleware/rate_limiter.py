"""
Per-tenant rate limiter using sliding window counter.
Uses Redis when available, falls back to in-memory tracking.
"""
import time
import logging
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.utils.config import settings

logger = logging.getLogger(__name__)

# Endpoints exempt from rate limiting
EXEMPT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._local_counters: dict = defaultdict(list)  # tenant -> [timestamps]
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        try:
            import redis
            self._redis = redis.Redis(
                host=settings.redis_host, port=settings.redis_port,
                db=settings.redis_db, decode_responses=True,
                socket_connect_timeout=1, socket_timeout=1,
            )
            self._redis.ping()
        except Exception:
            self._redis = None

    def _check_rate_limit_redis(self, tenant_id: str) -> tuple[bool, int]:
        """Sliding window rate limit using Redis sorted set."""
        key = f"ratelimit:{tenant_id}"
        now = time.time()
        window_start = now - settings.rate_limit_window_seconds

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {f"{now}": now})
        pipe.zcard(key)
        pipe.expire(key, settings.rate_limit_window_seconds + 1)
        results = pipe.execute()

        count = results[2]
        remaining = max(0, settings.rate_limit_requests - count)
        return count <= settings.rate_limit_requests, remaining

    def _check_rate_limit_local(self, tenant_id: str) -> tuple[bool, int]:
        """In-memory sliding window fallback."""
        now = time.time()
        window_start = now - settings.rate_limit_window_seconds

        # Prune old entries
        self._local_counters[tenant_id] = [
            t for t in self._local_counters[tenant_id] if t > window_start
        ]
        self._local_counters[tenant_id].append(now)

        count = len(self._local_counters[tenant_id])
        remaining = max(0, settings.rate_limit_requests - count)
        return count <= settings.rate_limit_requests, remaining

    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if path in EXEMPT_PATHS:
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", "unknown")

        try:
            if self._redis:
                allowed, remaining = self._check_rate_limit_redis(tenant_id)
            else:
                allowed, remaining = self._check_rate_limit_local(tenant_id)
        except Exception as e:
            logger.warning("Rate limit check failed, allowing request: %s", e)
            allowed, remaining = True, -1

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit of {settings.rate_limit_requests} requests per "
                               f"{settings.rate_limit_window_seconds}s exceeded for tenant '{tenant_id}'",
                    "retry_after_seconds": settings.rate_limit_window_seconds,
                },
                headers={
                    "Retry-After": str(settings.rate_limit_window_seconds),
                    "X-RateLimit-Limit": str(settings.rate_limit_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
