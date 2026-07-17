from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = PROJECT_ROOT / "scripts" / "deploy-production.sh"
DEPLOY_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "deploy-production.yml"
NGROK_GATEWAY = (
    PROJECT_ROOT / "infra" / "nginx" / "bi-rmp-ngrok-gateway.conf.example"
)


def test_production_deploy_requires_liff_configuration():
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'ENV_FILE="${APP_DIR}/.env"' in source
    assert "validate_liff_configuration()" in source
    assert "read_env_value LINE_LIFF_ID" in source
    assert "read_env_value LINE_LOGIN_CHANNEL_ID" in source
    assert source.count("validate_liff_configuration") == 2
    assert source.rindex("validate_liff_configuration") < source.index(
        'sudo systemctl restart "${BACKEND_SERVICE}"'
    )


def test_production_deploy_smoke_checks_liff_routes():
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert '"http://127.0.0.1:${BACKEND_PORT}/register"' in source
    assert '"http://127.0.0.1:${BACKEND_PORT}/api/liff/config"' in source
    assert "run_flex_smoke_test()" in source
    assert "DEPLOYED_FLEX_SMOKE_TEST=PASS" in source
    assert "BUBBLE_SIZE=\" + messages[0][\"contents\"][\"size\"]" in source


def test_production_deploy_supports_scoped_backend_only_deployments():
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'DEPLOY_SCOPE="${2:-auto}"' in source
    assert "auto|backend-only|full" in source
    assert 'SHOULD_DEPLOY_BACKEND=true' in source
    assert 'SHOULD_DEPLOY_N8N=false' in source
    assert 'SHOULD_RUN_MIGRATIONS=false' in source
    assert 'echo "[7/8] n8n deployment skipped by scope."' in source
    assert "deploy_n8n" in source
    assert source.rindex('if [[ "${SHOULD_DEPLOY_N8N}" == "true" ]]') < source.rindex(
        'deploy_n8n "${N8N_CHANGED}" "${N8N_WORKFLOW_CHANGED}"'
    )


def test_production_deploy_creates_rollback_point_without_env_copy():
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "create_backup()" in source
    assert 'BACKUP_DIR="/home/harcker8119/backups/bi-rmp-${deploy_ts}"' in source
    assert 'git rev-parse HEAD > "${BACKUP_DIR}/previous_commit.txt"' in source
    assert 'cp -a Backend "${BACKUP_DIR}/Backend"' in source
    assert 'cp -a infra/n8n "${BACKUP_DIR}/infra/n8n"' in source
    assert 'cp -a database "${BACKUP_DIR}/database"' in source
    assert 'cp -a .env' not in source


def test_production_workflow_exposes_deploy_scope_input():
    source = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "deploy_scope:" in source
    assert "default: auto" in source
    assert "- backend-only" in source
    assert "- full" in source
    assert 'DEPLOY_SCOPE: ${{ github.event.inputs.deploy_scope || \'auto\' }}' in source
    assert 'bash scripts/deploy-production.sh "${{ github.sha }}" "${DEPLOY_SCOPE}"' in source


def test_ngrok_gateway_routes_liff_to_backend_and_other_traffic_to_n8n():
    source = NGROK_GATEWAY.read_text(encoding="utf-8")

    assert "listen 127.0.0.1:8080;" in source
    assert "location = /register" in source
    assert "location = /api/liff/config" in source
    assert "location = /api/liff/business/register" in source
    assert source.count("proxy_pass http://127.0.0.1:8001;") == 3
    assert "location /" in source
    assert "proxy_pass http://127.0.0.1:5678;" in source
