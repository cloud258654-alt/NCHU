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
STAGING_DEPLOY_PROFILE="${STAGING_DEPLOY_PROFILE:-full}"

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
    LINE_CHANNEL_ACCESS_TOKEN
    LINE_CHANNEL_SECRET
    LINE_LIFF_ID
    LINE_LOGIN_CHANNEL_ID
    BI_RMP_LINE_ALLOWED_USER_IDS
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

check_status() {
    local label="$1"
    local url="$2"
    local expected_status="$3"
    local actual_status
    actual_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "${url}" || true)"
    if [[ "${actual_status}" == "${expected_status}" ]]; then
        echo "${label}=PASS"
    else
        echo "${label}=FAIL"
        return 1
    fi
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

configure_required_env_keys() {
    required_env_keys=("${core_required_env_keys[@]}")
    if [[ "${STAGING_DEPLOY_PROFILE}" == "full" ]]; then
        required_env_keys+=("${full_line_env_keys[@]}")
    fi
}

verify_supabase_connection() {
    if (
        set -a
        # shellcheck disable=SC1090
        source "${STAGING_ENV_FILE}"
        set +a
        PYTHONPATH="${STAGING_APP_DIR}/Backend" "${STAGING_APP_DIR}/.venv/bin/python" -c \
            'from core.supabase import get_connection; connection = get_connection(); connection.close()'
    ) >/dev/null 2>&1; then
        echo "SUPABASE_CONNECTION=PASS"
    else
        echo "SUPABASE_CONNECTION=FAIL"
        return 1
    fi
}

verify_gateway_config() {
    local gateway_config
    local gateway_configs=(
        "/etc/nginx/sites-enabled/bi-rmp-staging-gateway.conf"
        "/etc/nginx/conf.d/bi-rmp-staging-gateway.conf"
    )
    local config_matched=0

    for gateway_config in "${gateway_configs[@]}"; do
        if [[ -f "${gateway_config}" ]] && grep -F "127.0.0.1:${STAGING_BACKEND_PORT}" "${gateway_config}" >/dev/null; then
            config_matched=1
            break
        fi
    done
    if [[ "${config_matched}" != "1" ]]; then
        echo "GATEWAY_CONFIG=FAIL"
        return 1
    fi
    if nginx -t >/dev/null 2>&1; then
        echo "GATEWAY_CONFIG=PASS"
    else
        echo "GATEWAY_CONFIG=FAIL"
        return 1
    fi
}

require_running_container() {
    local label="$1"
    local container="$2"

    if docker ps --format '{{.Names}}' | grep -Fx "${container}" >/dev/null; then
        echo "${label}=PRESENT"
    else
        echo "${label}=MISSING"
        return 1
    fi
}

require_healthy_postgres_container() {
    local health
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' "${STAGING_N8N_POSTGRES_CONTAINER}" 2>/dev/null || true)"

    if [[ "${health}" == "healthy" ]]; then
        echo "N8N_POSTGRES=HEALTHY"
    else
        echo "N8N_POSTGRES=UNHEALTHY"
        return 1
    fi
}

verify_production_isolation() {
    local production_backend_state
    local production_n8n_state
    production_backend_state="$(systemctl is-active bi-rmp.service 2>/dev/null || echo inactive-or-missing)"
    production_n8n_state="$(docker inspect --format '{{.State.Running}}' bi-rmp-n8n 2>/dev/null || echo missing)"
    echo "PRODUCTION_BACKEND_STATUS=${production_backend_state}"
    echo "PRODUCTION_N8N_STATUS=${production_n8n_state}"
    echo "PRODUCTION_N8N_UNCHANGED=REQUIRES_DEPLOYMENT_BASELINE"
}

cd "${STAGING_APP_DIR}"

validate_deploy_profile
configure_required_env_keys

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
if [[ "${STAGING_DEPLOY_PROFILE}" == "core" && "$(read_env_value N8N_HOST)" != "localhost" ]]; then
    echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
    echo "REASON: core profile requires N8N_HOST=localhost"
    exit 1
fi
if [[ "${STAGING_DEPLOY_PROFILE}" == "core" && "$(read_env_value N8N_WEBHOOK_URL)" != "http://127.0.0.1:${STAGING_N8N_HOST_PORT}/" ]]; then
    echo "RESULT: WAITING_EXTERNAL_CONFIGURATION"
    echo "REASON: core profile requires a local n8n webhook URL"
    exit 1
fi

systemctl is-active --quiet "${STAGING_BACKEND_SERVICE}" && echo "BACKEND_SERVICE=ACTIVE" || echo "BACKEND_SERVICE=INACTIVE"
check_url "BACKEND_HEALTH" "http://127.0.0.1:${STAGING_BACKEND_PORT}/health"
verify_supabase_connection
check_url "N8N_READINESS" "http://127.0.0.1:${STAGING_N8N_HOST_PORT}/healthz/readiness"
verify_gateway_config
check_url "GATEWAY_HEALTH" "http://127.0.0.1:${STAGING_GATEWAY_PORT}/health"

require_running_container "N8N_CONTAINER" "${STAGING_N8N_CONTAINER}"
require_running_container "N8N_POSTGRES_CONTAINER" "${STAGING_N8N_POSTGRES_CONTAINER}"
require_healthy_postgres_container
verify_production_isolation

if [[ "${STAGING_DEPLOY_PROFILE}" == "core" ]]; then
    check_status "LIFF_CONFIG_DEFERRED" "http://127.0.0.1:${STAGING_BACKEND_PORT}/api/liff/config" 503
    echo "LINE_INTEGRATION=DEFERRED"
    echo "LIFF_INTEGRATION=DEFERRED"
    echo "CUSTOMER_E2E=NOT_EXECUTED"
    echo "PUBLIC_HTTPS=DEFERRED"
elif [[ -n "${STAGING_PUBLIC_BASE_URL}" ]]; then
    check_url "PUBLIC_HEALTH" "${STAGING_PUBLIC_BASE_URL%/}/health"
    check_url "PUBLIC_REGISTER" "${STAGING_PUBLIC_BASE_URL%/}/register"
    check_url "PUBLIC_LIFF_CONFIG" "${STAGING_PUBLIC_BASE_URL%/}/api/liff/config"
else
    echo "PUBLIC_HTTPS=WAITING_EXTERNAL_CONFIGURATION"
fi

echo "STAGING_DEPLOY_PROFILE=${STAGING_DEPLOY_PROFILE}"
echo "RESULT: VERIFY_STAGING_COMPLETED"
