#!/usr/bin/env bash

set -Eeuo pipefail

STAGING_HOST_MODE="${STAGING_HOST_MODE:-shared}"
STAGING_USER="${STAGING_USER:-$(id -un)}"
STAGING_HOME="${STAGING_HOME:-$(getent passwd "${STAGING_USER}" 2>/dev/null | cut -d: -f6 || true)}"
STAGING_HOME="${STAGING_HOME:-${HOME:-}}"
STAGING_APP_DIR="${STAGING_APP_DIR:-${STAGING_HOME}/BI-RMP-STAGING}"
STAGING_ENV_FILE="${STAGING_ENV_FILE:-${STAGING_APP_DIR}/.env.staging.runtime}"
STAGING_BACKEND_SERVICE="${STAGING_BACKEND_SERVICE:-bi-rmp-staging.service}"
STAGING_BACKEND_PORT="${STAGING_BACKEND_PORT:-8101}"
STAGING_N8N_HOST_PORT="${STAGING_N8N_HOST_PORT:-5679}"
STAGING_GATEWAY_PORT="${STAGING_GATEWAY_PORT:-8180}"
STAGING_COMPOSE_PROJECT_NAME="${STAGING_COMPOSE_PROJECT_NAME:-bi-rmp-staging-n8n}"
STAGING_N8N_CONTAINER="${STAGING_N8N_CONTAINER:-bi-rmp-staging-n8n}"
STAGING_N8N_POSTGRES_CONTAINER="${STAGING_N8N_POSTGRES_CONTAINER:-bi-rmp-staging-n8n-postgres}"
STAGING_LOCK_FILE="${STAGING_LOCK_FILE:-/tmp/bi-rmp-staging-deploy.lock}"
STAGING_BACKUP_ROOT="${STAGING_BACKUP_ROOT:-${STAGING_HOME}/backups}"
STAGING_PUBLIC_BASE_URL="${STAGING_PUBLIC_BASE_URL:-}"
STAGING_DEPLOY_PROFILE="${STAGING_DEPLOY_PROFILE:-full}"
TARGET_REF="${1:-HEAD}"
PREVIOUS_SHA=""
BACKUP_DIR=""
TEMP_N8N_WORKFLOW_IMPORT=""
TARGET_BRANCH=""
PRODUCTION_BACKEND_STATE_BEFORE=""
PRODUCTION_N8N_STATE_BEFORE=""

core_required_env_keys=(
    APP_ENV
    SUPABASE_PROJECT_REF
    SUPABASE_URL
    DATABASE_URL
    ALLOW_DATABASE_WRITES
    ALLOW_PRODUCTION_DB
    BI_RMP_INTERNAL_API_KEY
    BI_RMP_BACKEND_BASE_URL
    N8N_HOST
    N8N_WEBHOOK_URL
    N8N_ENCRYPTION_KEY
    N8N_DB_PASSWORD
    COMPOSE_PROJECT_NAME
)

full_line_env_keys=(
    BI_RMP_LINE_ALLOWED_USER_IDS
    LINE_CHANNEL_ACCESS_TOKEN
    LINE_CHANNEL_SECRET
    LINE_LIFF_ID
    LINE_LOGIN_CHANNEL_ID
    N8N_WORKFLOW_ID
)

required_env_keys=()

case "${STAGING_DEPLOY_PROFILE}" in
    core|full) ;;
    *)
        echo "RESULT: FAIL"
        echo "REASON: unsupported staging deploy profile"
        exit 1
        ;;
esac

cleanup() {
    if [[ -n "${TEMP_N8N_WORKFLOW_IMPORT}" ]]; then
        rm -f -- "${TEMP_N8N_WORKFLOW_IMPORT}"
    fi
}
trap cleanup EXIT

exec 9>"${STAGING_LOCK_FILE}"
if ! flock -n 9; then
    echo "RESULT: FAIL"
    echo "REASON: another staging deployment is running"
    exit 1
fi

read_env_value() {
    local key="$1"
    local value=""
    if [[ -f "${STAGING_ENV_FILE}" ]]; then
        value="$(
            grep -E "^[[:space:]]*${key}=" "${STAGING_ENV_FILE}" \
                | tail -n 1 \
                | sed -E "s/^[[:space:]]*${key}=//" \
                | tr -d '\r' \
                || true
        )"
    fi
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    printf '%s' "${value}"
}

