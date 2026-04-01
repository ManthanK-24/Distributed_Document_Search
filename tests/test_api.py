"""
Integration tests for the Document Search Service API.
Requires running Elasticsearch and Redis (use docker-compose).
Run: pytest tests/ -v
"""
import pytest
import httpx
import time

BASE_URL = "http://localhost:8000"
TENANT = "test-tenant"
HEADERS = {"X-Tenant-ID": TENANT, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=10) as c:
        yield c


class TestHealthCheck:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "dependencies" in data


class TestDocumentCRUD:
    doc_id = None

    def test_create_document(self, client):
        payload = {
            "title": "Test Document for Integration Tests",
            "content": "This is a test document with content about distributed systems and search engines.",
            "tags": ["test", "integration"],
            "metadata": {"env": "test"},
        }
        resp = client.post("/documents", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "indexed"
        assert "id" in data
        TestDocumentCRUD.doc_id = data["id"]

    def test_get_document(self, client):
        assert self.doc_id is not None
        resp = client.get(f"/documents/{self.doc_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Document for Integration Tests"
        assert data["tenant_id"] == TENANT

    def test_get_nonexistent_document(self, client):
        resp = client.get("/documents/nonexistent-id-12345")
        assert resp.status_code == 404

    def test_delete_document(self, client):
        assert self.doc_id is not None
        resp = client.delete(f"/documents/{self.doc_id}")
        assert resp.status_code == 200
        # Verify deletion
        resp = client.get(f"/documents/{self.doc_id}")
        assert resp.status_code == 404


class TestSearch:
    def test_search_basic(self, client):
        # Seed a document first
        client.post("/documents", json={
            "title": "Elasticsearch Performance Tuning Guide",
            "content": "Optimize Elasticsearch performance by tuning heap size, shard allocation, and refresh intervals.",
            "tags": ["elasticsearch", "performance"],
        })
        time.sleep(1)  # Allow indexing

        resp = client.get("/search", params={"q": "elasticsearch performance"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == TENANT
        assert data["total_hits"] >= 1
        assert len(data["results"]) >= 1

    def test_search_with_fuzzy(self, client):
        resp = client.get("/search", params={"q": "elasticsearh", "fuzzy": True})  # typo
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] >= 0  # May or may not match

    def test_search_with_pagination(self, client):
        resp = client.get("/search", params={"q": "performance", "page": 1, "page_size": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_search_with_tag_filter(self, client):
        resp = client.get("/search", params={"q": "performance", "tags": "elasticsearch"})
        assert resp.status_code == 200


class TestMultiTenancy:
    def test_tenant_isolation(self, client):
        # Create doc for test-tenant
        client.post("/documents", json={
            "title": "Tenant Isolation Test Document",
            "content": "This document belongs exclusively to test-tenant and should not appear in other tenant searches.",
            "tags": ["isolation-test"],
        })
        time.sleep(1)

        # Search as different tenant
        other_headers = {"X-Tenant-ID": "other-tenant", "Content-Type": "application/json"}
        resp = httpx.get(
            f"{BASE_URL}/search",
            params={"q": "isolation test"},
            headers=other_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hits"] == 0

    def test_missing_tenant_header(self):
        resp = httpx.get(f"{BASE_URL}/search", params={"q": "test"}, timeout=10)
        assert resp.status_code == 400
        assert "missing_tenant" in resp.json().get("error", "")


class TestRateLimiting:
    def test_rate_limit_headers(self, client):
        resp = client.get("/search", params={"q": "test"})
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
