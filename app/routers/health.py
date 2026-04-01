"""
Health check endpoint with dependency status reporting.
"""
import asyncio
import time
from fastapi import APIRouter, Request
from app.models.schemas import HealthResponse, DependencyHealth

router = APIRouter()

_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """
    Returns service health including all dependency statuses.
    Used by load balancers, orchestrators, and monitoring systems.
    """
    dependencies = []

    # Check Elasticsearch
    try:
        es = request.app.state.es_service
        es_health = await asyncio.wait_for(es.health_check(), timeout=6.0)
        dependencies.append(DependencyHealth(
            name="elasticsearch",
            status=es_health["status"],
            latency_ms=es_health.get("latency_ms"),
            details=es_health.get("cluster_status") or es_health.get("details"),
        ))
    except Exception as e:
        dependencies.append(DependencyHealth(
            name="elasticsearch", status="unhealthy", details=str(e)
        ))

    # Check Cache (Redis)
    try:
        cache = request.app.state.cache_service
        cache_health = cache.health_check()
        dependencies.append(DependencyHealth(
            name="cache",
            status=cache_health["status"],
            latency_ms=cache_health.get("latency_ms"),
            details=cache_health.get("backend"),
        ))
    except Exception as e:
        dependencies.append(DependencyHealth(
            name="cache", status="unhealthy", details=str(e)
        ))

    # Overall status: unhealthy if any critical dependency is down
    statuses = [d.status for d in dependencies]
    if "unhealthy" in statuses:
        overall = "unhealthy" if dependencies[0].status == "unhealthy" else "degraded"
    else:
        overall = "healthy"

    return HealthResponse(
        status=overall,
        version="1.0.0",
        uptime_seconds=round(time.time() - _start_time, 2),
        dependencies=dependencies,
    )