validate_deploy_profile() {
    case "${STAGING_DEPLOY_PROFILE}" in
        core|full) ;;
        *)
            echo "RESULT: FAIL"
            echo "REASON: unsupported staging deploy profile"
            exit 1
            ;;
    esac
}

validate_host_mode() {
    case "${STAGING_HOST_MODE}" in
        shared|dedicated) ;;
        *)
            echo "RESULT: FAIL"
            echo "REASON: unsupported staging host mode"
            exit 1
            ;;
    esac
}

configure_required_env_keys() {
    required_env_keys=("${core_required_env_keys[@]}")
    if [[ "${STAGING_DEPLOY_PROFILE}" == "full" ]]; then
        required_env_keys+=("${full_line_env_keys[@]}")
    fi
}

env_key_status() {
    local key="$1"
    local value
    value="$(read_env_value "${key}")"
    if [[ -z "${value}" ]]; then
        echo "${key}=MISSING"
    else
        echo "${key}=PRESENT"
    fi
}

wait_for_url() {
    local label="$1"
    local url="$2"
    local attempts="${3:-20}"
    local attempt

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if curl --fail --silent --show-error "${url}" >/dev/null 2>&1; then
            echo "${label}=PASS"
            return 0
        fi
        sleep 2
    done

    echo "${label}=FAIL"
    return 1
}

fail_if_production_collision() {
    if [[ "${STAGING_APP_DIR}" == "/home/harcker8119/BI-RMP" ]]; then
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: STAGING_APP_DIR matches production app dir"
        exit 1
    fi
    if [[ "${STAGING_BACKEND_SERVICE}" == "bi-rmp.service" ]]; then
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: staging backend service matches production service"
        exit 1
    fi
    if [[ "${STAGING_BACKEND_PORT}" == "8001" || "${STAGING_N8N_HOST_PORT}" == "5678" || "${STAGING_GATEWAY_PORT}" == "8080" ]]; then
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: staging port overlaps known production/default ports"
        exit 1
    fi
    if [[ "${STAGING_COMPOSE_PROJECT_NAME}" == "bi-rmp-n8n" || "${STAGING_N8N_CONTAINER}" == "bi-rmp-n8n" || "${STAGING_N8N_POSTGRES_CONTAINER}" == "bi-rmp-n8n-postgres" ]]; then
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: staging n8n name overlaps production name"
        exit 1
    fi
}

is_port_listening() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltn "sport = :${port}" 2>/dev/null | grep -qE ":${port}\b" && return 0
    fi
    if command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:"${port}" -sTCP:LISTEN -n -P >/dev/null 2>&1 && return 0
    fi
    return 1
}

get_listener_pids() {
    local port="$1"
    local pids=""
    if command -v ss >/dev/null 2>&1; then
        pids="$(ss -ltnp "sport = :${port}" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u | tr '\n' ' ')"
    fi
    if [[ -z "${pids// /}" ]] && command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ')"
    fi
    if [[ -z "${pids// /}" ]] && command -v fuser >/dev/null 2>&1; then
        pids="$(fuser "${port}/tcp" 2>/dev/null | tr '\n' ' ')"
    fi
    printf '%s' "${pids}"
}

