from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_staging_host_mode_defaults_to_shared_and_rejects_unknown_values() -> None:
    for relative_path in (
        "scripts/bootstrap-staging-host.sh",
        "scripts/deploy-staging.sh",
        "scripts/verify-staging.sh",
        "scripts/rollback-staging.sh",
    ):
        source = _read(relative_path)
        assert 'STAGING_HOST_MODE="${STAGING_HOST_MODE:-shared}"' in source
        assert "shared|dedicated" in source
        assert "unsupported staging host mode" in source


def test_dedicated_host_uses_configurable_home_and_blocks_production_resources() -> None:
    for relative_path in (
        "scripts/bootstrap-staging-host.sh",
        "scripts/deploy-staging.sh",
        "scripts/verify-staging.sh",
        "scripts/rollback-staging.sh",
    ):
        source = _read(relative_path)
        assert 'STAGING_USER="${STAGING_USER:-$(id -un)}"' in source
        assert 'STAGING_APP_DIR="${STAGING_APP_DIR:-${STAGING_HOME}/BI-RMP-STAGING}"' in source
        assert "BLOCKED_UNEXPECTED_PRODUCTION_RESOURCES" in source


def test_core_dedicated_bootstrap_uses_loopback_gateway_and_no_hostname() -> None:
    bootstrap = _read("scripts/bootstrap-staging-host.sh")
    nginx = _read("infra/nginx/bi-rmp-staging-gateway.conf.example")

    assert '[[ "${STAGING_DEPLOY_PROFILE}" == "full" && -z "${STAGING_HOSTNAME}" ]]' in bootstrap
    assert 'NGINX_LISTEN="listen 127.0.0.1:${STAGING_GATEWAY_PORT};"' in bootstrap
    assert 'NGINX_SERVER_NAME="_"' in bootstrap
    assert "__STAGING_GATEWAY_LISTEN__" in nginx
    assert "__STAGING_SERVER_NAME__" in nginx
    assert "verify_dedicated_gateway_binding" in _read("scripts/verify-staging.sh")


def test_systemd_template_uses_only_staging_placeholders() -> None:
    source = _read("infra/systemd/bi-rmp-staging.service.example")

    assert "__STAGING_APP_DIR__" in source
    assert "__STAGING_ENV_FILE__" in source
    assert "__STAGING_USER__" in source
    assert "__STAGING_GROUP__" in source
    assert "harcker8119" not in source
