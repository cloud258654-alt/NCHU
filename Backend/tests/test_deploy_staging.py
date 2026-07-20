from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _to_posix(path: Path) -> str:
    try:
        res = subprocess.run(["cygpath", "-u", str(path)], capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return str(path).replace("\\", "/")


def _find_bash() -> str | None:
    git_bash_candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ]
    for candidate in git_bash_candidates:
        if os.path.exists(candidate):
            return candidate

    bash_path = shutil.which("bash") or shutil.which("sh")
    if bash_path:
        try:
            res = subprocess.run([bash_path, "-c", "echo OK"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and "OK" in res.stdout:
                return bash_path
        except Exception:
            pass
    return None


def _run_bash_snippet(snippet: str, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    bash_cmd = _find_bash()
    if not bash_cmd:
        pytest.skip("Working bash executable is not available on this host environment.")

    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    res = subprocess.run(
        [bash_cmd, "-c", snippet],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=full_env,
        cwd=str(ROOT),
    )
    return res.returncode, res.stdout, res.stderr


def test_staging_deploy_uses_independent_topology_and_blocks_production_names() -> None:
    source = _read("scripts/deploy-staging.sh")

    assert "set -Eeuo pipefail" in source
    assert 'STAGING_APP_DIR="${STAGING_APP_DIR:-/home/harcker8119/BI-RMP-STAGING}"' in source
    assert 'STAGING_BACKEND_SERVICE="${STAGING_BACKEND_SERVICE:-bi-rmp-staging.service}"' in source
    assert 'STAGING_BACKEND_PORT="${STAGING_BACKEND_PORT:-8101}"' in source
    assert 'STAGING_N8N_HOST_PORT="${STAGING_N8N_HOST_PORT:-5679}"' in source
    assert 'STAGING_GATEWAY_PORT="${STAGING_GATEWAY_PORT:-8180}"' in source
    assert 'STAGING_LOCK_FILE="${STAGING_LOCK_FILE:-/tmp/bi-rmp-staging-deploy.lock}"' in source
    assert "BLOCKED_PRODUCTION_COLLISION" in source
    assert '/home/harcker8119/BI-RMP"' in source
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


def test_deploy_staging_port_verification_functions() -> None:
    snippet = r"""
    STAGING_APP_DIR="$PWD"
    STAGING_LOCK_FILE="/tmp/bi-rmp-test-deploy.lock"
    exec() { :; }
    flock() { return 0; }
    exit() { return "${1:-0}"; }

    eval "$(sed '/^cd /q' scripts/deploy-staging.sh | grep -v '^cd ')"

    # 1. Unused ports return 0
    is_port_listening() { return 1; }
    verify_staging_backend_port || exit 10
    verify_staging_n8n_port || exit 11
    verify_staging_gateway_port || exit 12

    # 2. Port 8101 active & owned by staging service returns 0
    is_port_listening() { return 0; }
    systemctl() {
        if [[ "$1" == "is-active" ]]; then return 0; fi
        if [[ "$1" == "show" ]]; then echo "1234"; fi
        if [[ "$1" == "status" ]]; then echo "bi-rmp-staging.service"; fi
    }
    get_listener_pids() { echo "1234"; }
    verify_staging_backend_port || exit 20

    # 3. Port 8101 occupied by unknown process blocks
    get_listener_pids() { echo "9999"; }
    systemctl() {
        if [[ "$1" == "is-active" ]]; then return 1; fi
        if [[ "$1" == "show" ]]; then echo "1234"; fi
        if [[ "$1" == "status" ]]; then echo "other.service"; fi
    }
    output="$(verify_staging_backend_port 2>&1 || true)"
    echo "${output}" | grep -q "BLOCKED_PRODUCTION_COLLISION" || exit 30

    # 4. Port 5679 mapped by staging n8n container returns 0
    docker() {
        if [[ "$1" == "ps" ]]; then echo "bi-rmp-staging-n8n"; fi
        if [[ "$1" == "port" ]]; then echo "0.0.0.0:5679"; fi
    }
    verify_staging_n8n_port || exit 40

    # 5. Port 5679 occupied by unknown container/process blocks
    docker() {
        if [[ "$1" == "ps" ]]; then echo "bi-rmp-n8n"; fi
        if [[ "$1" == "port" ]]; then echo "0.0.0.0:5678"; fi
    }
    output="$(verify_staging_n8n_port 2>&1 || true)"
    echo "${output}" | grep -q "BLOCKED_PRODUCTION_COLLISION" || exit 50

    # 6. Port 8180 owned by staging nginx gateway returns 0
    ps() { echo "nginx"; }
    nginx() {
        if [[ "$1" == "-T" ]]; then
            echo "server { listen 8180; proxy_pass http://127.0.0.1:8101; bi-rmp-staging; }"
        fi
    }
    verify_staging_gateway_port || exit 60

    # 7. Port 8180 occupied by non-staging listener blocks
    ps() { echo "unknown_proc"; }
    systemctl() { return 1; }
    pgrep() { return 1; }
    output="$(verify_staging_gateway_port 2>&1 || true)"
    echo "${output}" | grep -q "BLOCKED_PRODUCTION_COLLISION" || exit 70

    echo "ALL_PORT_VERIFICATION_PASS"
    """
    code, stdout, stderr = _run_bash_snippet(snippet)
    assert code == 0, f"Bash snippet failed with exit code {code}:\nStdout: {stdout}\nStderr: {stderr}"
    assert "ALL_PORT_VERIFICATION_PASS" in stdout


def test_production_collision_guards_in_deploy_and_bootstrap() -> None:
    for script in ["scripts/deploy-staging.sh", "scripts/bootstrap-staging-host.sh"]:
        snippet = r"""
        STAGING_APP_DIR="/home/harcker8119/BI-RMP"
        STAGING_HOSTNAME="staging.example.com"
        exec() { :; }
        flock() { return 0; }
        exit() { echo "EXIT_CALLED_$1"; return 0; }
        eval "$(sed '/^cd /q' """ + script + r""" | grep -v '^cd ')"
        fail_if_production_collision
        """
        code, stdout, stderr = _run_bash_snippet(snippet)
        assert "BLOCKED_PRODUCTION_COLLISION" in stdout, f"Script {script} failed to block production dir:\nStdout: {stdout}\nStderr: {stderr}"

        snippet2 = r"""
        STAGING_APP_DIR="/home/harcker8119/BI-RMP-STAGING"
        STAGING_BACKEND_SERVICE="bi-rmp.service"
        STAGING_HOSTNAME="staging.example.com"
        exec() { :; }
        flock() { return 0; }
        exit() { echo "EXIT_CALLED_$1"; return 0; }
        eval "$(sed '/^cd /q' """ + script + r""" | grep -v '^cd ')"
        fail_if_production_collision
        """
        code2, stdout2, stderr2 = _run_bash_snippet(snippet2)
        assert "BLOCKED_PRODUCTION_COLLISION" in stdout2, f"Script {script} failed to block production service:\nStdout: {stdout2}\nStderr: {stderr2}"


def test_bootstrap_staging_host_idempotency_and_isolation(tmp_path: Path) -> None:
    staging_dir_posix = _to_posix(tmp_path / "BI-RMP-STAGING")
    env_file_posix = f"{staging_dir_posix}/.env.staging.runtime"
    hostname = "staging.test.local"

    # Run 1: initial bootstrap
    snippet1 = f"STAGING_APP_DIR='{staging_dir_posix}' STAGING_ENV_FILE='{env_file_posix}' bash scripts/bootstrap-staging-host.sh --hostname {hostname}"
    code1, stdout1, stderr1 = _run_bash_snippet(snippet1)
    assert code1 == 0, f"Initial bootstrap failed:\nStdout: {stdout1}\nStderr: {stderr1}"
    assert "BOOTSTRAP_STAGING_HOST_COMPLETED" in stdout1
    assert "STAGING_ENV_FILE=CREATED_FROM_EXAMPLE" in stdout1
    assert (tmp_path / "BI-RMP-STAGING").exists()
    assert (tmp_path / "BI-RMP-STAGING" / ".env.staging.runtime").exists()

    # Modify env_file with custom secret to verify idempotency
    (tmp_path / "BI-RMP-STAGING" / ".env.staging.runtime").write_text("APP_ENV=staging\nSECRET_KEY=MY_CUSTOM_SECRET_123\n", encoding="utf-8")

    # Run 2: repeatable bootstrap
    snippet2 = f"STAGING_APP_DIR='{staging_dir_posix}' STAGING_ENV_FILE='{env_file_posix}' bash scripts/bootstrap-staging-host.sh --hostname {hostname}"
    code2, stdout2, stderr2 = _run_bash_snippet(snippet2)
    assert code2 == 0, f"Repeatable bootstrap failed:\nStdout: {stdout2}\nStderr: {stderr2}"
    assert "BOOTSTRAP_STAGING_HOST_COMPLETED" in stdout2
    assert "STAGING_ENV_FILE=EXISTS_PRESERVED" in stdout2

    # Secret preserved
    content = (tmp_path / "BI-RMP-STAGING" / ".env.staging.runtime").read_text(encoding="utf-8")
    assert "MY_CUSTOM_SECRET_123" in content
    # Secrets not leaked in stdout
    assert "MY_CUSTOM_SECRET_123" not in stdout2


def test_bootstrap_staging_host_requires_hostname() -> None:
    snippet = "bash scripts/bootstrap-staging-host.sh"
    code, stdout, stderr = _run_bash_snippet(snippet)
    assert code != 0
    assert "RESULT: FAIL" in stdout
    assert "explicit staging hostname is required" in stdout
