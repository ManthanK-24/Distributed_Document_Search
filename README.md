# Distributed Document Search Service

A multi-tenant, full-text document search service built with **FastAPI**, **Elasticsearch**, and **Redis**. Designed for enterprise-scale workloads with sub-second search, tenant isolation, caching, and rate limiting.

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│   Client     │────▶│  FastAPI     │────▶│  Elasticsearch   │
│              │     │  (API +      │     │  (Full-text      │
│              │     │   Middleware) │     │   search index)  │
└─────────────┘     └──────┬───────┘     └──────────────────┘
                           │
                    ┌──────▼───────┐
                    │    Redis     │
                    │ (Cache +     │
                    │  Rate Limit) │
                    └──────────────┘
```

**Key features:**
- Full-text search with BM25 relevance ranking, highlighting, fuzzy matching
- Per-tenant data isolation (index-per-tenant strategy)
- Redis-backed caching with automatic invalidation on writes
- Sliding-window rate limiting per tenant
- Health check endpoint with dependency status
- Docker Compose for one-command startup


## 0 Container Health
![Container Health](./static/I1_Health.png) 

## 1 Add Doc A
![Add Doc A](./static/I2_Add_Doc_A.png) 

## 2 Add Doc B
![Add Doc B](./static/I3_Add_Doc_B.png) 

## 3 Add Doc C
![Add Doc C](./static/I3_Add_Doc_C.png) 

## 4 Add Doc D
![Add Doc D](./static/I4_Add_Doc_D.png)

## 5 Add Invalid Doc E
![Add Doc D](./static/I5_Add_Invalid_Doc.png)

## 6 Basic Search
![Basic Search](./static/I6_Basic_Search.png)

## 7 Multi Search
![Multi Search](./static/I7_Multi_Search.png)

## 8 Fuzzy Search
![Fuzzy Search](./static/I8_Fuzzy_Search.png)

## 9 Invalid Tag Search
![Tag Search](./static/I9_Tag_Search.png)

## 10 Valid Tag Search
![Tag Search](./static/I10_Tag_Search.png)

## 11 Paginated Search
![Paginated Search](./static/I11_Paginated_Search.png)

## 12 No Result Search
![No Result Search](./static/I12_No_Result_Search.png)

## 13 Advance Search
![Advance Search](./static/I13_Advance_Search.png)

## 14 Retrieve Doc 
![Retrieve Doc](./static/I14_Retrive_Doc.png)


## 15 Non Existing Doc 
![Non Existing Doc](./static/I15_Non_Existing_Doc.png)

## 16 Other Tenant Doc
![Other Tenant Doc](./static/I16_Other_Tenant_Doc.png)

## 17 Own Tenant Doc
![Own Tenant Doc](./static/I17_Own_Tenant_Doc.png)

## 18 Tenant Missing Header
![Tenant Missing Header](./static/I18_Tenant_Missing_Header.png)

## 19 Tenant_Query
![Tenant_Query](./static/I19_Tenant_Query.png)

## 20 Added_Doc_To_Delete
![Added_Doc_To_Delete](./static/I20_Added_Doc_To_Delete.png)


## 21 Delete_NonExisting_Doc
![Delete_NonExisting_Doc](./static/I21_Delete_NonExisting_Doc.png)

## 22 Deleted_Doc
![Deleted_Doc](./static/I22_Deleted_Doc.png)

## 23 Again_Delete_Same_Doc
![Again_Delete_Same_Doc](./static/I23_Again_Delete_Same_Doc.png)

## 24 Search_Deleted_Doc
![Search_Deleted_Doc](./static/I24_Search_Deleted_Doc.png)


## 25 Rate_Limiting
![Rate_Limiting](./static/I25_Rate_Limiting.png)

## 26 Swagger_UI
![Swagger_UI](./static/I26_Swagger_UI.png)


## 27 Postman
![Postman](./static/I27_Postman.png)


## 28 Docker
![Docker](./static/I28_Docker.png)
---


<!-- ## Quick Start

### Prerequisites

- Docker & Docker Compose (v2+)
- Python 3.11+ (for running without Docker)

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone <repo-url> && cd distributed-doc-search

# Start all services
docker compose up -d --build

# Wait for Elasticsearch to be healthy (~30s)
docker compose logs -f elasticsearch  # Wait for "started"

# Seed sample data
python scripts/seed_data.py --tenant acme-corp --count 10

# Try a search
curl -s -H "X-Tenant-ID: acme-corp" "http://localhost:8000/search?q=kubernetes" | python -m json.tool
```

### Option 2: Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start Elasticsearch and Redis (via Docker)
docker run -d --name es -p 9200:9200 -e "discovery.type=single-node" -e "xpack.security.enabled=false" docker.elastic.co/elasticsearch/elasticsearch:8.15.2
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Run the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Seed data
python scripts/seed_data.py
```

### Interactive API Docs

Once running, visit: **http://localhost:8000/docs** (Swagger UI)

---

## API Reference

All endpoints require the `X-Tenant-ID` header (or `?tenant=` query param).

### Index a Document

```bash
curl -X POST http://localhost:8000/documents \
  -H "X-Tenant-ID: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Kubernetes Scaling Guide",
    "content": "Horizontal Pod Autoscaler adjusts replicas based on CPU...",
    "tags": ["kubernetes", "devops"],
    "metadata": {"department": "engineering"}
  }'