verify_staging_backend_port() {
    local port="${STAGING_BACKEND_PORT}"
    if ! is_port_listening "${port}"; then
        return 0
    fi

    if ! systemctl is-active --quiet "${STAGING_BACKEND_SERVICE}" 2>/dev/null; then
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: port ${port} is listening but ${STAGING_BACKEND_SERVICE} is not active"
        exit 1
    fi

    local service_main_pid
    service_main_pid="$(systemctl show "${STAGING_BACKEND_SERVICE}" -p MainPID --value 2>/dev/null || true)"

    local pids
    pids="$(get_listener_pids "${port}")"

    local pid_matched=0
    if [[ -n "${pids// /}" ]]; then
        for pid in ${pids}; do
            if [[ -n "${service_main_pid}" && "${service_main_pid}" != "0" && "${pid}" == "${service_main_pid}" ]]; then
                pid_matched=1
                break
            fi
            if [[ -f "/proc/${pid}/cgroup" ]] && grep -q "${STAGING_BACKEND_SERVICE}" "/proc/${pid}/cgroup" 2>/dev/null; then
                pid_matched=1
                break
            fi
            if systemctl status "${pid}" 2>/dev/null | grep -q "${STAGING_BACKEND_SERVICE}"; then
                pid_matched=1
                break
            fi
        done
    else
        if [[ -n "${service_main_pid}" && "${service_main_pid}" != "0" ]]; then
            pid_matched=1
        fi
    fi

    if [[ "${pid_matched}" == "1" ]]; then
        return 0
    else
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: port ${port} is listening by a process not belonging to ${STAGING_BACKEND_SERVICE}"
        exit 1
    fi
}

verify_staging_n8n_port() {
    local port="${STAGING_N8N_HOST_PORT}"
    if ! is_port_listening "${port}"; then
        return 0
    fi

    if ! command -v docker >/dev/null 2>&1; then
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: port ${port} is listening but docker command is unavailable"
        exit 1
    fi

    local running_container
    running_container="$(docker ps --filter "name=^/${STAGING_N8N_CONTAINER}$" --filter "status=running" --format '{{.Names}}' 2>/dev/null || true)"

    if [[ "${running_container}" != "${STAGING_N8N_CONTAINER}" ]]; then
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: port ${port} is listening but container ${STAGING_N8N_CONTAINER} is not running"
        exit 1
    fi

    local mapped_ports
    mapped_ports="$(docker port "${STAGING_N8N_CONTAINER}" 2>/dev/null || true)"
    if echo "${mapped_ports}" | grep -q ":${port}\b"; then
        return 0
    else
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: port ${port} is listening but not mapped by container ${STAGING_N8N_CONTAINER}"
        exit 1
    fi
}

verify_staging_gateway_port() {
    local port="${STAGING_GATEWAY_PORT}"
    if ! is_port_listening "${port}"; then
        return 0
    fi

    local pids
    pids="$(get_listener_pids "${port}")"
    local is_nginx=0
    if [[ -n "${pids// /}" ]]; then
        for pid in ${pids}; do
            local p_name
            p_name="$(ps -p "${pid}" -o comm= 2>/dev/null || true)"
            if [[ "${p_name}" == "nginx" ]]; then
                is_nginx=1
                break
            fi
        done
    else
        if systemctl is-active --quiet nginx 2>/dev/null || pgrep -x nginx >/dev/null 2>&1; then
            is_nginx=1
        fi
    fi

    if [[ "${is_nginx}" != "1" ]]; then
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: port ${port} is listening by a non-nginx process"
        exit 1
    fi

    local config_matched=0
    local conf_files=(
        "/etc/nginx/sites-enabled/bi-rmp-staging-gateway.conf"
        "/etc/nginx/conf.d/bi-rmp-staging-gateway.conf"
        "/etc/nginx/sites-enabled/bi-rmp-staging.conf"
    )
    local f
    for f in "${conf_files[@]}"; do
        if [[ -f "${f}" ]] && grep -qE "listen\s+([0-9.]+:)?${port}\b" "${f}" 2>/dev/null && grep -qE "(bi-rmp-staging|proxy_pass http://127.0.0.1:${STAGING_BACKEND_PORT})" "${f}" 2>/dev/null; then
            config_matched=1
            break
        fi
    done

    if [[ "${config_matched}" == "0" ]]; then
        if command -v nginx >/dev/null 2>&1; then
            local nginx_dump
            nginx_dump="$(nginx -T 2>/dev/null || true)"
            if echo "${nginx_dump}" | grep -qE "listen\s+([0-9.]+:)?${port}\b" && echo "${nginx_dump}" | grep -qE "(bi-rmp-staging|proxy_pass http://127.0.0.1:${STAGING_BACKEND_PORT})"; then
                config_matched=1
            fi
        fi
    fi

    if [[ "${config_matched}" == "1" ]]; then
        return 0
    else
        echo "RESULT: BLOCKED_PRODUCTION_COLLISION"
        echo "REASON: port ${port} is listening by nginx but no valid bi-rmp-staging gateway config was verified"
        exit 1
    fi
}

