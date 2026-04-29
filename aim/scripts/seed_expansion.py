"""
AIM Seed Expansion — 170+ additional entities and 350+ relationships
for the Nexus Technologies demo universe.

Imported by ``seed_demo.py`` when the ``--full`` flag is used.
"""
from __future__ import annotations

import uuid


def _id(name: str) -> str:
    """Deterministic UUID from a name so re-runs are idempotent."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"nexus.demo.{name}"))


# ═══════════════════════════════════════════════════════════════════════════════
#  PEOPLE  (30 new engineers, PMs, designers, data scientists, managers)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_PEOPLE = [
    {
        "entity_id": _id("raj-krishnan"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("raj-krishnan"),
            "name": "Raj Krishnan",
            "title": "Senior Engineer — Platform",
            "description": "Senior Platform Engineer at Nexus Technologies. Maintains the Kubernetes cluster (EKS, 180 nodes across 3 AZs) and Istio service mesh. Built the automated canary analysis system that evaluates error rates and latency during deployments. Previously at AWS on the EKS team. CKA and CKAD certified. Authored the internal Kubernetes best practices guide used by all 30+ services.",
            "department": "Engineering",
            "location": "Seattle",
            "expertise": "kubernetes, istio, AWS, infrastructure",
            "created_at": "2023-10-01T09:00:00Z",
            "updated_at": "2025-03-20T11:00:00Z",
        },
    },
    {
        "entity_id": _id("sofia-martinez"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("sofia-martinez"),
            "name": "Sofia Martinez",
            "title": "Senior Engineer — Backend",
            "description": "Senior Backend Engineer at Nexus Technologies. Owns the Order Service which processes 500K orders/day with 99.97% success rate. Migrated the service from synchronous REST to event-driven architecture per ADR-001. Expert in Go and PostgreSQL performance tuning. Previously at Shopify where she scaled the checkout pipeline to handle 1M+ concurrent checkouts during flash sales.",
            "department": "Engineering",
            "location": "Toronto",
            "expertise": "golang, postgresql, event-driven architecture, performance",
            "created_at": "2023-09-15T09:00:00Z",
            "updated_at": "2025-03-18T14:00:00Z",
        },
    },
    {
        "entity_id": _id("james-wu"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("james-wu"),
            "name": "James Wu",
            "title": "Engineer — Frontend",
            "description": "Frontend Engineer at Nexus Technologies. Built the real-time notification system using WebSockets and the React component for live order tracking. Implemented the dark mode system across the entire @nexus/ui component library (120+ components). Active contributor to the Next.js 14 migration. Expert in CSS architecture and design systems.",
            "department": "Engineering",
            "location": "San Francisco",
            "expertise": "react, typescript, design systems, CSS",
            "created_at": "2024-05-01T09:00:00Z",
            "updated_at": "2025-03-22T10:00:00Z",
        },
    },
    {
        "entity_id": _id("nina-oconnell"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("nina-oconnell"),
            "name": "Nina O'Connell",
            "title": "Senior Engineer — Data",
            "description": "Senior Data Engineer at Nexus Technologies. Architected the data lake on S3 with Delta Lake format, processing 2TB/day through Spark jobs. Built the real-time analytics pipeline that powers the executive dashboard. Maintains the dbt transformation layer with 400+ models. Previously at Netflix where she built the A/B testing data pipeline.",
            "department": "Data",
            "location": "New York",
            "expertise": "spark, delta lake, dbt, data pipelines, SQL",
            "created_at": "2024-02-15T09:00:00Z",
            "updated_at": "2025-03-25T09:00:00Z",
        },
    },
    {
        "entity_id": _id("tom-andersen"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("tom-andersen"),
            "name": "Tom Andersen",
            "title": "Engineer — Platform",
            "description": "Platform Engineer at Nexus Technologies. Maintains the CI/CD pipeline (GitHub Actions) and internal developer tooling. Built the local dev environment (Tilt-based) that spins up all 30+ services in 3 minutes. Reduced CI build times from 18 minutes to 6 minutes through caching and parallelization. Active contributor to the Terraform modules.",
            "department": "Engineering",
            "location": "Denver",
            "expertise": "CI/CD, github actions, tilt, developer tooling",
            "created_at": "2024-04-01T09:00:00Z",
            "updated_at": "2025-03-15T16:00:00Z",
        },
    },
    {
        "entity_id": _id("aisha-mohammed"),
        "labels": ["Entity", "Person", "DataScientist"],
        "properties": {
            "aim_id": _id("aisha-mohammed"),
            "name": "Aisha Mohammed",
            "title": "Senior Data Scientist",
            "description": "Senior Data Scientist at Nexus Technologies. Built the recommendation engine that drives 35% of product discovery. Owns the cross-encoder re-ranker model (ms-marco-MiniLM-L-12-v2) used in Project Aurora, fine-tuned on 50K Nexus-specific query-document pairs. Published research on hybrid search at SIGIR 2024. Partners with Priya Patel on model deployment via the ML Infrastructure team.",
            "department": "Data Science",
            "location": "Boston",
            "expertise": "NLP, information retrieval, transformers, pytorch",
            "created_at": "2024-06-01T09:00:00Z",
            "updated_at": "2025-03-28T11:00:00Z",
        },
    },
    {
        "entity_id": _id("chen-wei"),
        "labels": ["Entity", "Person", "DataScientist"],
        "properties": {
            "aim_id": _id("chen-wei"),
            "name": "Chen Wei",
            "title": "Data Scientist",
            "description": "Data Scientist at Nexus Technologies. Builds and maintains the fraud detection models (XGBoost ensemble) that block $2M+/month in fraudulent transactions. Implemented the real-time scoring pipeline with 8ms p99 latency through the Feature Store. Collaborates with the Payment Service team on fraud rules. Previously at Capital One on the fraud analytics team.",
            "department": "Data Science",
            "location": "New York",
            "expertise": "fraud detection, XGBoost, feature engineering, python",
            "created_at": "2024-03-01T09:00:00Z",
            "updated_at": "2025-03-20T14:00:00Z",
        },
    },
    {
        "entity_id": _id("maya-kapoor"),
        "labels": ["Entity", "Person", "Designer"],
        "properties": {
            "aim_id": _id("maya-kapoor"),
            "name": "Maya Kapoor",
            "title": "Senior Product Designer",
            "description": "Senior Product Designer at Nexus Technologies. Designed the conversational search UI for Project Aurora Phase 3 — conducted 20 user interviews and 3 rounds of usability testing. Owns the Nexus Design System in Figma with 200+ tokens and 80+ components. Previously at Airbnb where she redesigned the booking flow increasing conversion by 12%.",
            "department": "Design",
            "location": "San Francisco",
            "expertise": "UX design, design systems, user research, figma",
            "created_at": "2024-01-15T09:00:00Z",
            "updated_at": "2025-03-26T15:00:00Z",
        },
    },
    {
        "entity_id": _id("daniel-park"),
        "labels": ["Entity", "Person", "ProductManager"],
        "properties": {
            "aim_id": _id("daniel-park"),
            "name": "Daniel Park",
            "title": "Product Manager — Platform",
            "description": "PM for the Platform team at Nexus Technologies. Owns the internal developer experience product area. Led the developer satisfaction survey (NPS improved from +22 to +48 after Tilt local dev env launch). Manages the platform services roadmap including the multi-region expansion (Project Horizon). Previously PM at Datadog where he launched the Kubernetes monitoring product.",
            "department": "Product",
            "location": "San Francisco",
            "expertise": "developer experience, platform products, data-driven PM",
            "created_at": "2024-07-01T09:00:00Z",
            "updated_at": "2025-03-22T10:00:00Z",
        },
    },
    {
        "entity_id": _id("olivia-chen"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("olivia-chen"),
            "name": "Olivia Chen",
            "title": "Senior Engineer — ML Infrastructure",
            "description": "Senior ML Infrastructure Engineer at Nexus Technologies. Owns the model serving pipeline (TorchServe + Triton) handling 200+ models with auto-scaling based on GPU utilization. Built the A/B testing framework for ML models with automatic metric collection and statistical significance testing. Previously at Google Brain on the TFX team.",
            "department": "Engineering",
            "location": "Mountain View",
            "expertise": "model serving, triton, GPU optimization, MLOps",
            "created_at": "2024-04-15T09:00:00Z",
            "updated_at": "2025-03-25T11:00:00Z",
        },
    },
    {
        "entity_id": _id("kevin-brown"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("kevin-brown"),
            "name": "Kevin Brown",
            "title": "Engineer — Backend",
            "description": "Backend Engineer at Nexus Technologies. Owns the Notification Service which sends 2M+ emails, push notifications, and SMS messages daily via a priority queue system. Implemented the template engine with A/B testing for notification content. Migrated from SendGrid to a multi-provider setup (SES + Twilio + Firebase) for cost optimization saving $4K/month.",
            "department": "Engineering",
            "location": "Austin",
            "expertise": "messaging systems, AWS SES, event-driven, python",
            "created_at": "2024-06-15T09:00:00Z",
            "updated_at": "2025-03-18T10:00:00Z",
        },
    },
    {
        "entity_id": _id("hannah-lee"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("hannah-lee"),
            "name": "Hannah Lee",
            "title": "Senior Engineer — Frontend",
            "description": "Senior Frontend Engineer at Nexus Technologies. Led the performance optimization initiative that brought LCP from 4.2s to 1.2s. Built the React Server Components architecture for the product catalog (2M+ SKUs) with streaming SSR. Maintains the @nexus/ui Storybook with visual regression testing via Chromatic. Expert in web accessibility (WCAG 2.1 AA compliance).",
            "department": "Engineering",
            "location": "London",
            "expertise": "react, performance, accessibility, server components",
            "created_at": "2024-03-01T09:00:00Z",
            "updated_at": "2025-03-24T09:00:00Z",
        },
    },
    {
        "entity_id": _id("diego-reyes"),
        "labels": ["Entity", "Person", "SRE"],
        "properties": {
            "aim_id": _id("diego-reyes"),
            "name": "Diego Reyes",
            "title": "SRE",
            "description": "Site Reliability Engineer at Nexus Technologies. Manages the Prometheus + Grafana monitoring stack (42 dashboards). Built the SLO framework that tracks error budget burn rates across all services. Implemented automated runbooks via PagerDuty Process Automation for common incidents (pod restarts, disk cleanup, certificate rotation). On-call every 4th week.",
            "department": "Engineering",
            "location": "Mexico City",
            "expertise": "prometheus, grafana, SLOs, automation, linux",
            "created_at": "2024-08-01T09:00:00Z",
            "updated_at": "2025-03-27T08:00:00Z",
        },
    },
    {
        "entity_id": _id("lena-johansson"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("lena-johansson"),
            "name": "Lena Johansson",
            "title": "Senior Engineer — Security",
            "description": "Senior Security Engineer at Nexus Technologies. Working on Project Fortress (zero trust). Implemented mTLS across all 30+ services via Istio. Building the ABAC system to replace coarse RBAC (23 fine-grained permissions). Runs the monthly security training and quarterly penetration testing. Previously at Snyk where she built the SAST scanning engine. CISSP certified.",
            "department": "Security",
            "location": "Stockholm",
            "expertise": "security, mTLS, ABAC, penetration testing, compliance",
            "created_at": "2024-09-01T09:00:00Z",
            "updated_at": "2025-03-22T14:00:00Z",
        },
    },
    {
        "entity_id": _id("michael-taylor"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("michael-taylor"),
            "name": "Michael Taylor",
            "title": "Engineer — Backend",
            "description": "Backend Engineer at Nexus Technologies. Owns the Payment Service which processes $15M/month in transactions with 99.99% reliability. Integrated with Stripe Connect for marketplace payments and implemented the reconciliation pipeline that catches discrepancies within 5 minutes. Built the retry mechanism with exponential backoff for failed payment captures.",
            "department": "Engineering",
            "location": "Chicago",
            "expertise": "payments, stripe, financial systems, golang",
            "created_at": "2024-01-01T09:00:00Z",
            "updated_at": "2025-03-20T15:00:00Z",
        },
    },
    {
        "entity_id": _id("yuki-tanaka"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("yuki-tanaka"),
            "name": "Yuki Tanaka",
            "title": "Engineer — Data",
            "description": "Data Engineer at Nexus Technologies. Maintains the Airflow orchestration platform (200+ DAGs) and the data quality framework (Great Expectations, 1500+ expectations). Built the customer 360 pipeline that unifies data from 8 sources into a single customer profile used by marketing and support teams. Previously at dbt Labs.",
            "department": "Data",
            "location": "Tokyo",
            "expertise": "airflow, dbt, data quality, great expectations",
            "created_at": "2024-05-15T09:00:00Z",
            "updated_at": "2025-03-19T12:00:00Z",
        },
    },
    {
        "entity_id": _id("rachel-green"),
        "labels": ["Entity", "Person", "ProductManager"],
        "properties": {
            "aim_id": _id("rachel-green"),
            "name": "Rachel Green",
            "title": "Product Manager — Growth",
            "description": "PM for the Growth team at Nexus Technologies. Owns the onboarding funnel (improved activation rate from 34% to 52% through progressive disclosure and personalized onboarding paths). Manages the experimentation platform with 40+ concurrent A/B tests via LaunchDarkly. Previously PM at Amplitude where she launched the behavioral cohort feature.",
            "department": "Product",
            "location": "San Francisco",
            "expertise": "growth, experimentation, onboarding, analytics",
            "created_at": "2024-08-01T09:00:00Z",
            "updated_at": "2025-03-21T10:00:00Z",
        },
    },
    {
        "entity_id": _id("sam-patel"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("sam-patel"),
            "name": "Sam Patel",
            "title": "Senior Engineer — Mobile",
            "description": "Senior Mobile Engineer at Nexus Technologies. Leads the React Native app (iOS + Android) which has 500K+ MAU and 4.7 star rating. Implemented offline-first architecture with local SQLite and background sync. Built the mobile push notification system with deep linking. Previously at Uber on the rider app team.",
            "department": "Engineering",
            "location": "San Francisco",
            "expertise": "react native, iOS, android, mobile architecture",
            "created_at": "2024-02-01T09:00:00Z",
            "updated_at": "2025-03-25T14:00:00Z",
        },
    },
    {
        "entity_id": _id("anna-kowalski"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("anna-kowalski"),
            "name": "Anna Kowalski",
            "title": "Engineer — Backend",
            "description": "Backend Engineer at Nexus Technologies. Owns the Inventory Service which tracks 2M+ SKUs across 12 warehouses with real-time stock updates via Kafka. Implemented the reservation system that prevents overselling during flash sales (99.99% accuracy). Built the warehouse allocation algorithm that reduced shipping costs by 15%.",
            "department": "Engineering",
            "location": "Warsaw",
            "expertise": "inventory systems, kafka, python, algorithms",
            "created_at": "2024-07-01T09:00:00Z",
            "updated_at": "2025-03-23T11:00:00Z",
        },
    },
    {
        "entity_id": _id("carlos-vega"),
        "labels": ["Entity", "Person", "Engineer"],
        "properties": {
            "aim_id": _id("carlos-vega"),
            "name": "Carlos Vega",
            "title": "Senior Engineer — Backend",
            "description": "Senior Backend Engineer at Nexus Technologies. Owns the Pricing Service which computes dynamic pricing for 2M+ products using a rules engine combined with ML-based demand forecasting. Handles 100K pricing lookups/minute with p99 latency of 15ms via Redis caching. Previously at Amazon on the dynamic pricing team.",
            "department": "Engineering",
            "location": "Madrid",
            "expertise": "pricing algorithms, redis, microservices, java",
            "created_at": "2024-03-15T09:00:00Z",
            "updated_at": "2025-03-19T16:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  SERVICES  (20 new microservices)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_SERVICES = [
    {
        "entity_id": _id("svc-orders"),
        "labels": ["Entity", "Service", "Product"],
        "properties": {
            "aim_id": _id("svc-orders"),
            "name": "Order Service",
            "title": "Order Processing Service",
            "description": "Handles the full order lifecycle: creation, payment capture, fulfillment, and delivery tracking. Processes 500K orders/day with a saga pattern for distributed transactions across payment, inventory, and shipping services. Migrated from synchronous REST to event-driven (ADR-001) in Q1 2025. Uses PostgreSQL for order state and publishes domain events to Kafka (order-created, order-paid, order-shipped, order-delivered).",
            "tech_stack": "Go, PostgreSQL, Kafka",
            "status": "production",
            "tier": "critical",
            "owner": _id("sofia-martinez"),
            "slack_channel": "#svc-orders",
            "jira_project": "ORD",
            "github_repo": "nexus/order-service",
            "created_at": "2023-04-01T09:00:00Z",
            "updated_at": "2025-03-18T14:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-payments"),
        "labels": ["Entity", "Service", "Product"],
        "properties": {
            "aim_id": _id("svc-payments"),
            "name": "Payment Service",
            "title": "Payment Processing Service",
            "description": "Processes $15M/month in transactions via Stripe Connect. Supports credit cards, ACH, and wallet payments. Implements PCI DSS Level 1 compliance with tokenized card storage. The reconciliation pipeline runs every 5 minutes and catches discrepancies within the same cycle. Retry mechanism with exponential backoff handles transient Stripe API failures (0.02% failure rate).",
            "tech_stack": "Go, PostgreSQL, Stripe SDK",
            "status": "production",
            "tier": "critical",
            "owner": _id("michael-taylor"),
            "slack_channel": "#svc-payments",
            "jira_project": "PAY",
            "github_repo": "nexus/payment-service",
            "created_at": "2023-04-15T09:00:00Z",
            "updated_at": "2025-03-20T15:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-inventory"),
        "labels": ["Entity", "Service", "Product"],
        "properties": {
            "aim_id": _id("svc-inventory"),
            "name": "Inventory Service",
            "title": "Inventory Management Service",
            "description": "Tracks 2M+ SKUs across 12 warehouses. Real-time stock updates via Kafka consumer (inventory-events topic). The reservation system uses optimistic locking with PostgreSQL to prevent overselling during flash sales (99.99% accuracy across 10K concurrent reservations). Warehouse allocation algorithm reduced shipping costs by 15% by routing orders to the nearest warehouse with stock.",
            "tech_stack": "Python, FastAPI, PostgreSQL, Kafka",
            "status": "production",
            "tier": "high",
            "owner": _id("anna-kowalski"),
            "slack_channel": "#svc-inventory",
            "jira_project": "INV",
            "github_repo": "nexus/inventory-service",
            "created_at": "2023-05-01T09:00:00Z",
            "updated_at": "2025-03-23T11:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-notifications"),
        "labels": ["Entity", "Service", "Product"],
        "properties": {
            "aim_id": _id("svc-notifications"),
            "name": "Notification Service",
            "title": "Multi-Channel Notification Service",
            "description": "Sends 2M+ messages daily across email (SES), push (Firebase), and SMS (Twilio). Priority queue ensures transactional messages (order confirmations, password resets) are sent within 30 seconds while marketing messages are batched. Template engine supports A/B testing for notification content. Migrated from SendGrid to multi-provider setup saving $4K/month.",
            "tech_stack": "Python, Celery, Redis, SES, Twilio, Firebase",
            "status": "production",
            "tier": "high",
            "owner": _id("kevin-brown"),
            "slack_channel": "#svc-notifications",
            "jira_project": "NOTIF",
            "github_repo": "nexus/notification-service",
            "created_at": "2023-06-01T09:00:00Z",
            "updated_at": "2025-03-18T10:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-pricing"),
        "labels": ["Entity", "Service", "Product"],
        "properties": {
            "aim_id": _id("svc-pricing"),
            "name": "Pricing Service",
            "title": "Dynamic Pricing Service",
            "description": "Computes dynamic pricing for 2M+ products using a rules engine combined with ML-based demand forecasting. Handles 100K pricing lookups/minute with p99 latency of 15ms via Redis caching with 5-minute TTL. Supports promotional pricing, volume discounts, and geographic pricing. The ML model retrains weekly on 90 days of historical data.",
            "tech_stack": "Java, Spring Boot, Redis, Kafka",
            "status": "production",
            "tier": "high",
            "owner": _id("carlos-vega"),
            "slack_channel": "#svc-pricing",
            "jira_project": "PRICE",
            "github_repo": "nexus/pricing-service",
            "created_at": "2023-08-01T09:00:00Z",
            "updated_at": "2025-03-19T16:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-mobile-api"),
        "labels": ["Entity", "Service", "Product"],
        "properties": {
            "aim_id": _id("svc-mobile-api"),
            "name": "Mobile BFF",
            "title": "Mobile Backend-For-Frontend",
            "description": "Backend-For-Frontend tailored for the mobile app. Aggregates responses from 5+ microservices into mobile-optimized payloads (30% smaller than web API responses). Supports GraphQL for flexible queries and REST for simple endpoints. Handles offline sync via conflict resolution (last-write-wins with vector clocks for critical fields). Serves 500K+ MAU.",
            "tech_stack": "Node.js, GraphQL, Apollo Server",
            "status": "production",
            "tier": "high",
            "owner": _id("sam-patel"),
            "slack_channel": "#svc-mobile",
            "jira_project": "MOB",
            "github_repo": "nexus/mobile-bff",
            "created_at": "2024-02-01T09:00:00Z",
            "updated_at": "2025-03-25T14:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-recommendations"),
        "labels": ["Entity", "Service", "MLInfra"],
        "properties": {
            "aim_id": _id("svc-recommendations"),
            "name": "Recommendation Service",
            "title": "Product Recommendation Engine",
            "description": "Serves personalized product recommendations driving 35% of product discovery. Uses a two-tower neural network (user tower + item tower) with real-time features from the Feature Store. Candidate generation via approximate nearest neighbor search (HNSW index on 128-dim embeddings), followed by a ranking model. Serves 50K requests/minute with p99 latency of 25ms. A/B testing shows 18% CTR improvement over the previous collaborative filtering approach.",
            "tech_stack": "Python, TorchServe, Redis, Feature Store",
            "status": "production",
            "tier": "high",
            "owner": _id("aisha-mohammed"),
            "slack_channel": "#svc-recommendations",
            "jira_project": "MLINFRA",
            "github_repo": "nexus/recommendation-service",
            "created_at": "2024-06-01T09:00:00Z",
            "updated_at": "2025-03-28T11:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-fraud"),
        "labels": ["Entity", "Service", "MLInfra"],
        "properties": {
            "aim_id": _id("svc-fraud"),
            "name": "Fraud Detection Service",
            "title": "Real-Time Fraud Detection",
            "description": "Blocks $2M+/month in fraudulent transactions using an XGBoost ensemble model with 150 features from the Feature Store. Real-time scoring with 8ms p99 latency. Combines ML scores with rule-based checks (velocity limits, geofencing, device fingerprinting). False positive rate: 0.3%. The model retrains daily on confirmed fraud labels. Integrated with Stripe Radar for additional signal.",
            "tech_stack": "Python, XGBoost, Feature Store, Redis",
            "status": "production",
            "tier": "critical",
            "owner": _id("chen-wei"),
            "slack_channel": "#svc-fraud",
            "jira_project": "SEC",
            "github_repo": "nexus/fraud-detection",
            "created_at": "2024-03-01T09:00:00Z",
            "updated_at": "2025-03-20T14:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-data-lake"),
        "labels": ["Entity", "Service", "Data"],
        "properties": {
            "aim_id": _id("svc-data-lake"),
            "name": "Data Lake",
            "title": "Data Lake & Analytics Platform",
            "description": "S3-based data lake with Delta Lake format. Ingests 2TB/day from 8 sources (PostgreSQL CDC, Kafka topics, API logs, clickstream). Spark jobs process raw → curated → consumption layers. The dbt transformation layer has 400+ models with daily freshness. Supports ad-hoc queries via Presto and scheduled analytics via Airflow (200+ DAGs). Powers the executive dashboard and all business intelligence reporting.",
            "tech_stack": "S3, Delta Lake, Spark, Presto, Airflow, dbt",
            "status": "production",
            "tier": "high",
            "owner": _id("nina-oconnell"),
            "slack_channel": "#data-platform",
            "jira_project": "DATA",
            "github_repo": "nexus/data-lake",
            "created_at": "2024-02-15T09:00:00Z",
            "updated_at": "2025-03-25T09:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-user-profile"),
        "labels": ["Entity", "Service", "Product"],
        "properties": {
            "aim_id": _id("svc-user-profile"),
            "name": "User Profile Service",
            "title": "User Profile & Preferences Service",
            "description": "Central user profile service holding 1.2M user records. Manages profile data, preferences, notification settings, and privacy consents (GDPR/CCPA). Supports profile merge for duplicate accounts (500+ merges/month). GraphQL API for flexible field selection. Write-behind caching via Redis with 5-minute TTL. The GDPR data export endpoint generates a complete user archive within 2 hours.",
            "tech_stack": "Go, PostgreSQL, Redis, GraphQL",
            "status": "production",
            "tier": "high",
            "owner": _id("sofia-martinez"),
            "slack_channel": "#svc-users",
            "jira_project": "USR",
            "github_repo": "nexus/user-profile-service",
            "created_at": "2023-04-01T09:00:00Z",
            "updated_at": "2025-03-21T12:00:00Z",
        },
    },
    {
        "entity_id": _id("svc-media"),
        "labels": ["Entity", "Service", "Infrastructure"],
        "properties": {
            "aim_id": _id("svc-media"),
            "name": "Media Service",
            "title": "Image & Media Processing Service",
            "description": "Handles image upload, processing, and CDN distribution for product images. Processes 50K images/day through a pipeline of resizing (6 sizes), format conversion (WebP + AVIF), quality optimization (sharp), and CDN upload (CloudFront). Average processing time: 1.2 seconds per image. Supports lazy thumbnail generation for long-tail images. Storage: S3 with lifecycle policies (hot → glacier after 180 days).",
            "tech_stack": "Node.js, Sharp, S3, CloudFront, SQS",
            "status": "production",
            "tier": "medium",
            "owner": _id("james-wu"),
            "slack_channel": "#svc-media",
            "jira_project": "PLAT",
            "github_repo": "nexus/media-service",
            "created_at": "2023-07-01T09:00:00Z",
            "updated_at": "2025-03-15T11:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  DECISIONS  (10 new ADRs)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_DECISIONS = [
    {
        "entity_id": _id("adr-006"),
        "labels": ["Entity", "Decision", "ADR"],
        "properties": {
            "aim_id": _id("adr-006"),
            "name": "ADR-006: GraphQL for Mobile BFF",
            "title": "ADR-006: Adopt GraphQL for Mobile Backend",
            "content": "Status: Accepted (2024-02-15). Context: The mobile app made 5-8 REST calls per screen, leading to waterfall requests and over-fetching. Battery usage was high due to frequent network calls. Decision: Implement GraphQL via Apollo Server for the Mobile BFF, keeping REST for the web frontend. Automatic persisted queries reduce payload size by 90%. DataLoader pattern for N+1 prevention. Consequences: Mobile payloads reduced by 30%, battery usage improved by 20%, but requires schema governance and versioning discipline.",
            "status": "accepted",
            "date": "2024-02-15",
            "proposed_by": _id("sam-patel"),
            "approved_by": _id("sarah-chen"),
            "jira_ticket": "MOB-089",
            "created_at": "2024-02-10T09:00:00Z",
            "updated_at": "2024-02-15T14:00:00Z",
        },
    },
    {
        "entity_id": _id("adr-007"),
        "labels": ["Entity", "Decision", "ADR"],
        "properties": {
            "aim_id": _id("adr-007"),
            "name": "ADR-007: Saga Pattern for Distributed Transactions",
            "title": "ADR-007: Saga Pattern for Order Processing",
            "content": "Status: Accepted (2024-05-20). Context: The order flow spans 4 services (orders, payments, inventory, shipping). Two-phase commit was too slow (200ms overhead) and fragile. Decision: Implement choreography-based saga using Kafka events. Each service publishes domain events; compensating transactions handle failures (e.g., payment captured but inventory unavailable triggers refund). Idempotency keys prevent duplicate processing. Consequences: Eventual consistency (orders may show 'processing' for up to 30 seconds), but eliminates distributed lock contention and enables independent service scaling.",
            "status": "accepted",
            "date": "2024-05-20",
            "proposed_by": _id("sofia-martinez"),
            "approved_by": _id("sarah-chen"),
            "jira_ticket": "ORD-156",
            "created_at": "2024-05-15T09:00:00Z",
            "updated_at": "2024-05-20T16:00:00Z",
        },
    },
    {
        "entity_id": _id("adr-008"),
        "labels": ["Entity", "Decision", "ADR"],
        "properties": {
            "aim_id": _id("adr-008"),
            "name": "ADR-008: Delta Lake for Data Platform",
            "title": "ADR-008: Delta Lake as Data Lake Storage Format",
            "content": "Status: Accepted (2024-03-01). Context: Raw Parquet files lacked ACID transactions, time travel, and schema enforcement. Data quality issues (duplicates, late-arriving data) caused incorrect reports. Decision: Adopt Delta Lake format for all data lake tables. MERGE operations for upserts, time travel for point-in-time queries, schema evolution for backward-compatible changes. Z-ordering for query optimization on high-cardinality columns. Consequences: 40% faster queries through data skipping, reliable CDC ingestion, but requires Spark for writes (no direct Presto writes).",
            "status": "accepted",
            "date": "2024-03-01",
            "proposed_by": _id("nina-oconnell"),
            "approved_by": _id("sarah-chen"),
            "jira_ticket": "DATA-201",
            "created_at": "2024-02-25T09:00:00Z",
            "updated_at": "2024-03-01T11:00:00Z",
        },
    },
    {
        "entity_id": _id("adr-009"),
        "labels": ["Entity", "Decision", "ADR"],
        "properties": {
            "aim_id": _id("adr-009"),
            "name": "ADR-009: Feature Flags via LaunchDarkly",
            "title": "ADR-009: LaunchDarkly for Feature Flag Management",
            "content": "Status: Accepted (2024-01-15). Context: Feature flags were managed via environment variables, requiring redeployments for changes and offering no targeting capabilities. Rolling out features to specific user segments was impossible without code changes. Decision: Adopt LaunchDarkly for feature flag management. All new features behind flags. Targeting rules support: percentage rollout, user attributes (plan, region, cohort), and A/B test bucketing. SDK integration in all services (server-side Go/Python/Node.js) and frontend (React SDK with streaming updates). Consequences: 40+ concurrent experiments running, deploy-decoupled releases, but $1.2K/month cost and requires flag cleanup discipline (quarterly flag audit).",
            "status": "accepted",
            "date": "2024-01-15",
            "proposed_by": _id("rachel-green"),
            "approved_by": _id("lisa-zhang"),
            "jira_ticket": "GROW-067",
            "created_at": "2024-01-10T09:00:00Z",
            "updated_at": "2024-01-15T15:00:00Z",
        },
    },
    {
        "entity_id": _id("adr-010"),
        "labels": ["Entity", "Decision", "ADR"],
        "properties": {
            "aim_id": _id("adr-010"),
            "name": "ADR-010: ABAC Authorization Model",
            "title": "ADR-010: Attribute-Based Access Control",
            "content": "Status: In Progress (2025-03-01). Context: The current RBAC system has 5 static roles (admin, manager, member, viewer, service) which are too coarse for multi-tenant isolation and fine-grained permissions. Adding new permissions requires code changes and redeployments. Decision: Migrate to ABAC using OPA (Open Policy Agent) policies. 23 fine-grained permissions evaluated against user attributes (role, department, tenant, data classification). Policies stored in OPA bundle server, synced every 30 seconds. p99 evaluation time target: < 2ms. Part of Project Fortress. Consequences: Flexible permission model, policy-as-code in git, but OPA learning curve and need for comprehensive policy testing.",
            "status": "in_progress",
            "date": "2025-03-01",
            "proposed_by": _id("lena-johansson"),
            "approved_by": _id("alex-rivera"),
            "jira_ticket": "SEC-345",
            "created_at": "2025-02-20T09:00:00Z",
            "updated_at": "2025-03-22T14:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  INCIDENTS  (8 new incidents)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_INCIDENTS = [
    {
        "entity_id": _id("inc-2024-018"),
        "labels": ["Entity", "Incident", "Postmortem"],
        "properties": {
            "aim_id": _id("inc-2024-018"),
            "name": "INC-2024-018: Cascading REST Failure",
            "title": "Incident: 90-Minute Cascading Failure (The Catalyst for ADR-001)",
            "content": "Severity: P1. Duration: 2024-08-22 10:15 UTC to 2024-08-22 11:45 UTC (90 minutes). Impact: Complete order processing outage. $240K in SLA credits issued. This was THE incident that led to ADR-001 (event-driven migration). Root Cause: Order Service timeout (30s) calling Auth Service for token validation. Auth Service was slow due to a PostgreSQL connection pool exhaustion (max_connections=100, all held by long-running SAML validation queries). Order Service retries (3x with no backoff) amplified load 4x, overwhelming Auth Service completely. Auth Service crash cascaded to 8 downstream services. Detection: PagerDuty multi-service alert storm at 10:17 UTC. Resolution: Manually killed long-running queries, increased connection pool, added circuit breakers as emergency measure. Post-incident: Sarah Chen mandated the event-driven migration within 6 months.",
            "severity": "P1",
            "duration_minutes": 90,
            "date": "2024-08-22",
            "responders": f"{_id('marcus-johnson')},{_id('david-okafor')},{_id('alex-rivera')}",
            "jira_ticket": "PLAT-298",
            "created_at": "2024-08-22T10:15:00Z",
            "updated_at": "2024-09-05T10:00:00Z",
        },
    },
    {
        "entity_id": _id("inc-2025-015"),
        "labels": ["Entity", "Incident", "Postmortem"],
        "properties": {
            "aim_id": _id("inc-2025-015"),
            "name": "INC-2025-015: Payment Double-Charge",
            "title": "Incident: Payment Service Double-Charges Due to Idempotency Bug",
            "content": "Severity: P2. Duration: 2025-02-14 15:30 UTC to 2025-02-14 16:45 UTC (75 minutes). Impact: 847 customers double-charged totaling $42K. All refunds processed automatically within 4 hours. Root Cause: The idempotency key implementation in the Payment Service used a Redis key with 24-hour TTL. During a Redis cluster failover (scheduled maintenance), the idempotency keys were lost. Stripe webhook retries (due to a 502 from the Payment Service during failover) were processed as new charges because the idempotency check returned cache-miss. Detection: Customer support spike + automated reconciliation pipeline detected discrepancy. Resolution: Implemented idempotency keys in PostgreSQL (persistent) in addition to Redis (cache). Stripe idempotency keys now also passed to prevent double-capture at the gateway level.",
            "severity": "P2",
            "duration_minutes": 75,
            "date": "2025-02-14",
            "responders": f"{_id('michael-taylor')},{_id('sofia-martinez')}",
            "jira_ticket": "PAY-234",
            "created_at": "2025-02-14T15:30:00Z",
            "updated_at": "2025-02-20T10:00:00Z",
        },
    },
    {
        "entity_id": _id("inc-2025-019"),
        "labels": ["Entity", "Incident", "Postmortem"],
        "properties": {
            "aim_id": _id("inc-2025-019"),
            "name": "INC-2025-019: CDN Cache Poisoning",
            "title": "Incident: CloudFront Cache Serving Wrong Product Images",
            "content": "Severity: P2. Duration: 2025-03-10 08:00 UTC to 2025-03-10 10:30 UTC (150 minutes). Impact: ~15K product pages displayed incorrect images for 2.5 hours. Customer confusion but no financial impact. Root Cause: A media service deployment changed the image URL hashing algorithm without invalidating the CDN cache. New uploads got hash-colliding URLs with existing cached images. The CloudFront cache key didn't include a version parameter. Detection: Customer reports via support chat (5+ tickets in 30 minutes). Resolution: Full CDN cache invalidation (took 45 minutes to propagate globally). Added version prefix to all image URLs and cache keys.",
            "severity": "P2",
            "duration_minutes": 150,
            "date": "2025-03-10",
            "responders": f"{_id('james-wu')},{_id('david-okafor')}",
            "jira_ticket": "PLAT-445",
            "created_at": "2025-03-10T08:00:00Z",
            "updated_at": "2025-03-14T10:00:00Z",
        },
    },
    {
        "entity_id": _id("inc-2025-022"),
        "labels": ["Entity", "Incident", "Postmortem"],
        "properties": {
            "aim_id": _id("inc-2025-022"),
            "name": "INC-2025-022: Data Lake Staleness",
            "title": "Incident: 12-Hour Data Lake Staleness Due to Airflow Deadlock",
            "content": "Severity: P3. Duration: 2025-03-15 02:00 UTC to 2025-03-15 14:00 UTC (12 hours). Impact: Executive dashboard showed stale data from previous day. No customer impact. Root Cause: Two Airflow DAGs (customer-360 and revenue-daily) competed for the same Delta Lake table lock, causing a deadlock. Airflow's default executor (LocalExecutor) couldn't handle the 200+ concurrent tasks, leading to task queue starvation. Detection: Airflow SLA miss alert at 06:00 UTC. Nina O'Connell investigated during business hours. Resolution: Migrated Airflow to CeleryExecutor with 8 workers. Added table lock timeouts (30s) and retry logic. Restructured DAG dependencies to avoid concurrent writes to the same table.",
            "severity": "P3",
            "duration_minutes": 720,
            "date": "2025-03-15",
            "responders": f"{_id('nina-oconnell')},{_id('yuki-tanaka')}",
            "jira_ticket": "DATA-312",
            "created_at": "2025-03-15T02:00:00Z",
            "updated_at": "2025-03-18T10:00:00Z",
        },
    },
    {
        "entity_id": _id("inc-2025-025"),
        "labels": ["Entity", "Incident", "Postmortem"],
        "properties": {
            "aim_id": _id("inc-2025-025"),
            "name": "INC-2025-025: Mobile App Crash Spike",
            "title": "Incident: 40% Crash Rate on iOS After App Update",
            "content": "Severity: P1. Duration: 2025-03-20 16:00 UTC to 2025-03-20 18:30 UTC (150 minutes). Impact: 40% crash rate on iOS 16 devices after v3.8.0 release. ~80K users affected. App Store rating dropped from 4.7 to 4.2 within 2 hours. Root Cause: A React Native bridge module for offline sync used a deprecated iOS 16 API (NSURLSession background configuration) that was removed in a Xcode 15.4 build. The crash occurred on app launch when the sync module initialized. Android was unaffected. Detection: Sentry alert on crash rate > 5% at 16:05 UTC. App Store Connect crash reports confirmed iOS 16 specificity. Resolution: Emergency hotfix (v3.8.1) deployed via CodePush within 90 minutes, bypassing App Store review. Full fix in v3.8.2 via standard release 2 days later.",
            "severity": "P1",
            "duration_minutes": 150,
            "date": "2025-03-20",
            "responders": f"{_id('sam-patel')},{_id('emma-nakamura')}",
            "jira_ticket": "MOB-312",
            "created_at": "2025-03-20T16:00:00Z",
            "updated_at": "2025-03-24T10:00:00Z",
        },
    },
    {
        "entity_id": _id("inc-2025-028"),
        "labels": ["Entity", "Incident", "Postmortem"],
        "properties": {
            "aim_id": _id("inc-2025-028"),
            "name": "INC-2025-028: Recommendation Service Bias",
            "title": "Incident: Recommendation Engine Popularity Bias After Retraining",
            "content": "Severity: P3. Duration: 2025-03-25 00:00 UTC to 2025-03-26 10:00 UTC (34 hours). Impact: Recommendations showed only top-100 popular items for 34 hours, reducing long-tail product discovery by 80%. Revenue from long-tail products dropped 15% for the day. Root Cause: Weekly model retraining ingested a data pipeline bug that duplicated popular item interactions 10x. The training data validation check (Great Expectations) didn't have a distribution skew test. Model deployed automatically via the ML CI/CD pipeline without human review. Detection: Business metrics alert on long-tail product CTR drop at 10:00 UTC next day. Resolution: Rolled back to previous model version. Added distribution skew tests to training data validation. Implemented human-in-the-loop approval for model deployments with metric drift > 10%.",
            "severity": "P3",
            "duration_minutes": 2040,
            "date": "2025-03-25",
            "responders": f"{_id('aisha-mohammed')},{_id('olivia-chen')}",
            "jira_ticket": "MLINFRA-195",
            "created_at": "2025-03-25T00:00:00Z",
            "updated_at": "2025-03-28T10:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  PROJECTS  (5 new initiatives)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_PROJECTS = [
    {
        "entity_id": _id("proj-mercury"),
        "labels": ["Entity", "Project", "Initiative"],
        "properties": {
            "aim_id": _id("proj-mercury"),
            "name": "Project Mercury",
            "title": "Project Mercury — Mobile App Rewrite",
            "description": "Rewrite the mobile app from React Native Expo to bare React Native with native modules for performance-critical paths (camera, offline sync, push notifications). Target: 60fps animations, 50% reduced battery usage, offline-first architecture with local SQLite. Led by Sam Patel with Maya Kapoor on design. Budget: $120K. Timeline: 6 months starting Q2 2025.",
            "status": "planning",
            "start_date": "2025-04-01",
            "target_date": "2025-09-30",
            "lead": _id("sam-patel"),
            "jira_project": "MOB",
            "slack_channel": "#proj-mercury",
            "created_at": "2025-03-01T09:00:00Z",
            "updated_at": "2025-03-28T10:00:00Z",
        },
    },
    {
        "entity_id": _id("proj-atlas"),
        "labels": ["Entity", "Project", "Initiative"],
        "properties": {
            "aim_id": _id("proj-atlas"),
            "name": "Project Atlas",
            "title": "Project Atlas — Data Mesh Migration",
            "description": "Migrate from centralized data lake to data mesh architecture. Each domain team (orders, payments, users, search) will own their data products with standardized interfaces. Self-serve data platform with automated data quality checks, schema registry, and discovery catalog. Led by Nina O'Connell. Expected to reduce time-to-insight from 2 weeks to 2 days for new analytics use cases.",
            "status": "planning",
            "start_date": "2025-06-01",
            "target_date": "2025-12-31",
            "lead": _id("nina-oconnell"),
            "jira_project": "DATA",
            "slack_channel": "#proj-atlas",
            "created_at": "2025-03-10T09:00:00Z",
            "updated_at": "2025-03-25T09:00:00Z",
        },
    },
    {
        "entity_id": _id("proj-sentinel"),
        "labels": ["Entity", "Project", "Initiative"],
        "properties": {
            "aim_id": _id("proj-sentinel"),
            "name": "Project Sentinel",
            "title": "Project Sentinel — ML Model Governance",
            "description": "Implement comprehensive ML model governance: model registry with approval workflows, automated bias detection, A/B test statistical rigor checks, and model rollback automation. Motivated by INC-2025-028 (recommendation bias incident). Led by Olivia Chen with Aisha Mohammed. Deliverables: model card templates, automated fairness metrics, human-in-the-loop deployment gates for metric drift > 10%.",
            "status": "in_progress",
            "start_date": "2025-03-28",
            "target_date": "2025-06-30",
            "lead": _id("olivia-chen"),
            "jira_project": "MLINFRA",
            "slack_channel": "#proj-sentinel",
            "created_at": "2025-03-28T09:00:00Z",
            "updated_at": "2025-04-01T10:00:00Z",
        },
    },
    {
        "entity_id": _id("proj-growth-v2"),
        "labels": ["Entity", "Project", "Initiative"],
        "properties": {
            "aim_id": _id("proj-growth-v2"),
            "name": "Growth Engine v2",
            "title": "Growth Engine v2 — Personalized Onboarding",
            "description": "Next-generation onboarding experience with ML-driven personalization. Users get a tailored first-run experience based on their signup source, industry, and behavior in the first 5 minutes. A/B tested with 6 variants. Target: improve activation rate from 52% to 65%. Uses the recommendation engine for personalized product suggestions during onboarding. Led by Rachel Green with Maya Kapoor on design.",
            "status": "in_progress",
            "start_date": "2025-02-01",
            "target_date": "2025-05-31",
            "lead": _id("rachel-green"),
            "jira_project": "GROW",
            "slack_channel": "#proj-growth-v2",
            "created_at": "2025-02-01T09:00:00Z",
            "updated_at": "2025-03-21T10:00:00Z",
        },
    },
    {
        "entity_id": _id("proj-soc2"),
        "labels": ["Entity", "Project", "Initiative"],
        "properties": {
            "aim_id": _id("proj-soc2"),
            "name": "SOC 2 Type II Certification",
            "title": "SOC 2 Type II Audit Preparation",
            "description": "Preparing for SOC 2 Type II certification to unlock enterprise sales. Covers Trust Service Criteria: Security, Availability, Processing Integrity, Confidentiality. Evidence collection across all 30+ services: access logs, change management records, incident response documentation, encryption-at-rest/in-transit proof. Working with external auditor (Deloitte). Part of Project Fortress. Target: audit-ready by Q2 2025, certification by Q3 2025.",
            "status": "in_progress",
            "start_date": "2025-01-15",
            "target_date": "2025-06-30",
            "lead": _id("lena-johansson"),
            "jira_project": "SEC",
            "slack_channel": "#proj-soc2",
            "created_at": "2025-01-15T09:00:00Z",
            "updated_at": "2025-03-22T14:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  DOCUMENTS  (15 new docs/runbooks)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_DOCS = [
    {
        "entity_id": _id("doc-k8s-guide"),
        "labels": ["Entity", "Document", "Standard"],
        "properties": {
            "aim_id": _id("doc-k8s-guide"),
            "name": "Kubernetes Best Practices",
            "title": "Nexus Kubernetes Best Practices Guide",
            "content": "Authored by Raj Krishnan. All services must: (1) Define resource requests AND limits (CPU: request=100m-500m, limit=1-2 cores; Memory: request=128Mi-512Mi, limit=512Mi-2Gi), (2) Use readiness and liveness probes (readiness: HTTP GET /ready, liveness: HTTP GET /health, initialDelaySeconds=10), (3) Run as non-root (securityContext.runAsNonRoot=true), (4) Use PodDisruptionBudgets (minAvailable=1 for non-critical, minAvailable=2 for critical), (5) Enable HPA with CPU target 70% (min 2 replicas, max 10 for standard services), (6) Use anti-affinity to spread pods across AZs, (7) Define network policies (deny all by default, allow only required ingress/egress).",
            "author": _id("raj-krishnan"),
            "confluence_url": "https://nexus.atlassian.net/wiki/spaces/PLAT/pages/k8s-best-practices",
            "created_at": "2024-01-15T09:00:00Z",
            "updated_at": "2025-03-10T10:00:00Z",
        },
    },
    {
        "entity_id": _id("doc-data-quality"),
        "labels": ["Entity", "Document", "Standard"],
        "properties": {
            "aim_id": _id("doc-data-quality"),
            "name": "Data Quality Framework",
            "title": "Data Quality Standards & Great Expectations Guide",
            "content": "Authored by Yuki Tanaka. All data pipelines must include quality checks at ingestion and transformation stages. Framework: Great Expectations with 1500+ expectations across 400+ dbt models. Required checks: (1) Schema validation — column types match expected, no unexpected nulls in non-nullable columns, (2) Freshness — data must arrive within SLA (default 2 hours for daily, 15 minutes for real-time), (3) Volume — row count within 2 standard deviations of 30-day average, (4) Uniqueness — primary keys must be unique, (5) Referential integrity — foreign keys must resolve. Distribution skew tests added after INC-2025-028. Failures trigger PagerDuty alerts and block downstream DAGs.",
            "author": _id("yuki-tanaka"),
            "confluence_url": "https://nexus.atlassian.net/wiki/spaces/DATA/pages/data-quality",
            "created_at": "2024-06-01T09:00:00Z",
            "updated_at": "2025-03-28T10:00:00Z",
        },
    },
    {
        "entity_id": _id("doc-security-standards"),
        "labels": ["Entity", "Document", "Standard"],
        "properties": {
            "aim_id": _id("doc-security-standards"),
            "name": "Security Standards",
            "title": "Nexus Security Standards & Compliance Guide",
            "content": "Authored by Lena Johansson. Mandatory for all services: (1) mTLS for all inter-service communication (Istio-managed), (2) Secrets in HashiCorp Vault, never in env vars or config files, (3) All data encrypted at rest (AES-256) and in transit (TLS 1.3), (4) Quarterly penetration testing by external firm, (5) Monthly security training (phishing simulation + OWASP Top 10), (6) Dependency scanning via Snyk on every PR (block on critical/high), (7) SAST scanning on every PR (Snyk Code), (8) Access reviews quarterly — remove inactive accounts within 30 days, (9) Break-glass access requires 2-person approval via Vault, (10) Audit logging for all administrative actions (retained 1 year).",
            "author": _id("lena-johansson"),
            "confluence_url": "https://nexus.atlassian.net/wiki/spaces/SEC/pages/security-standards",
            "created_at": "2025-01-20T09:00:00Z",
            "updated_at": "2025-03-22T14:00:00Z",
        },
    },
    {
        "entity_id": _id("doc-ml-playbook"),
        "labels": ["Entity", "Document", "Runbook"],
        "properties": {
            "aim_id": _id("doc-ml-playbook"),
            "name": "ML Model Deployment Playbook",
            "title": "Machine Learning Model Deployment & Operations Playbook",
            "content": "Authored by Olivia Chen. Model deployment lifecycle: (1) Train in MLflow experiment, log metrics + artifacts, (2) Register in model registry with model card (owner, training data, metrics, bias report), (3) Automated validation: offline metrics must beat current production model by > 1% on primary metric, (4) Shadow deployment: run new model in parallel for 48 hours, compare predictions, (5) Canary deployment: 5% traffic via Feature Store flag, monitor business metrics for 24 hours, (6) Full rollout: 100% traffic, monitor for 1 week, (7) Post-deployment: weekly retraining with fresh data, monthly full retrain with hyperparameter search. Rollback: set feature flag to previous model version (instant, no redeployment needed). Updated after INC-2025-028 to require human approval for metric drift > 10%.",
            "author": _id("olivia-chen"),
            "confluence_url": "https://nexus.atlassian.net/wiki/spaces/MLINFRA/pages/ml-playbook",
            "created_at": "2024-08-01T09:00:00Z",
            "updated_at": "2025-03-28T15:00:00Z",
        },
    },
    {
        "entity_id": _id("doc-mobile-architecture"),
        "labels": ["Entity", "Document", "Standard"],
        "properties": {
            "aim_id": _id("doc-mobile-architecture"),
            "name": "Mobile Architecture Guide",
            "title": "Nexus Mobile App Architecture Guide",
            "content": "Authored by Sam Patel. Architecture: React Native with bare workflow (no Expo). State management: Zustand for local state, React Query for server state with offline persistence. Offline-first: SQLite (via react-native-quick-sqlite) stores last 7 days of data. Background sync via WorkManager (Android) and BGTaskScheduler (iOS). Conflict resolution: last-write-wins for most fields, vector clocks for order status and payment state. Navigation: React Navigation 6 with deep linking (all screens addressable via URL). Push notifications: Firebase Cloud Messaging with priority channels (transactional vs marketing). CodePush for emergency hotfixes (bypasses App Store review). Testing: Jest + React Native Testing Library (unit), Detox (E2E on real devices via BrowserStack).",
            "author": _id("sam-patel"),
            "confluence_url": "https://nexus.atlassian.net/wiki/spaces/MOB/pages/architecture",
            "created_at": "2024-04-01T09:00:00Z",
            "updated_at": "2025-03-25T14:00:00Z",
        },
    },
    {
        "entity_id": _id("doc-design-system"),
        "labels": ["Entity", "Document", "Standard"],
        "properties": {
            "aim_id": _id("doc-design-system"),
            "name": "Nexus Design System",
            "title": "Nexus Design System Documentation",
            "content": "Authored by Maya Kapoor. The Nexus Design System (NDS) provides a unified visual language across web and mobile. Figma library: 200+ design tokens (colors, typography, spacing, shadows), 80+ components (buttons, inputs, cards, modals, navigation). React implementation: @nexus/ui on internal npm, 120+ components with Storybook documentation and visual regression testing via Chromatic. Principles: (1) Consistency — same component looks identical on web and mobile, (2) Accessibility — WCAG 2.1 AA minimum, all interactive elements keyboard-navigable, (3) Performance — components lazy-loaded, CSS-in-JS eliminated in favor of Tailwind CSS utility classes, (4) Dark mode — full support via CSS custom properties, all components tested in both themes. Contribution: PRs to @nexus/ui require design review from Maya + code review from Hannah Lee.",
            "author": _id("maya-kapoor"),
            "confluence_url": "https://nexus.atlassian.net/wiki/spaces/DESIGN/pages/design-system",
            "created_at": "2024-03-01T09:00:00Z",
            "updated_at": "2025-03-26T15:00:00Z",
        },
    },
    {
        "entity_id": _id("doc-runbook-payments"),
        "labels": ["Entity", "Document", "Runbook"],
        "properties": {
            "aim_id": _id("doc-runbook-payments"),
            "name": "Payment Service Runbook",
            "title": "Payment Service Incident Response Runbook",
            "content": "Authored by Michael Taylor. Updated after INC-2025-015 (double-charge incident). Common issues: (1) Stripe API errors: Check Stripe status page first. If 5xx, our retry mechanism handles it (3 retries, exponential backoff). If persistent, escalate to Stripe support with correlation IDs from our logs. (2) Double-charges: Run reconciliation query `SELECT * FROM payments WHERE stripe_charge_id IN (SELECT stripe_charge_id FROM payments GROUP BY stripe_charge_id HAVING COUNT(*) > 1)`. Auto-refund via `POST /admin/refund-duplicates`. (3) Reconciliation mismatches: Check the recon dashboard in Grafana. Mismatches > $100 alert automatically. Common causes: webhook delays (wait 15 min), timezone issues in Stripe reporting API. (4) PCI compliance: Never log full card numbers. Use Stripe's tokenization. If you suspect a data breach, escalate immediately to Lena Johansson (Security) and Alex Rivera (Auth).",
            "author": _id("michael-taylor"),
            "confluence_url": "https://nexus.atlassian.net/wiki/spaces/PAY/pages/runbook",
            "created_at": "2024-06-01T09:00:00Z",
            "updated_at": "2025-02-20T10:00:00Z",
        },
    },
    {
        "entity_id": _id("doc-experimentation"),
        "labels": ["Entity", "Document", "Standard"],
        "properties": {
            "aim_id": _id("doc-experimentation"),
            "name": "Experimentation Guide",
            "title": "A/B Testing & Experimentation Guide",
            "content": "Authored by Rachel Green. All product experiments must follow this process: (1) Hypothesis document: state the expected impact (e.g., 'Personalized onboarding will increase activation by 10%'), success metric, guardrail metrics, sample size calculation (using our internal calculator, minimum 95% confidence, 80% power), (2) Implementation: use LaunchDarkly targeting rules (ADR-009), ensure metric instrumentation is in place before launch, (3) Runtime: minimum 2 weeks, check for novelty effects at week 2 vs week 4, (4) Analysis: use our Bayesian analysis notebook (data-science/notebooks/ab_analysis.ipynb), report effect size with 95% credible interval, (5) Decision: ship if the primary metric improves AND no guardrail metric degrades by > 2%. Currently running 40+ concurrent experiments. Quarterly experiment review meeting (Rachel + Lisa Zhang + Daniel Park).",
            "author": _id("rachel-green"),
            "confluence_url": "https://nexus.atlassian.net/wiki/spaces/GROW/pages/experimentation",
            "created_at": "2024-10-01T09:00:00Z",
            "updated_at": "2025-03-21T10:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  TEAMS  (5 new teams)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_TEAMS = [
    {
        "entity_id": _id("team-backend"),
        "labels": ["Entity", "Team"],
        "properties": {
            "aim_id": _id("team-backend"),
            "name": "Backend Team",
            "title": "Backend Engineering Team",
            "description": "Owns the core business services: Orders, Payments, Inventory, Pricing, User Profiles, and Notifications. 8 engineers including Sofia Martinez, Michael Taylor, Kevin Brown, Anna Kowalski, and Carlos Vega. Responsible for 99.97% uptime across all product services. The team migrated 4 services to event-driven architecture (ADR-001) in Q4 2024. On-call rotation: weekly, secondary backup from Platform team.",
            "slack_channel": "#team-backend",
            "jira_project": "BACK",
            "created_at": "2023-03-01T09:00:00Z",
            "updated_at": "2025-03-18T10:00:00Z",
        },
    },
    {
        "entity_id": _id("team-data"),
        "labels": ["Entity", "Team"],
        "properties": {
            "aim_id": _id("team-data"),
            "name": "Data Engineering Team",
            "title": "Data Engineering Team",
            "description": "Owns the data platform: data lake (S3 + Delta Lake), ETL pipelines (Spark + Airflow), transformation layer (dbt), and data quality framework (Great Expectations). 4 engineers led by Nina O'Connell, including Yuki Tanaka. Processes 2TB/day. Partners with Data Science team on feature engineering and with BI team on analytics. Planning Project Atlas (data mesh migration) for H2 2025.",
            "slack_channel": "#team-data-eng",
            "jira_project": "DATA",
            "created_at": "2024-02-15T09:00:00Z",
            "updated_at": "2025-03-25T09:00:00Z",
        },
    },
    {
        "entity_id": _id("team-data-science"),
        "labels": ["Entity", "Team"],
        "properties": {
            "aim_id": _id("team-data-science"),
            "name": "Data Science Team",
            "title": "Data Science Team",
            "description": "3-person team: Aisha Mohammed (search/recommendations), Chen Wei (fraud detection), plus one open headcount for a computer vision specialist. The team owns ML models, not infrastructure (ML Infra owns the platform). Ships 2-3 model updates per month. Key models: recommendation engine (35% of product discovery), fraud detection ($2M+/month blocked), search re-ranker (NDCG@10: 0.58). Partners closely with ML Infrastructure team on deployment.",
            "slack_channel": "#team-data-science",
            "jira_project": "DS",
            "created_at": "2024-03-01T09:00:00Z",
            "updated_at": "2025-03-28T11:00:00Z",
        },
    },
    {
        "entity_id": _id("team-security"),
        "labels": ["Entity", "Team"],
        "properties": {
            "aim_id": _id("team-security"),
            "name": "Security Team",
            "title": "Security Engineering Team",
            "description": "Owns security across Nexus: mTLS (Istio), ABAC migration (OPA), penetration testing, compliance (SOC 2), and security training. 3 engineers led by Lena Johansson, with Alex Rivera as the cross-functional sponsor from Platform. Running Project Fortress (zero trust) and SOC 2 Type II certification. Monthly security training has reduced phishing click rate from 12% to 3%.",
            "slack_channel": "#team-security",
            "jira_project": "SEC",
            "created_at": "2024-09-01T09:00:00Z",
            "updated_at": "2025-03-22T14:00:00Z",
        },
    },
    {
        "entity_id": _id("team-mobile"),
        "labels": ["Entity", "Team"],
        "properties": {
            "aim_id": _id("team-mobile"),
            "name": "Mobile Team",
            "title": "Mobile Engineering Team",
            "description": "Owns the Nexus mobile app (React Native, iOS + Android) and Mobile BFF (GraphQL). 3 engineers led by Sam Patel. The app has 500K+ MAU, 4.7 star rating, and supports offline-first with background sync. Planning Project Mercury (mobile rewrite) for Q2-Q3 2025. Uses CodePush for emergency updates. Bi-weekly release cadence with Detox E2E tests on BrowserStack.",
            "slack_channel": "#team-mobile",
            "jira_project": "MOB",
            "created_at": "2024-02-01T09:00:00Z",
            "updated_at": "2025-03-25T14:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  COMPONENTS  (15 internal libraries/components)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_COMPONENTS = [
    {
        "entity_id": _id("comp-nexus-ui"),
        "labels": ["Entity", "Component", "Library"],
        "properties": {
            "aim_id": _id("comp-nexus-ui"),
            "name": "@nexus/ui",
            "title": "@nexus/ui — Design System Component Library",
            "description": "Internal React component library with 120+ components published on internal npm registry. Built with TypeScript, Tailwind CSS, and Radix UI primitives. Storybook documentation with visual regression testing via Chromatic. Components include: buttons, inputs, cards, modals, tables, navigation, charts, and layout primitives. Used by both web app and admin dashboard. Maintained by Hannah Lee with design oversight from Maya Kapoor.",
            "tech_stack": "React, TypeScript, Tailwind CSS, Radix UI",
            "owner": _id("hannah-lee"),
            "github_repo": "nexus/nexus-ui",
            "created_at": "2023-08-01T09:00:00Z",
            "updated_at": "2025-03-24T09:00:00Z",
        },
    },
    {
        "entity_id": _id("comp-kafka-consumer"),
        "labels": ["Entity", "Component", "Library"],
        "properties": {
            "aim_id": _id("comp-kafka-consumer"),
            "name": "nexus-kafka-consumer",
            "title": "nexus-kafka-consumer — Internal Kafka Consumer Framework",
            "description": "Custom Kafka consumer framework that reduces boilerplate by 60%. Built by Marcus Johnson. Features: automatic dead-letter queue routing for deserialization failures, idempotency key tracking, consumer lag metrics exported to Prometheus, graceful shutdown with at-least-once delivery guarantee, and configurable retry policies. Used by all 12 event-driven services. Updated after INC-2025-003 to add schema compatibility validation on startup.",
            "tech_stack": "Python, confluent-kafka, Prometheus",
            "owner": _id("marcus-johnson"),
            "github_repo": "nexus/kafka-consumer-framework",
            "created_at": "2024-10-01T09:00:00Z",
            "updated_at": "2025-03-12T10:00:00Z",
        },
    },
    {
        "entity_id": _id("comp-terraform-modules"),
        "labels": ["Entity", "Component", "Infrastructure"],
        "properties": {
            "aim_id": _id("comp-terraform-modules"),
            "name": "nexus-terraform-modules",
            "title": "Nexus Terraform Module Library",
            "description": "87 reusable Terraform modules for AWS infrastructure provisioning. Covers: EKS clusters, RDS instances, ElastiCache, S3 buckets, CloudFront distributions, IAM roles, VPC networking, and security groups. All modules versioned with semantic versioning. 100% drift-free via weekly drift detection in CI. Maintained by David Okafor and Raj Krishnan. Being extended for multi-region support (Project Horizon).",
            "tech_stack": "Terraform, AWS",
            "owner": _id("david-okafor"),
            "github_repo": "nexus/terraform-modules",
            "created_at": "2023-06-01T09:00:00Z",
            "updated_at": "2025-03-29T08:00:00Z",
        },
    },
    {
        "entity_id": _id("comp-tilt-dev"),
        "labels": ["Entity", "Component", "Infrastructure"],
        "properties": {
            "aim_id": _id("comp-tilt-dev"),
            "name": "nexus-local-dev",
            "title": "Tilt-Based Local Development Environment",
            "description": "Local development environment powered by Tilt that spins up all 30+ services, databases, and message brokers in 3 minutes. Uses Docker Compose under the hood with Tilt for hot-reload and log aggregation. Includes seed data for all services. Built by Tom Andersen. Developer satisfaction NPS improved from +22 to +48 after launch. Supports Apple Silicon (M1/M2/M3) natively.",
            "tech_stack": "Tilt, Docker Compose, Make",
            "owner": _id("tom-andersen"),
            "github_repo": "nexus/local-dev",
            "created_at": "2024-06-01T09:00:00Z",
            "updated_at": "2025-03-15T16:00:00Z",
        },
    },
    {
        "entity_id": _id("comp-slo-framework"),
        "labels": ["Entity", "Component", "Infrastructure"],
        "properties": {
            "aim_id": _id("comp-slo-framework"),
            "name": "nexus-slo-framework",
            "title": "SLO Framework — Error Budget Tracking",
            "description": "Custom SLO framework built on Prometheus that tracks error budget burn rates across all services. Defines SLOs in YAML (availability, latency percentiles, error rate). Grafana dashboards show burn rate with multi-window alerting (5min, 30min, 6hr windows). When error budget is < 20% remaining, deploys are auto-blocked for the service. Built by Diego Reyes. Currently tracking 45 SLOs across 30+ services.",
            "tech_stack": "Prometheus, Grafana, YAML, Python",
            "owner": _id("diego-reyes"),
            "github_repo": "nexus/slo-framework",
            "created_at": "2024-10-01T09:00:00Z",
            "updated_at": "2025-03-27T08:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
#  WAVE 2 — additional people, services, incidents, docs, components to hit 200+
# ═══════════════════════════════════════════════════════════════════════════════

WAVE2_PEOPLE = [
    {"entity_id": _id("ben-carter"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("ben-carter"), "name": "Ben Carter", "title": "Engineer — Platform", "description": "Platform Engineer at Nexus. Maintains ArgoCD and GitOps workflows. Built the automated canary rollback system that prevented 12 bad deployments in Q1 2025.", "department": "Engineering", "location": "Portland", "expertise": "argocd, gitops, kubernetes", "created_at": "2024-09-01T09:00:00Z", "updated_at": "2025-03-15T10:00:00Z"}},
    {"entity_id": _id("grace-kim"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("grace-kim"), "name": "Grace Kim", "title": "Senior Engineer — Backend", "description": "Senior Backend Engineer at Nexus. Owns the Shipping Service integrating with 4 carriers (FedEx, UPS, USPS, DHL). Built the rate shopping algorithm that saves $200K/year in shipping costs.", "department": "Engineering", "location": "Los Angeles", "expertise": "logistics, APIs, golang, microservices", "created_at": "2024-01-15T09:00:00Z", "updated_at": "2025-03-22T11:00:00Z"}},
    {"entity_id": _id("omar-hassan"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("omar-hassan"), "name": "Omar Hassan", "title": "Engineer — Frontend", "description": "Frontend Engineer at Nexus. Built the real-time chat widget used by 50K customers/day for support. Implemented WebSocket connection pooling reducing server load by 40%.", "department": "Engineering", "location": "Cairo", "expertise": "websockets, react, real-time systems", "created_at": "2024-07-15T09:00:00Z", "updated_at": "2025-03-20T12:00:00Z"}},
    {"entity_id": _id("elena-volkov"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("elena-volkov"), "name": "Elena Volkov", "title": "Senior Engineer — Data", "description": "Senior Data Engineer at Nexus. Built the real-time CDC pipeline from PostgreSQL to Kafka using Debezium. Processes 500M change events/day with exactly-once delivery guarantees.", "department": "Data", "location": "Berlin", "expertise": "debezium, CDC, kafka connect, postgresql", "created_at": "2024-05-01T09:00:00Z", "updated_at": "2025-03-25T14:00:00Z"}},
    {"entity_id": _id("jason-wright"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("jason-wright"), "name": "Jason Wright", "title": "Engineer — Security", "description": "Security Engineer at Nexus. Runs the bug bounty program (HackerOne, 45 valid reports in 2024). Performs monthly penetration testing and maintains the SAST/DAST pipeline.", "department": "Security", "location": "Austin", "expertise": "penetration testing, SAST, DAST, bug bounty", "created_at": "2025-01-01T09:00:00Z", "updated_at": "2025-03-22T10:00:00Z"}},
    {"entity_id": _id("lisa-nguyen"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("lisa-nguyen"), "name": "Lisa Nguyen", "title": "Engineer — ML Infrastructure", "description": "ML Infrastructure Engineer at Nexus. Maintains the MLflow experiment tracking platform (2000+ experiments, 15K runs). Built the automated hyperparameter tuning service using Optuna.", "department": "Engineering", "location": "San Jose", "expertise": "MLflow, experiment tracking, Optuna, python", "created_at": "2024-08-15T09:00:00Z", "updated_at": "2025-03-28T09:00:00Z"}},
    {"entity_id": _id("ahmed-ibrahim"), "labels": ["Entity", "Person", "SRE"], "properties": {"aim_id": _id("ahmed-ibrahim"), "name": "Ahmed Ibrahim", "title": "SRE", "description": "Site Reliability Engineer at Nexus. Built the chaos engineering platform (Chaos Monkey + Litmus) that runs weekly failure injection tests. Reduced MTTR by 30% through automated runbook execution.", "department": "Engineering", "location": "Dubai", "expertise": "chaos engineering, litmus, automation, SRE", "created_at": "2024-10-01T09:00:00Z", "updated_at": "2025-03-27T11:00:00Z"}},
    {"entity_id": _id("sarah-murphy"), "labels": ["Entity", "Person", "ProductManager"], "properties": {"aim_id": _id("sarah-murphy"), "name": "Sarah Murphy", "title": "Product Manager — Commerce", "description": "PM for the Commerce domain at Nexus (Orders, Payments, Inventory). Led the checkout redesign that improved conversion rate by 8%. Manages the marketplace expansion roadmap.", "department": "Product", "location": "Dublin", "expertise": "e-commerce, checkout optimization, payments", "created_at": "2024-04-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("wei-zhang"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("wei-zhang"), "name": "Wei Zhang", "title": "Senior Engineer — Backend", "description": "Senior Backend Engineer at Nexus. Owns the Catalog Service managing 2M+ products with faceted search, category taxonomy (3 levels, 500+ categories), and bulk import API. Built the product data syndication pipeline.", "department": "Engineering", "location": "Shanghai", "expertise": "catalog systems, elasticsearch, data modeling", "created_at": "2024-02-15T09:00:00Z", "updated_at": "2025-03-18T16:00:00Z"}},
    {"entity_id": _id("julia-santos"), "labels": ["Entity", "Person", "Designer"], "properties": {"aim_id": _id("julia-santos"), "name": "Julia Santos", "title": "Product Designer", "description": "Product Designer at Nexus. Designed the checkout flow optimization (8% conversion lift). Created the mobile onboarding experience for Growth v2. Expert in motion design and micro-interactions.", "department": "Design", "location": "Sao Paulo", "expertise": "UX design, motion design, mobile UX, prototyping", "created_at": "2024-06-01T09:00:00Z", "updated_at": "2025-03-21T15:00:00Z"}},
    {"entity_id": _id("nate-wilson"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("nate-wilson"), "name": "Nate Wilson", "title": "Engineer — Backend", "description": "Backend Engineer at Nexus. Owns the Reviews & Ratings Service (8M reviews, 150K new reviews/month). Implemented content moderation pipeline using Claude API for toxic content detection (99.2% accuracy).", "department": "Engineering", "location": "Atlanta", "expertise": "content moderation, APIs, python, NLP", "created_at": "2024-09-15T09:00:00Z", "updated_at": "2025-03-19T11:00:00Z"}},
    {"entity_id": _id("kate-morrison"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("kate-morrison"), "name": "Kate Morrison", "title": "Senior Engineer — Frontend", "description": "Senior Frontend Engineer at Nexus. Built the admin dashboard (internal tool) used by 200+ ops staff. Implemented real-time order tracking map with Mapbox GL. Expert in data visualization with D3.js.", "department": "Engineering", "location": "Vancouver", "expertise": "react, data visualization, d3.js, mapbox", "created_at": "2024-03-15T09:00:00Z", "updated_at": "2025-03-24T10:00:00Z"}},
    {"entity_id": _id("eric-johansson"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("eric-johansson"), "name": "Eric Johansson", "title": "Engineer — Platform", "description": "Platform Engineer at Nexus. Maintains the secret management system (HashiCorp Vault). Built the automated certificate rotation system that rotates 500+ TLS certificates every 90 days with zero downtime.", "department": "Engineering", "location": "Stockholm", "expertise": "vault, PKI, certificate management, security", "created_at": "2024-11-01T09:00:00Z", "updated_at": "2025-03-20T09:00:00Z"}},
    {"entity_id": _id("priya-sharma"), "labels": ["Entity", "Person", "DataScientist"], "properties": {"aim_id": _id("priya-sharma"), "name": "Priya Sharma", "title": "Data Scientist — NLP", "description": "NLP Data Scientist at Nexus. Building the conversational search system for Aurora Phase 3. Fine-tuned a Claude-based query understanding model that classifies intent with 94% accuracy across 12 query types.", "department": "Data Science", "location": "Bangalore", "expertise": "NLP, LLMs, query understanding, RAG", "created_at": "2025-01-15T09:00:00Z", "updated_at": "2025-03-28T14:00:00Z"}},
    {"entity_id": _id("marco-rossi"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("marco-rossi"), "name": "Marco Rossi", "title": "Engineer — Backend", "description": "Backend Engineer at Nexus. Owns the Reporting Service that generates 50K+ reports daily (PDF, CSV, Excel). Built the async report generation pipeline using Celery + S3 with pre-signed URL delivery.", "department": "Engineering", "location": "Milan", "expertise": "reporting, PDF generation, celery, python", "created_at": "2024-08-01T09:00:00Z", "updated_at": "2025-03-17T12:00:00Z"}},
    {"entity_id": _id("tanya-okonkwo"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("tanya-okonkwo"), "name": "Tanya Okonkwo", "title": "Engineer — Mobile", "description": "Mobile Engineer at Nexus. Built the offline-capable product catalog browser for the mobile app. Implemented image lazy loading and prefetching that reduced mobile data usage by 35%.", "department": "Engineering", "location": "Lagos", "expertise": "react native, mobile performance, offline-first", "created_at": "2024-10-01T09:00:00Z", "updated_at": "2025-03-25T10:00:00Z"}},
    {"entity_id": _id("alex-petrov"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("alex-petrov"), "name": "Alex Petrov", "title": "Senior Engineer — Data", "description": "Senior Data Engineer at Nexus. Built the real-time analytics pipeline powering the executive dashboard (5-second data freshness). Maintains the Presto cluster (200 daily users, 5K queries/day).", "department": "Data", "location": "Moscow", "expertise": "presto, real-time analytics, kafka streams", "created_at": "2024-06-15T09:00:00Z", "updated_at": "2025-03-22T11:00:00Z"}},
    {"entity_id": _id("mia-chen"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("mia-chen"), "name": "Mia Chen", "title": "Engineer — Frontend", "description": "Frontend Engineer at Nexus. Implemented i18n support for 12 languages across the web app. Built the translation management pipeline with Crowdin integration and automated PR creation for new translations.", "department": "Engineering", "location": "Taipei", "expertise": "i18n, react, next.js, localization", "created_at": "2024-11-15T09:00:00Z", "updated_at": "2025-03-23T09:00:00Z"}},
    {"entity_id": _id("david-kim"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("david-kim"), "name": "David Kim", "title": "Engineer — Backend", "description": "Backend Engineer at Nexus. Owns the Webhook Service that delivers 5M+ webhooks/day to merchant integrations. Implemented the retry system with dead-letter queue and webhook debugging dashboard.", "department": "Engineering", "location": "Seoul", "expertise": "webhooks, event delivery, reliability, golang", "created_at": "2024-07-01T09:00:00Z", "updated_at": "2025-03-19T14:00:00Z"}},
    {"entity_id": _id("emma-fischer"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("emma-fischer"), "name": "Emma Fischer", "title": "QA Lead", "description": "QA Lead at Nexus. Built the E2E test framework (Playwright, 800+ tests, 15-minute full suite). Maintains the performance test suite (k6, 50K virtual users). Reduced production bug escape rate from 8% to 2%.", "department": "Engineering", "location": "Munich", "expertise": "QA, playwright, k6, test automation", "created_at": "2024-04-15T09:00:00Z", "updated_at": "2025-03-26T10:00:00Z"}},
]

WAVE2_SERVICES = [
    {"entity_id": _id("svc-shipping"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-shipping"), "name": "Shipping Service", "title": "Shipping & Logistics Service", "description": "Integrates with 4 carriers (FedEx, UPS, USPS, DHL) for rate shopping, label generation, and tracking. Rate shopping algorithm compares prices across carriers in real-time saving $200K/year. Processes 50K shipments/day. Real-time tracking updates via webhook callbacks from carriers, published to Kafka for customer notification.", "tech_stack": "Go, PostgreSQL, Kafka", "status": "production", "tier": "high", "owner": _id("grace-kim"), "slack_channel": "#svc-shipping", "jira_project": "SHIP", "github_repo": "nexus/shipping-service", "created_at": "2023-06-01T09:00:00Z", "updated_at": "2025-03-22T11:00:00Z"}},
    {"entity_id": _id("svc-catalog"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-catalog"), "name": "Catalog Service", "title": "Product Catalog Service", "description": "Manages 2M+ products with faceted search, category taxonomy (3 levels, 500+ categories), and bulk import API. Elasticsearch for search with custom analyzers for product-specific tokenization. Supports multi-tenant catalog isolation. Product data syndication to 3 marketplace channels.", "tech_stack": "Python, FastAPI, Elasticsearch, PostgreSQL", "status": "production", "tier": "high", "owner": _id("wei-zhang"), "slack_channel": "#svc-catalog", "jira_project": "CAT", "github_repo": "nexus/catalog-service", "created_at": "2023-05-15T09:00:00Z", "updated_at": "2025-03-18T16:00:00Z"}},
    {"entity_id": _id("svc-reviews"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-reviews"), "name": "Reviews Service", "title": "Reviews & Ratings Service", "description": "Manages 8M reviews with 150K new reviews/month. Content moderation pipeline uses Claude API for toxic content detection (99.2% accuracy). Aggregated ratings computed asynchronously via Kafka events. Supports photo reviews with moderation. Review helpfulness ranking uses a Wilson score interval.", "tech_stack": "Python, FastAPI, PostgreSQL, Claude API", "status": "production", "tier": "medium", "owner": _id("nate-wilson"), "slack_channel": "#svc-reviews", "jira_project": "REV", "github_repo": "nexus/reviews-service", "created_at": "2024-01-01T09:00:00Z", "updated_at": "2025-03-19T11:00:00Z"}},
    {"entity_id": _id("svc-admin"), "labels": ["Entity", "Service", "Internal"], "properties": {"aim_id": _id("svc-admin"), "name": "Admin Dashboard", "title": "Internal Admin Dashboard", "description": "Next.js internal tool used by 200+ operations staff. Features: order management, customer support tools, real-time order tracking map (Mapbox GL), content moderation queue, inventory management, and reporting. Real-time updates via WebSocket. Access controlled by RBAC with 5 role levels.", "tech_stack": "Next.js, React, Mapbox GL, WebSocket", "status": "production", "tier": "medium", "owner": _id("kate-morrison"), "slack_channel": "#svc-admin", "jira_project": "ADMIN", "github_repo": "nexus/admin-dashboard", "created_at": "2023-09-01T09:00:00Z", "updated_at": "2025-03-24T10:00:00Z"}},
    {"entity_id": _id("svc-webhooks"), "labels": ["Entity", "Service", "Infrastructure"], "properties": {"aim_id": _id("svc-webhooks"), "name": "Webhook Service", "title": "Outbound Webhook Delivery Service", "description": "Delivers 5M+ webhooks/day to merchant integrations. Guaranteed at-least-once delivery with exponential backoff (5 retries over 24 hours). Dead-letter queue for permanently failed deliveries. HMAC signature verification for security. Debugging dashboard shows delivery status, response codes, and retry history per endpoint.", "tech_stack": "Go, Redis, PostgreSQL, Kafka", "status": "production", "tier": "high", "owner": _id("david-kim"), "slack_channel": "#svc-webhooks", "jira_project": "PLAT", "github_repo": "nexus/webhook-service", "created_at": "2024-03-01T09:00:00Z", "updated_at": "2025-03-19T14:00:00Z"}},
    {"entity_id": _id("svc-reporting"), "labels": ["Entity", "Service", "Internal"], "properties": {"aim_id": _id("svc-reporting"), "name": "Reporting Service", "title": "Report Generation Service", "description": "Generates 50K+ reports daily (PDF, CSV, Excel). Async pipeline using Celery workers + S3 storage with pre-signed URL delivery via email. Supports scheduled reports (daily/weekly/monthly). Template engine with 30+ report templates. Powers the executive dashboard exports and merchant settlement reports.", "tech_stack": "Python, Celery, Redis, S3, WeasyPrint", "status": "production", "tier": "medium", "owner": _id("marco-rossi"), "slack_channel": "#svc-reporting", "jira_project": "RPT", "github_repo": "nexus/reporting-service", "created_at": "2024-01-15T09:00:00Z", "updated_at": "2025-03-17T12:00:00Z"}},
    {"entity_id": _id("svc-chat"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-chat"), "name": "Live Chat Service", "title": "Customer Support Live Chat", "description": "Real-time chat service used by 50K customers/day. WebSocket-based with connection pooling. Supports file attachments, typing indicators, and read receipts. AI-powered auto-responses handle 40% of queries without human agent. Integrates with Zendesk for ticket escalation.", "tech_stack": "Node.js, WebSocket, Redis Pub/Sub, Zendesk API", "status": "production", "tier": "high", "owner": _id("omar-hassan"), "slack_channel": "#svc-chat", "jira_project": "SUP", "github_repo": "nexus/chat-service", "created_at": "2024-07-15T09:00:00Z", "updated_at": "2025-03-20T12:00:00Z"}},
    {"entity_id": _id("svc-vault"), "labels": ["Entity", "Service", "Security"], "properties": {"aim_id": _id("svc-vault"), "name": "Secret Manager", "title": "HashiCorp Vault — Secret Management", "description": "HashiCorp Vault manages all secrets, API keys, database credentials, and TLS certificates. 500+ TLS certs rotated every 90 days automatically. Dynamic database credentials with 1-hour TTL. PKI backend for mTLS certificate issuance. Break-glass access requires 2-person approval.", "tech_stack": "HashiCorp Vault, Consul, Terraform", "status": "production", "tier": "critical", "owner": _id("eric-johansson"), "slack_channel": "#svc-vault", "jira_project": "SEC", "github_repo": "nexus/vault-config", "created_at": "2024-01-01T09:00:00Z", "updated_at": "2025-03-20T09:00:00Z"}},
    {"entity_id": _id("svc-analytics"), "labels": ["Entity", "Service", "Data"], "properties": {"aim_id": _id("svc-analytics"), "name": "Analytics Service", "title": "Real-Time Analytics & Event Tracking", "description": "Collects and processes user behavior events (page views, clicks, conversions). 100M events/day ingested via Kafka, processed through Kafka Streams for real-time aggregations. Powers the product analytics dashboard (Mixpanel-like, built in-house). Supports funnel analysis, cohort analysis, and retention curves.", "tech_stack": "Kafka Streams, ClickHouse, Python", "status": "production", "tier": "high", "owner": _id("alex-petrov"), "slack_channel": "#svc-analytics", "jira_project": "DATA", "github_repo": "nexus/analytics-service", "created_at": "2024-06-15T09:00:00Z", "updated_at": "2025-03-22T11:00:00Z"}},
]

WAVE2_INCIDENTS = [
    {"entity_id": _id("inc-2024-022"), "labels": ["Entity", "Incident", "Postmortem"], "properties": {"aim_id": _id("inc-2024-022"), "name": "INC-2024-022: DNS Failover Delay", "title": "Incident: 20-Minute DNS Propagation Delay During Failover", "content": "Severity: P2. Duration: 2024-11-15 06:00 UTC to 2024-11-15 06:20 UTC (20 minutes). Impact: EU customers experienced 20-minute connectivity issues when Route53 health check failed to detect an ELB outage. Root Cause: Route53 health check interval was 30 seconds with 3 failures required = 90 seconds detection + 300s TTL propagation. Resolution: Reduced TTL to 60s, health check interval to 10s, and failure threshold to 2. Added latency-based routing as secondary strategy.", "severity": "P2", "duration_minutes": 20, "date": "2024-11-15", "responders": f"{_id('raj-krishnan')},{_id('david-okafor')}", "jira_ticket": "PLAT-356", "created_at": "2024-11-15T06:00:00Z", "updated_at": "2024-11-20T10:00:00Z"}},
    {"entity_id": _id("inc-2025-030"), "labels": ["Entity", "Incident", "Postmortem"], "properties": {"aim_id": _id("inc-2025-030"), "name": "INC-2025-030: Shipping Label API Outage", "title": "Incident: FedEx API Outage Blocked Label Generation", "content": "Severity: P2. Duration: 2025-03-28 14:00 UTC to 2025-03-28 16:30 UTC (150 minutes). Impact: 3K shipments delayed because FedEx label generation API returned 503. UPS and USPS unaffected but couldn't absorb all FedEx-designated shipments due to carrier-specific packaging requirements. Resolution: Implemented multi-carrier fallback with automatic rerouting when primary carrier API is unavailable. Added carrier health checks to pre-flight validation.", "severity": "P2", "duration_minutes": 150, "date": "2025-03-28", "responders": f"{_id('grace-kim')},{_id('sofia-martinez')}", "jira_ticket": "SHIP-089", "created_at": "2025-03-28T14:00:00Z", "updated_at": "2025-04-01T10:00:00Z"}},
    {"entity_id": _id("inc-2025-032"), "labels": ["Entity", "Incident", "Postmortem"], "properties": {"aim_id": _id("inc-2025-032"), "name": "INC-2025-032: Vault Seal Event", "title": "Incident: HashiCorp Vault Sealed During Maintenance", "content": "Severity: P1. Duration: 2025-04-02 03:00 UTC to 2025-04-02 03:25 UTC (25 minutes). Impact: All services failed to rotate credentials. 3 services with expiring DB credentials lost database connectivity for 10 minutes. Root Cause: Vault auto-unseal via AWS KMS failed because the KMS key had been scheduled for deletion as part of a key rotation. The new KMS key wasn't configured in Vault. Resolution: Manually unsealed with Shamir keys. Updated KMS key rotation procedure to include Vault seal configuration.", "severity": "P1", "duration_minutes": 25, "date": "2025-04-02", "responders": f"{_id('eric-johansson')},{_id('lena-johansson')},{_id('david-okafor')}", "jira_ticket": "SEC-412", "created_at": "2025-04-02T03:00:00Z", "updated_at": "2025-04-05T10:00:00Z"}},
    {"entity_id": _id("inc-2025-035"), "labels": ["Entity", "Incident", "Postmortem"], "properties": {"aim_id": _id("inc-2025-035"), "name": "INC-2025-035: Catalog Search Degradation", "title": "Incident: Elasticsearch Cluster Yellow Status", "content": "Severity: P3. Duration: 2025-04-05 08:00 UTC to 2025-04-05 12:00 UTC (4 hours). Impact: Catalog search latency increased 3x (p95 from 80ms to 240ms). No outage but degraded UX. Root Cause: One data node ran out of disk space (95% full), triggering shard relocation. Elasticsearch entered yellow status with unassigned replica shards. Resolution: Added disk space, added monitoring alert at 80% disk usage, implemented ILM policy for index lifecycle management.", "severity": "P3", "duration_minutes": 240, "date": "2025-04-05", "responders": f"{_id('wei-zhang')},{_id('diego-reyes')}", "jira_ticket": "CAT-178", "created_at": "2025-04-05T08:00:00Z", "updated_at": "2025-04-07T10:00:00Z"}},
]

WAVE2_DOCS = [
    {"entity_id": _id("doc-shipping-runbook"), "labels": ["Entity", "Document", "Runbook"], "properties": {"aim_id": _id("doc-shipping-runbook"), "name": "Shipping Service Runbook", "title": "Shipping Service Operational Runbook", "content": "Authored by Grace Kim. Common issues: (1) Carrier API timeout: Check carrier status pages. Fallback to secondary carrier if primary is down > 5 min. (2) Label generation failures: Check the DLQ topic shipping-labels.dlq. Most common cause: invalid address data. (3) Rate shopping errors: Redis cache miss — verify Redis connection and pricing cache TTL. (4) Tracking webhook delays: Check the webhook ingestion Kafka consumer lag.", "author": _id("grace-kim"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/SHIP/pages/runbook", "created_at": "2024-08-01T09:00:00Z", "updated_at": "2025-04-01T10:00:00Z"}},
    {"entity_id": _id("doc-chaos-playbook"), "labels": ["Entity", "Document", "Runbook"], "properties": {"aim_id": _id("doc-chaos-playbook"), "name": "Chaos Engineering Playbook", "title": "Chaos Engineering Playbook & Drill Schedule", "content": "Authored by Ahmed Ibrahim. Monthly chaos drills: Week 1 — Pod kill (random pod termination in each service), Week 2 — Network partition (Istio fault injection between service pairs), Week 3 — Database failover (PostgreSQL primary/replica switchover), Week 4 — Full AZ failure simulation. All drills run during business hours with the SRE team monitoring. Results logged in the chaos-results Confluence space. Automated blast radius limiting: drills auto-abort if error rate > 5% or p99 > 5x baseline.", "author": _id("ahmed-ibrahim"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/SRE/pages/chaos-playbook", "created_at": "2024-12-01T09:00:00Z", "updated_at": "2025-03-27T11:00:00Z"}},
    {"entity_id": _id("doc-testing-standards"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-testing-standards"), "name": "Testing Standards", "title": "Nexus Testing Standards & Quality Guide", "content": "Authored by Emma Fischer. Required test coverage: 85% line coverage minimum (enforced in CI). Test pyramid: 70% unit, 20% integration, 10% E2E. E2E suite: 800+ Playwright tests, 15-minute full run, parallelized across 8 workers. Performance testing: k6 load tests before every major release (50K VU, 15-minute sustained). Visual regression: Chromatic for @nexus/ui (catches CSS regressions). Contract testing: Pact for service-to-service API contracts. Flaky test policy: 3 consecutive flakes = test quarantined, owner notified.", "author": _id("emma-fischer"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/QA/pages/testing-standards", "created_at": "2024-06-01T09:00:00Z", "updated_at": "2025-03-26T10:00:00Z"}},
    {"entity_id": _id("doc-vault-runbook"), "labels": ["Entity", "Document", "Runbook"], "properties": {"aim_id": _id("doc-vault-runbook"), "name": "Vault Operations Runbook", "title": "HashiCorp Vault Operations Runbook", "content": "Authored by Eric Johansson. Updated after INC-2025-032 (Vault seal event). Emergency unseal: 3 of 5 Shamir key holders must provide their keys. Key holders: Sarah Chen, Alex Rivera, David Okafor, Lena Johansson, Eric Johansson. Seal recovery: (1) Check Vault status: `vault status`, (2) If sealed, initiate unseal: `vault operator unseal`, (3) If auto-unseal failed, check AWS KMS key status in the AWS console. Secret rotation: All database credentials rotate every 1 hour via dynamic secrets. TLS certificates rotate every 90 days via PKI backend. Break-glass: `vault write auth/approle/login` with emergency role — requires 2-person approval.", "author": _id("eric-johansson"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/SEC/pages/vault-runbook", "created_at": "2024-06-01T09:00:00Z", "updated_at": "2025-04-05T10:00:00Z"}},
    {"entity_id": _id("doc-analytics-guide"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-analytics-guide"), "name": "Analytics Implementation Guide", "title": "Event Tracking & Analytics Implementation Guide", "content": "Authored by Alex Petrov. All product events must follow the Nexus Event Schema v2: {event_type, user_id, session_id, timestamp, properties, context}. Required events: page_view, button_click, form_submit, search_query, product_view, add_to_cart, checkout_start, purchase_complete. Custom events: use snake_case naming, max 50 properties per event. Data retention: raw events 90 days in ClickHouse, aggregated metrics 2 years. Privacy: PII fields (email, IP) hashed before storage. GDPR deletion: events anonymized within 30 days of deletion request.", "author": _id("alex-petrov"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/DATA/pages/analytics-guide", "created_at": "2024-09-01T09:00:00Z", "updated_at": "2025-03-22T11:00:00Z"}},
    {"entity_id": _id("doc-graphql-guide"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-graphql-guide"), "name": "GraphQL Best Practices", "title": "GraphQL API Design & Best Practices", "content": "Authored by Sam Patel. Guidelines for the Mobile BFF GraphQL API: (1) Query depth limit: 5 levels max (enforced by graphql-depth-limit), (2) Cost analysis: queries scored by field complexity, max 1000 points per query, (3) Persisted queries: all production queries must be persisted (automatic persisted queries via Apollo), (4) N+1 prevention: DataLoader required for all list field resolvers, (5) Schema governance: all schema changes reviewed by Sam Patel, breaking changes require 2-week deprecation period, (6) Error handling: use union types for expected errors (e.g., OrderResult = Order | OrderNotFound | InsufficientStock).", "author": _id("sam-patel"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/MOB/pages/graphql-guide", "created_at": "2024-04-01T09:00:00Z", "updated_at": "2025-03-25T14:00:00Z"}},
    {"entity_id": _id("doc-i18n-guide"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-i18n-guide"), "name": "Internationalization Guide", "title": "i18n & Localization Guide", "content": "Authored by Mia Chen. 12 supported languages: en, es, fr, de, ja, ko, zh-CN, zh-TW, pt-BR, it, nl, ar. Translation workflow: (1) Engineers add strings in en using next-intl, (2) Crowdin syncs new strings automatically via GitHub integration, (3) Professional translators complete translations within 5 business days, (4) Crowdin creates PR with translations, reviewed by Mia Chen, (5) Merged translations auto-deployed. RTL support for Arabic via CSS logical properties. Date/number formatting via Intl API. Currency formatting: always use user's locale, convert amounts via Pricing Service FX rates (updated hourly).", "author": _id("mia-chen"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/FE/pages/i18n-guide", "created_at": "2024-12-01T09:00:00Z", "updated_at": "2025-03-23T09:00:00Z"}},
]

WAVE2_COMPONENTS = [
    {"entity_id": _id("comp-chaos-platform"), "labels": ["Entity", "Component", "Infrastructure"], "properties": {"aim_id": _id("comp-chaos-platform"), "name": "nexus-chaos", "title": "Chaos Engineering Platform", "description": "Automated chaos engineering platform built on Litmus and Chaos Monkey. Runs weekly failure injection drills across all services. Supports pod kill, network partition, CPU/memory stress, and AZ failure simulation. Results tracked in a dedicated Grafana dashboard. Auto-abort if blast radius exceeds thresholds.", "tech_stack": "Litmus, Kubernetes, Python", "owner": _id("ahmed-ibrahim"), "github_repo": "nexus/chaos-platform", "created_at": "2024-12-01T09:00:00Z", "updated_at": "2025-03-27T11:00:00Z"}},
    {"entity_id": _id("comp-e2e-framework"), "labels": ["Entity", "Component", "Infrastructure"], "properties": {"aim_id": _id("comp-e2e-framework"), "name": "nexus-e2e", "title": "E2E Test Framework", "description": "Playwright-based E2E test framework with 800+ tests. Parallelized across 8 workers for 15-minute full suite execution. Visual regression testing via Chromatic. Performance benchmarks via Lighthouse CI. Flaky test quarantine system automatically disables tests after 3 consecutive failures and notifies owners.", "tech_stack": "Playwright, TypeScript, Chromatic", "owner": _id("emma-fischer"), "github_repo": "nexus/e2e-tests", "created_at": "2024-06-01T09:00:00Z", "updated_at": "2025-03-26T10:00:00Z"}},
    {"entity_id": _id("comp-mlflow"), "labels": ["Entity", "Component", "MLInfra"], "properties": {"aim_id": _id("comp-mlflow"), "name": "nexus-mlflow", "title": "MLflow Experiment Tracking Platform", "description": "MLflow deployment managing 2000+ experiments and 15K+ runs. Custom plugins: automatic GPU utilization logging, model card generation, cost tracking (GPU hours × instance price). S3 artifact store with lifecycle policies. Integrated with the model registry for deployment approval workflows.", "tech_stack": "MLflow, Python, S3, PostgreSQL", "owner": _id("lisa-nguyen"), "github_repo": "nexus/mlflow-config", "created_at": "2024-08-15T09:00:00Z", "updated_at": "2025-03-28T09:00:00Z"}},
    {"entity_id": _id("comp-feature-flags"), "labels": ["Entity", "Component", "Infrastructure"], "properties": {"aim_id": _id("comp-feature-flags"), "name": "nexus-feature-flags", "title": "Feature Flag SDK Wrapper", "description": "Thin wrapper around LaunchDarkly SDK providing: circuit breaker for LaunchDarkly API failures (falls back to cached flag values), automatic flag usage tracking, stale flag detection (flags unchanged for 90+ days flagged for cleanup). Used by all services. Quarterly flag audit script identifies flags ready for removal.", "tech_stack": "Python, Go, TypeScript, LaunchDarkly SDK", "owner": _id("rachel-green"), "github_repo": "nexus/feature-flags", "created_at": "2024-03-01T09:00:00Z", "updated_at": "2025-03-21T10:00:00Z"}},
    {"entity_id": _id("comp-cdc-pipeline"), "labels": ["Entity", "Component", "Data"], "properties": {"aim_id": _id("comp-cdc-pipeline"), "name": "nexus-cdc", "title": "CDC Pipeline (Debezium)", "description": "Change Data Capture pipeline using Debezium connectors for PostgreSQL. Captures all database changes (inserts, updates, deletes) and publishes to Kafka topics in real-time. Supports schema evolution via Confluent Schema Registry. Processes 500M change events/day with exactly-once delivery using Kafka transactions.", "tech_stack": "Debezium, Kafka Connect, PostgreSQL", "owner": _id("elena-volkov"), "github_repo": "nexus/cdc-pipeline", "created_at": "2024-05-01T09:00:00Z", "updated_at": "2025-03-25T14:00:00Z"}},
]

WAVE2_DECISIONS = [
    {"entity_id": _id("adr-011"), "labels": ["Entity", "Decision", "ADR"], "properties": {"aim_id": _id("adr-011"), "name": "ADR-011: ClickHouse for Real-Time Analytics", "title": "ADR-011: ClickHouse for Event Analytics", "content": "Status: Accepted (2024-07-01). Context: Product analytics queries on Elasticsearch were slow (p95 > 5s for funnel queries spanning 30 days). Elasticsearch wasn't designed for OLAP workloads. Decision: Adopt ClickHouse for real-time analytics. Kafka Streams aggregations feed into ClickHouse materialized views. 5-second data freshness for dashboards. Consequences: 100x faster analytical queries, but operational complexity of managing a ClickHouse cluster.", "status": "accepted", "date": "2024-07-01", "proposed_by": _id("alex-petrov"), "approved_by": _id("nina-oconnell"), "jira_ticket": "DATA-245", "created_at": "2024-06-25T09:00:00Z", "updated_at": "2024-07-01T14:00:00Z"}},
    {"entity_id": _id("adr-012"), "labels": ["Entity", "Decision", "ADR"], "properties": {"aim_id": _id("adr-012"), "name": "ADR-012: Playwright for E2E Testing", "title": "ADR-012: Migrate from Cypress to Playwright", "content": "Status: Accepted (2024-05-15). Context: Cypress tests were flaky (8% flake rate), slow (45-min suite), and didn't support multi-tab or cross-origin testing needed for OAuth flows. Decision: Migrate to Playwright for E2E testing. Native multi-browser support, parallel execution across 8 workers, and auto-waiting reduces flakiness. Consequences: Suite time reduced from 45 to 15 minutes, flake rate from 8% to 1.5%, but required rewriting 500+ tests.", "status": "accepted", "date": "2024-05-15", "proposed_by": _id("emma-fischer"), "approved_by": _id("emma-nakamura"), "jira_ticket": "QA-134", "created_at": "2024-05-10T09:00:00Z", "updated_at": "2024-05-15T11:00:00Z"}},
    {"entity_id": _id("adr-013"), "labels": ["Entity", "Decision", "ADR"], "properties": {"aim_id": _id("adr-013"), "name": "ADR-013: CDC via Debezium", "title": "ADR-013: Debezium for Change Data Capture", "content": "Status: Accepted (2024-04-20). Context: Batch ETL from PostgreSQL to data lake ran every 6 hours causing stale analytics. Custom CDC scripts were unreliable and missed deletes. Decision: Adopt Debezium for PostgreSQL CDC. Kafka Connect source connectors capture all changes (including deletes) in real-time. Schema evolution handled via Schema Registry. Consequences: 6-hour staleness → real-time, reliable deletes/updates, but requires Kafka Connect cluster management.", "status": "accepted", "date": "2024-04-20", "proposed_by": _id("elena-volkov"), "approved_by": _id("nina-oconnell"), "jira_ticket": "DATA-189", "created_at": "2024-04-15T09:00:00Z", "updated_at": "2024-04-20T15:00:00Z"}},
    {"entity_id": _id("adr-014"), "labels": ["Entity", "Decision", "ADR"], "properties": {"aim_id": _id("adr-014"), "name": "ADR-014: Content Moderation via Claude API", "title": "ADR-014: Claude API for Content Moderation", "content": "Status: Accepted (2025-01-20). Context: Rule-based content moderation had 78% accuracy with high false positives blocking legitimate reviews. Human moderation queue had 48-hour backlog. Decision: Use Claude API for first-pass content moderation. Classify reviews as safe/toxic/needs-review with 99.2% accuracy. Human review only for 'needs-review' category (8% of reviews). Consequences: Moderation latency from 48 hours to < 5 seconds, accuracy improved from 78% to 99.2%, but $800/month API cost.", "status": "accepted", "date": "2025-01-20", "proposed_by": _id("nate-wilson"), "approved_by": _id("sarah-murphy"), "jira_ticket": "REV-089", "created_at": "2025-01-15T09:00:00Z", "updated_at": "2025-01-20T14:00:00Z"}},
    {"entity_id": _id("adr-015"), "labels": ["Entity", "Decision", "ADR"], "properties": {"aim_id": _id("adr-015"), "name": "ADR-015: Chaos Engineering Program", "title": "ADR-015: Adopt Chaos Engineering for Resilience", "content": "Status: Accepted (2024-12-01). Context: Three P1 incidents in 2024 revealed gaps in fault tolerance that testing alone couldn't catch. Services passed unit/integration tests but failed under real failure conditions. Decision: Implement monthly chaos engineering drills using Litmus. Start with pod kills, progress to network partitions and AZ failures. Automated blast radius limiting and abort conditions. Consequences: MTTR reduced 30%, discovered 15 resilience gaps in first quarter, but requires 2 engineer-days/month for drill preparation and analysis.", "status": "accepted", "date": "2024-12-01", "proposed_by": _id("ahmed-ibrahim"), "approved_by": _id("david-okafor"), "jira_ticket": "SRE-345", "created_at": "2024-11-25T09:00:00Z", "updated_at": "2024-12-01T11:00:00Z"}},
]

WAVE2_PROJECTS = [
    {"entity_id": _id("proj-marketplace"), "labels": ["Entity", "Project", "Initiative"], "properties": {"aim_id": _id("proj-marketplace"), "name": "Marketplace Expansion", "title": "Marketplace Expansion — Third-Party Sellers", "description": "Enable third-party sellers on the Nexus platform. Features: seller onboarding, product listing API, order routing, commission calculation, seller dashboard, and settlement reporting. Target: 100 sellers in beta by Q3 2025. Led by Sarah Murphy (PM) with Grace Kim and Sofia Martinez on backend. Budget: $200K.", "status": "planning", "start_date": "2025-05-01", "target_date": "2025-10-31", "lead": _id("sofia-martinez"), "pm": _id("sarah-murphy"), "jira_project": "MKT", "slack_channel": "#proj-marketplace", "created_at": "2025-03-15T09:00:00Z", "updated_at": "2025-04-01T10:00:00Z"}},
    {"entity_id": _id("proj-perf"), "labels": ["Entity", "Project", "Initiative"], "properties": {"aim_id": _id("proj-perf"), "name": "Performance Excellence", "title": "Performance Excellence — Sub-100ms P95 API Latency", "description": "Cross-team initiative to bring all API endpoints to sub-100ms p95 latency. Current baseline: 180ms p95 across all endpoints. Workstreams: (1) Database query optimization, (2) Redis caching strategy, (3) gRPC migration for internal calls, (4) CDN edge computing for personalization. Led by Carlos Vega with Marcus Johnson. Target: 50% latency reduction by Q3 2025.", "status": "in_progress", "start_date": "2025-02-15", "target_date": "2025-08-31", "lead": _id("carlos-vega"), "jira_project": "PERF", "slack_channel": "#proj-performance", "created_at": "2025-02-15T09:00:00Z", "updated_at": "2025-03-28T10:00:00Z"}},
]

WAVE2_TEAMS = [
    {"entity_id": _id("team-commerce"), "labels": ["Entity", "Team"], "properties": {"aim_id": _id("team-commerce"), "name": "Commerce Team", "title": "Commerce Product Team", "description": "Cross-functional product team owning the commerce domain: orders, payments, shipping, inventory, and pricing. 12 engineers + 2 PMs (Sarah Murphy, Daniel Park) + 1 designer (Julia Santos). Responsible for the entire purchase flow from cart to delivery. Processing $15M/month in transactions. Planning marketplace expansion for H2 2025.", "slack_channel": "#team-commerce", "jira_project": "COM", "created_at": "2025-01-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("team-qa"), "labels": ["Entity", "Team"], "properties": {"aim_id": _id("team-qa"), "name": "QA Team", "title": "Quality Assurance Team", "description": "3-person QA team led by Emma Fischer. Owns the E2E test framework (Playwright, 800+ tests), performance testing (k6), visual regression (Chromatic), and contract testing (Pact). Embedded in sprint teams but maintains shared testing infrastructure. Reduced production bug escape rate from 8% to 2%.", "slack_channel": "#team-qa", "jira_project": "QA", "created_at": "2024-04-15T09:00:00Z", "updated_at": "2025-03-26T10:00:00Z"}},
]

# ═══════════════════════════════════════════════════════════════════════════════
#  WAVE 3 — final batch to reach 200+ entities
# ═══════════════════════════════════════════════════════════════════════════════

WAVE3_PEOPLE = [
    {"entity_id": _id("ryan-obrien"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("ryan-obrien"), "name": "Ryan O'Brien", "title": "Engineer — Backend", "description": "Backend Engineer at Nexus. Owns the Coupon & Promotions Service. Implements complex promotion rules (BOGO, tiered discounts, bundle pricing, flash sales). Processes 2M coupon validations/day with p99 of 5ms via Redis-backed rules cache.", "department": "Engineering", "location": "Dublin", "expertise": "promotions, rules engines, redis, python", "created_at": "2024-08-01T09:00:00Z", "updated_at": "2025-03-18T10:00:00Z"}},
    {"entity_id": _id("natasha-ivanova"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("natasha-ivanova"), "name": "Natasha Ivanova", "title": "Senior Engineer — Backend", "description": "Senior Backend Engineer at Nexus. Owns the Tax Service integrating with Avalara for real-time tax calculation across 50 US states and 30 international jurisdictions. Handles tax exemptions, marketplace facilitator rules, and automated filing.", "department": "Engineering", "location": "Prague", "expertise": "tax systems, compliance, APIs, golang", "created_at": "2024-05-15T09:00:00Z", "updated_at": "2025-03-20T14:00:00Z"}},
    {"entity_id": _id("jake-henderson"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("jake-henderson"), "name": "Jake Henderson", "title": "Engineer — Frontend", "description": "Frontend Engineer at Nexus. Built the checkout flow optimization that improved conversion by 8%. Implemented one-click checkout with Apple Pay and Google Pay integration. Expert in animation and micro-interactions using Framer Motion.", "department": "Engineering", "location": "Melbourne", "expertise": "react, checkout UX, web payments, animation", "created_at": "2024-09-01T09:00:00Z", "updated_at": "2025-03-22T10:00:00Z"}},
    {"entity_id": _id("amara-osei"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("amara-osei"), "name": "Amara Osei", "title": "Engineer — Data", "description": "Data Engineer at Nexus. Maintains the Great Expectations data quality framework (1500+ expectations). Built the data lineage tracker that maps data flow from source to dashboard. Implemented automated data anomaly detection using statistical process control.", "department": "Data", "location": "Accra", "expertise": "data quality, great expectations, data lineage", "created_at": "2025-01-01T09:00:00Z", "updated_at": "2025-03-25T11:00:00Z"}},
    {"entity_id": _id("lucas-weber"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("lucas-weber"), "name": "Lucas Weber", "title": "Engineer — Platform", "description": "Platform Engineer at Nexus. Maintains the internal API marketplace (backstage.io) — service catalog, API documentation, and developer portal. Built the service health scorecard that rates all 30+ services on 15 operational metrics.", "department": "Engineering", "location": "Zurich", "expertise": "backstage, developer portal, API governance", "created_at": "2024-12-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("mei-lin"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("mei-lin"), "name": "Mei Lin", "title": "Senior Engineer — ML Infrastructure", "description": "Senior ML Infra Engineer at Nexus. Owns the embedding pipeline that generates 768-dim vectors via OpenAI text-embedding-3-small for Pinecone ingestion. Processes 100K documents/day. Built the embedding caching layer that saved $3K/month in API costs.", "department": "Engineering", "location": "Singapore", "expertise": "embeddings, vector databases, pinecone, python", "created_at": "2024-07-01T09:00:00Z", "updated_at": "2025-03-28T12:00:00Z"}},
    {"entity_id": _id("pedro-silva"), "labels": ["Entity", "Person", "SRE"], "properties": {"aim_id": _id("pedro-silva"), "name": "Pedro Silva", "title": "SRE", "description": "Site Reliability Engineer at Nexus. Manages the logging pipeline (Fluentd → Elasticsearch → Kibana) processing 2TB/day. Built the log-based anomaly detection system that auto-correlates error spikes across services. On-call every 4th week.", "department": "Engineering", "location": "Lisbon", "expertise": "ELK stack, log analysis, fluentd, kibana", "created_at": "2024-11-01T09:00:00Z", "updated_at": "2025-03-26T08:00:00Z"}},
    {"entity_id": _id("anya-kozlov"), "labels": ["Entity", "Person", "ProductManager"], "properties": {"aim_id": _id("anya-kozlov"), "name": "Anya Kozlov", "title": "Product Manager — Data", "description": "PM for the Data Platform team at Nexus. Owns the internal analytics tools, data quality dashboards, and self-serve data products. Led the data literacy program that trained 50+ non-engineering staff on SQL and dashboard creation.", "department": "Product", "location": "Berlin", "expertise": "data products, analytics, data literacy", "created_at": "2024-10-01T09:00:00Z", "updated_at": "2025-03-22T10:00:00Z"}},
    {"entity_id": _id("tyler-jackson"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("tyler-jackson"), "name": "Tyler Jackson", "title": "Engineer — Backend", "description": "Backend Engineer at Nexus. Owns the Search Index Service that keeps Elasticsearch in sync with the product catalog via CDC events. Handles 50K index updates/hour with eventual consistency guarantee of < 5 seconds. Built the custom Elasticsearch analyzer for product search.", "department": "Engineering", "location": "Nashville", "expertise": "elasticsearch, indexing, search infrastructure", "created_at": "2024-06-01T09:00:00Z", "updated_at": "2025-03-19T11:00:00Z"}},
    {"entity_id": _id("sophie-dubois"), "labels": ["Entity", "Person", "Designer"], "properties": {"aim_id": _id("sophie-dubois"), "name": "Sophie Dubois", "title": "UX Researcher", "description": "UX Researcher at Nexus. Runs the user research program: 8 usability studies/quarter, continuous NPS tracking (current: +42), and customer journey mapping. Led the research that validated Project Aurora's hybrid search approach (500-query test with statistical significance p < 0.01).", "department": "Design", "location": "Paris", "expertise": "user research, usability testing, analytics, NPS", "created_at": "2024-08-15T09:00:00Z", "updated_at": "2025-03-24T10:00:00Z"}},
]

WAVE3_SERVICES = [
    {"entity_id": _id("svc-promotions"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-promotions"), "name": "Promotions Service", "title": "Coupon & Promotions Engine", "description": "Manages coupons, promotions, and discount rules. Supports BOGO, tiered discounts, bundle pricing, flash sales (with countdown timers), and referral codes. Rules engine evaluates 2M coupon validations/day with p99 of 5ms via Redis. Integrates with Pricing Service for final price calculation.", "tech_stack": "Python, FastAPI, Redis, PostgreSQL", "status": "production", "tier": "high", "owner": _id("ryan-obrien"), "slack_channel": "#svc-promotions", "jira_project": "PROMO", "github_repo": "nexus/promotions-service", "created_at": "2024-01-01T09:00:00Z", "updated_at": "2025-03-18T10:00:00Z"}},
    {"entity_id": _id("svc-tax"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-tax"), "name": "Tax Service", "title": "Tax Calculation Service (Avalara)", "description": "Real-time tax calculation via Avalara AvaTax. Supports 50 US states (including marketplace facilitator rules) and 30 international jurisdictions. Handles tax exemptions via certificate management. Caches tax rates for 1 hour (Redis). Automated tax filing via Avalara Returns.", "tech_stack": "Go, Avalara SDK, Redis", "status": "production", "tier": "high", "owner": _id("natasha-ivanova"), "slack_channel": "#svc-tax", "jira_project": "TAX", "github_repo": "nexus/tax-service", "created_at": "2024-05-15T09:00:00Z", "updated_at": "2025-03-20T14:00:00Z"}},
    {"entity_id": _id("svc-search-index"), "labels": ["Entity", "Service", "Infrastructure"], "properties": {"aim_id": _id("svc-search-index"), "name": "Search Indexer", "title": "Search Index Sync Service", "description": "Keeps Elasticsearch product index in sync with the catalog via CDC events from Debezium. Handles 50K index updates/hour with < 5 second consistency. Custom Elasticsearch analyzers for product search: edge n-grams, synonym expansion, and language-specific stemmers. Supports reindexing 2M products in 4 hours for schema migrations.", "tech_stack": "Python, Kafka, Elasticsearch", "status": "production", "tier": "high", "owner": _id("tyler-jackson"), "slack_channel": "#svc-search-index", "jira_project": "AURORA", "github_repo": "nexus/search-indexer", "created_at": "2024-06-01T09:00:00Z", "updated_at": "2025-03-19T11:00:00Z"}},
    {"entity_id": _id("svc-backstage"), "labels": ["Entity", "Service", "Internal"], "properties": {"aim_id": _id("svc-backstage"), "name": "Developer Portal", "title": "Backstage Developer Portal", "description": "Internal developer portal built on Backstage. Service catalog with 30+ services, API documentation (OpenAPI specs auto-synced from repos), tech docs, and service health scorecards. 15 operational metrics per service: uptime, latency p50/p95/p99, error rate, deploy frequency, MTTR, test coverage, dependency freshness, etc. Used by all 60+ engineers daily.", "tech_stack": "Backstage, TypeScript, PostgreSQL", "status": "production", "tier": "medium", "owner": _id("lucas-weber"), "slack_channel": "#backstage", "jira_project": "PLAT", "github_repo": "nexus/backstage", "created_at": "2024-12-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("svc-embedding"), "labels": ["Entity", "Service", "MLInfra"], "properties": {"aim_id": _id("svc-embedding"), "name": "Embedding Service", "title": "Document Embedding Pipeline", "description": "Generates 768-dim vectors via OpenAI text-embedding-3-small for Pinecone ingestion. Processes 100K documents/day. Embedding cache (Redis, 30-day TTL) saves $3K/month by avoiding re-embedding unchanged documents. Supports batch and streaming modes. Content chunking with 512-token windows and 50-token overlap for long documents.", "tech_stack": "Python, OpenAI API, Redis, Kafka", "status": "production", "tier": "high", "owner": _id("mei-lin"), "slack_channel": "#svc-embeddings", "jira_project": "MLINFRA", "github_repo": "nexus/embedding-service", "created_at": "2024-07-01T09:00:00Z", "updated_at": "2025-03-28T12:00:00Z"}},
]

WAVE3_DOCS = [
    {"entity_id": _id("doc-promotion-rules"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-promotion-rules"), "name": "Promotion Rules Guide", "title": "Promotions & Coupon Rules Configuration Guide", "content": "Authored by Ryan O'Brien. Promotion types: (1) PERCENTAGE_OFF — flat percentage discount, stackable, (2) FIXED_AMOUNT — dollar amount off, (3) BOGO — buy X get Y free, (4) TIERED — spend thresholds trigger increasing discounts, (5) BUNDLE — specific product combinations at special price, (6) FLASH_SALE — time-limited promotion with countdown, inventory cap. Rules evaluation order: most specific first, then highest value. Stacking: max 2 promotions per order (1 coupon + 1 automatic). Flash sales require capacity planning approval from SRE team (Redis pub/sub for real-time countdown sync).", "author": _id("ryan-obrien"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/PROMO/pages/rules-guide", "created_at": "2024-09-01T09:00:00Z", "updated_at": "2025-03-18T10:00:00Z"}},
    {"entity_id": _id("doc-embedding-ops"), "labels": ["Entity", "Document", "Runbook"], "properties": {"aim_id": _id("doc-embedding-ops"), "name": "Embedding Pipeline Runbook", "title": "Embedding Pipeline Operations Runbook", "content": "Authored by Mei Lin. Common issues: (1) OpenAI API rate limiting — check rate limit headers, adjust batch size. Fallback: local sentence-transformers model (lower quality but no API dependency). (2) Vector dimension mismatch — embedding model change requires full re-index. Schedule during off-peak, expected time: 8 hours for 2M documents. (3) Pinecone upsert failures — check index quota. Current usage: 2M vectors, quota: 5M. Alert at 80%. (4) Cache invalidation — if embedding model changes, flush Redis cache: `redis-cli FLUSHDB 3`. (5) High API cost — check cache hit rate in Grafana. Should be > 70%. If lower, investigate content churn.", "author": _id("mei-lin"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/MLINFRA/pages/embedding-runbook", "created_at": "2024-09-01T09:00:00Z", "updated_at": "2025-04-10T14:00:00Z"}},
    {"entity_id": _id("doc-backstage-guide"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-backstage-guide"), "name": "Developer Portal Guide", "title": "Backstage Developer Portal User Guide", "content": "Authored by Lucas Weber. The developer portal at backstage.nexus.internal is the single entry point for all engineering documentation. Features: (1) Service Catalog — browse all 30+ services, view owners, dependencies, health scorecards, (2) API Docs — auto-synced OpenAPI specs with interactive explorer, (3) Tech Docs — markdown docs from each repo's /docs folder, built automatically, (4) Scaffolder — create new services from templates (Go/Python/Node.js), pre-configured with CI/CD, monitoring, and Kubernetes manifests, (5) Search — full-text search across all docs, APIs, and entities. Updating your service's scorecard: add service-info.yaml to your repo root (schema documented in PLAT Confluence).", "author": _id("lucas-weber"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/PLAT/pages/backstage-guide", "created_at": "2025-01-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("doc-data-lineage"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-data-lineage"), "name": "Data Lineage Guide", "title": "Data Lineage & Governance Guide", "content": "Authored by Amara Osei. Data lineage tracks the complete flow of data from source to dashboard. Implementation: dbt lineage graph + custom metadata extraction from Kafka Connect, Spark, and Airflow. Visualization: DataHub portal showing upstream/downstream dependencies for every table and dashboard. Data classification: PII (email, phone, address), Financial (revenue, costs), Confidential (salaries, contracts), Public (product data). All PII fields tagged in DataHub and subject to GDPR deletion and export requirements.", "author": _id("amara-osei"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/DATA/pages/lineage-guide", "created_at": "2025-02-01T09:00:00Z", "updated_at": "2025-03-25T11:00:00Z"}},
]

WAVE3_COMPONENTS = [
    {"entity_id": _id("comp-backstage-plugins"), "labels": ["Entity", "Component", "Infrastructure"], "properties": {"aim_id": _id("comp-backstage-plugins"), "name": "nexus-backstage-plugins", "title": "Custom Backstage Plugins", "description": "5 custom Backstage plugins: (1) Service Scorecard — 15-metric health assessment pulled from Prometheus and GitHub, (2) Incident Timeline — shows recent incidents and on-call for each service, (3) Cost Dashboard — AWS cost attribution per service from Cost Explorer API, (4) Dependency Graph — interactive force-directed graph of service dependencies, (5) Deploy Tracker — real-time deploy status from ArgoCD.", "tech_stack": "TypeScript, React, Backstage SDK", "owner": _id("lucas-weber"), "github_repo": "nexus/backstage-plugins", "created_at": "2024-12-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("comp-embedding-cache"), "labels": ["Entity", "Component", "MLInfra"], "properties": {"aim_id": _id("comp-embedding-cache"), "name": "nexus-embedding-cache", "title": "Embedding Cache Layer", "description": "Redis-backed caching layer for document embeddings. Content-addressable cache using SHA-256 hash of input text as key. 30-day TTL. Saves $3K/month in OpenAI API costs with 75% cache hit rate. Supports batch lookups and pre-warming for bulk ingestion. Metrics: cache hit/miss rates exported to Prometheus.", "tech_stack": "Python, Redis, Prometheus", "owner": _id("mei-lin"), "github_repo": "nexus/embedding-cache", "created_at": "2024-09-01T09:00:00Z", "updated_at": "2025-03-28T12:00:00Z"}},
    {"entity_id": _id("comp-data-quality-suite"), "labels": ["Entity", "Component", "Data"], "properties": {"aim_id": _id("comp-data-quality-suite"), "name": "nexus-data-quality", "title": "Data Quality Test Suite", "description": "Great Expectations-based data quality framework with 1500+ expectations across 400+ dbt models. Automated distribution skew detection (added after INC-2025-028). CI integration: data quality checks run on every dbt model change. Dashboards in Grafana show quality scores per data domain. PagerDuty alerts on critical quality failures.", "tech_stack": "Great Expectations, Python, dbt, Grafana", "owner": _id("amara-osei"), "github_repo": "nexus/data-quality", "created_at": "2025-01-01T09:00:00Z", "updated_at": "2025-03-25T11:00:00Z"}},
]

WAVE3_EXTRA = [
    {"entity_id": _id("chris-morgan"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("chris-morgan"), "name": "Chris Morgan", "title": "Engineer — Backend", "description": "Backend Engineer at Nexus. Owns the Subscription & Billing Service handling 200K recurring subscriptions with Stripe Billing integration. Implements proration, plan upgrades/downgrades, and usage-based billing.", "department": "Engineering", "location": "London", "expertise": "billing, subscriptions, stripe, golang", "created_at": "2024-04-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("sarah-anderson"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("sarah-anderson"), "name": "Sarah Anderson", "title": "Engineer — Frontend", "description": "Frontend Engineer at Nexus. Built the product comparison tool and the wishlist feature. Implemented server-side rendering for SEO-critical product pages. Expert in Next.js ISR (Incremental Static Regeneration) for product catalog.", "department": "Engineering", "location": "Boston", "expertise": "next.js, ISR, SEO, react", "created_at": "2024-10-15T09:00:00Z", "updated_at": "2025-03-23T11:00:00Z"}},
    {"entity_id": _id("rashid-al-farsi"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("rashid-al-farsi"), "name": "Rashid Al-Farsi", "title": "Engineer — Backend", "description": "Backend Engineer at Nexus. Owns the Address & Geolocation Service. Integrates with Google Maps Platform for address validation, geocoding, and distance calculation. Supports address autocomplete in 30 countries.", "department": "Engineering", "location": "Abu Dhabi", "expertise": "geolocation, google maps API, golang", "created_at": "2024-08-15T09:00:00Z", "updated_at": "2025-03-19T12:00:00Z"}},
    {"entity_id": _id("jenny-clark"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("jenny-clark"), "name": "Jenny Clark", "title": "Senior Engineer — Backend", "description": "Senior Backend Engineer at Nexus. Owns the Customer Support API powering the Zendesk integration, automated ticket routing, and self-service help center. Built the AI ticket classification system using Claude API.", "department": "Engineering", "location": "Portland", "expertise": "support systems, zendesk, APIs, python", "created_at": "2024-02-01T09:00:00Z", "updated_at": "2025-03-21T10:00:00Z"}},
    {"entity_id": _id("alex-thompson"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("alex-thompson"), "name": "Alex Thompson", "title": "Engineer — Data", "description": "Data Engineer at Nexus. Built the BI dashboard layer using Looker connected to the data lake. Maintains 60+ dashboards for exec, product, and ops teams. Automated weekly business review report generation.", "department": "Data", "location": "Chicago", "expertise": "looker, BI, SQL, data modeling", "created_at": "2024-09-01T09:00:00Z", "updated_at": "2025-03-24T09:00:00Z"}},
    {"entity_id": _id("svc-billing"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-billing"), "name": "Billing Service", "title": "Subscription & Billing Service", "description": "Manages 200K recurring subscriptions via Stripe Billing. Supports monthly/annual plans, usage-based billing, proration for plan changes, and automated dunning for failed payments. Revenue recognition compliant with ASC 606. Generates invoice PDFs via the Reporting Service.", "tech_stack": "Go, Stripe Billing SDK, PostgreSQL", "status": "production", "tier": "critical", "owner": _id("chris-morgan"), "slack_channel": "#svc-billing", "jira_project": "BILL", "github_repo": "nexus/billing-service", "created_at": "2024-04-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("svc-address"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-address"), "name": "Address Service", "title": "Address & Geolocation Service", "description": "Address validation, geocoding, and distance calculation via Google Maps Platform. Supports address autocomplete in 30 countries. Caches geocoding results in Redis (90-day TTL) saving $2K/month in API costs. Used by shipping, tax, and fraud services for location-based logic.", "tech_stack": "Go, Google Maps API, Redis", "status": "production", "tier": "medium", "owner": _id("rashid-al-farsi"), "slack_channel": "#svc-address", "jira_project": "PLAT", "github_repo": "nexus/address-service", "created_at": "2024-08-15T09:00:00Z", "updated_at": "2025-03-19T12:00:00Z"}},
    {"entity_id": _id("svc-support"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-support"), "name": "Support API", "title": "Customer Support Integration Service", "description": "Powers Zendesk integration for customer support. Automated ticket routing based on issue type and priority. AI ticket classification via Claude API (92% accuracy, 15K tickets/day). Self-service help center with 500+ articles. Escalation rules: VIP customers auto-prioritized, SLA tracking per tier.", "tech_stack": "Python, FastAPI, Claude API, Zendesk SDK", "status": "production", "tier": "high", "owner": _id("jenny-clark"), "slack_channel": "#svc-support", "jira_project": "SUP", "github_repo": "nexus/support-service", "created_at": "2024-02-01T09:00:00Z", "updated_at": "2025-03-21T10:00:00Z"}},
    {"entity_id": _id("svc-looker"), "labels": ["Entity", "Service", "Data"], "properties": {"aim_id": _id("svc-looker"), "name": "BI Platform", "title": "Looker BI Platform", "description": "Business intelligence layer with 60+ dashboards across exec (revenue, growth, unit economics), product (funnels, cohorts, feature adoption), and ops (SLAs, incident trends, deploy velocity). Connected to the data lake via Presto. Self-service analytics for 50+ non-engineering users. Weekly business review auto-generated report.", "tech_stack": "Looker, LookML, Presto", "status": "production", "tier": "medium", "owner": _id("alex-thompson"), "slack_channel": "#bi-platform", "jira_project": "DATA", "github_repo": "nexus/looker-config", "created_at": "2024-09-01T09:00:00Z", "updated_at": "2025-03-24T09:00:00Z"}},
    {"entity_id": _id("doc-billing-guide"), "labels": ["Entity", "Document", "Runbook"], "properties": {"aim_id": _id("doc-billing-guide"), "name": "Billing Operations Guide", "title": "Billing & Subscription Operations Guide", "content": "Authored by Chris Morgan. Common issues: (1) Failed payment retry: Stripe dunning retries 4 times over 3 weeks. Check dunning status at stripe.com/dashboard. (2) Proration disputes: Use `GET /billing/invoices/:id/line-items` to show proration calculation. (3) Plan change errors: Verify plan migration path in billing-config.yaml. (4) Revenue recognition: Monthly close process runs on 3rd business day via Airflow DAG.", "author": _id("chris-morgan"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/BILL/pages/billing-guide", "created_at": "2024-06-01T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("doc-support-runbook"), "labels": ["Entity", "Document", "Runbook"], "properties": {"aim_id": _id("doc-support-runbook"), "name": "Support Service Runbook", "title": "Customer Support Service Runbook", "content": "Authored by Jenny Clark. AI classification accuracy monitoring: check Grafana dashboard 'Support AI Metrics'. If accuracy drops below 90%, check for new ticket categories not in training data. Zendesk sync issues: verify webhook endpoint health at /health/zendesk. Escalation rules are in support-config.yaml — changes require PM approval.", "author": _id("jenny-clark"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/SUP/pages/support-runbook", "created_at": "2024-04-01T09:00:00Z", "updated_at": "2025-03-21T10:00:00Z"}},
    {"entity_id": _id("doc-bi-standards"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-bi-standards"), "name": "BI Dashboard Standards", "title": "Business Intelligence Dashboard Standards", "content": "Authored by Alex Thompson. All dashboards must follow: (1) Naming: {team}-{metric}-{view} (e.g., growth-activation-weekly), (2) Data freshness label required on every dashboard, (3) Metric definitions linked to the Metric Dictionary (Confluence), (4) Access control: sensitive dashboards (revenue, costs) restricted to leadership role, (5) Performance: no dashboard should take > 10 seconds to load — use aggregate tables for heavy queries.", "author": _id("alex-thompson"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/DATA/pages/bi-standards", "created_at": "2024-11-01T09:00:00Z", "updated_at": "2025-03-24T09:00:00Z"}},
    {"entity_id": _id("comp-ai-moderation"), "labels": ["Entity", "Component", "Library"], "properties": {"aim_id": _id("comp-ai-moderation"), "name": "nexus-ai-moderation", "title": "AI Content Moderation Library", "description": "Shared library wrapping Claude API for content moderation. Used by Reviews Service (review text), Chat Service (live messages), and Support Service (ticket classification). Configurable safety thresholds per use case. Batch mode for bulk processing. Cost tracking per service consumer.", "tech_stack": "Python, Anthropic SDK", "owner": _id("nate-wilson"), "github_repo": "nexus/ai-moderation", "created_at": "2025-01-01T09:00:00Z", "updated_at": "2025-03-19T11:00:00Z"}},
]

WAVE3_FINAL = [
    {"entity_id": _id("zara-ahmed"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("zara-ahmed"), "name": "Zara Ahmed", "title": "Engineer — Mobile", "description": "Mobile Engineer at Nexus. Built the push notification deep-linking system. Implemented A/B testing for mobile onboarding flows. Expert in React Native performance profiling.", "department": "Engineering", "location": "Karachi", "expertise": "react native, mobile testing, deep linking", "created_at": "2025-02-01T09:00:00Z", "updated_at": "2025-03-25T10:00:00Z"}},
    {"entity_id": _id("leo-fernandez"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("leo-fernandez"), "name": "Leo Fernandez", "title": "Engineer — Platform", "description": "Platform Engineer at Nexus. Maintains the DNS and CDN infrastructure (Route53 + CloudFront). Built the edge function framework for A/B test bucketing at the CDN level. Reduced TTFB by 40% via edge caching.", "department": "Engineering", "location": "Buenos Aires", "expertise": "CDN, edge computing, cloudfront, DNS", "created_at": "2024-12-01T09:00:00Z", "updated_at": "2025-03-20T11:00:00Z"}},
    {"entity_id": _id("helen-zhao"), "labels": ["Entity", "Person", "Engineer"], "properties": {"aim_id": _id("helen-zhao"), "name": "Helen Zhao", "title": "Senior Engineer — Backend", "description": "Senior Backend Engineer at Nexus. Owns the Marketplace Seller API (Project Marketplace). Building seller onboarding, product listing API, and commission calculation. Previously at Etsy on the seller tools team.", "department": "Engineering", "location": "New York", "expertise": "marketplace, e-commerce, APIs, golang", "created_at": "2025-03-01T09:00:00Z", "updated_at": "2025-04-01T10:00:00Z"}},
    {"entity_id": _id("svc-seller-api"), "labels": ["Entity", "Service", "Product"], "properties": {"aim_id": _id("svc-seller-api"), "name": "Seller API", "title": "Marketplace Seller API", "description": "API for third-party sellers to manage their storefront, list products, track orders, and view earnings. Part of Project Marketplace. Features: seller onboarding with KYC verification, product listing with image upload, order routing, commission calculation (15% standard, 10% volume tier), and settlement reporting.", "tech_stack": "Go, PostgreSQL, Kafka, S3", "status": "development", "tier": "high", "owner": _id("helen-zhao"), "slack_channel": "#svc-seller-api", "jira_project": "MKT", "github_repo": "nexus/seller-api", "created_at": "2025-03-01T09:00:00Z", "updated_at": "2025-04-01T10:00:00Z"}},
    {"entity_id": _id("doc-seller-api-spec"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-seller-api-spec"), "name": "Seller API Specification", "title": "Marketplace Seller API v1 Specification", "content": "Authored by Helen Zhao. OpenAPI 3.1 spec for the Seller API. Endpoints: POST /sellers (onboarding), GET /sellers/:id/products (catalog), POST /sellers/:id/products (listing), GET /sellers/:id/orders (order tracking), GET /sellers/:id/earnings (commission statements). Auth: OAuth 2.0 with seller scopes. Rate limit: 1000 RPM per seller.", "author": _id("helen-zhao"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/MKT/pages/seller-api-spec", "created_at": "2025-03-15T09:00:00Z", "updated_at": "2025-04-01T10:00:00Z"}},
    {"entity_id": _id("comp-rate-limiter"), "labels": ["Entity", "Component", "Library"], "properties": {"aim_id": _id("comp-rate-limiter"), "name": "nexus-rate-limiter", "title": "Distributed Rate Limiter Library", "description": "Shared rate limiting library using Redis sorted sets (sliding window algorithm). Supports per-tenant, per-API-key, and per-IP rate limits. Used by API Gateway, Seller API, and Webhook Service. Configurable burst allowance and graceful degradation when Redis is unavailable.", "tech_stack": "Go, Python, Redis", "owner": _id("alex-rivera"), "github_repo": "nexus/rate-limiter", "created_at": "2023-08-01T09:00:00Z", "updated_at": "2025-03-22T10:00:00Z"}},
    {"entity_id": _id("comp-idempotency"), "labels": ["Entity", "Component", "Library"], "properties": {"aim_id": _id("comp-idempotency"), "name": "nexus-idempotency", "title": "Idempotency Key Library", "description": "Shared idempotency key library for safe retries. Dual-storage: Redis (fast, 24h TTL) + PostgreSQL (persistent, 7d TTL). Handles the Idempotency-Key header per API Design Standards. Added persistent storage after INC-2025-015 (payment double-charge). Used by Orders, Payments, and Webhook services.", "tech_stack": "Go, Python, Redis, PostgreSQL", "owner": _id("sofia-martinez"), "github_repo": "nexus/idempotency", "created_at": "2025-02-20T09:00:00Z", "updated_at": "2025-03-20T10:00:00Z"}},
    {"entity_id": _id("proj-ai-support"), "labels": ["Entity", "Project", "Initiative"], "properties": {"aim_id": _id("proj-ai-support"), "name": "AI-Powered Support", "title": "AI-Powered Customer Support", "description": "Enhance customer support with AI: (1) Claude-powered auto-responses for common queries (40% deflection rate), (2) AI ticket classification and routing (92% accuracy), (3) Agent assist — real-time suggested responses during live chat, (4) Knowledge base article generation from resolved tickets. Led by Jenny Clark. Target: reduce median ticket resolution time from 4 hours to 1 hour.", "status": "in_progress", "start_date": "2025-02-15", "target_date": "2025-07-31", "lead": _id("jenny-clark"), "jira_project": "SUP", "slack_channel": "#proj-ai-support", "created_at": "2025-02-15T09:00:00Z", "updated_at": "2025-03-21T10:00:00Z"}},
    {"entity_id": _id("doc-onboarding-mobile"), "labels": ["Entity", "Document", "Runbook"], "properties": {"aim_id": _id("doc-onboarding-mobile"), "name": "Mobile Development Guide", "title": "Mobile Developer Onboarding Guide", "content": "Authored by Sam Patel. Getting started with the Nexus mobile app: (1) Clone nexus/mobile-app, (2) Install React Native CLI (not Expo), (3) Run `yarn install && cd ios && pod install`, (4) Start Metro: `yarn start`, (5) Run on simulator: `yarn ios` or `yarn android`. Key architecture: Zustand for state, React Query for API, SQLite for offline. CodePush for OTA updates. Testing: Jest + RNTL for unit, Detox for E2E.", "author": _id("sam-patel"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/MOB/pages/getting-started", "created_at": "2024-06-01T09:00:00Z", "updated_at": "2025-03-25T14:00:00Z"}},
    {"entity_id": _id("doc-cost-optimization"), "labels": ["Entity", "Document", "Standard"], "properties": {"aim_id": _id("doc-cost-optimization"), "name": "Cloud Cost Optimization Guide", "title": "AWS Cost Optimization Guide", "content": "Authored by David Okafor and Raj Krishnan. Monthly AWS spend: $85K. Savings initiatives: (1) Reserved Instances for EKS nodes — 40% savings ($12K/month), (2) Spot instances for batch processing (Spark, Airflow) — 70% savings ($5K/month), (3) S3 lifecycle policies — Glacier for data > 90 days ($2K/month), (4) Right-sizing — Kubernetes VPA recommendations applied monthly ($3K/month), (5) Embedding cache — reduced OpenAI API costs 75% ($3K/month). Cost attribution: per-service tagging via Backstage cost dashboard.", "author": _id("david-okafor"), "confluence_url": "https://nexus.atlassian.net/wiki/spaces/SRE/pages/cost-optimization", "created_at": "2025-01-15T09:00:00Z", "updated_at": "2025-03-29T08:00:00Z"}},
]

WAVE3_INCIDENTS = [
    {"entity_id": _id("inc-2025-037"), "labels": ["Entity", "Incident", "Postmortem"], "properties": {"aim_id": _id("inc-2025-037"), "name": "INC-2025-037: Promotion Stack Overflow", "title": "Incident: Promotions Engine Infinite Loop During Flash Sale", "content": "Severity: P2. Duration: 2025-04-07 12:00 UTC to 2025-04-07 12:45 UTC (45 minutes). Impact: Checkout latency spiked to 15 seconds for 45 minutes during a planned flash sale (5000 units). ~2K orders delayed. Root Cause: A circular promotion rule (coupon A triggers bundle B which triggers coupon A) caused infinite evaluation loop. The rules engine had no depth limit. Resolution: Added max evaluation depth (10), circular dependency detection in rule creation API, and mandatory pre-flight validation for all new promotions.", "severity": "P2", "duration_minutes": 45, "date": "2025-04-07", "responders": f"{_id('ryan-obrien')},{_id('carlos-vega')}", "jira_ticket": "PROMO-167", "created_at": "2025-04-07T12:00:00Z", "updated_at": "2025-04-09T10:00:00Z"}},
    {"entity_id": _id("inc-2025-039"), "labels": ["Entity", "Incident", "Postmortem"], "properties": {"aim_id": _id("inc-2025-039"), "name": "INC-2025-039: Embedding Pipeline Backlog", "title": "Incident: 48-Hour Embedding Pipeline Backlog", "content": "Severity: P3. Duration: 2025-04-08 00:00 UTC to 2025-04-10 00:00 UTC (48 hours). Impact: New product listings not appearing in vector search for 48 hours. Keyword search (Elasticsearch) unaffected. Root Cause: OpenAI API rate limit reduction (from 10K RPM to 3K RPM) on their side without notice. The embedding pipeline's retry logic with backoff consumed the entire rate budget on retries, starving new documents. Resolution: Implemented priority queue (new documents > re-embeddings), rate limiter with token bucket, and fallback to local sentence-transformers model for overflow.", "severity": "P3", "duration_minutes": 2880, "date": "2025-04-08", "responders": f"{_id('mei-lin')},{_id('priya-patel')}", "jira_ticket": "MLINFRA-210", "created_at": "2025-04-08T00:00:00Z", "updated_at": "2025-04-10T10:00:00Z"}},
]

# ═══════════════════════════════════════════════════════════════════════════════
#  Aggregate all expansion entities
# ═══════════════════════════════════════════════════════════════════════════════

ALL_EXPANSION_ENTITIES = (
    EXPANSION_PEOPLE
    + EXPANSION_SERVICES
    + EXPANSION_DECISIONS
    + EXPANSION_INCIDENTS
    + EXPANSION_PROJECTS
    + EXPANSION_DOCS
    + EXPANSION_TEAMS
    + EXPANSION_COMPONENTS
    + WAVE2_PEOPLE
    + WAVE2_SERVICES
    + WAVE2_INCIDENTS
    + WAVE2_DOCS
    + WAVE2_COMPONENTS
    + WAVE2_DECISIONS
    + WAVE2_PROJECTS
    + WAVE2_TEAMS
    + WAVE3_PEOPLE
    + WAVE3_SERVICES
    + WAVE3_INCIDENTS
    + WAVE3_DOCS
    + WAVE3_COMPONENTS
    + WAVE3_EXTRA
    + WAVE3_FINAL
)

# ═══════════════════════════════════════════════════════════════════════════════
#  RELATIONSHIPS  (350+)
# ═══════════════════════════════════════════════════════════════════════════════

EXPANSION_RELATIONSHIPS = [
    # ── Org structure: Sarah manages new senior leads ───────────────────────
    {"rel_type": "MANAGES", "source_id": _id("sarah-chen"), "target_id": _id("nina-oconnell"), "properties": {"since": "2024-06"}},
    {"rel_type": "MANAGES", "source_id": _id("sarah-chen"), "target_id": _id("sam-patel"), "properties": {"since": "2024-04"}},
    {"rel_type": "MANAGES", "source_id": _id("sarah-chen"), "target_id": _id("lena-johansson"), "properties": {"since": "2024-11"}},

    # ── Team leadership ─────────────────────────────────────────────────────
    {"rel_type": "LEADS", "source_id": _id("sofia-martinez"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "LEADS", "source_id": _id("nina-oconnell"), "target_id": _id("team-data"), "properties": {}},
    {"rel_type": "LEADS", "source_id": _id("aisha-mohammed"), "target_id": _id("team-data-science"), "properties": {}},
    {"rel_type": "LEADS", "source_id": _id("lena-johansson"), "target_id": _id("team-security"), "properties": {}},
    {"rel_type": "LEADS", "source_id": _id("sam-patel"), "target_id": _id("team-mobile"), "properties": {}},

    # ── Team membership ─────────────────────────────────────────────────────
    # Platform team
    {"rel_type": "MEMBER_OF", "source_id": _id("raj-krishnan"), "target_id": _id("team-platform"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("tom-andersen"), "target_id": _id("team-platform"), "properties": {}},
    # Backend team
    {"rel_type": "MEMBER_OF", "source_id": _id("sofia-martinez"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("michael-taylor"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("kevin-brown"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("anna-kowalski"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("carlos-vega"), "target_id": _id("team-backend"), "properties": {}},
    # Frontend team
    {"rel_type": "MEMBER_OF", "source_id": _id("james-wu"), "target_id": _id("team-frontend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("hannah-lee"), "target_id": _id("team-frontend"), "properties": {}},
    # Data team
    {"rel_type": "MEMBER_OF", "source_id": _id("nina-oconnell"), "target_id": _id("team-data"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("yuki-tanaka"), "target_id": _id("team-data"), "properties": {}},
    # Data Science team
    {"rel_type": "MEMBER_OF", "source_id": _id("aisha-mohammed"), "target_id": _id("team-data-science"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("chen-wei"), "target_id": _id("team-data-science"), "properties": {}},
    # ML Infra team
    {"rel_type": "MEMBER_OF", "source_id": _id("olivia-chen"), "target_id": _id("team-ml"), "properties": {}},
    # Security team
    {"rel_type": "MEMBER_OF", "source_id": _id("lena-johansson"), "target_id": _id("team-security"), "properties": {}},
    # Mobile team
    {"rel_type": "MEMBER_OF", "source_id": _id("sam-patel"), "target_id": _id("team-mobile"), "properties": {}},
    # Design (cross-functional — Maya works with Frontend and Mobile)
    {"rel_type": "MEMBER_OF", "source_id": _id("maya-kapoor"), "target_id": _id("team-frontend"), "properties": {"role": "design"}},
    # SRE
    {"rel_type": "MEMBER_OF", "source_id": _id("diego-reyes"), "target_id": _id("team-platform"), "properties": {"role": "SRE"}},
    # Product (cross-functional)
    {"rel_type": "MEMBER_OF", "source_id": _id("daniel-park"), "target_id": _id("team-platform"), "properties": {"role": "PM"}},
    {"rel_type": "MEMBER_OF", "source_id": _id("rachel-green"), "target_id": _id("team-frontend"), "properties": {"role": "PM"}},

    # ── Service ownership ───────────────────────────────────────────────────
    {"rel_type": "OWNS", "source_id": _id("sofia-martinez"), "target_id": _id("svc-orders"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("sofia-martinez"), "target_id": _id("svc-user-profile"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("michael-taylor"), "target_id": _id("svc-payments"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("anna-kowalski"), "target_id": _id("svc-inventory"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("kevin-brown"), "target_id": _id("svc-notifications"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("carlos-vega"), "target_id": _id("svc-pricing"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("sam-patel"), "target_id": _id("svc-mobile-api"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("aisha-mohammed"), "target_id": _id("svc-recommendations"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("chen-wei"), "target_id": _id("svc-fraud"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("nina-oconnell"), "target_id": _id("svc-data-lake"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("james-wu"), "target_id": _id("svc-media"), "properties": {}},

    # Component ownership
    {"rel_type": "OWNS", "source_id": _id("hannah-lee"), "target_id": _id("comp-nexus-ui"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("marcus-johnson"), "target_id": _id("comp-kafka-consumer"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("david-okafor"), "target_id": _id("comp-terraform-modules"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("tom-andersen"), "target_id": _id("comp-tilt-dev"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("diego-reyes"), "target_id": _id("comp-slo-framework"), "properties": {}},

    # ── Service dependencies ────────────────────────────────────────────────
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-orders"), "target_id": _id("svc-payments"), "properties": {"protocol": "Kafka saga"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-orders"), "target_id": _id("svc-inventory"), "properties": {"protocol": "Kafka saga"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-orders"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-orders"), "target_id": _id("svc-notifications"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-payments"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-payments"), "target_id": _id("svc-fraud"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-inventory"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-notifications"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-pricing"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-mobile-api"), "target_id": _id("svc-gateway"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-mobile-api"), "target_id": _id("svc-orders"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-mobile-api"), "target_id": _id("svc-user-profile"), "properties": {"protocol": "GraphQL"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-recommendations"), "target_id": _id("svc-feature-store"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-recommendations"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-fraud"), "target_id": _id("svc-feature-store"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-fraud"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-data-lake"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka Connect"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-user-profile"), "target_id": _id("svc-auth"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-user-profile"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-media"), "target_id": _id("svc-events"), "properties": {"protocol": "SQS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-frontend"), "target_id": _id("svc-search"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-frontend"), "target_id": _id("svc-recommendations"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-frontend"), "target_id": _id("svc-user-profile"), "properties": {"protocol": "HTTPS"}},

    # ── Decisions → people ──────────────────────────────────────────────────
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-006"), "target_id": _id("sam-patel"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-006"), "target_id": _id("sarah-chen"), "properties": {}},
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-007"), "target_id": _id("sofia-martinez"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-007"), "target_id": _id("sarah-chen"), "properties": {}},
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-008"), "target_id": _id("nina-oconnell"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-008"), "target_id": _id("sarah-chen"), "properties": {}},
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-009"), "target_id": _id("rachel-green"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-009"), "target_id": _id("lisa-zhang"), "properties": {}},
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-010"), "target_id": _id("lena-johansson"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-010"), "target_id": _id("alex-rivera"), "properties": {}},

    # ── Decisions → services ────────────────────────────────────────────────
    {"rel_type": "AFFECTS", "source_id": _id("adr-006"), "target_id": _id("svc-mobile-api"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-007"), "target_id": _id("svc-orders"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-007"), "target_id": _id("svc-payments"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-007"), "target_id": _id("svc-inventory"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-008"), "target_id": _id("svc-data-lake"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-009"), "target_id": _id("svc-frontend"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-009"), "target_id": _id("svc-mobile-api"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-010"), "target_id": _id("svc-auth"), "properties": {}},

    # ── Incidents → services ────────────────────────────────────────────────
    {"rel_type": "IMPACTED", "source_id": _id("inc-2024-018"), "target_id": _id("svc-orders"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2024-018"), "target_id": _id("svc-auth"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-015"), "target_id": _id("svc-payments"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-019"), "target_id": _id("svc-media"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-019"), "target_id": _id("svc-frontend"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-022"), "target_id": _id("svc-data-lake"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-025"), "target_id": _id("svc-mobile-api"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-028"), "target_id": _id("svc-recommendations"), "properties": {}},

    # ── Incidents → responders ──────────────────────────────────────────────
    {"rel_type": "RESPONDED_TO", "source_id": _id("marcus-johnson"), "target_id": _id("inc-2024-018"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("david-okafor"), "target_id": _id("inc-2024-018"), "properties": {"role": "SRE"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("alex-rivera"), "target_id": _id("inc-2024-018"), "properties": {"role": "Auth owner"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("michael-taylor"), "target_id": _id("inc-2025-015"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("sofia-martinez"), "target_id": _id("inc-2025-015"), "properties": {"role": "Backend lead"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("james-wu"), "target_id": _id("inc-2025-019"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("david-okafor"), "target_id": _id("inc-2025-019"), "properties": {"role": "SRE"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("nina-oconnell"), "target_id": _id("inc-2025-022"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("yuki-tanaka"), "target_id": _id("inc-2025-022"), "properties": {"role": "Data eng"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("sam-patel"), "target_id": _id("inc-2025-025"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("emma-nakamura"), "target_id": _id("inc-2025-025"), "properties": {"role": "Eng manager"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("aisha-mohammed"), "target_id": _id("inc-2025-028"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("olivia-chen"), "target_id": _id("inc-2025-028"), "properties": {"role": "ML Infra"}},

    # ── Causal lineage ──────────────────────────────────────────────────────
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2024-018"), "target_id": _id("svc-auth"), "properties": {"mechanism": "PostgreSQL connection pool exhaustion under SAML validation load"}},
    {"rel_type": "LED_TO", "source_id": _id("inc-2024-018"), "target_id": _id("adr-001"), "properties": {"context": "Cascading REST failure led to event-driven architecture adoption"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-015"), "target_id": _id("svc-payments"), "properties": {"mechanism": "Idempotency keys lost during Redis failover"}},
    {"rel_type": "LED_TO", "source_id": _id("inc-2025-015"), "target_id": _id("doc-runbook-payments"), "properties": {"context": "Double-charge incident led to payment runbook creation"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-019"), "target_id": _id("svc-media"), "properties": {"mechanism": "URL hash collision after algorithm change without CDN cache invalidation"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-022"), "target_id": _id("svc-data-lake"), "properties": {"mechanism": "Airflow LocalExecutor deadlock on concurrent Delta Lake table writes"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-025"), "target_id": _id("svc-mobile-api"), "properties": {"mechanism": "Deprecated iOS 16 API in React Native bridge module"}},
    {"rel_type": "LED_TO", "source_id": _id("inc-2025-025"), "target_id": _id("proj-mercury"), "properties": {"context": "iOS crash incident accelerated mobile app rewrite planning"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-028"), "target_id": _id("svc-recommendations"), "properties": {"mechanism": "Training data pipeline duplicated popular items 10x, no skew detection"}},
    {"rel_type": "LED_TO", "source_id": _id("inc-2025-028"), "target_id": _id("proj-sentinel"), "properties": {"context": "Recommendation bias incident led to ML model governance initiative"}},
    {"rel_type": "LED_TO", "source_id": _id("inc-2025-028"), "target_id": _id("doc-data-quality"), "properties": {"context": "Added distribution skew tests to data quality framework"}},

    # ── Projects → people & services ────────────────────────────────────────
    {"rel_type": "LEADS_PROJECT", "source_id": _id("sam-patel"), "target_id": _id("proj-mercury"), "properties": {"role": "tech_lead"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("maya-kapoor"), "target_id": _id("proj-mercury"), "properties": {"role": "design_lead"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("nina-oconnell"), "target_id": _id("proj-atlas"), "properties": {"role": "tech_lead"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("olivia-chen"), "target_id": _id("proj-sentinel"), "properties": {"role": "tech_lead"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("aisha-mohammed"), "target_id": _id("proj-sentinel"), "properties": {"role": "ds_lead"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("rachel-green"), "target_id": _id("proj-growth-v2"), "properties": {"role": "pm"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("maya-kapoor"), "target_id": _id("proj-growth-v2"), "properties": {"role": "design_lead"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("lena-johansson"), "target_id": _id("proj-soc2"), "properties": {"role": "tech_lead"}},

    {"rel_type": "PART_OF", "source_id": _id("svc-mobile-api"), "target_id": _id("proj-mercury"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-data-lake"), "target_id": _id("proj-atlas"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-recommendations"), "target_id": _id("proj-sentinel"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-fraud"), "target_id": _id("proj-sentinel"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-frontend"), "target_id": _id("proj-growth-v2"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-recommendations"), "target_id": _id("proj-growth-v2"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-auth"), "target_id": _id("proj-soc2"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("proj-fortress"), "target_id": _id("proj-soc2"), "properties": {}},

    # ── Docs → related ──────────────────────────────────────────────────────
    {"rel_type": "REFERENCES", "source_id": _id("doc-k8s-guide"), "target_id": _id("svc-deployment"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-k8s-guide"), "target_id": _id("comp-terraform-modules"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-data-quality"), "target_id": _id("svc-data-lake"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-data-quality"), "target_id": _id("inc-2025-028"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-security-standards"), "target_id": _id("svc-auth"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-security-standards"), "target_id": _id("proj-fortress"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-security-standards"), "target_id": _id("proj-soc2"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-ml-playbook"), "target_id": _id("svc-feature-store"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-ml-playbook"), "target_id": _id("svc-recommendations"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-ml-playbook"), "target_id": _id("inc-2025-028"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-mobile-architecture"), "target_id": _id("svc-mobile-api"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-mobile-architecture"), "target_id": _id("adr-006"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-design-system"), "target_id": _id("comp-nexus-ui"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-design-system"), "target_id": _id("svc-frontend"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-runbook-payments"), "target_id": _id("svc-payments"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-runbook-payments"), "target_id": _id("inc-2025-015"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-experimentation"), "target_id": _id("adr-009"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-experimentation"), "target_id": _id("proj-growth-v2"), "properties": {}},

    # ── Cross-team collaboration ────────────────────────────────────────────
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-backend"), "target_id": _id("team-platform"), "properties": {"context": "Event-driven migration — backend services adopting Kafka consumer framework"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-backend"), "target_id": _id("team-data"), "properties": {"context": "CDC pipelines from order/payment/inventory PostgreSQL to data lake"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-data-science"), "target_id": _id("team-ml"), "properties": {"context": "Model development (DS) and deployment (ML Infra) partnership"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-mobile"), "target_id": _id("team-frontend"), "properties": {"context": "Shared design system (@nexus/ui) and user experience consistency"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-mobile"), "target_id": _id("team-backend"), "properties": {"context": "Mobile BFF aggregates backend service APIs"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-security"), "target_id": _id("team-platform"), "properties": {"context": "Istio mTLS and OPA policy deployment on Kubernetes"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-data"), "target_id": _id("team-data-science"), "properties": {"context": "Feature engineering and training data pipelines"}},

    # ── Person-to-person collaboration ──────────────────────────────────────
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("aisha-mohammed"), "target_id": _id("priya-patel"), "properties": {"context": "Re-ranker model fine-tuning and Feature Store integration for Aurora"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("nina-oconnell"), "target_id": _id("yuki-tanaka"), "properties": {"context": "Data quality framework and Airflow orchestration"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("maya-kapoor"), "target_id": _id("hannah-lee"), "properties": {"context": "Design system — Figma components to React implementation"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("lena-johansson"), "target_id": _id("alex-rivera"), "properties": {"context": "Project Fortress — zero trust and ABAC implementation"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("raj-krishnan"), "target_id": _id("david-okafor"), "properties": {"context": "Kubernetes operations and Terraform modules"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("chen-wei"), "target_id": _id("michael-taylor"), "properties": {"context": "Fraud detection integration with Payment Service"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("olivia-chen"), "target_id": _id("aisha-mohammed"), "properties": {"context": "Model serving pipeline and A/B testing framework for ML models"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("tom-andersen"), "target_id": _id("raj-krishnan"), "properties": {"context": "Local dev environment mirrors Kubernetes production setup"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("sofia-martinez"), "target_id": _id("marcus-johnson"), "properties": {"context": "Saga pattern implementation using the Kafka consumer framework"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("rachel-green"), "target_id": _id("lisa-zhang"), "properties": {"context": "Growth and search product strategy alignment"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("daniel-park"), "target_id": _id("david-okafor"), "properties": {"context": "Project Horizon planning — multi-region requirements and timeline"}},

    # ── Technology: USED_IN ──────────────────────────────────────────────────
    {"rel_type": "USED_IN", "source_id": _id("svc-feature-store"), "target_id": _id("svc-recommendations"), "properties": {"role": "User and item features for recommendation ranking"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-feature-store"), "target_id": _id("svc-fraud"), "properties": {"role": "Real-time features for fraud scoring (150 features, 8ms p99)"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-orders"), "properties": {"role": "Event consumption for saga pattern"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-inventory"), "properties": {"role": "Inventory update events processing"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-notifications"), "properties": {"role": "Notification trigger events"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-data-lake"), "properties": {"role": "CDC event ingestion via Kafka Connect"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-nexus-ui"), "target_id": _id("svc-frontend"), "properties": {"role": "120+ UI components for customer-facing web app"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-slo-framework"), "target_id": _id("svc-monitoring"), "properties": {"role": "SLO dashboards and error budget alerting"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-terraform-modules"), "target_id": _id("svc-deployment"), "properties": {"role": "Infrastructure provisioning for all AWS resources"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-monitoring"), "target_id": _id("doc-runbook-payments"), "properties": {"role": "Grafana dashboards for payment reconciliation monitoring"}},

    # ── Documents authored by ───────────────────────────────────────────────
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-k8s-guide"), "target_id": _id("raj-krishnan"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-data-quality"), "target_id": _id("yuki-tanaka"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-security-standards"), "target_id": _id("lena-johansson"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-ml-playbook"), "target_id": _id("olivia-chen"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-mobile-architecture"), "target_id": _id("sam-patel"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-design-system"), "target_id": _id("maya-kapoor"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-runbook-payments"), "target_id": _id("michael-taylor"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-experimentation"), "target_id": _id("rachel-green"), "properties": {}},

    # ── Mentorship ──────────────────────────────────────────────────────────
    {"rel_type": "MENTORS", "source_id": _id("marcus-johnson"), "target_id": _id("raj-krishnan"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("marcus-johnson"), "target_id": _id("tom-andersen"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("priya-patel"), "target_id": _id("olivia-chen"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("alex-rivera"), "target_id": _id("lena-johansson"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("emma-nakamura"), "target_id": _id("james-wu"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("emma-nakamura"), "target_id": _id("hannah-lee"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("sofia-martinez"), "target_id": _id("anna-kowalski"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("sofia-martinez"), "target_id": _id("kevin-brown"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("nina-oconnell"), "target_id": _id("yuki-tanaka"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("sarah-chen"), "target_id": _id("sofia-martinez"), "properties": {}},

    # ── SUPERSEDES (decision evolution) ─────────────────────────────────────
    {"rel_type": "EXTENDS", "source_id": _id("adr-010"), "target_id": _id("adr-003"), "properties": {"reason": "ABAC adds fine-grained attribute-based authorization on top of the JWT authentication from ADR-003"}},

    # ── Additional technology connections ───────────────────────────────────
    {"rel_type": "USED_IN", "source_id": _id("svc-events"), "target_id": _id("svc-payments"), "properties": {"role": "Payment confirmation and refund events"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-events"), "target_id": _id("svc-inventory"), "properties": {"role": "Inventory reservation and stock update events"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-events"), "target_id": _id("svc-notifications"), "properties": {"role": "Notification trigger events from all domain services"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-events"), "target_id": _id("svc-pricing"), "properties": {"role": "Price update events for cache invalidation"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-events"), "target_id": _id("svc-data-lake"), "properties": {"role": "All domain events ingested for analytics and reporting"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-auth"), "target_id": _id("svc-user-profile"), "properties": {"role": "JWT validation for user profile access"}},

    # ── Components → decisions ──────────────────────────────────────────────
    {"rel_type": "IMPLEMENTS", "source_id": _id("comp-kafka-consumer"), "target_id": _id("adr-001"), "properties": {"context": "Framework that standardizes event-driven patterns from ADR-001"}},
    {"rel_type": "IMPLEMENTS", "source_id": _id("comp-slo-framework"), "target_id": _id("doc-incident-response"), "properties": {"context": "SLO tracking informs incident severity classification"}},
    {"rel_type": "IMPLEMENTS", "source_id": _id("comp-nexus-ui"), "target_id": _id("adr-004"), "properties": {"context": "Component library migrated to RSC-compatible during Next.js 14 migration"}},

    # ═══════════════════════════════════════════════════════════════════════
    #  WAVE 2 relationships
    # ═══════════════════════════════════════════════════════════════════════

    # ── Wave2 team membership ───────────────────────────────────────────
    {"rel_type": "MEMBER_OF", "source_id": _id("ben-carter"), "target_id": _id("team-platform"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("grace-kim"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("omar-hassan"), "target_id": _id("team-frontend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("elena-volkov"), "target_id": _id("team-data"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("jason-wright"), "target_id": _id("team-security"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("lisa-nguyen"), "target_id": _id("team-ml"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("ahmed-ibrahim"), "target_id": _id("team-platform"), "properties": {"role": "SRE"}},
    {"rel_type": "MEMBER_OF", "source_id": _id("sarah-murphy"), "target_id": _id("team-commerce"), "properties": {"role": "PM"}},
    {"rel_type": "MEMBER_OF", "source_id": _id("wei-zhang"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("julia-santos"), "target_id": _id("team-commerce"), "properties": {"role": "design"}},
    {"rel_type": "MEMBER_OF", "source_id": _id("nate-wilson"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("kate-morrison"), "target_id": _id("team-frontend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("eric-johansson"), "target_id": _id("team-security"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("priya-sharma"), "target_id": _id("team-data-science"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("marco-rossi"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("tanya-okonkwo"), "target_id": _id("team-mobile"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("alex-petrov"), "target_id": _id("team-data"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("mia-chen"), "target_id": _id("team-frontend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("david-kim"), "target_id": _id("team-platform"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("emma-fischer"), "target_id": _id("team-qa"), "properties": {}},
    {"rel_type": "LEADS", "source_id": _id("emma-fischer"), "target_id": _id("team-qa"), "properties": {}},

    # Commerce team membership
    {"rel_type": "MEMBER_OF", "source_id": _id("sofia-martinez"), "target_id": _id("team-commerce"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("michael-taylor"), "target_id": _id("team-commerce"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("grace-kim"), "target_id": _id("team-commerce"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("anna-kowalski"), "target_id": _id("team-commerce"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("carlos-vega"), "target_id": _id("team-commerce"), "properties": {}},

    # ── Wave2 service ownership ─────────────────────────────────────────
    {"rel_type": "OWNS", "source_id": _id("grace-kim"), "target_id": _id("svc-shipping"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("wei-zhang"), "target_id": _id("svc-catalog"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("nate-wilson"), "target_id": _id("svc-reviews"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("kate-morrison"), "target_id": _id("svc-admin"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("david-kim"), "target_id": _id("svc-webhooks"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("marco-rossi"), "target_id": _id("svc-reporting"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("omar-hassan"), "target_id": _id("svc-chat"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("eric-johansson"), "target_id": _id("svc-vault"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("alex-petrov"), "target_id": _id("svc-analytics"), "properties": {}},

    # Component ownership
    {"rel_type": "OWNS", "source_id": _id("ahmed-ibrahim"), "target_id": _id("comp-chaos-platform"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("emma-fischer"), "target_id": _id("comp-e2e-framework"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("lisa-nguyen"), "target_id": _id("comp-mlflow"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("rachel-green"), "target_id": _id("comp-feature-flags"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("elena-volkov"), "target_id": _id("comp-cdc-pipeline"), "properties": {}},

    # ── Wave2 service dependencies ──────────────────────────────────────
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-orders"), "target_id": _id("svc-shipping"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-shipping"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-shipping"), "target_id": _id("svc-notifications"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-catalog"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-catalog"), "target_id": _id("svc-media"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-reviews"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-reviews"), "target_id": _id("svc-media"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-admin"), "target_id": _id("svc-gateway"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-admin"), "target_id": _id("svc-orders"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-admin"), "target_id": _id("svc-user-profile"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-webhooks"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-reporting"), "target_id": _id("svc-data-lake"), "properties": {"protocol": "Presto"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-chat"), "target_id": _id("svc-user-profile"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-chat"), "target_id": _id("svc-auth"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-vault"), "target_id": _id("svc-monitoring"), "properties": {"protocol": "Prometheus"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-analytics"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka Streams"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-frontend"), "target_id": _id("svc-catalog"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-frontend"), "target_id": _id("svc-reviews"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-frontend"), "target_id": _id("svc-chat"), "properties": {"protocol": "WebSocket"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-mobile-api"), "target_id": _id("svc-catalog"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-mobile-api"), "target_id": _id("svc-recommendations"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-mobile-api"), "target_id": _id("svc-chat"), "properties": {"protocol": "WebSocket"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-pricing"), "target_id": _id("svc-feature-store"), "properties": {"protocol": "gRPC"}},

    # All services depend on vault for secrets
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-auth"), "target_id": _id("svc-vault"), "properties": {"protocol": "Vault API"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-payments"), "target_id": _id("svc-vault"), "properties": {"protocol": "Vault API"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-orders"), "target_id": _id("svc-vault"), "properties": {"protocol": "Vault API"}},

    # ── Wave2 decisions → people/services ───────────────────────────────
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-011"), "target_id": _id("alex-petrov"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-011"), "target_id": _id("nina-oconnell"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-011"), "target_id": _id("svc-analytics"), "properties": {}},
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-012"), "target_id": _id("emma-fischer"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-012"), "target_id": _id("emma-nakamura"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-012"), "target_id": _id("comp-e2e-framework"), "properties": {}},
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-013"), "target_id": _id("elena-volkov"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-013"), "target_id": _id("nina-oconnell"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-013"), "target_id": _id("comp-cdc-pipeline"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-013"), "target_id": _id("svc-data-lake"), "properties": {}},
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-014"), "target_id": _id("nate-wilson"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-014"), "target_id": _id("sarah-murphy"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-014"), "target_id": _id("svc-reviews"), "properties": {}},
    {"rel_type": "PROPOSED_BY", "source_id": _id("adr-015"), "target_id": _id("ahmed-ibrahim"), "properties": {}},
    {"rel_type": "APPROVED_BY", "source_id": _id("adr-015"), "target_id": _id("david-okafor"), "properties": {}},
    {"rel_type": "AFFECTS", "source_id": _id("adr-015"), "target_id": _id("comp-chaos-platform"), "properties": {}},

    # ── Wave2 incidents → services & responders ─────────────────────────
    {"rel_type": "IMPACTED", "source_id": _id("inc-2024-022"), "target_id": _id("svc-gateway"), "properties": {}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("raj-krishnan"), "target_id": _id("inc-2024-022"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("david-okafor"), "target_id": _id("inc-2024-022"), "properties": {"role": "SRE"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2024-022"), "target_id": _id("svc-gateway"), "properties": {"mechanism": "Route53 health check interval too long for ELB failover detection"}},

    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-030"), "target_id": _id("svc-shipping"), "properties": {}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("grace-kim"), "target_id": _id("inc-2025-030"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("sofia-martinez"), "target_id": _id("inc-2025-030"), "properties": {"role": "Backend lead"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-030"), "target_id": _id("svc-shipping"), "properties": {"mechanism": "FedEx API outage with no multi-carrier fallback"}},

    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-032"), "target_id": _id("svc-vault"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-032"), "target_id": _id("svc-auth"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-032"), "target_id": _id("svc-payments"), "properties": {}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("eric-johansson"), "target_id": _id("inc-2025-032"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("lena-johansson"), "target_id": _id("inc-2025-032"), "properties": {"role": "Security"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("david-okafor"), "target_id": _id("inc-2025-032"), "properties": {"role": "SRE"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-032"), "target_id": _id("svc-vault"), "properties": {"mechanism": "KMS key scheduled for deletion broke Vault auto-unseal"}},
    {"rel_type": "LED_TO", "source_id": _id("inc-2025-032"), "target_id": _id("doc-vault-runbook"), "properties": {"context": "Vault seal incident led to runbook update with emergency unseal procedures"}},

    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-035"), "target_id": _id("svc-catalog"), "properties": {}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("wei-zhang"), "target_id": _id("inc-2025-035"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("diego-reyes"), "target_id": _id("inc-2025-035"), "properties": {"role": "SRE"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-035"), "target_id": _id("svc-catalog"), "properties": {"mechanism": "Elasticsearch data node disk space exhaustion triggered shard relocation"}},

    # ── Wave2 projects → people & services ──────────────────────────────
    {"rel_type": "LEADS_PROJECT", "source_id": _id("sofia-martinez"), "target_id": _id("proj-marketplace"), "properties": {"role": "tech_lead"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("sarah-murphy"), "target_id": _id("proj-marketplace"), "properties": {"role": "pm"}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("carlos-vega"), "target_id": _id("proj-perf"), "properties": {"role": "tech_lead"}},
    {"rel_type": "PART_OF", "source_id": _id("svc-orders"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-payments"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-catalog"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-shipping"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-pricing"), "target_id": _id("proj-perf"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-gateway"), "target_id": _id("proj-perf"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-search"), "target_id": _id("proj-perf"), "properties": {}},

    # ── Wave2 docs → references ─────────────────────────────────────────
    {"rel_type": "REFERENCES", "source_id": _id("doc-shipping-runbook"), "target_id": _id("svc-shipping"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-shipping-runbook"), "target_id": _id("inc-2025-030"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-chaos-playbook"), "target_id": _id("comp-chaos-platform"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-chaos-playbook"), "target_id": _id("svc-monitoring"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-testing-standards"), "target_id": _id("comp-e2e-framework"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-testing-standards"), "target_id": _id("svc-deployment"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-vault-runbook"), "target_id": _id("svc-vault"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-vault-runbook"), "target_id": _id("inc-2025-032"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-analytics-guide"), "target_id": _id("svc-analytics"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-analytics-guide"), "target_id": _id("svc-data-lake"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-graphql-guide"), "target_id": _id("svc-mobile-api"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-graphql-guide"), "target_id": _id("adr-006"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-i18n-guide"), "target_id": _id("svc-frontend"), "properties": {}},

    # ── Wave2 docs authored by ──────────────────────────────────────────
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-shipping-runbook"), "target_id": _id("grace-kim"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-chaos-playbook"), "target_id": _id("ahmed-ibrahim"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-testing-standards"), "target_id": _id("emma-fischer"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-vault-runbook"), "target_id": _id("eric-johansson"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-analytics-guide"), "target_id": _id("alex-petrov"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-graphql-guide"), "target_id": _id("sam-patel"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-i18n-guide"), "target_id": _id("mia-chen"), "properties": {}},

    # ── Wave2 USED_IN (technology connections) ──────────────────────────
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-shipping"), "properties": {"role": "Shipping event consumption"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-pricing"), "properties": {"role": "Price update event consumption"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-reviews"), "properties": {"role": "Review event consumption for aggregation"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-webhooks"), "properties": {"role": "Domain event consumption for webhook delivery"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-analytics"), "properties": {"role": "User event consumption for analytics"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-cdc-pipeline"), "target_id": _id("svc-data-lake"), "properties": {"role": "Real-time CDC from PostgreSQL to data lake"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-feature-flags"), "target_id": _id("svc-frontend"), "properties": {"role": "LaunchDarkly React SDK for feature toggles"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-feature-flags"), "target_id": _id("svc-search"), "properties": {"role": "Feature flag for Aurora beta traffic routing"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-feature-flags"), "target_id": _id("svc-recommendations"), "properties": {"role": "Model version flag for recommendation A/B testing"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-e2e-framework"), "target_id": _id("svc-frontend"), "properties": {"role": "E2E testing of customer-facing web flows"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-e2e-framework"), "target_id": _id("svc-admin"), "properties": {"role": "E2E testing of admin dashboard workflows"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-mlflow"), "target_id": _id("svc-recommendations"), "properties": {"role": "Experiment tracking for recommendation model iterations"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-mlflow"), "target_id": _id("svc-fraud"), "properties": {"role": "Experiment tracking for fraud model retraining"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-nexus-ui"), "target_id": _id("svc-admin"), "properties": {"role": "Shared UI components for admin dashboard"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-vault"), "target_id": _id("svc-deployment"), "properties": {"role": "Secret injection during deployment pipeline"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-monitoring"), "target_id": _id("comp-chaos-platform"), "properties": {"role": "Monitoring blast radius during chaos drills"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-analytics"), "target_id": _id("svc-data-lake"), "properties": {"role": "Aggregated metrics flow to data lake for long-term storage"}},

    # ── Wave2 mentorship ────────────────────────────────────────────────
    {"rel_type": "MENTORS", "source_id": _id("david-okafor"), "target_id": _id("ahmed-ibrahim"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("david-okafor"), "target_id": _id("diego-reyes"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("marcus-johnson"), "target_id": _id("ben-carter"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("alex-rivera"), "target_id": _id("jason-wright"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("alex-rivera"), "target_id": _id("eric-johansson"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("priya-patel"), "target_id": _id("lisa-nguyen"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("emma-nakamura"), "target_id": _id("omar-hassan"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("emma-nakamura"), "target_id": _id("mia-chen"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("nina-oconnell"), "target_id": _id("elena-volkov"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("nina-oconnell"), "target_id": _id("alex-petrov"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("sofia-martinez"), "target_id": _id("grace-kim"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("aisha-mohammed"), "target_id": _id("priya-sharma"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("sam-patel"), "target_id": _id("tanya-okonkwo"), "properties": {}},

    # ── Wave2 collaboration ─────────────────────────────────────────────
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("grace-kim"), "target_id": _id("anna-kowalski"), "properties": {"context": "Shipping and inventory coordination for order fulfillment"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("wei-zhang"), "target_id": _id("priya-patel"), "properties": {"context": "Catalog data feeds search index via Project Aurora"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("elena-volkov"), "target_id": _id("marcus-johnson"), "properties": {"context": "Debezium CDC uses Kafka Connect on the event platform"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("omar-hassan"), "target_id": _id("hannah-lee"), "properties": {"context": "Chat widget integration in web app frontend"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("eric-johansson"), "target_id": _id("lena-johansson"), "properties": {"context": "Vault secret management for Project Fortress security initiative"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("priya-sharma"), "target_id": _id("aisha-mohammed"), "properties": {"context": "Query understanding model for Aurora Phase 3 conversational search"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("emma-fischer"), "target_id": _id("hannah-lee"), "properties": {"context": "Visual regression testing for @nexus/ui component library"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-qa"), "target_id": _id("team-frontend"), "properties": {"context": "E2E test coverage for all customer-facing flows"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-qa"), "target_id": _id("team-backend"), "properties": {"context": "Contract testing and API integration tests"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("team-commerce"), "target_id": _id("team-data"), "properties": {"context": "Commerce data pipeline for analytics and reporting"}},

    # ── Wave2 IMPLEMENTS ────────────────────────────────────────────────
    {"rel_type": "IMPLEMENTS", "source_id": _id("comp-cdc-pipeline"), "target_id": _id("adr-013"), "properties": {"context": "Debezium connectors implementing CDC decision"}},
    {"rel_type": "IMPLEMENTS", "source_id": _id("comp-chaos-platform"), "target_id": _id("adr-015"), "properties": {"context": "Chaos engineering platform implementing resilience testing decision"}},
    {"rel_type": "IMPLEMENTS", "source_id": _id("comp-e2e-framework"), "target_id": _id("adr-012"), "properties": {"context": "Playwright framework implementing the Cypress migration decision"}},
    {"rel_type": "IMPLEMENTS", "source_id": _id("comp-feature-flags"), "target_id": _id("adr-009"), "properties": {"context": "SDK wrapper implementing LaunchDarkly feature flag decision"}},

    # ── Aurora Phase 3 relationships ────────────────────────────────────
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("priya-sharma"), "target_id": _id("proj-aurora"), "properties": {"role": "query understanding model"}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("emma-nakamura"), "target_id": _id("proj-aurora"), "properties": {"role": "conversational search UI"}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("maya-kapoor"), "target_id": _id("proj-aurora"), "properties": {"role": "search UX design"}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("aisha-mohammed"), "target_id": _id("proj-aurora"), "properties": {"role": "re-ranker model fine-tuning"}},

    # ═══════════════════════════════════════════════════════════════════════
    #  WAVE 3 relationships
    # ═══════════════════════════════════════════════════════════════════════

    # Team membership
    {"rel_type": "MEMBER_OF", "source_id": _id("ryan-obrien"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("ryan-obrien"), "target_id": _id("team-commerce"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("natasha-ivanova"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("natasha-ivanova"), "target_id": _id("team-commerce"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("jake-henderson"), "target_id": _id("team-frontend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("amara-osei"), "target_id": _id("team-data"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("lucas-weber"), "target_id": _id("team-platform"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("mei-lin"), "target_id": _id("team-ml"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("pedro-silva"), "target_id": _id("team-platform"), "properties": {"role": "SRE"}},
    {"rel_type": "MEMBER_OF", "source_id": _id("anya-kozlov"), "target_id": _id("team-data"), "properties": {"role": "PM"}},
    {"rel_type": "MEMBER_OF", "source_id": _id("tyler-jackson"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("sophie-dubois"), "target_id": _id("team-frontend"), "properties": {"role": "UX research"}},

    # Service ownership
    {"rel_type": "OWNS", "source_id": _id("ryan-obrien"), "target_id": _id("svc-promotions"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("natasha-ivanova"), "target_id": _id("svc-tax"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("tyler-jackson"), "target_id": _id("svc-search-index"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("lucas-weber"), "target_id": _id("svc-backstage"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("mei-lin"), "target_id": _id("svc-embedding"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("amara-osei"), "target_id": _id("comp-data-quality-suite"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("lucas-weber"), "target_id": _id("comp-backstage-plugins"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("mei-lin"), "target_id": _id("comp-embedding-cache"), "properties": {}},

    # Service dependencies
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-orders"), "target_id": _id("svc-promotions"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-orders"), "target_id": _id("svc-tax"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-promotions"), "target_id": _id("svc-pricing"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-promotions"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-tax"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-search-index"), "target_id": _id("svc-catalog"), "properties": {"protocol": "CDC events"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-search-index"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-search"), "target_id": _id("svc-search-index"), "properties": {"protocol": "Elasticsearch"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-search"), "target_id": _id("svc-embedding"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-embedding"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},

    # Incidents
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-037"), "target_id": _id("svc-promotions"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-037"), "target_id": _id("svc-orders"), "properties": {}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("ryan-obrien"), "target_id": _id("inc-2025-037"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("carlos-vega"), "target_id": _id("inc-2025-037"), "properties": {"role": "Pricing owner"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-037"), "target_id": _id("svc-promotions"), "properties": {"mechanism": "Circular promotion rule caused infinite evaluation loop"}},

    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-039"), "target_id": _id("svc-embedding"), "properties": {}},
    {"rel_type": "IMPACTED", "source_id": _id("inc-2025-039"), "target_id": _id("svc-search"), "properties": {}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("mei-lin"), "target_id": _id("inc-2025-039"), "properties": {"role": "IC"}},
    {"rel_type": "RESPONDED_TO", "source_id": _id("priya-patel"), "target_id": _id("inc-2025-039"), "properties": {"role": "ML Infra lead"}},
    {"rel_type": "CAUSED_BY", "source_id": _id("inc-2025-039"), "target_id": _id("svc-embedding"), "properties": {"mechanism": "OpenAI rate limit reduction caused retry storm that starved new documents"}},
    {"rel_type": "LED_TO", "source_id": _id("inc-2025-039"), "target_id": _id("doc-embedding-ops"), "properties": {"context": "Embedding backlog incident led to major runbook revision adding fallback procedures and rate-limit playbook"}},

    # Docs
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-promotion-rules"), "target_id": _id("ryan-obrien"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-embedding-ops"), "target_id": _id("mei-lin"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-backstage-guide"), "target_id": _id("lucas-weber"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-data-lineage"), "target_id": _id("amara-osei"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-promotion-rules"), "target_id": _id("svc-promotions"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-promotion-rules"), "target_id": _id("svc-pricing"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-embedding-ops"), "target_id": _id("svc-embedding"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-embedding-ops"), "target_id": _id("inc-2025-039"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-backstage-guide"), "target_id": _id("svc-backstage"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-backstage-guide"), "target_id": _id("comp-backstage-plugins"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-data-lineage"), "target_id": _id("svc-data-lake"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-data-lineage"), "target_id": _id("comp-cdc-pipeline"), "properties": {}},

    # USED_IN
    {"rel_type": "USED_IN", "source_id": _id("comp-embedding-cache"), "target_id": _id("svc-embedding"), "properties": {"role": "Cache layer reducing OpenAI API costs by 75%"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-backstage-plugins"), "target_id": _id("svc-backstage"), "properties": {"role": "Custom plugins for service catalog and health scoring"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-data-quality-suite"), "target_id": _id("svc-data-lake"), "properties": {"role": "Data quality checks on all data lake tables"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-cdc-pipeline"), "target_id": _id("svc-search-index"), "properties": {"role": "CDC events trigger Elasticsearch index updates"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-embedding"), "target_id": _id("svc-search"), "properties": {"role": "Vector embeddings for Pinecone ANN search in Project Aurora"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-search-index"), "properties": {"role": "CDC event consumption for index sync"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-kafka-consumer"), "target_id": _id("svc-promotions"), "properties": {"role": "Promotion event processing"}},

    # Collaboration
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("mei-lin"), "target_id": _id("priya-patel"), "properties": {"context": "Embedding pipeline for Project Aurora vector search"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("tyler-jackson"), "target_id": _id("wei-zhang"), "properties": {"context": "Catalog CDC events feed search index updates"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("tyler-jackson"), "target_id": _id("elena-volkov"), "properties": {"context": "Debezium CDC pipeline for search index sync"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("ryan-obrien"), "target_id": _id("carlos-vega"), "properties": {"context": "Promotions and pricing integration for checkout"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("natasha-ivanova"), "target_id": _id("michael-taylor"), "properties": {"context": "Tax calculation integration in payment flow"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("amara-osei"), "target_id": _id("yuki-tanaka"), "properties": {"context": "Data quality framework and dbt model testing"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("lucas-weber"), "target_id": _id("tom-andersen"), "properties": {"context": "Developer portal and local dev environment integration"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("sophie-dubois"), "target_id": _id("maya-kapoor"), "properties": {"context": "User research informing design system evolution"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("sophie-dubois"), "target_id": _id("lisa-zhang"), "properties": {"context": "Search UX research for Project Aurora"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("jake-henderson"), "target_id": _id("julia-santos"), "properties": {"context": "Checkout UX optimization with motion design"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("pedro-silva"), "target_id": _id("diego-reyes"), "properties": {"context": "Logging and monitoring stack operations"}},

    # Mentorship
    {"rel_type": "MENTORS", "source_id": _id("marcus-johnson"), "target_id": _id("lucas-weber"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("david-okafor"), "target_id": _id("pedro-silva"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("priya-patel"), "target_id": _id("mei-lin"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("nina-oconnell"), "target_id": _id("amara-osei"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("sofia-martinez"), "target_id": _id("natasha-ivanova"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("emma-nakamura"), "target_id": _id("jake-henderson"), "properties": {}},

    # Aurora search pipeline chain
    {"rel_type": "PART_OF", "source_id": _id("svc-search-index"), "target_id": _id("proj-aurora"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-embedding"), "target_id": _id("proj-aurora"), "properties": {}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("tyler-jackson"), "target_id": _id("proj-aurora"), "properties": {"role": "search index maintenance"}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("mei-lin"), "target_id": _id("proj-aurora"), "properties": {"role": "embedding pipeline"}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("sophie-dubois"), "target_id": _id("proj-aurora"), "properties": {"role": "search UX research"}},

    # Marketplace project
    {"rel_type": "PART_OF", "source_id": _id("svc-promotions"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-tax"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("natasha-ivanova"), "target_id": _id("proj-marketplace"), "properties": {"role": "tax compliance for sellers"}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("ryan-obrien"), "target_id": _id("proj-marketplace"), "properties": {"role": "seller promotion rules"}},

    # ═══════════════════════════════════════════════════════════════════════
    #  WAVE 3 EXTRA relationships
    # ═══════════════════════════════════════════════════════════════════════

    # Team membership
    {"rel_type": "MEMBER_OF", "source_id": _id("chris-morgan"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("chris-morgan"), "target_id": _id("team-commerce"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("sarah-anderson"), "target_id": _id("team-frontend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("rashid-al-farsi"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("jenny-clark"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("alex-thompson"), "target_id": _id("team-data"), "properties": {}},

    # Ownership
    {"rel_type": "OWNS", "source_id": _id("chris-morgan"), "target_id": _id("svc-billing"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("rashid-al-farsi"), "target_id": _id("svc-address"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("jenny-clark"), "target_id": _id("svc-support"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("alex-thompson"), "target_id": _id("svc-looker"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("nate-wilson"), "target_id": _id("comp-ai-moderation"), "properties": {}},

    # Service dependencies
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-billing"), "target_id": _id("svc-payments"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-billing"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-billing"), "target_id": _id("svc-notifications"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-billing"), "target_id": _id("svc-reporting"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-shipping"), "target_id": _id("svc-address"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-tax"), "target_id": _id("svc-address"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-fraud"), "target_id": _id("svc-address"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-support"), "target_id": _id("svc-user-profile"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-support"), "target_id": _id("svc-orders"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-support"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-looker"), "target_id": _id("svc-data-lake"), "properties": {"protocol": "Presto"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-frontend"), "target_id": _id("svc-promotions"), "properties": {"protocol": "HTTPS"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-mobile-api"), "target_id": _id("svc-promotions"), "properties": {"protocol": "gRPC"}},

    # USED_IN
    {"rel_type": "USED_IN", "source_id": _id("comp-ai-moderation"), "target_id": _id("svc-reviews"), "properties": {"role": "Content moderation for user reviews"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-ai-moderation"), "target_id": _id("svc-chat"), "properties": {"role": "Real-time message moderation"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-ai-moderation"), "target_id": _id("svc-support"), "properties": {"role": "AI ticket classification"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-looker"), "target_id": _id("doc-bi-standards"), "properties": {"role": "BI dashboard governance and standards"}},
    {"rel_type": "USED_IN", "source_id": _id("svc-address"), "target_id": _id("svc-shipping"), "properties": {"role": "Address validation for shipping labels"}},

    # Docs
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-billing-guide"), "target_id": _id("chris-morgan"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-support-runbook"), "target_id": _id("jenny-clark"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-bi-standards"), "target_id": _id("alex-thompson"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-billing-guide"), "target_id": _id("svc-billing"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-billing-guide"), "target_id": _id("svc-payments"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-support-runbook"), "target_id": _id("svc-support"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-support-runbook"), "target_id": _id("svc-chat"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-bi-standards"), "target_id": _id("svc-looker"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-bi-standards"), "target_id": _id("svc-data-lake"), "properties": {}},

    # Marketplace project
    {"rel_type": "PART_OF", "source_id": _id("svc-billing"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("chris-morgan"), "target_id": _id("proj-marketplace"), "properties": {"role": "seller billing & payout"}},

    # Collaboration
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("chris-morgan"), "target_id": _id("michael-taylor"), "properties": {"context": "Billing and payment service integration for subscriptions"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("rashid-al-farsi"), "target_id": _id("grace-kim"), "properties": {"context": "Address validation for shipping label generation"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("jenny-clark"), "target_id": _id("omar-hassan"), "properties": {"context": "Chat escalation to support ticket integration"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("alex-thompson"), "target_id": _id("anya-kozlov"), "properties": {"context": "BI dashboard standards and self-serve analytics"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("sarah-anderson"), "target_id": _id("hannah-lee"), "properties": {"context": "Product page SSR optimization and SEO"}},

    # ═══════════════════════════════════════════════════════════════════════
    #  WAVE 3 FINAL relationships
    # ═══════════════════════════════════════════════════════════════════════

    {"rel_type": "MEMBER_OF", "source_id": _id("zara-ahmed"), "target_id": _id("team-mobile"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("leo-fernandez"), "target_id": _id("team-platform"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("helen-zhao"), "target_id": _id("team-backend"), "properties": {}},
    {"rel_type": "MEMBER_OF", "source_id": _id("helen-zhao"), "target_id": _id("team-commerce"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("helen-zhao"), "target_id": _id("svc-seller-api"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("alex-rivera"), "target_id": _id("comp-rate-limiter"), "properties": {}},
    {"rel_type": "OWNS", "source_id": _id("sofia-martinez"), "target_id": _id("comp-idempotency"), "properties": {}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-seller-api"), "target_id": _id("svc-auth"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-seller-api"), "target_id": _id("svc-catalog"), "properties": {"protocol": "gRPC"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-seller-api"), "target_id": _id("svc-payments"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "DEPENDS_ON", "source_id": _id("svc-seller-api"), "target_id": _id("svc-events"), "properties": {"protocol": "Kafka"}},
    {"rel_type": "PART_OF", "source_id": _id("svc-seller-api"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-support"), "target_id": _id("proj-ai-support"), "properties": {}},
    {"rel_type": "PART_OF", "source_id": _id("svc-chat"), "target_id": _id("proj-ai-support"), "properties": {}},
    {"rel_type": "LEADS_PROJECT", "source_id": _id("jenny-clark"), "target_id": _id("proj-ai-support"), "properties": {"role": "tech_lead"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-rate-limiter"), "target_id": _id("svc-gateway"), "properties": {"role": "Per-tenant rate limiting at the gateway"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-rate-limiter"), "target_id": _id("svc-seller-api"), "properties": {"role": "Per-seller rate limiting"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-rate-limiter"), "target_id": _id("svc-webhooks"), "properties": {"role": "Outbound webhook rate limiting per endpoint"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-idempotency"), "target_id": _id("svc-orders"), "properties": {"role": "Idempotent order creation"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-idempotency"), "target_id": _id("svc-payments"), "properties": {"role": "Idempotent payment capture"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-idempotency"), "target_id": _id("svc-webhooks"), "properties": {"role": "Idempotent webhook delivery"}},
    {"rel_type": "USED_IN", "source_id": _id("comp-ai-moderation"), "target_id": _id("svc-support"), "properties": {"role": "AI ticket classification"}},
    {"rel_type": "LED_TO", "source_id": _id("inc-2025-015"), "target_id": _id("comp-idempotency"), "properties": {"context": "Payment double-charge incident led to creating persistent idempotency library"}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-seller-api-spec"), "target_id": _id("helen-zhao"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-onboarding-mobile"), "target_id": _id("sam-patel"), "properties": {}},
    {"rel_type": "AUTHORED_BY", "source_id": _id("doc-cost-optimization"), "target_id": _id("david-okafor"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-seller-api-spec"), "target_id": _id("svc-seller-api"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-seller-api-spec"), "target_id": _id("proj-marketplace"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-seller-api-spec"), "target_id": _id("doc-api-standards"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-onboarding-mobile"), "target_id": _id("doc-mobile-architecture"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-cost-optimization"), "target_id": _id("comp-terraform-modules"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-cost-optimization"), "target_id": _id("comp-embedding-cache"), "properties": {}},
    {"rel_type": "REFERENCES", "source_id": _id("doc-cost-optimization"), "target_id": _id("comp-backstage-plugins"), "properties": {}},
    {"rel_type": "CONTRIBUTES_TO", "source_id": _id("helen-zhao"), "target_id": _id("proj-marketplace"), "properties": {"role": "seller API architecture"}},
    {"rel_type": "MENTORS", "source_id": _id("sam-patel"), "target_id": _id("zara-ahmed"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("raj-krishnan"), "target_id": _id("leo-fernandez"), "properties": {}},
    {"rel_type": "MENTORS", "source_id": _id("sofia-martinez"), "target_id": _id("helen-zhao"), "properties": {}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("helen-zhao"), "target_id": _id("sarah-murphy"), "properties": {"context": "Seller API requirements and marketplace product strategy"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("leo-fernandez"), "target_id": _id("raj-krishnan"), "properties": {"context": "CDN and edge function deployment on Kubernetes"}},
    {"rel_type": "COLLABORATES_WITH", "source_id": _id("zara-ahmed"), "target_id": _id("tanya-okonkwo"), "properties": {"context": "Mobile push notification and offline sync"}},
]
