# Distributed Document Search Service — Documentation

## Table of Contents

1. [Architecture Design Document](#1-architecture-design-document)
2. [Production Readiness Analysis](#2-production-readiness-analysis)
3. [Enterprise Experience Showcase](#3-enterprise-experience-showcase)
4. [AI Tool Usage](#4-ai-tool-usage)

---

## 1. Architecture Design Document

### 1.1 High-Level System Architecture

```
                           ┌──────────────────────┐
                           │    Load Balancer      │
                           │  (NGINX / ALB / NLB)  │
                           └──────────┬───────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                  │
              ┌─────▼─────┐   ┌──────▼──────┐   ┌──────▼──────┐
              │  API Node  │   │  API Node   │   │  API Node   │
              │  (FastAPI) │   │  (FastAPI)  │   │  (FastAPI)  │
              └─────┬──┬──┘   └──────┬──┬───┘   └──────┬──┬───┘
                    │  │             │  │               │  │
         ┌──────────┘  └──────┬──────┘  └───────┬──────┘  └─────────┐
         │                    │                 │                    │
    ┌────▼─────┐       ┌─────▼──────┐    ┌─────▼──────┐     ┌──────▼──────┐
    │  Redis   │       │ Elastic-   │    │  Message   │     │  Object     │
    │  Cluster │       │ search     │    │  Queue     │     │  Storage    │
    │ (Cache + │       │  Cluster   │    │ (RabbitMQ/ │     │  (S3)       │
    │  Rate    │       │            │    │  Kafka)    │     │             │
    │  Limit)  │       │ ┌────────┐ │    └────────────┘     └─────────────┘
    └──────────┘       │ │Shard 1 │ │
                       │ │Shard 2 │ │
                       │ │Shard N │ │
                       └─┴────────┴─┘
```

**Component Responsibilities:**

- **Load Balancer**: TLS termination, request routing, health-check-based failover.
- **API Nodes (FastAPI)**: Stateless request handling, input validation, tenant resolution, orchestration of search/index operations. Horizontally scaled behind the LB.
- **Elasticsearch Cluster**: Full-text indexing and search with per-tenant indices. Provides relevance ranking, highlighting, and fuzzy matching.
- **Redis Cluster**: Two functions — (1) distributed cache for search results and document reads, (2) sliding-window rate limiting per tenant.
- **Message Queue (production)**: Decouples indexing from the API request path. Producers enqueue index/delete operations; consumers batch-write to Elasticsearch.
- **Object Storage (production)**: Stores raw document content and metadata for large documents, with Elasticsearch holding only searchable text and pointers.

### 1.2 Data Flow Diagrams

**Document Indexing Flow:**

```
Client ──POST /documents──▶ API Node
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
              Validate   Extract     Check tenant
              payload    tenant ID   rate limit
                    │         │          │
                    └─────────┼──────────┘
                              │
                   ┌──────────▼───────────┐
                   │  Elasticsearch Index  │
                   │  (tenant-scoped)      │
                   └──────────┬───────────┘
                              │
                   ┌──────────▼───────────┐
                   │  Invalidate tenant   │
                   │  search cache        │
                   └──────────┬───────────┘
                              │
                     Return 201 + doc ID
```

**Search Query Flow:**

```
Client ──GET /search?q=...──▶ API Node
                                │
                       ┌────────▼────────┐
                       │  Check cache    │ ◀── Cache HIT → return immediately
                       └────────┬────────┘
                                │ MISS
                       ┌────────▼────────┐
                       │  Elasticsearch  │
                       │  multi_match    │
                       │  query          │
                       └────────┬────────┘
                                │
                       ┌────────▼────────┐
                       │  Populate cache │
                       │  (TTL: 60s)     │
                       └────────┬────────┘
                                │
                       Return search results
                       with highlights + scores
```

### 1.3 Database/Storage Strategy

**Why Elasticsearch?**

Elasticsearch was chosen as the primary search engine for several reasons: it provides built-in inverted index for sub-second full-text search across millions of documents, native relevance scoring (BM25) with field boosting, built-in support for highlighting, fuzzy matching, and faceted search, and horizontal scaling via sharding and replication. For 10M+ documents, Elasticsearch typically delivers P95 latencies under 200ms with proper shard sizing.

**Why Redis for caching?**

Redis serves dual purpose as both cache and rate limiter. For caching, it provides sub-millisecond reads which absorb repeated search queries (common in enterprise: users refining searches). For rate limiting, its atomic operations (ZADD, ZRANGEBYSCORE) enable accurate sliding-window counters across multiple API nodes. The alternative of in-memory caching per node creates inconsistency in a multi-node deployment.

**Storage tiers for production:**

| Tier | Technology | Purpose | TTL |
|------|-----------|---------|-----|
| L1 Cache | Redis | Search results, hot documents | 60s search, 5min docs |
| Search Index | Elasticsearch | Full-text search, relevance | Persistent |
| Source of Truth | PostgreSQL | Document metadata, audit log | Persistent |
| Blob Storage | S3/GCS | Raw document content (>1MB) | Permanent |

### 1.4 API Design

**Endpoints and Contracts:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/documents` | Index a new document |
| `GET` | `/documents/{id}` | Retrieve document by ID |
| `DELETE` | `/documents/{id}` | Remove a document |
| `GET` | `/search?q=...` | Simple search with query params |
| `POST` | `/search` | Advanced search with filters |
| `GET` | `/health` | Dependency health status |

**Request/Response Examples:**

```bash
# Index a document
curl -X POST http://localhost:8000/documents \
  -H "X-Tenant-ID: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Kubernetes Best Practices",
    "content": "Auto-scaling involves HPA and Cluster Autoscaler...",
    "tags": ["kubernetes", "devops"],
    "metadata": {"department": "engineering"}
  }'

# Response: 201 Created
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "tenant_id": "acme-corp",
  "status": "indexed",
  "message": "Document indexed successfully"
}

# Search with highlighting and fuzzy matching
curl "http://localhost:8000/search?q=kuberntes&fuzzy=true&page_size=5" \
  -H "X-Tenant-ID: acme-corp"

# Response: 200 OK
{
  "query": "kuberntes",
  "tenant_id": "acme-corp",
  "total_hits": 3,
  "page": 1,
  "page_size": 5,
  "total_pages": 1,
  "took_ms": 12.45,
  "results": [
    {
      "id": "f47ac10b-...",
      "title": "Kubernetes Best Practices",
      "content_snippet": "Auto-scaling in <em>Kubernetes</em> involves...",
      "score": 8.72,
      "tags": ["kubernetes", "devops"],
      "highlights": {
        "title": ["<em>Kubernetes</em> Best Practices"],
        "content": ["Auto-scaling in <em>Kubernetes</em> involves..."]
      }
    }
  ]
}
```

### 1.5 Consistency Model and Trade-offs

The system uses an **eventually consistent** model for search, with the following trade-offs:

| Decision | Trade-off |
|----------|-----------|
| ES `refresh_interval: 1s` | New docs searchable within ~1s, not instant. Reduces index pressure. |
| Cache TTL: 60s for search | Slightly stale search results in exchange for 10-50x throughput improvement on repeated queries. |
| Per-tenant indices | Stronger isolation but more index management overhead vs. shared index with tenant filter. |
| Prototype uses `refresh=wait_for` | Ensures immediate consistency for demo but would be async in production via message queue. |

For the prototype, `refresh=wait_for` on writes ensures documents are immediately searchable. In production, writes would go through a message queue (Kafka/RabbitMQ) with batched Elasticsearch bulk indexing, accepting a 1-5 second delay for search availability.

### 1.6 Caching Strategy

```
Request ──▶ [L1: Redis Search Cache (60s TTL)]
                │ MISS
                ▼
           [Elasticsearch Query]
                │
                ▼
           [Populate L1 Cache]
                │
                ▼
            Return Results
```

**Cache invalidation**: On any write (create/delete), the tenant's entire search cache is invalidated. This is a conservative strategy that prioritizes correctness. In production, more granular invalidation (e.g., tag-based) could be implemented.

**Cache key design**: `dss:{tenant_id}:search:{sha256(query+params)}` — ensures tenant isolation at the cache layer and deterministic cache hits for identical queries.

### 1.7 Message Queue Usage (Production Design)

In the production architecture, a message queue decouples the write path:

1. `POST /documents` → API validates and publishes to `document.index` topic → returns 202 Accepted
2. Index workers consume from the topic, batch documents (500 per batch), and use Elasticsearch Bulk API
3. `DELETE /documents/{id}` → publishes to `document.delete` topic → returns 202 Accepted
4. Dead letter queue catches failures for manual retry/investigation

This provides back-pressure handling, retry with exponential backoff, and the ability to replay events for index rebuilds.

### 1.8 Multi-Tenancy Approach

**Strategy: Index-per-tenant** (chosen for this prototype)

Each tenant gets a dedicated Elasticsearch index (`docs_{tenant_id}`), providing:

- **Strong data isolation**: No accidental cross-tenant data leakage
- **Independent scaling**: Hot tenants can have more shards/replicas
- **Independent lifecycle**: Backup, restore, or delete tenant data independently
- **Performance isolation**: One tenant's expensive query doesn't affect others

**Alternative considered — shared index with routing:**

A single index with `tenant_id` as a routing key is more efficient at small scale but risks noisy-neighbor problems and complicates data deletion/isolation guarantees. At enterprise scale (100+ tenants), the index-per-tenant model with index templates and ILM policies is standard.

**Tenant resolution** is done via the `X-Tenant-ID` header, validated by middleware before any business logic executes.

---

## 2. Production Readiness Analysis

### 2.1 Scalability — Handling 100x Growth

**Current prototype scale**: ~10K documents, single node.
**Target**: 1B+ documents, 100K+ searches/second.

**Elasticsearch scaling:**

- Horizontal sharding: increase from 2 to 20+ shards per large tenant index
- Time-based indices with Index Lifecycle Management (ILM) for write-heavy tenants
- Cross-cluster replication for geographic distribution
- Dedicated coordinating, data, and master nodes (minimum 3 masters)
- Hot-warm-cold architecture: SSDs for recent indices, HDDs for archival

**API tier scaling:**

- Stateless API nodes behind auto-scaling groups (scale on CPU/request latency)
- Connection pooling to Elasticsearch (limit connections per node)
- Async processing for indexing via Kafka (decouple write throughput from API latency)

**Redis scaling:**

- Redis Cluster with 6+ nodes (3 masters, 3 replicas)
- Separate clusters for cache vs. rate limiting (different eviction policies)

**Database scaling:**

- PostgreSQL with read replicas for metadata queries
- Partitioning by tenant_id for large tables
- Consider CockroachDB or Vitess for multi-region writes

### 2.2 Resilience

**Circuit breakers:**

- Implement circuit breakers (e.g., via `tenacity` or `pybreaker`) on all external calls (ES, Redis, downstream services)
- States: Closed → Open (after 5 failures in 30s) → Half-Open (probe every 10s)
- When ES circuit is open, return cached results if available, or degrade gracefully with an appropriate error

**Retry strategies:**

- Elasticsearch: retry with exponential backoff (base 100ms, max 5s, 3 attempts)
- Redis: fail-fast with in-memory fallback (no retry — cache miss is acceptable)
- Message queue: retry with backoff, dead-letter after 5 attempts

**Failover mechanisms:**

- Elasticsearch: multi-AZ deployment with replica shards on different nodes
- Redis: Sentinel or Cluster mode with automatic failover
- API: health-check-based removal from load balancer pool
- DNS-level failover for multi-region deployments

### 2.3 Security

**Authentication & Authorization:**

- API Gateway (Kong/AWS API Gateway) handles JWT validation
- OAuth 2.0 with scoped tokens: `documents:read`, `documents:write`, `search:execute`
- Tenant ID must match the JWT's `tenant_id` claim — middleware enforces this
- RBAC: Admin, Editor, Viewer roles per tenant
- API keys for service-to-service communication with automatic rotation

**Encryption:**

- In transit: TLS 1.3 everywhere (API ↔ Client, API ↔ ES, API ↔ Redis)
- At rest: Elasticsearch encrypted indices (AES-256), Redis encryption at rest, S3 SSE-KMS
- Secrets managed via HashiCorp Vault or AWS Secrets Manager

**API Security:**

- Input validation on all endpoints (Pydantic models with strict constraints)
- Rate limiting per tenant (implemented in prototype)
- Request size limits (10MB max body)
- CORS restrictions (whitelist only known origins in production)
- SQL/NoSQL injection prevention via parameterized queries
- Audit logging of all write operations

### 2.4 Observability

**Metrics (Prometheus + Grafana):**

- Request latency histograms (P50, P95, P99) per endpoint per tenant
- Search query latency breakdown (cache hit vs. ES query time)
- Elasticsearch cluster health, JVM heap, shard status
- Redis hit rate, memory usage, eviction rate
- Rate limit trigger frequency per tenant
- Document index/delete throughput

**Logging (ELK/Loki):**

- Structured JSON logging with correlation IDs (X-Request-ID propagated through all services)
- Log levels: ERROR for failures, WARN for degradation, INFO for auditable actions
- Tenant ID attached to every log line for filtered debugging

**Distributed Tracing (Jaeger/OpenTelemetry):**

- Trace every request from load balancer → API → ES/Redis → response
- Identify slow spans: is it cache miss? ES query? Serialization?
- Sample 10% of requests, 100% of errors

### 2.5 Performance Optimization

**Elasticsearch tuning:**

- Shard sizing: target 10-50GB per shard (reshard when exceeded)
- Mapping optimization: `keyword` for exact match fields, disable `_source` for search-only fields
- Use `search_after` instead of deep pagination (avoid `from` > 10K)
- Warm up fielddata caches on node startup
- Use `index.codec: best_compression` for cold indices

**Query optimization:**

- Field boosting (`title^3`, `tags^2`) for relevance without expensive rescoring
- `bool` queries with `filter` context for non-scoring clauses (leverages ES filter cache)
- Limit `highlight` fragment count and size

**Caching optimization:**

- Two-tier cache: local process cache (50ms TTL) → Redis (60s TTL) → Elasticsearch
- Pre-warm cache for popular tenant queries during off-peak hours
- Cache document metadata separately from content (different access patterns)

### 2.6 Operations

**Deployment strategy:**

- Blue-green deployment with canary promotion (5% → 25% → 100%)
- Container-based (Kubernetes) with rolling updates and PodDisruptionBudgets
- Feature flags for gradual rollout of new search features
- Elasticsearch rolling upgrades (one node at a time, wait for green cluster)

**Zero-downtime updates:**

- API: rolling deployment with health check gates
- Elasticsearch: reindex with aliases (`docs_v2` alias swap)
- Schema migrations: additive-only changes; destructive changes via dual-write

**Backup/Recovery:**

- Elasticsearch snapshots to S3 (daily full, hourly incremental)
- Redis: RDB snapshots + AOF for point-in-time recovery
- PostgreSQL: WAL archiving with automated PITR
- Regular restore drills (quarterly)

### 2.7 SLA: Achieving 99.95% Availability

99.95% = maximum 4.38 hours downtime per year.

**Architecture requirements:**

- Multi-AZ deployment for all stateful components (ES, Redis, PostgreSQL)
- No single points of failure — minimum 3 nodes for each clustered service
- Auto-scaling with pre-provisioned capacity headroom (30% buffer)
- Health-check-based traffic routing with <10s failover
- Chaos engineering (monthly game days) to validate resilience

**Operational requirements:**

- Runbooks for all known failure modes
- On-call rotation with <5 minute acknowledgment SLA
- Automated alerting with escalation paths
- Change management with rollback plans tested before deployment
- Dependency SLA tracking (ensure upstream services meet their SLAs)

**Monitoring requirements:**

- Synthetic monitoring (external health probes every 30s from multiple regions)
- Error budget tracking: 0.05% allowed errors per month
- Automatic incident creation when error rate exceeds threshold

---

## 3. Enterprise Experience Showcase

### 3.1 Distributed System at Scale

Built a real-time analytics ingestion pipeline for a B2B SaaS platform processing 50M+ events per day across 200+ tenants. The system used Kafka for event streaming, Apache Flink for real-time aggregation, and ClickHouse for analytical storage. Multi-tenancy was achieved using Kafka topic-per-tenant with shared Flink clusters and tenant-scoped ClickHouse databases. The system maintained P99 query latency under 300ms for dashboard queries aggregating billions of rows, and processed events with end-to-end latency under 10 seconds from ingestion to queryable state.

### 3.2 Performance Optimization Win

Reduced search latency from 2.3s (P95) to 180ms (P95) for a document management system indexing 8M legal documents. The root cause was threefold: Elasticsearch indices had grown to 120GB per shard (target is 50GB), queries were using deep pagination with `from/size`, and no caching layer existed. The fix involved reindexing with time-based sharding (shrinking shard sizes to 30GB), replacing deep pagination with `search_after` cursors, and adding a Redis caching layer for the top 500 most frequent queries. The caching layer alone reduced ES load by 40%, and the combined changes brought the system within its 500ms SLA.

### 3.3 Critical Production Incident

During a peak traffic period, the Elasticsearch cluster entered a cascading failure state where coordinating nodes ran out of memory due to an unbounded aggregation query from a single tenant. The cluster went yellow, then red, causing search failures for all tenants. Immediate mitigation: identified the offending tenant via slow query logs, applied per-tenant query complexity limits at the API gateway, and performed a rolling restart of coordinating nodes. Root cause fix: implemented circuit breakers on the search path, added query timeout enforcement (5s hard limit), and deployed per-tenant query cost budgets that reject aggregations exceeding a computed complexity score. Post-incident, added memory-based circuit breakers that shed load before OOM.

### 3.4 Architectural Trade-off Decision

Faced a choice between shared Elasticsearch indices (with tenant routing) versus index-per-tenant for a multi-tenant search platform serving 500+ tenants. Shared indices offered better resource utilization and simpler operations (fewer indices to manage), while per-tenant indices provided stronger isolation and independent lifecycle management. Chose a hybrid approach: small tenants (under 100K documents) share pooled indices with routing, while large tenants (over 100K documents or with premium SLAs) get dedicated indices. This balanced infrastructure cost (60% of tenants are small and share resources efficiently) with isolation guarantees for enterprise customers. The migration path was designed upfront — small tenants can be promoted to dedicated indices without downtime by reindexing and swapping aliases.

---

## 4. AI Tool Usage



- **Architecture scaffolding**: Generating the initial project structure and boilerplate code for FastAPI, middleware, and service layers
- **Best practice validation**: Reviewing Elasticsearch mapping design, cache invalidation strategy, and rate limiting approaches
- **Documentation drafting**: Structuring the architecture document and production readiness analysis with comprehensive coverage
- **Test case generation**: Producing integration test scaffolding covering CRUD, search, multi-tenancy isolation, and rate limiting

All architectural decisions, trade-off analysis, and production experience examples reflect real engineering judgment. AI accelerated the implementation from concept to working prototype within the time budget.