validate_environment_contract() {
    if [[ ! -f "${STAGING_ENV_FILE}" ]]; then
        echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
        echo "MISSING_ENV_FILE=${STAGING_ENV_FILE}"
        exit 1
    fi

    echo "Environment key presence:"
    local missing=0
    local key
    for key in "${required_env_keys[@]}"; do
        env_key_status "${key}"
        if [[ -z "$(read_env_value "${key}")" ]]; then
            missing=1
        fi
    done

    if [[ "$(read_env_value APP_ENV)" != "staging" ]]; then
        echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
        echo "INVALID_FORMAT=APP_ENV"
        exit 1
    fi
    if [[ "$(read_env_value SUPABASE_PROJECT_REF)" != "qlhykeeyjaoikczoambe" ]]; then
        echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
        echo "INVALID_FORMAT=SUPABASE_PROJECT_REF"
        exit 1
    fi
    if [[ "$(read_env_value ALLOW_PRODUCTION_DB)" != "false" ]]; then
        echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
        echo "INVALID_FORMAT=ALLOW_PRODUCTION_DB"
        exit 1
    fi
    if [[ "${STAGING_DEPLOY_PROFILE}" == "core" && "$(read_env_value N8N_HOST)" != "localhost" ]]; then
        echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
        echo "INVALID_FORMAT=N8N_HOST"
        exit 1
    fi
    if [[ "${STAGING_DEPLOY_PROFILE}" == "core" && "$(read_env_value N8N_WEBHOOK_URL)" != "http://127.0.0.1:${STAGING_N8N_HOST_PORT}/" ]]; then
        echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
        echo "INVALID_FORMAT=N8N_WEBHOOK_URL"
        exit 1
    fi
    if [[ "${missing}" == "1" ]]; then
        echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
        echo "REASON: required staging secrets or public settings are missing"
        exit 1
    fi
}

create_backup() {
    local deploy_ts
    deploy_ts="$(date -u +%Y%m%dT%H%M%SZ)"
    BACKUP_DIR="${STAGING_BACKUP_ROOT}/bi-rmp-staging-${deploy_ts}"
    mkdir -p "${BACKUP_DIR}"
    git rev-parse HEAD > "${BACKUP_DIR}/previous_commit.txt"
    cp -a Backend "${BACKUP_DIR}/Backend"
    cp -a infra/n8n "${BACKUP_DIR}/n8n"
    echo "BACKUP_DIR=${BACKUP_DIR}"
}

docker_compose_staging() {
    COMPOSE_PROJECT_NAME="${STAGING_COMPOSE_PROJECT_NAME}" \
    STAGING_N8N_CONTAINER="${STAGING_N8N_CONTAINER}" \
    STAGING_N8N_POSTGRES_CONTAINER="${STAGING_N8N_POSTGRES_CONTAINER}" \
    N8N_HOST_PORT="${STAGING_N8N_HOST_PORT}" \
    docker compose \
        --env-file "${STAGING_ENV_FILE}" \
        -f infra/n8n/docker-compose.yml \
        -f infra/n8n/docker-compose.staging.yml \
        "$@"
}

n8n_cli() {
    docker exec -u node "${STAGING_N8N_CONTAINER}" n8n "$@"
}