```

**Response (201):**
```json
{
  "id": "a1b2c3d4-...",
  "tenant_id": "acme-corp",
  "status": "indexed",
  "message": "Document indexed successfully"
}
```

### Search Documents

```bash
# Basic search
curl -H "X-Tenant-ID: acme-corp" \
  "http://localhost:8000/search?q=kubernetes+scaling&page_size=5"

# Fuzzy search (handles typos)
curl -H "X-Tenant-ID: acme-corp" \
  "http://localhost:8000/search?q=kuberntes&fuzzy=true"

# Filter by tags
curl -H "X-Tenant-ID: acme-corp" \
  "http://localhost:8000/search?q=performance&tags=devops,kubernetes"
```

**Response (200):**
```json
{
  "query": "kubernetes scaling",
  "tenant_id": "acme-corp",
  "total_hits": 2,
  "page": 1,
  "page_size": 5,
  "total_pages": 1,
  "took_ms": 14.32,
  "results": [
    {
      "id": "a1b2c3d4-...",
      "title": "Kubernetes Scaling Guide",
      "content_snippet": "...<em>Kubernetes</em> involves <em>scaling</em>...",
      "score": 9.21,
      "tags": ["kubernetes", "devops"],
      "highlights": {
        "title": ["<em>Kubernetes</em> <em>Scaling</em> Guide"],
        "content": ["...<em>Kubernetes</em> involves <em>scaling</em>..."]
      },
      "created_at": "2025-10-15T08:30:00Z"
    }
  ]
}
```

### Advanced Search (POST)

```bash
curl -X POST http://localhost:8000/search \
  -H "X-Tenant-ID: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "database migration",
    "filters": {"department": "engineering"},
    "tags": ["database"],
    "page": 1,
    "page_size": 10,
    "highlight": true,
    "fuzzy": false
  }'
```

### Retrieve a Document

```bash
curl -H "X-Tenant-ID: acme-corp" \
  http://localhost:8000/documents/{document_id}
```

### Delete a Document

```bash
curl -X DELETE -H "X-Tenant-ID: acme-corp" \
  http://localhost:8000/documents/{document_id}
```

### Health Check

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 342.5,
  "dependencies": [
    {"name": "elasticsearch", "status": "healthy", "latency_ms": 3.21, "details": "green"},
    {"name": "cache", "status": "healthy", "latency_ms": 0.45, "details": "redis"}
  ]
}
```

---

## Multi-Tenancy

Every request is scoped to a tenant via the `X-Tenant-ID` header. Tenants are fully isolated:

- **Separate Elasticsearch indices** per tenant (`docs_acme-corp`, `docs_globex`)
- **Separate cache namespaces** in Redis
- **Independent rate limits** per tenant
- **No cross-tenant data leakage** — enforced at middleware and query level

```bash
# Tenant A indexes a document
curl -X POST http://localhost:8000/documents \
  -H "X-Tenant-ID: tenant-a" \
  -H "Content-Type: application/json" \
  -d '{"title": "Secret Plan", "content": "Top secret content for tenant A only"}'

# Tenant B cannot see it
curl -H "X-Tenant-ID: tenant-b" "http://localhost:8000/search?q=secret+plan"
# → {"total_hits": 0, "results": []}
```

---

## Rate Limiting

Sliding-window rate limiting is applied per tenant (default: 100 requests/minute).

Response headers on every request:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
```

When exceeded:
```json
{
  "error": "rate_limit_exceeded",
  "message": "Rate limit of 100 requests per 60s exceeded for tenant 'acme-corp'",
  "retry_after_seconds": 60
}
```

Configure via environment variables:
- `RATE_LIMIT_REQUESTS` (default: 100)
- `RATE_LIMIT_WINDOW_SECONDS` (default: 60)

---

## Running Tests

```bash
# Start infrastructure
docker compose up -d elasticsearch redis

# Run tests (requires running services)
pip install -r requirements.txt
pytest tests/ -v
```

---

## Project Structure

```
distributed-doc-search/
├── app/
│   ├── main.py                  # FastAPI app with lifespan, middleware, routers
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   ├── routers/
│   │   ├── documents.py         # CRUD endpoints
│   │   ├── search.py            # Search endpoints (GET + POST)
│   │   └── health.py            # Health check with dependency status
│   ├── services/
│   │   ├── elasticsearch_service.py  # ES indexing, search, tenant isolation
│   │   └── cache_service.py          # Redis cache with in-memory fallback
│   ├── middleware/
│   │   ├── tenant.py            # Tenant extraction & validation
│   │   └── rate_limiter.py      # Per-tenant sliding window rate limiter
│   └── utils/
│       └── config.py            # Environment-based configuration
├── tests/
│   └── test_api.py              # Integration tests
├── scripts/
│   └── seed_data.py             # Sample data seeder
├── docs/
│   └── (architecture diagrams)
├── docker-compose.yml           # Full stack: API + ES + Redis
├── Dockerfile                   # API container image
├── requirements.txt             # Python dependencies
├── DOCUMENTATION.md             # Architecture + Production Readiness + Experience
└── README.md                    # This file
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTICSEARCH_HOST` | `http://localhost:9200` | Elasticsearch URL |
| `REDIS_HOST` | `localhost` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `CACHE_ENABLED` | `true` | Enable/disable caching |
| `CACHE_TTL_SECONDS` | `300` | Default cache TTL |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per window per tenant |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window duration |

---

## Documentation

See **[DOCUMENTATION.md](./DOCUMENTATION.md)** for:
- Architecture Design Document (with diagrams and trade-off analysis)
- Production Readiness Analysis (scalability, resilience, security, observability)
- Enterprise Experience Showcase
- AI Tool Usage disclosure -->
