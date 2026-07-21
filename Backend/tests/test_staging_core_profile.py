from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_core_profile_defers_line_and_liff_requirements() -> None:
    deploy = _read("scripts/deploy-staging.sh")
    verify = _read("scripts/verify-staging.sh")

    for source in (deploy, verify):
        assert 'STAGING_DEPLOY_PROFILE="${STAGING_DEPLOY_PROFILE:-full}"' in source
        assert "unsupported staging deploy profile" in source
        assert "core_required_env_keys" in source
        assert "full_line_env_keys" in source

    assert "LINE_INTEGRATION=DEFERRED" in deploy
    assert "LIFF_INTEGRATION=DEFERRED" in deploy
    assert "PUBLIC_HTTPS=DEFERRED" in deploy
    assert "deploy_n8n_core" in deploy
    assert "deploy_n8n_workflow" in deploy
    assert 'TARGET_BRANCH="feature/core-shared-staging-profile"' in deploy
    assert "verify_production_unchanged" in deploy
    assert "LIFF_CONFIG_DEFERRED" in verify
    assert "SUPABASE_CONNECTION=PASS" in verify
    assert "GATEWAY_CONFIG=PASS" in verify
    assert 'wait_for_url "GATEWAY_HEALTH" "http://127.0.0.1:${STAGING_GATEWAY_PORT}/health" 20' in deploy
    assert 'check_url "GATEWAY_HEALTH" "http://127.0.0.1:${STAGING_GATEWAY_PORT}/health"' in verify
    assert "require_running_container" in verify
    assert "require_healthy_postgres_container" in verify
    assert "N8N_POSTGRES=HEALTHY" in verify
    assert "/etc/nginx/conf.d/bi-rmp-staging-gateway.conf" in verify
    assert "Backend/tests/test_staging_core_profile.py" in deploy


def test_core_env_template_uses_local_n8n_defaults() -> None:
    source = _read(".env.staging.example")

    assert "N8N_HOST=localhost" in source
    assert "N8N_WEBHOOK_URL=http://127.0.0.1:5679/" in source
    assert "N8N_PROTOCOL=http" in source
    assert "N8N_SECURE_COOKIE=false" in source


def test_rollback_supports_core_and_full_profiles() -> None:
    source = _read("scripts/rollback-staging.sh")

    assert 'STAGING_DEPLOY_PROFILE="${STAGING_DEPLOY_PROFILE:-full}"' in source
    assert "core|full" in source
    assert "unsupported staging deploy profile" in source
    assert "STAGING_DEPLOY_PROFILE=${STAGING_DEPLOY_PROFILE}" in source