deploy_n8n_workflow() {
    local workflow_id
    local import_basename
    local import_container_path
    workflow_id="$(read_env_value N8N_WORKFLOW_ID)"
    if [[ -z "${workflow_id}" || ! "${workflow_id}" =~ ^[A-Za-z0-9_-]+$ ]]; then
        echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
        echo "INVALID_FORMAT=N8N_WORKFLOW_ID"
        exit 1
    fi

    import_basename=".reputation-optimization-flow.staging.${TARGET_SHA}.json"
    TEMP_N8N_WORKFLOW_IMPORT="${STAGING_APP_DIR}/infra/n8n/workflows/${import_basename}"
    import_container_path="/opt/bi-rmp/n8n-workflows/${import_basename}"

    "${STAGING_APP_DIR}/.venv/bin/python" - "${workflow_id}" "${TEMP_N8N_WORKFLOW_IMPORT}" <<'PY'
import json
import sys
from pathlib import Path

workflow_id = sys.argv[1]
output = Path(sys.argv[2])
source = Path("infra/n8n/workflows/reputation-optimization-flow.json")
data = json.loads(source.read_text(encoding="utf-8"))
data["id"] = workflow_id
data["active"] = True
output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

    deploy_n8n_core

    n8n_cli import:workflow \
        --input="${import_container_path}"
    if ! n8n_cli publish:workflow --id="${workflow_id}"; then
        n8n_cli update:workflow --id="${workflow_id}" --active=true
    fi
    docker_compose_staging up -d --no-deps --force-recreate n8n
    wait_for_url "N8N_READINESS_AFTER_IMPORT" "http://127.0.0.1:${STAGING_N8N_HOST_PORT}/healthz/readiness" 30
}

fail_if_unexpected_dedicated_production_resources() {
    [[ "${STAGING_HOST_MODE}" == "dedicated" ]] || return 0
    if [[ -d "/home/harcker8119/BI-RMP" ]] \
        || systemctl cat bi-rmp.service >/dev/null 2>&1 \
        || { command -v docker >/dev/null 2>&1 && docker inspect bi-rmp-n8n >/dev/null 2>&1; } \
        || { command -v docker >/dev/null 2>&1 && docker inspect bi-rmp-n8n-postgres >/dev/null 2>&1; } \
        || is_port_listening 8001 \
        || is_port_listening 5678 \
        || is_port_listening 8080; then
        echo "RESULT: BLOCKED_UNEXPECTED_PRODUCTION_RESOURCES"
        exit 1
    fi
    echo "PRODUCTION_RESOURCES=ABSENT_AS_EXPECTED"
}

snapshot_production_state() {
    [[ "${STAGING_HOST_MODE}" == "shared" ]] || return 0
    PRODUCTION_BACKEND_STATE_BEFORE="$(systemctl is-active bi-rmp.service 2>/dev/null || echo inactive-or-missing)"
    PRODUCTION_N8N_STATE_BEFORE="$(docker inspect --format '{{.State.Running}}' bi-rmp-n8n 2>/dev/null || echo missing)"
}

verify_production_unchanged() {
    if [[ "${STAGING_HOST_MODE}" == "dedicated" ]]; then
        fail_if_unexpected_dedicated_production_resources
        return 0
    fi
    local backend_state_after
    local n8n_state_after
    backend_state_after="$(systemctl is-active bi-rmp.service 2>/dev/null || echo inactive-or-missing)"
    n8n_state_after="$(docker inspect --format '{{.State.Running}}' bi-rmp-n8n 2>/dev/null || echo missing)"

    if [[ "${PRODUCTION_BACKEND_STATE_BEFORE}" != "${backend_state_after}" || "${PRODUCTION_N8N_STATE_BEFORE}" != "${n8n_state_after}" ]]; then
        echo "RESULT: FAIL"
        echo "REASON: production service state changed during staging deployment"
        exit 1
    fi

    echo "PRODUCTION_BACKEND_UNCHANGED=YES"
    echo "PRODUCTION_N8N_UNCHANGED=YES"
}

deploy_n8n_core() {
    docker_compose_staging config --quiet
    docker_compose_staging up -d postgres
    docker_compose_staging up -d n8n
    wait_for_url "N8N_READINESS" "http://127.0.0.1:${STAGING_N8N_HOST_PORT}/healthz/readiness" 30
}

run_focused_tests() {
    if [[ "${STAGING_DEPLOY_PROFILE}" == "core" ]]; then
        "${STAGING_APP_DIR}/.venv/bin/python" -m pytest -q Backend/tests/test_deploy_staging.py Backend/tests/test_staging_core_profile.py
    else
        "${STAGING_APP_DIR}/.venv/bin/python" -m pytest -q Backend/tests/api/test_staging_line_allowlist.py Backend/tests/test_n8n_zero_push_workflow.py
    fi
}

