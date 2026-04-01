"""
Elasticsearch service layer.
Handles index management, document CRUD, and search with multi-tenant isolation.
"""
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from elasticsearch import AsyncElasticsearch, NotFoundError, ConnectionError as ESConnectionError
from app.utils.config import settings

logger = logging.getLogger(__name__)


class ElasticsearchService:
    """Manages all Elasticsearch operations with tenant-scoped indices."""

    # Index mapping with optimized analyzers for full-text search
    INDEX_MAPPINGS = {
        "settings": {
            "number_of_shards": 2,
            "number_of_replicas": 1,
            "refresh_interval": "1s",
            "analysis": {
                "analyzer": {
                    "content_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "snowball", "word_delimiter_graph"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "tenant_id":  {"type": "keyword"},
                "title":      {"type": "text", "analyzer": "content_analyzer",
                               "fields": {"keyword": {"type": "keyword"}}},
                "content":    {"type": "text", "analyzer": "content_analyzer"},
                "metadata":   {"type": "object", "enabled": True},
                "tags":       {"type": "keyword"},
                "source":     {"type": "keyword"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    }

    def __init__(self):
        self.client: Optional[AsyncElasticsearch] = None

    async def initialize(self):
        """Connect to Elasticsearch and ensure indices exist."""
        self.client = AsyncElasticsearch(
            hosts=[settings.es_host],
            request_timeout=30,
            retry_on_timeout=True,
            max_retries=3,
        )
        logger.info("Elasticsearch client initialized: %s", settings.es_host)

    async def close(self):
        if self.client:
            await self.client.close()

    def _index_name(self, tenant_id: str) -> str:
        """Tenant-scoped index name. Each tenant gets its own index for isolation."""
        return f"{settings.es_index_prefix}_{tenant_id}"

    async def ensure_index(self, tenant_id: str):
        """Create index for tenant if it doesn't exist."""
        index = self._index_name(tenant_id)
        exists = await self.client.indices.exists(index=index)
        if not exists:
            await self.client.indices.create(index=index, body=self.INDEX_MAPPINGS)
            logger.info("Created index: %s", index)

    # ---- CRUD Operations ----

    async def index_document(self, tenant_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Index a new document. Returns the document ID."""
        await self.ensure_index(tenant_id)
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        body = {
            "tenant_id": tenant_id,
            "title": doc["title"],
            "content": doc["content"],
            "metadata": doc.get("metadata", {}),
            "tags": doc.get("tags", []),
            "source": doc.get("source"),
            "created_at": now,
            "updated_at": now,
        }

        await self.client.index(
            index=self._index_name(tenant_id),
            id=doc_id,
            body=body,
            refresh="wait_for",  # Ensures doc is searchable immediately (prototype convenience)
        )
        return {"id": doc_id, "tenant_id": tenant_id}

    async def get_document(self, tenant_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single document by ID, scoped to tenant."""
        try:
            result = await self.client.get(
                index=self._index_name(tenant_id), id=doc_id
            )
            source = result["_source"]
            if source.get("tenant_id") != tenant_id:
                return None  # Tenant isolation enforcement
            source["id"] = result["_id"]
            return source
        except NotFoundError:
            return None

    async def delete_document(self, tenant_id: str, doc_id: str) -> bool:
        """Delete a document by ID, scoped to tenant."""
        try:
            await self.client.delete(
                index=self._index_name(tenant_id), id=doc_id, refresh="wait_for"
            )
            return True
        except NotFoundError:
            return False

    # ---- Search ----

    async def search(
        self,
        tenant_id: str,
        query: str,
        page: int = 1,
        page_size: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        tags: Optional[list] = None,
        highlight: bool = True,
        fuzzy: bool = False,
    ) -> Dict[str, Any]:
        """
        Full-text search with relevance ranking, highlighting, and filtering.
        Scoped to a single tenant index for isolation.
        """
        await self.ensure_index(tenant_id)

        # Build the query
        must_clauses = []

        if fuzzy:
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "content", "tags^2"],
                    "fuzziness": "AUTO",
                    "prefix_length": 2,
                }
            })
        else:
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "content", "tags^2"],
                    "type": "best_fields",
                }
            })

        # Apply filters
        filter_clauses = [{"term": {"tenant_id": tenant_id}}]
        if tags:
            filter_clauses.append({"terms": {"tags": tags}})
        if filters:
            for key, value in filters.items():
                filter_clauses.append({"term": {f"metadata.{key}": value}})

        body: Dict[str, Any] = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "from": (page - 1) * page_size,
            "size": page_size,
            "sort": ["_score", {"created_at": "desc"}],
        }

        if highlight:
            body["highlight"] = {
                "fields": {
                    "title": {"fragment_size": 200, "number_of_fragments": 1},
                    "content": {"fragment_size": 250, "number_of_fragments": 3},
                },
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
            }

        start = time.perf_counter()
        result = await self.client.search(
            index=self._index_name(tenant_id),
            body=body,
            request_timeout=settings.search_timeout_seconds,
        )
        took_ms = (time.perf_counter() - start) * 1000

        # Format results
        hits = []
        for hit in result["hits"]["hits"]:
            source = hit["_source"]
            content_snippet = source.get("content", "")[:300]

            highlights = None
            if "highlight" in hit:
                highlights = hit["highlight"]
                # Use highlighted content as snippet if available
                if "content" in hit["highlight"]:
                    content_snippet = " ... ".join(hit["highlight"]["content"])

            hits.append({
                "id": hit["_id"],
                "title": source.get("title", ""),
                "content_snippet": content_snippet,
                "score": hit["_score"],
                "tags": source.get("tags", []),
                "metadata": source.get("metadata", {}),
                "highlights": highlights,
                "created_at": source.get("created_at", ""),
            })

        total = result["hits"]["total"]["value"]
        return {
            "total_hits": total,
            "took_ms": round(took_ms, 2),
            "results": hits,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    # ---- Health Check ----

    async def health_check(self) -> Dict[str, Any]:
        """Check Elasticsearch cluster health."""
        try:
            start = time.perf_counter()
            info = await self.client.cluster.health(request_timeout=5)
            latency = (time.perf_counter() - start) * 1000
            status = "healthy" if info["status"] in ("green", "yellow") else "unhealthy"
            return {"status": status, "latency_ms": round(latency, 2), "cluster_status": info["status"]}
        except Exception as e:
            return {"status": "unhealthy", "latency_ms": None, "details": str(e)}
