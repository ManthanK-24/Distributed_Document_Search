"""Application configuration via environment variables."""
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # Elasticsearch
    es_host: str = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
    es_index_prefix: str = os.getenv("ES_INDEX_PREFIX", "docs")

    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    # Cache
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))
    cache_enabled: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"

    # Rate Limiting (per tenant)
    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Search defaults
    default_page_size: int = 20
    max_page_size: int = 100
    search_timeout_seconds: int = 5

    # Multi-tenancy
    tenant_header: str = "X-Tenant-ID"
    default_tenant: str = "default"


settings = Settings()