validate_deploy_profile
validate_host_mode
configure_required_env_keys
cd "${STAGING_APP_DIR}"
fail_if_production_collision
fail_if_unexpected_dedicated_production_resources
snapshot_production_state
verify_staging_backend_port
verify_staging_n8n_port
verify_staging_gateway_port

git fetch origin --prune
git cat-file -e "${TARGET_REF}^{commit}"
TARGET_SHA="$(git rev-parse "${TARGET_REF}^{commit}")"
PREVIOUS_SHA="$(git rev-parse HEAD)"
CURRENT_BRANCH="$(git branch --show-current || true)"

if [[ "${STAGING_DEPLOY_PROFILE}" == "core" ]]; then
    TARGET_BRANCH="feature/core-shared-staging-profile"
else
    TARGET_BRANCH="feature/customer-validation-gate-c2"
fi

if [[ "${CURRENT_BRANCH}" != "${TARGET_BRANCH}" && ! "${TARGET_REF}" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
    echo "RESULT: FAIL"
    echo "REASON: deploy accepts the selected profile branch or an explicit target SHA"
    exit 1
fi

db_changes="$(
    git diff --name-only "${PREVIOUS_SHA}" "${TARGET_SHA}" -- database supabase 2>/dev/null \
        | grep -v '^database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql$' \
        || true
)"
if [[ -n "${db_changes}" ]]; then
    echo "RESULT: FAIL"
    echo "REASON: database or Supabase schema changes are present"
    echo "${db_changes}"
    exit 1
fi

validate_environment_contract
create_backup

if git show-ref --verify --quiet "refs/heads/${TARGET_BRANCH}"; then
    git switch "${TARGET_BRANCH}"
else
    git switch -c "${TARGET_BRANCH}"
fi
git reset --hard "${TARGET_SHA}"

"${STAGING_APP_DIR}/.venv/bin/python" -m pip install --disable-pip-version-check -r requirements.txt
"${STAGING_APP_DIR}/.venv/bin/python" -m compileall -q Backend
run_focused_tests

sudo systemctl daemon-reload
sudo systemctl restart "${STAGING_BACKEND_SERVICE}"
sudo systemctl is-active --quiet "${STAGING_BACKEND_SERVICE}"
wait_for_url "BACKEND_HEALTH" "http://127.0.0.1:${STAGING_BACKEND_PORT}/health" 20
if [[ "${STAGING_DEPLOY_PROFILE}" == "core" ]]; then
    deploy_n8n_core
    wait_for_url "GATEWAY_HEALTH" "http://127.0.0.1:${STAGING_GATEWAY_PORT}/health" 20
    echo "LINE_INTEGRATION=DEFERRED"
    echo "LIFF_INTEGRATION=DEFERRED"
    echo "PUBLIC_HTTPS=DEFERRED"
    verify_production_unchanged
    echo "RESULT: DEPLOYED_STAGING_CORE"
else
    wait_for_url "LIFF_PAGE" "http://127.0.0.1:${STAGING_BACKEND_PORT}/register" 5
    wait_for_url "LIFF_CONFIG" "http://127.0.0.1:${STAGING_BACKEND_PORT}/api/liff/config" 5
    deploy_n8n_workflow
    if [[ -n "${STAGING_PUBLIC_BASE_URL}" ]]; then
        wait_for_url "PUBLIC_HEALTH" "${STAGING_PUBLIC_BASE_URL%/}/health" 10
        wait_for_url "PUBLIC_REGISTER" "${STAGING_PUBLIC_BASE_URL%/}/register" 10
        wait_for_url "PUBLIC_LIFF_CONFIG" "${STAGING_PUBLIC_BASE_URL%/}/api/liff/config" 10
    else
        echo "PUBLIC_HTTPS=WAITING_EXTERNAL_CONFIGURATION"
    fi
    verify_production_unchanged
    echo "RESULT: DEPLOYED_STAGING_PENDING_E2E"
fi

echo "STAGING_DEPLOY_PROFILE=${STAGING_DEPLOY_PROFILE}"
echo "HOST_MODE=${STAGING_HOST_MODE}"
echo "TARGET_SHA=${TARGET_SHA}"
echo "PREVIOUS_SHA=${PREVIOUS_SHA}"
echo "ROLLBACK_COMMAND=scripts/rollback-staging.sh"
