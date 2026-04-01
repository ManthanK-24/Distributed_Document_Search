"""
Search endpoints with caching, highlighting, and fuzzy matching.
"""
from typing import Optional, List
from fastapi import APIRouter, Request, Query
from app.models.schemas import SearchRequest, SearchResponse, SearchHit

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search_documents(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    tags: Optional[str] = Query(None, description="Comma-separated tag filter"),
    fuzzy: bool = Query(False, description="Enable fuzzy matching"),
    highlight: bool = Query(True, description="Enable highlighting"),
):
    """
    Full-text search across documents for the current tenant.
    Supports pagination, tag filtering, fuzzy matching, and result highlighting.
    """
    tenant_id = request.state.tenant_id
    es = request.app.state.es_service
    cache = request.app.state.cache_service

    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    cache_params = {"page": page, "page_size": page_size, "tags": tags, "fuzzy": fuzzy}

    # Check cache
    cached = cache.get_search_results(tenant_id, q, **cache_params)
    if cached:
        cached["query"] = q
        cached["tenant_id"] = tenant_id
        return SearchResponse(**cached)

    # Execute search
    results = await es.search(
        tenant_id=tenant_id,
        query=q,
        page=page,
        page_size=page_size,
        tags=tag_list,
        highlight=highlight,
        fuzzy=fuzzy,
    )

    # Cache results
    cache.set_search_results(tenant_id, q, results, **cache_params)

    return SearchResponse(
        query=q,
        tenant_id=tenant_id,
        **results,
    )


@router.post("/search", response_model=SearchResponse)
async def search_documents_advanced(body: SearchRequest, request: Request):
    """
    Advanced search with JSON body for complex filter expressions.
    """
    tenant_id = request.state.tenant_id
    es = request.app.state.es_service
    cache = request.app.state.cache_service

    cache_params = {
        "page": body.page, "page_size": body.page_size,
        "tags": ",".join(body.tags) if body.tags else None,
        "fuzzy": body.fuzzy, "filters": str(body.filters),
    }

    cached = cache.get_search_results(tenant_id, body.query, **cache_params)
    if cached:
        cached["query"] = body.query
        cached["tenant_id"] = tenant_id
        return SearchResponse(**cached)

    results = await es.search(
        tenant_id=tenant_id,
        query=body.query,
        page=body.page,
        page_size=body.page_size,
        filters=body.filters,
        tags=body.tags,
        highlight=body.highlight,
        fuzzy=body.fuzzy,
    )

    cache.set_search_results(tenant_id, body.query, results, **cache_params)

    return SearchResponse(query=body.query, tenant_id=tenant_id, **results)
