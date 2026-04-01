#!/usr/bin/env python3
"""
Seed script: populates the search service with sample documents for demo purposes.
Usage: python scripts/seed_data.py [--base-url URL] [--tenant TENANT_ID] [--count N]
"""
import argparse
import json
import random
import sys
import urllib.request

SAMPLE_DOCS = [
    {
        "title": "Kubernetes Cluster Auto-Scaling Best Practices",
        "content": "Auto-scaling in Kubernetes involves both Horizontal Pod Autoscaler (HPA) and Cluster Autoscaler. HPA adjusts the number of pod replicas based on CPU utilization, memory, or custom metrics. Cluster Autoscaler adds or removes nodes when pods cannot be scheduled due to insufficient resources. Best practices include setting appropriate resource requests and limits, using Pod Disruption Budgets, and configuring scale-down delays to prevent thrashing.",
        "tags": ["kubernetes", "devops", "scaling"],
        "metadata": {"department": "engineering", "category": "infrastructure"},
        "source": "internal-wiki",
    },
    {
        "title": "Q3 2025 Revenue Analysis Report",
        "content": "Total revenue for Q3 2025 reached $47.2M, representing 23% year-over-year growth. SaaS recurring revenue accounted for 78% of total revenue, up from 71% in Q3 2024. Key growth drivers included enterprise contract expansions and new customer acquisition in the EMEA region. Churn rate decreased to 3.2%, the lowest in company history.",
        "tags": ["finance", "quarterly", "revenue"],
        "metadata": {"department": "finance", "fiscal_year": 2025, "quarter": "Q3"},
        "source": "finance-reports",
    },
    {
        "title": "Microservices Authentication with OAuth 2.0 and JWT",
        "content": "Implementing authentication in a microservices architecture requires a centralized identity provider issuing JWTs. Each service validates tokens independently using public keys, eliminating the need for inter-service auth calls. Refresh token rotation adds security, while API gateways handle initial token validation to reduce load on downstream services. Consider using short-lived access tokens (15 minutes) with longer-lived refresh tokens (7 days).",
        "tags": ["security", "authentication", "microservices"],
        "metadata": {"department": "engineering", "category": "security"},
        "source": "tech-blog",
    },
    {
        "title": "Employee Onboarding Checklist 2025",
        "content": "New employee onboarding process includes: Day 1 - IT setup, badge access, and orientation session. Week 1 - Team introductions, codebase walkthrough, development environment setup. Week 2 - First code review participation, CI/CD pipeline training. Month 1 - Complete security awareness training, shadow on-call rotation. Month 2 - Independent feature development with mentor review.",
        "tags": ["hr", "onboarding", "process"],
        "metadata": {"department": "hr", "year": 2025},
        "source": "hr-portal",
    },
    {
        "title": "Database Migration Strategy: PostgreSQL to CockroachDB",
        "content": "Migrating from PostgreSQL to CockroachDB for global distribution requires careful planning. Phase 1: Schema compatibility audit - CockroachDB supports most PostgreSQL syntax but has differences in sequence handling and some data types. Phase 2: Dual-write period where both databases receive writes. Phase 3: Shadow reads to validate consistency. Phase 4: Cutover with rollback plan. Key consideration: CockroachDB's serializable isolation may surface previously hidden race conditions.",
        "tags": ["database", "migration", "distributed-systems"],
        "metadata": {"department": "engineering", "category": "database"},
        "source": "architecture-decisions",
    },
    {
        "title": "Incident Response Playbook: Service Degradation",
        "content": "When service degradation is detected: 1) Acknowledge the alert within 5 minutes. 2) Assess blast radius using the service dependency map. 3) Communicate status via #incidents Slack channel. 4) If customer-facing, post to status page within 15 minutes. 5) Identify root cause using distributed tracing (Jaeger) and metrics (Grafana). 6) Apply mitigation - circuit breakers, traffic shifting, or rollback. 7) Post-incident: blameless postmortem within 48 hours.",
        "tags": ["incident-response", "sre", "operations"],
        "metadata": {"department": "engineering", "category": "operations"},
        "source": "runbooks",
    },
    {
        "title": "Machine Learning Model Deployment Pipeline",
        "content": "Our ML deployment pipeline uses MLflow for experiment tracking and model versioning. Models are containerized using Docker and deployed to Kubernetes via Argo CD. A canary deployment strategy routes 5% of traffic to new model versions, with automatic rollback if prediction quality metrics (measured by shadow scoring) degrade below thresholds. Feature stores ensure consistent feature computation between training and serving.",
        "tags": ["machine-learning", "mlops", "deployment"],
        "metadata": {"department": "data-science", "category": "mlops"},
        "source": "ds-wiki",
    },
    {
        "title": "API Rate Limiting and Throttling Design",
        "content": "Rate limiting protects services from abuse and ensures fair resource allocation across tenants. Our implementation uses a token bucket algorithm with Redis-backed distributed counters. Limits are applied per-tenant with configurable tiers: Free (100 req/min), Pro (1000 req/min), Enterprise (custom). Response headers include X-RateLimit-Limit, X-RateLimit-Remaining, and Retry-After. Burst allowances permit short spikes up to 2x the base rate.",
        "tags": ["api-design", "rate-limiting", "architecture"],
        "metadata": {"department": "engineering", "category": "api"},
        "source": "design-docs",
    },
    {
        "title": "Data Privacy Compliance: GDPR and CCPA Requirements",
        "content": "All systems processing personal data must comply with GDPR and CCPA regulations. Key requirements: data minimization, purpose limitation, right to erasure (implement data deletion pipelines), consent management, and data portability. Encryption at rest (AES-256) and in transit (TLS 1.3) is mandatory. Data retention policies must be documented and enforced automatically. Annual privacy impact assessments are required for new data processing activities.",
        "tags": ["compliance", "privacy", "gdpr", "security"],
        "metadata": {"department": "legal", "category": "compliance"},
        "source": "compliance-docs",
    },
    {
        "title": "Cost Optimization: Cloud Infrastructure Review",
        "content": "Monthly cloud spend analysis identified $34K in potential savings. Recommendations: 1) Right-size over-provisioned RDS instances (est. $12K/mo savings). 2) Purchase reserved instances for stable workloads (est. $8K/mo). 3) Implement S3 lifecycle policies to move cold data to Glacier (est. $5K/mo). 4) Consolidate underutilized EKS clusters (est. $6K/mo). 5) Enable spot instances for batch processing workloads (est. $3K/mo).",
        "tags": ["cloud", "cost-optimization", "infrastructure"],
        "metadata": {"department": "engineering", "category": "infrastructure", "estimated_savings": 34000},
        "source": "finops-reports",
    },
]


def seed(base_url: str, tenant_id: str, count: int):
    print(f"Seeding {count} documents for tenant '{tenant_id}' at {base_url}")
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": tenant_id,
    }

    for i in range(count):
        doc = SAMPLE_DOCS[i % len(SAMPLE_DOCS)].copy()
        if i >= len(SAMPLE_DOCS):
            doc["title"] = f"{doc['title']} (variant {i // len(SAMPLE_DOCS)})"

        data = json.dumps(doc).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/documents", data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                print(f"  [{i+1}/{count}] Indexed: {result['id']} - {doc['title'][:50]}")
        except Exception as e:
            print(f"  [{i+1}/{count}] ERROR: {e}")

    print(f"\nDone! Seeded {count} documents for tenant '{tenant_id}'.")
    print(f"Try: curl -H 'X-Tenant-ID: {tenant_id}' '{base_url}/search?q=kubernetes'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed sample documents")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--tenant", default="acme-corp")
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    seed(args.base_url, args.tenant, args.count)
