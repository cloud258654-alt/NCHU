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
STAGING_COMPOSE_PROJECT_NAME="${STAGING_COMPOSE_PROJECT_NAME:-bi-rmp-staging-n8n}"
STAGING_N8N_CONTAINER="${STAGING_N8N_CONTAINER:-bi-rmp-staging-n8n}"
STAGING_N8N_POSTGRES_CONTAINER="${STAGING_N8N_POSTGRES_CONTAINER:-bi-rmp-staging-n8n-postgres}"
STAGING_LOCK_FILE="${STAGING_LOCK_FILE:-/tmp/bi-rmp-staging-deploy.lock}"
STAGING_BACKUP_ROOT="${STAGING_BACKUP_ROOT:-${STAGING_HOME}/backups}"
STAGING_DEPLOY_PROFILE="${STAGING_DEPLOY_PROFILE:-full}"
ROLLBACK_SHA="${1:-}"

case "${STAGING_DEPLOY_PROFILE}" in
    core|full) ;;
    *)
        echo "RESULT: FAIL"
        echo "REASON: unsupported staging deploy profile"
        exit 1
        ;;
esac

case "${STAGING_HOST_MODE}" in
    shared|dedicated) ;;
    *)
        echo "RESULT: FAIL"
        echo "REASON: unsupported staging host mode"
        exit 1
        ;;
esac

fail_if_unexpected_dedicated_production_resources() {
    [[ "${STAGING_HOST_MODE}" == "dedicated" ]] || return 0
    if [[ -d "/home/harcker8119/BI-RMP" ]] \
        || systemctl cat bi-rmp.service >/dev/null 2>&1 \
        || { command -v docker >/dev/null 2>&1 && docker inspect bi-rmp-n8n >/dev/null 2>&1; } \
        || { command -v docker >/dev/null 2>&1 && docker inspect bi-rmp-n8n-postgres >/dev/null 2>&1; } \
        || { command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -qE ':(8001|5678|8080)\b'; }; then
        echo "RESULT: BLOCKED_UNEXPECTED_PRODUCTION_RESOURCES"
        exit 1
    fi
    echo "PRODUCTION_RESOURCES=ABSENT_AS_EXPECTED"
}

exec 9>"${STAGING_LOCK_FILE}"
if ! flock -n 9; then
    echo "RESULT: FAIL"
    echo "REASON: another staging deployment is running"
    exit 1
fi

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

cd "${STAGING_APP_DIR}"

fail_if_unexpected_dedicated_production_resources

if [[ -z "${ROLLBACK_SHA}" ]]; then
    previous_file="$(find "${STAGING_BACKUP_ROOT}" -path '*/previous_commit.txt' -type f -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | awk '{print $2}')"
    if [[ -n "${previous_file:-}" ]]; then
        ROLLBACK_SHA="$(cat "${previous_file}")"
    fi
fi

if [[ -z "${ROLLBACK_SHA}" ]]; then
    echo "RESULT: FAIL"
    echo "REASON: missing rollback SHA"
    exit 1
fi

git cat-file -e "${ROLLBACK_SHA}^{commit}"
git reset --hard "${ROLLBACK_SHA}"

sudo systemctl restart "${STAGING_BACKEND_SERVICE}"
sudo systemctl is-active --quiet "${STAGING_BACKEND_SERVICE}"
wait_for_url "BACKEND_HEALTH" "http://127.0.0.1:${STAGING_BACKEND_PORT}/health" 20

docker_compose_staging up -d postgres
docker_compose_staging up -d n8n
wait_for_url "N8N_READINESS" "http://127.0.0.1:${STAGING_N8N_HOST_PORT}/healthz/readiness" 30

echo "RESULT: ROLLBACK_STAGING_COMPLETED"
echo "STAGING_DEPLOY_PROFILE=${STAGING_DEPLOY_PROFILE}"
echo "HOST_MODE=${STAGING_HOST_MODE}"
echo "ROLLBACK_SHA=${ROLLBACK_SHA}"
