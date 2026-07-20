from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_staging_deploy_uses_independent_topology_and_blocks_production_names() -> None:
    source = _read("scripts/deploy-staging.sh")

    assert "set -Eeuo pipefail" in source
    assert "STAGING_APP_DIR=\"${STAGING_APP_DIR:-/home/harcker8119/BI-RMP-STAGING}\"" in source
    assert "STAGING_BACKEND_SERVICE=\"${STAGING_BACKEND_SERVICE:-bi-rmp-staging.service}\"" in source
    assert "STAGING_BACKEND_PORT=\"${STAGING_BACKEND_PORT:-8101}\"" in source
    assert "STAGING_N8N_HOST_PORT=\"${STAGING_N8N_HOST_PORT:-5679}\"" in source
    assert "STAGING_GATEWAY_PORT=\"${STAGING_GATEWAY_PORT:-8180}\"" in source
    assert "STAGING_LOCK_FILE=\"${STAGING_LOCK_FILE:-/tmp/bi-rmp-staging-deploy.lock}\"" in source
    assert "BLOCKED_PRODUCTION_COLLISION" in source
    assert "/home/harcker8119/BI-RMP\"" in source
    assert "bi-rmp.service" in source
    assert "8001" in source
    assert "5678" in source
    assert "8080" in source
    assert "bi-rmp-n8n" in source
    assert "git switch main" not in source
    assert "deploy-production.sh" not in source
    assert "ALLOW_PRODUCTION_DB" in source
    assert "qlhykeeyjaoikczoambe" in source


def test_staging_deploy_rejects_schema_changes_except_c2_rehearsal_sql() -> None:
    source = _read("scripts/deploy-staging.sh")

    assert "git diff --name-only" in source
    assert "-- database supabase" in source
    assert "database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql" in source
    assert "database or Supabase schema changes are present" in source
    assert "migration" not in source.lower().replace("no migrations", "")


def test_staging_compose_uses_isolated_names_ports_and_volumes() -> None:
    source = _read("infra/n8n/docker-compose.staging.yml")

    assert "name: ${COMPOSE_PROJECT_NAME:-bi-rmp-staging-n8n}" in source
    assert "container_name: ${STAGING_N8N_CONTAINER:-bi-rmp-staging-n8n}" in source
    assert "container_name: ${STAGING_N8N_POSTGRES_CONTAINER:-bi-rmp-staging-n8n-postgres}" in source
    assert "127.0.0.1:${N8N_HOST_PORT:-5679}:5678" in source
    assert "staging_n8n_data" in source
    assert "staging_n8n_postgres_data" in source
    assert "BI_RMP_LINE_ALLOWED_USER_IDS" in source


def test_staging_nginx_exposes_only_customer_paths() -> None:
    source = _read("infra/nginx/bi-rmp-staging-gateway.conf.example")

    assert "server_tokens off;" in source
    assert "location = /health" in source
    assert "location = /register" in source
    assert "location = /api/liff/config" in source
    assert "location = /api/liff/business/register" in source
    assert "location = /webhook/line/events" in source
    assert "proxy_pass http://127.0.0.1:8101" in source
    assert "proxy_pass http://127.0.0.1:5679/webhook/line/events" in source
    assert "return 404;" in source
    assert "/rest/" not in source
    assert "/docs" not in source


def test_staging_env_template_contains_only_placeholders_for_secrets() -> None:
    source = _read(".env.staging.example")

    assert "APP_ENV=staging" in source
    assert "SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe" in source
    assert "SUPABASE_URL=https://qlhykeeyjaoikczoambe.supabase.co" in source
    assert "ALLOW_DATABASE_WRITES=true" in source
    assert "ALLOW_PRODUCTION_DB=false" in source
    for key in (
        "DATABASE_URL",
        "BI_RMP_INTERNAL_API_KEY",
        "LINE_CHANNEL_ACCESS_TOKEN",
        "LINE_CHANNEL_SECRET",
        "N8N_ENCRYPTION_KEY",
        "N8N_DB_PASSWORD",
        "N8N_WORKFLOW_ID",
    ):
        assert f"{key}=\n" in source


def test_rollback_rehearsal_is_transactional_and_does_not_delete_shared_client() -> None:
    source = _read("database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql")

    assert source.strip().endswith("ROLLBACK;")
    assert "BEGIN;" in source
    assert "C2-E2E-TEST-%" in source
    assert "DELETE FROM clients" not in source
    assert "DELETE FROM business" in source
    assert "DELETE FROM service_tasks" in source
    assert "DELETE FROM crawl_jobs" in source
    assert "DELETE FROM crawl_posts" in source
    assert "DELETE FROM crawl_comments" in source
