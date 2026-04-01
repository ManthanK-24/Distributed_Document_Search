"""Pydantic models for request/response contracts."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


# --- Document Models ---

class DocumentCreate(BaseModel):
    """Request body for creating/indexing a document."""
    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    content: str = Field(..., min_length=1, description="Full document content")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arbitrary metadata")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")
    source: Optional[str] = Field(None, max_length=255, description="Source system or URL")

    model_config = {"json_schema_extra": {
        "example": {
            "title": "Quarterly Revenue Report Q3 2025",
            "content": "Revenue grew by 15% year over year driven by strong SaaS adoption...",
            "metadata": {"department": "finance", "fiscal_year": 2025},
            "tags": ["finance", "quarterly", "revenue"],
            "source": "internal-reports"
        }
    }}


class DocumentResponse(BaseModel):
    """Response for a single document."""
    id: str
    tenant_id: str
    title: str
    content: str
    metadata: Dict[str, Any] = {}
    tags: List[str] = []
    source: Optional[str] = None
    created_at: str
    updated_at: str


class DocumentIndexResponse(BaseModel):
    """Response after indexing a document."""
    id: str
    tenant_id: str
    status: str = "indexed"
    message: str = "Document indexed successfully"


# --- Search Models ---

class SearchRequest(BaseModel):
    """Advanced search request body."""
    query: str = Field(..., min_length=1, description="Search query string")
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Filter conditions")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Results per page")
    highlight: bool = Field(True, description="Enable search result highlighting")
    fuzzy: bool = Field(False, description="Enable fuzzy matching")


class SearchHit(BaseModel):
    """A single search result."""
    id: str
    title: str
    content_snippet: str = Field(description="Highlighted or truncated content snippet")
    score: float = Field(description="Relevance score")
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    highlights: Optional[Dict[str, List[str]]] = None
    created_at: str


class SearchResponse(BaseModel):
    """Paginated search response."""
    query: str
    tenant_id: str
    total_hits: int
    page: int
    page_size: int
    total_pages: int
    took_ms: float
    results: List[SearchHit]


# --- Health Models ---

class DependencyHealth(BaseModel):
    name: str
    status: str  # "healthy" | "degraded" | "unhealthy"
    latency_ms: Optional[float] = None
    details: Optional[str] = None


class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    version: str
    uptime_seconds: float
    dependencies: List[DependencyHealth]
