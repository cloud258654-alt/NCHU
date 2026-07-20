#!/usr/bin/env bash

set -Eeuo pipefail

STAGING_APP_DIR="${STAGING_APP_DIR:-/home/harcker8119/BI-RMP-STAGING}"
STAGING_ENV_FILE="${STAGING_ENV_FILE:-${STAGING_APP_DIR}/.env.staging.runtime}"
STAGING_BACKEND_SERVICE="${STAGING_BACKEND_SERVICE:-bi-rmp-staging.service}"
STAGING_BACKEND_PORT="${STAGING_BACKEND_PORT:-8101}"
STAGING_N8N_HOST_PORT="${STAGING_N8N_HOST_PORT:-5679}"
STAGING_GATEWAY_PORT="${STAGING_GATEWAY_PORT:-8180}"
STAGING_N8N_CONTAINER="${STAGING_N8N_CONTAINER:-bi-rmp-staging-n8n}"
STAGING_N8N_POSTGRES_CONTAINER="${STAGING_N8N_POSTGRES_CONTAINER:-bi-rmp-staging-n8n-postgres}"
STAGING_PUBLIC_BASE_URL="${STAGING_PUBLIC_BASE_URL:-}"

required_env_keys=(
    LINE_CHANNEL_ACCESS_TOKEN
    LINE_CHANNEL_SECRET
    LINE_LIFF_ID
    LINE_LOGIN_CHANNEL_ID
    N8N_WEBHOOK_URL
    N8N_ENCRYPTION_KEY
    N8N_DB_PASSWORD
    BI_RMP_INTERNAL_API_KEY
    DATABASE_URL
    BI_RMP_LINE_ALLOWED_USER_IDS
)

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

check_url() {
    local label="$1"
    local url="$2"
    if curl --fail --silent --show-error "${url}" >/dev/null 2>&1; then
        echo "${label}=PASS"
    else
        echo "${label}=FAIL"
        return 1
    fi
}

cd "${STAGING_APP_DIR}"

echo "BRANCH=$(git branch --show-current)"
echo "HEAD=$(git rev-parse HEAD)"
echo "WORKTREE=$(if [[ -z "$(git status --short)" ]]; then echo clean; else echo dirty; fi)"

if [[ -f "${STAGING_ENV_FILE}" ]]; then
    echo "ENV_FILE=PRESENT"
else
    echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
    echo "ENV_FILE=MISSING"
    exit 1
fi

for key in "${required_env_keys[@]}"; do
    if [[ -n "$(read_env_value "${key}")" ]]; then
        echo "${key}=PRESENT"
    else
        echo "${key}=MISSING"
    fi
done

if [[ "$(read_env_value APP_ENV)" != "staging" || "$(read_env_value SUPABASE_PROJECT_REF)" != "qlhykeeyjaoikczoambe" || "$(read_env_value ALLOW_PRODUCTION_DB)" != "false" ]]; then
    echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
    echo "REASON: staging database target contract is incomplete"
    exit 1
fi

systemctl is-active --quiet "${STAGING_BACKEND_SERVICE}" && echo "BACKEND_SERVICE=ACTIVE" || echo "BACKEND_SERVICE=INACTIVE"
check_url "BACKEND_HEALTH" "http://127.0.0.1:${STAGING_BACKEND_PORT}/health"
check_url "LIFF_PAGE" "http://127.0.0.1:${STAGING_BACKEND_PORT}/register"
check_url "LIFF_CONFIG" "http://127.0.0.1:${STAGING_BACKEND_PORT}/api/liff/config"
check_url "N8N_READINESS" "http://127.0.0.1:${STAGING_N8N_HOST_PORT}/healthz/readiness"

docker ps --format '{{.Names}}' | grep -Fx "${STAGING_N8N_CONTAINER}" >/dev/null && echo "N8N_CONTAINER=PRESENT" || echo "N8N_CONTAINER=MISSING"
docker ps --format '{{.Names}}' | grep -Fx "${STAGING_N8N_POSTGRES_CONTAINER}" >/dev/null && echo "N8N_POSTGRES_CONTAINER=PRESENT" || echo "N8N_POSTGRES_CONTAINER=MISSING"

if [[ -n "${STAGING_PUBLIC_BASE_URL}" ]]; then
    check_url "PUBLIC_HEALTH" "${STAGING_PUBLIC_BASE_URL%/}/health"
    check_url "PUBLIC_REGISTER" "${STAGING_PUBLIC_BASE_URL%/}/register"
    check_url "PUBLIC_LIFF_CONFIG" "${STAGING_PUBLIC_BASE_URL%/}/api/liff/config"
else
    echo "PUBLIC_HTTPS=WAITING_EXTERNAL_CONFIGURATION"
fi

echo "RESULT: VERIFY_STAGING_COMPLETED"
