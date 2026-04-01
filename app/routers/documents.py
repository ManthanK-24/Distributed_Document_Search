"""
Document CRUD endpoints.
All operations are tenant-scoped via middleware.
"""
from fastapi import APIRouter, Request, HTTPException
from app.models.schemas import DocumentCreate, DocumentResponse, DocumentIndexResponse

router = APIRouter()


@router.post("", response_model=DocumentIndexResponse, status_code=201)
async def create_document(doc: DocumentCreate, request: Request):
    """Index a new document for the current tenant."""
    tenant_id = request.state.tenant_id
    es: "ElasticsearchService" = request.app.state.es_service
    cache: "CacheService" = request.app.state.cache_service

    result = await es.index_document(tenant_id, doc.model_dump())

    # Invalidate search cache for this tenant (new doc may affect results)
    cache.invalidate_tenant_search_cache(tenant_id)

    return DocumentIndexResponse(
        id=result["id"],
        tenant_id=tenant_id,
        status="indexed",
        message="Document indexed successfully",
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, request: Request):
    """Retrieve a document by ID for the current tenant."""
    tenant_id = request.state.tenant_id
    es = request.app.state.es_service
    cache = request.app.state.cache_service

    # Check cache first
    cached = cache.get_document(tenant_id, doc_id)
    if cached:
        return DocumentResponse(**cached)

    doc = await es.get_document(tenant_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    # Populate cache
    cache.set_document(tenant_id, doc_id, doc)
    return DocumentResponse(**doc)


@router.delete("/{doc_id}", status_code=200)
async def delete_document(doc_id: str, request: Request):
    """Delete a document by ID for the current tenant."""
    tenant_id = request.state.tenant_id
    es = request.app.state.es_service
    cache = request.app.state.cache_service

    deleted = await es.delete_document(tenant_id, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    # Invalidate caches
    cache.delete_document(tenant_id, doc_id)
    cache.invalidate_tenant_search_cache(tenant_id)

    return {"id": doc_id, "status": "deleted", "message": "Document deleted successfully"}
