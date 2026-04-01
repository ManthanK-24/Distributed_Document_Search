"""
Tenant middleware - extracts and validates tenant ID from request headers.
Every request must be scoped to a tenant for data isolation.
"""
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.utils.config import settings

# Whitelist: only alphanumeric, hyphens, underscores
TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# Endpoints that don't require a tenant
EXEMPT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"

        # Skip tenant check for health/docs endpoints
        if path in EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            request.state.tenant_id = settings.default_tenant
            return await call_next(request)

        # Extract tenant ID from header or query param
        tenant_id = (
            request.headers.get(settings.tenant_header)
            or request.query_params.get("tenant")
            or None
        )

        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "missing_tenant",
                    "message": f"Tenant ID required via '{settings.tenant_header}' header or 'tenant' query param",
                },
            )

        if not TENANT_ID_PATTERN.match(tenant_id):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_tenant",
                    "message": "Tenant ID must be 1-64 alphanumeric characters, hyphens, or underscores",
                },
            )

        request.state.tenant_id = tenant_id
        return await call_next(request)
