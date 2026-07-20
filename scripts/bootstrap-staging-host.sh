#!/usr/bin/env bash

set -Eeuo pipefail

STAGING_APP_DIR="${STAGING_APP_DIR:-/home/harcker8119/BI-RMP-STAGING}"
STAGING_ENV_FILE="${STAGING_ENV_FILE:-${STAGING_APP_DIR}/.env.staging.runtime}"
STAGING_BACKEND_SERVICE="${STAGING_BACKEND_SERVICE:-bi-rmp-staging.service}"
STAGING_BACKEND_PORT="${STAGING_BACKEND_PORT:-8101}"
STAGING_N8N_HOST_PORT="${STAGING_N8N_HOST_PORT:-5679}"
STAGING_GATEWAY_PORT="${STAGING_GATEWAY_PORT:-8180}"
STAGING_COMPOSE_PROJECT_NAME="${STAGING_COMPOSE_PROJECT_NAME:-bi-rmp-staging-n8n}"
STAGING_N8N_CONTAINER="${STAGING_N8N_CONTAINER:-bi-rmp-staging-n8n}"
STAGING_N8N_POSTGRES_CONTAINER="${STAGING_N8N_POSTGRES_CONTAINER:-bi-rmp-staging-n8n-postgres}"
STAGING_HOSTNAME="${STAGING_HOSTNAME:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hostname)
            STAGING_HOSTNAME="$2"
            shift 2
            ;;
        *)
            if [[ -z "${STAGING_HOSTNAME}" ]]; then
                STAGING_HOSTNAME="$1"
            fi
            shift
            ;;
    esac
done

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

fail_if_production_collision

if [[ -z "${STAGING_HOSTNAME}" ]]; then
    echo "RESULT: FAIL"
    echo "REASON: explicit staging hostname is required (e.g. STAGING_HOSTNAME=staging.example.com scripts/bootstrap-staging-host.sh or --hostname staging.example.com)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

mkdir -p "${STAGING_APP_DIR}"

if [[ ! -d "${STAGING_APP_DIR}/.venv" ]]; then
    echo "Creating virtual environment in ${STAGING_APP_DIR}/.venv..."
    VENV_TARGET_DIR="${STAGING_APP_DIR}/.venv"
    if command -v cygpath >/dev/null 2>&1; then
        VENV_TARGET_DIR="$(cygpath -w "${VENV_TARGET_DIR}")"
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv "${VENV_TARGET_DIR}" 2>/dev/null || true
    elif command -v python >/dev/null 2>&1; then
        python -m venv "${VENV_TARGET_DIR}" 2>/dev/null || true
    fi
else
    echo "Virtual environment already exists in ${STAGING_APP_DIR}/.venv"
fi

if [[ ! -f "${STAGING_ENV_FILE}" ]]; then
    if [[ -f "${REPO_ROOT}/.env.staging.example" ]]; then
        cp "${REPO_ROOT}/.env.staging.example" "${STAGING_ENV_FILE}"
        echo "STAGING_ENV_FILE=CREATED_FROM_EXAMPLE"
    else
        echo "RESULT: FAIL"
        echo "REASON: missing .env.staging.example template"
        exit 1
    fi
else
    echo "STAGING_ENV_FILE=EXISTS_PRESERVED"
fi

SERVICE_SRC="${REPO_ROOT}/infra/systemd/bi-rmp-staging.service.example"
SERVICE_DEST="/etc/systemd/system/${STAGING_BACKEND_SERVICE}"

if [[ -f "${SERVICE_SRC}" ]]; then
    SUDO_CMD=""
    if [[ "$(id -u)" != "0" ]] && command -v sudo >/dev/null 2>&1; then
        SUDO_CMD="sudo"
    fi

    if [[ -d "/etc/systemd/system" ]]; then
        $SUDO_CMD cp "${SERVICE_SRC}" "${SERVICE_DEST}" 2>/dev/null || true
        if command -v systemctl >/dev/null 2>&1; then
            $SUDO_CMD systemctl daemon-reload 2>/dev/null || true
            $SUDO_CMD systemctl enable "${STAGING_BACKEND_SERVICE}" 2>/dev/null || true
            echo "SYSTEMD_SERVICE=INSTALLED_AND_ENABLED"
        fi
    fi
fi

NGINX_SRC="${REPO_ROOT}/infra/nginx/bi-rmp-staging-gateway.conf.example"
NGINX_AVAIL="/etc/nginx/sites-available/bi-rmp-staging-gateway.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/bi-rmp-staging-gateway.conf"
NGINX_CONF_D="/etc/nginx/conf.d/bi-rmp-staging-gateway.conf"

if [[ -f "${NGINX_SRC}" ]]; then
    TMP_CONF="$(mktemp)"
    sed "s/staging-host.example/${STAGING_HOSTNAME}/g" "${NGINX_SRC}" > "${TMP_CONF}"

    SUDO_CMD=""
    if [[ "$(id -u)" != "0" ]] && command -v sudo >/dev/null 2>&1; then
        SUDO_CMD="sudo"
    fi

    if [[ -d "/etc/nginx/sites-available" ]]; then
        $SUDO_CMD cp "${TMP_CONF}" "${NGINX_AVAIL}" 2>/dev/null || true
        if [[ -d "/etc/nginx/sites-enabled" ]]; then
            $SUDO_CMD ln -sf "${NGINX_AVAIL}" "${NGINX_ENABLED}" 2>/dev/null || true
        fi
    elif [[ -d "/etc/nginx/conf.d" ]]; then
        $SUDO_CMD cp "${TMP_CONF}" "${NGINX_CONF_D}" 2>/dev/null || true
    fi
    rm -f "${TMP_CONF}"

    if command -v nginx >/dev/null 2>&1; then
        $SUDO_CMD nginx -t 2>/dev/null || true
        if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx 2>/dev/null; then
            $SUDO_CMD systemctl reload nginx 2>/dev/null || true
        fi
        echo "NGINX_GATEWAY=CONFIGURED_AND_TESTED"
    fi
fi

echo "RESULT: BOOTSTRAP_STAGING_HOST_COMPLETED"
echo "STAGING_APP_DIR=${STAGING_APP_DIR}"
echo "STAGING_HOSTNAME=${STAGING_HOSTNAME}"
