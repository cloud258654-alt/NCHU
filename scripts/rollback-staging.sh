#!/usr/bin/env bash

set -Eeuo pipefail

STAGING_APP_DIR="${STAGING_APP_DIR:-/home/harcker8119/BI-RMP-STAGING}"
STAGING_ENV_FILE="${STAGING_ENV_FILE:-${STAGING_APP_DIR}/.env.staging.runtime}"
STAGING_BACKEND_SERVICE="${STAGING_BACKEND_SERVICE:-bi-rmp-staging.service}"
STAGING_BACKEND_PORT="${STAGING_BACKEND_PORT:-8101}"
STAGING_N8N_HOST_PORT="${STAGING_N8N_HOST_PORT:-5679}"
STAGING_COMPOSE_PROJECT_NAME="${STAGING_COMPOSE_PROJECT_NAME:-bi-rmp-staging-n8n}"
STAGING_N8N_CONTAINER="${STAGING_N8N_CONTAINER:-bi-rmp-staging-n8n}"
STAGING_N8N_POSTGRES_CONTAINER="${STAGING_N8N_POSTGRES_CONTAINER:-bi-rmp-staging-n8n-postgres}"
STAGING_LOCK_FILE="${STAGING_LOCK_FILE:-/tmp/bi-rmp-staging-deploy.lock}"
ROLLBACK_SHA="${1:-}"

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

if [[ -z "${ROLLBACK_SHA}" ]]; then
    previous_file="$(find /home/harcker8119/backups -path '*/previous_commit.txt' -type f -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | awk '{print $2}')"
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
echo "ROLLBACK_SHA=${ROLLBACK_SHA}"
