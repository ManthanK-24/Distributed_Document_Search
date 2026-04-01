"""
Distributed Document Search Service
Main application entry point with FastAPI
"""
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import documents, search, health
from app.services.elasticsearch_service import ElasticsearchService
from app.services.cache_service import CacheService
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.tenant import TenantMiddleware
from app.utils.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    # Startup
    es_service = ElasticsearchService()
    await es_service.initialize()
    app.state.es_service = es_service
    app.state.cache_service = CacheService()

    yield

    # Shutdown
    await es_service.close()
    app.state.cache_service.close()


app = FastAPI(
    title="Distributed Document Search Service",
    description="Enterprise-grade multi-tenant document search with sub-second response times",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Middleware (order matters: outermost first) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(TenantMiddleware)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """Add request ID and timing to every request."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.perf_counter()

    request.state.request_id = request_id
    response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

    return response


# --- Routers ---
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(search.router, tags=["Search"])
app.include_router(health.router, tags=["Health"])


@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Distributed Document Search Service",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )
