# Architecture Review & System Overview

Baseline Commit: `10e0ec6`
Date: 2026-07-20

---

## 1. System Architecture

BI-RMP is a modular Web application and crawler platform built with:
- **Backend API**: Modular FastAPI service (`Backend/api/main.py`) running on Python 3.11 with `uvicorn`.
- **Workflow Automation & Dispatch**: n8n containerized service for webhook handling, push notifications, and scheduling.
- **Database & Persistence**: Supabase PostgreSQL (`Backend/core/supabase.py` and `database/schema.sql`).
- **Crawler Subsystem**: Platform-specific crawlers (PTT, Google Maps) driven by `Backend/runner.py`.

> **Note on Architecture**: The system is designed as a modular monolith with event-driven workflow integration (n8n), rather than an over-engineered microservices network.

---

## 2. Capability Matrix

| Feature Module | Current Implementation Status | Production / Staging Readiness |
| :--- | :--- | :--- |
| **Database Schema** | Unified 4-layer entity model (`clients` -> `business` -> `service_tasks` -> `crawl_jobs` -> `crawl_posts` -> `crawl_comments`) | Ready (Supabase cutover schema `database/schema.sql`) |
| **PTT Crawler** | Readonly & Staging ingestion tested | Ready (`Backend/crawlers/ptt_crawler.py`) |
| **Google Maps Crawler** | Readonly & Staging ingestion tested | Ready (`Backend/crawlers/google_maps_crawler.py`) |
| **LINE LIFF Business Registration** | FastAPI endpoints & allowlist guard implemented | Staging code prepared; awaiting live LINE credentials |
| **LINE Multi-Tenant Isolation** | Tenant isolation logic & Gate C1 validation | Passed 343 local unit & integration tests |
| **Staging Deployment Topology** | Isolated ports (8101/5679/8180) and scripts prepared | Scripts verified (`scripts/bootstrap-staging-host.sh`, `scripts/deploy-staging.sh`) |
| **AI Analysis Pipeline** | Baseline contract & mocks implemented | Baseline phase; full LLM pipeline pending deployment |
| **Alert Notification Pipeline** | Threshold & message logger prepared | Baseline phase; n8n workflow integration in progress |

---

## 3. Risks & Technical Debt

1. **External Dependency Configuration**: Gate C2 deployment is waiting for external configuration (Staging LINE Channel, Public HTTPS Domain, Live Supabase DATABASE_URL).
2. **Windows Sandbox Launcher Limitations**: Host process launcher on Windows has ACL issues with `NUL` handles during sandboxed execution, requiring local execution or Git Bash fallback for bash script tests.
3. **Database Preflight Historical Note**: Historical preflight cutover note (reference `crawl_posts.id = 393`) requires clean DB rebuild or cutover script execution during live cutover window.

---

## 4. Key Entry Points & Best Practices

- **Crawler Entry Point**: Always use `Backend/runner.py`.
- **Database Write Layer**: Always use `Backend/core/supabase.py`.
- **Secret Safety**: Never commit `.env` files or write secrets to documentation/logs.
