"""
Cache service using Redis with in-memory fallback.
Provides per-tenant cache isolation and configurable TTL.
"""
import json
import time
import hashlib
import logging
from typing import Optional, Any

from app.utils.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """
    Two-layer cache: Redis for shared distributed cache,
    with a local in-memory LRU as fallback if Redis is unavailable.
    """

    def __init__(self):
        self.redis = None
        self._local_cache: dict = {}  # Fallback LRU-style dict
        self._local_cache_max = 10_000
        self._connect_redis()

    def _connect_redis(self):
        try:
            import redis
            self.redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self.redis.ping()
            logger.info("Redis cache connected: %s:%s", settings.redis_host, settings.redis_port)
        except Exception as e:
            logger.warning("Redis unavailable, falling back to in-memory cache: %s", e)
            self.redis = None

    @staticmethod
    def _cache_key(tenant_id: str, namespace: str, identifier: str) -> str:
        """Build a namespaced, tenant-scoped cache key."""
        raw = f"{tenant_id}:{namespace}:{identifier}"
        return f"dss:{raw}"

    @staticmethod
    def _query_hash(query: str, **params) -> str:
        """Deterministic hash for search query + params."""
        payload = json.dumps({"q": query, **params}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # ---- Core Operations ----

    def get(self, tenant_id: str, namespace: str, identifier: str) -> Optional[Any]:
        """Retrieve a cached value. Returns None on miss."""
        if not settings.cache_enabled:
            return None
        key = self._cache_key(tenant_id, namespace, identifier)
        try:
            if self.redis:
                val = self.redis.get(key)
                if val:
                    return json.loads(val)
            else:
                entry = self._local_cache.get(key)
                if entry and entry["exp"] > time.time():
                    return entry["val"]
                elif entry:
                    del self._local_cache[key]
        except Exception as e:
            logger.debug("Cache get error: %s", e)
        return None

    def set(self, tenant_id: str, namespace: str, identifier: str, value: Any, ttl: Optional[int] = None):
        """Store a value in cache with TTL."""
        if not settings.cache_enabled:
            return
        key = self._cache_key(tenant_id, namespace, identifier)
        ttl = ttl or settings.cache_ttl_seconds
        try:
            serialized = json.dumps(value)
            if self.redis:
                self.redis.setex(key, ttl, serialized)
            else:
                if len(self._local_cache) >= self._local_cache_max:
                    # Evict oldest 20%
                    keys_to_evict = list(self._local_cache.keys())[:self._local_cache_max // 5]
                    for k in keys_to_evict:
                        del self._local_cache[k]
                self._local_cache[key] = {"val": value, "exp": time.time() + ttl}
        except Exception as e:
            logger.debug("Cache set error: %s", e)

    def delete(self, tenant_id: str, namespace: str, identifier: str):
        """Remove a specific key from cache."""
        key = self._cache_key(tenant_id, namespace, identifier)
        try:
            if self.redis:
                self.redis.delete(key)
            else:
                self._local_cache.pop(key, None)
        except Exception as e:
            logger.debug("Cache delete error: %s", e)

    def invalidate_tenant_search_cache(self, tenant_id: str):
        """Invalidate all search cache for a tenant (on document change)."""
        pattern = self._cache_key(tenant_id, "search", "*")
        try:
            if self.redis:
                cursor = 0
                while True:
                    cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        self.redis.delete(*keys)
                    if cursor == 0:
                        break
            else:
                prefix = self._cache_key(tenant_id, "search", "")
                to_delete = [k for k in self._local_cache if k.startswith(prefix)]
                for k in to_delete:
                    del self._local_cache[k]
        except Exception as e:
            logger.debug("Cache invalidation error: %s", e)

    # ---- Convenience Methods ----

    def get_search_results(self, tenant_id: str, query: str, **params) -> Optional[Any]:
        qhash = self._query_hash(query, **params)
        return self.get(tenant_id, "search", qhash)

    def set_search_results(self, tenant_id: str, query: str, results: Any, **params):
        qhash = self._query_hash(query, **params)
        self.set(tenant_id, "search", qhash, results, ttl=60)  # Short TTL for search

    def get_document(self, tenant_id: str, doc_id: str) -> Optional[Any]:
        return self.get(tenant_id, "doc", doc_id)

    def set_document(self, tenant_id: str, doc_id: str, doc: Any):
        self.set(tenant_id, "doc", doc_id, doc)

    def delete_document(self, tenant_id: str, doc_id: str):
        self.delete(tenant_id, "doc", doc_id)

    # ---- Health ----

    def health_check(self) -> dict:
        try:
            if self.redis:
                start = time.perf_counter()
                self.redis.ping()
                latency = (time.perf_counter() - start) * 1000
                return {"status": "healthy", "latency_ms": round(latency, 2), "backend": "redis"}
            else:
                return {"status": "healthy", "latency_ms": 0.01, "backend": "in-memory",
                        "entries": len(self._local_cache)}
        except Exception as e:
            return {"status": "unhealthy", "details": str(e)}

    def close(self):
        if self.redis:
            self.redis.close()
