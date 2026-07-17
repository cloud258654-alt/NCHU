#!/usr/bin/env bash

set -Eeuo pipefail

APP_DIR="/home/harcker8119/BI-RMP"
ENV_FILE="${APP_DIR}/.env"

BACKEND_SERVICE="bi-rmp.service"
BACKEND_PORT="8001"

N8N_COMPOSE_FILE="${APP_DIR}/infra/n8n/docker-compose.yml"
N8N_CONTAINER="${N8N_CONTAINER:-bi-rmp-n8n}"
N8N_WORKFLOW_SOURCE="${APP_DIR}/infra/n8n/workflows/reputation-optimization-flow.json"
N8N_WORKFLOW_CONTAINER_DIR="/opt/bi-rmp/n8n-workflows"

TARGET_SHA="${1:?Missing target commit SHA}"
DEPLOY_SCOPE="${2:-auto}"
LOCK_FILE="/tmp/bi-rmp-deploy.lock"
TEMP_N8N_WORKFLOW_IMPORT=""
TEMP_N8N_WORKFLOW_EXPORT=""
BACKUP_DIR=""

case "${DEPLOY_SCOPE}" in
    auto|backend-only|full)
        ;;
    *)
        echo "ERROR: Unsupported deployment scope: ${DEPLOY_SCOPE}"
        exit 1
        ;;
esac

cleanup() {
    if [[ -n "${TEMP_N8N_WORKFLOW_IMPORT}" ]]; then
        rm -f -- "${TEMP_N8N_WORKFLOW_IMPORT}"
    fi

    if [[ -n "${TEMP_N8N_WORKFLOW_EXPORT}" ]]; then
        rm -f -- "${TEMP_N8N_WORKFLOW_EXPORT}"
    fi
}

trap cleanup EXIT

exec 9>"${LOCK_FILE}"

if ! flock -n 9; then
    echo "Another BI-RMP deployment is running."
    exit 1
fi

read_env_value() {
    local key="$1"
    local value=""

    if [[ -f "${ENV_FILE}" ]]; then
        value="$(
            grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" \
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

validate_liff_configuration() {
    local liff_id
    local line_login_channel_id
    local registration_url
    local missing_keys=()

    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "ERROR: ${ENV_FILE} is required for production deployment."
        exit 1
    fi

    liff_id="$(read_env_value LINE_LIFF_ID)"
    line_login_channel_id="$(read_env_value LINE_LOGIN_CHANNEL_ID)"
    registration_url="$(read_env_value BI_RMP_REGISTRATION_URL)"

    if [[ -z "${liff_id}" ]]; then
        missing_keys+=("LINE_LIFF_ID")
    fi

    if [[ -z "${line_login_channel_id}" ]]; then
        missing_keys+=("LINE_LOGIN_CHANNEL_ID")
    fi

    if (( ${#missing_keys[@]} > 0 )); then
        echo "ERROR: Missing required LIFF configuration in ${ENV_FILE}: ${missing_keys[*]}"
        exit 1
    fi

    if [[ -n "${registration_url}" ]]; then
        echo "WARNING: BI_RMP_REGISTRATION_URL is ignored while LINE_LIFF_ID is configured."
    fi

    echo "LIFF production configuration is present."
}

wait_for_url() {
    local service_name="$1"
    local url="$2"
    local attempts="${3:-20}"

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if curl --fail --silent --show-error "${url}" >/dev/null 2>&1; then
            echo "${service_name} health check passed."
            return 0
        fi

        echo "${service_name} not ready yet: ${attempt}/${attempts}"
        sleep 2
    done

    echo "ERROR: ${service_name} health check failed."
    return 1
}

run_flex_smoke_test() {
    "${APP_DIR}/.venv/bin/python" <<'PY'
import json
import sys

sys.path.insert(0, "Backend")

from api.line_flex import build_reputation_flex_message

sample = {
    "business": {
        "id": 1,
        "name": "部署驗收測試店家",
        "display_name": "部署驗收測試店家",
    },
    "overview": {
        "summary": "目前整體評價偏正向，建議持續留意新增負評與風險變化。",
        "risk_score": 5.9,
        "risk_points": None,
        "risk_level": "low",
        "total_reviews": 97,
        "analyzed_reviews": 97,
        "positive": 37,
        "neutral": 56,
        "negative": 4,
        "unclassified": 0,
        "positive_pct": 38.1,
        "neutral_pct": 57.7,
        "negative_pct": 4.1,
        "unclassified_pct": 0.0,
        "analysis_coverage_pct": 100.0,
        "dominant_sentiment": "positive",
        "updated_at": "2026-07-16T10:01:00+08:00",
    },
    "overall": {
        "score_status": "provisional",
    },
    "platforms": [
        {
            "platform": "ptt",
            "label": "PTT",
            "total": 97,
            "analyzed": 97,
            "positive": 37,
            "neutral": 56,
            "negative": 4,
            "unclassified": 0,
        }
    ],
}

messages = build_reputation_flex_message(sample)

assert messages[0]["type"] == "flex"
assert messages[0]["contents"]["type"] == "bubble"
assert messages[0]["contents"]["size"] == "mega"

payload = json.dumps(messages, ensure_ascii=False)

for text in (
    "🌟 網路評價量化報告",
    "夥伴提醒",
    "風險分數",
    "負評率",
    "分析覆蓋率",
    "評價情緒分布",
    "下次點選「查詢進度」",
):
    assert text in payload, text

print("DEPLOYED_FLEX_SMOKE_TEST=PASS")
print("MESSAGE_TYPE=" + messages[0]["type"])
print("BUBBLE_SIZE=" + messages[0]["contents"]["size"])
PY
}

create_backup() {
    local deploy_ts

    deploy_ts="$(date +%Y%m%d_%H%M%S)"
    BACKUP_DIR="/home/harcker8119/backups/bi-rmp-${deploy_ts}"

    mkdir -p "${BACKUP_DIR}"

    git rev-parse HEAD > "${BACKUP_DIR}/previous_commit.txt"

    if [[ -d Backend ]]; then
        cp -a Backend "${BACKUP_DIR}/Backend"
    fi

    if [[ -d infra/n8n ]]; then
        mkdir -p "${BACKUP_DIR}/infra"
        cp -a infra/n8n "${BACKUP_DIR}/infra/n8n"
    fi

    if [[ -d database ]]; then
        cp -a database "${BACKUP_DIR}/database"
    fi

    echo "Backup directory: ${BACKUP_DIR}"
}

docker_compose() {
    docker compose \
        --env-file "${ENV_FILE}" \
        -f "${N8N_COMPOSE_FILE}" \
        "$@"
}

n8n_cli() {
    docker exec \
        -u node \
        "${N8N_CONTAINER}" \
        n8n \
        "$@"
}

n8n_host_port() {
    local port

    port="$(
        docker port "${N8N_CONTAINER}" 5678/tcp 2>/dev/null \
            | sed -n 's/.*://p' \
            | head -n 1
    )"

    printf '%s' "${port:-5678}"
}

prepare_n8n_workflow_import() {
    local workflow_id="$1"
    local output_path="$2"

    "${APP_DIR}/.venv/bin/python" \
        - "${N8N_WORKFLOW_SOURCE}" "${output_path}" "${workflow_id}" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
output = Path(sys.argv[2])
workflow_id = sys.argv[3]

data = json.loads(source.read_text(encoding="utf-8"))
data["id"] = workflow_id
data["active"] = True

output.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

read_n8n_workflow_name() {
    "${APP_DIR}/.venv/bin/python" - "${N8N_WORKFLOW_SOURCE}" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
name = data.get("name", "")
if not name:
    raise SystemExit("Workflow JSON is missing a name.")
print(name)
PY
}

read_n8n_workflow_webhook_path() {
    "${APP_DIR}/.venv/bin/python" - "${N8N_WORKFLOW_SOURCE}" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

for node in data.get("nodes", []):
    if node.get("type") == "n8n-nodes-base.webhook":
        path = node.get("parameters", {}).get("path", "")
        if path:
            print(path)
            raise SystemExit(0)

raise SystemExit("Workflow JSON is missing a webhook path.")
PY
}

discover_n8n_workflow_id() {
    local workflow_name="$1"
    local webhook_path="$2"
    local export_path="$3"

    "${APP_DIR}/.venv/bin/python" - "${export_path}" "${workflow_name}" "${webhook_path}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
workflow_name = sys.argv[2]
webhook_path = sys.argv[3]

if isinstance(payload, dict):
    workflows = payload.get("workflows") or payload.get("data") or []
else:
    workflows = payload

name_matches = set()
path_matches = set()

for workflow in workflows:
    if not isinstance(workflow, dict):
        continue

    workflow_id = workflow.get("id")
    if not workflow_id:
        continue

    if workflow.get("name") == workflow_name:
        name_matches.add(str(workflow_id))
        continue

    for node in workflow.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if node.get("type") != "n8n-nodes-base.webhook":
            continue
        if node.get("parameters", {}).get("path") == webhook_path:
            path_matches.add(str(workflow_id))

if len(name_matches) == 1:
    print(next(iter(name_matches)))
    raise SystemExit(0)

if len(name_matches) > 1:
    print(
        f"name_matches={len(name_matches)};"
        f"webhook_matches={len(path_matches)};"
        f"ids={','.join(sorted(name_matches))}"
    )
    raise SystemExit(1)

if len(path_matches) != 1:
    print(
        f"name_matches=0;"
        f"webhook_matches={len(path_matches)};"
        f"ids={','.join(sorted(path_matches))}"
    )
    raise SystemExit(1)

print(next(iter(path_matches)))
PY
}

publish_or_activate_n8n_workflow() {
    local workflow_id="$1"

    if n8n_cli publish:workflow "--id=${workflow_id}"; then
        echo "n8n workflow published: ${workflow_id}"
        return 0
    fi

    echo "publish:workflow is unavailable or failed. Trying legacy active flag..."
    n8n_cli update:workflow "--id=${workflow_id}" --active=true
    echo "n8n workflow activated with legacy update:workflow: ${workflow_id}"
}

deploy_n8n() {
    local n8n_changed="$1"
    local workflow_changed="$2"
    local workflow_id
    local project_id
    local user_id
    local import_basename
    local import_container_path
    local import_args
    local port
    local workflow_name
    local webhook_path
    local export_basename
    local export_container_path
    local match_count

    echo "[7/8] Checking n8n deployment..."

    workflow_id="${N8N_WORKFLOW_ID:-$(read_env_value N8N_WORKFLOW_ID)}"
    project_id="${N8N_PROJECT_ID:-$(read_env_value N8N_PROJECT_ID)}"
    user_id="${N8N_USER_ID:-$(read_env_value N8N_USER_ID)}"

    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "ERROR: ${ENV_FILE} is required for n8n deployment."
        exit 1
    fi

    echo "Validating Docker Compose configuration..."
    docker_compose config --quiet

    if [[ "${n8n_changed}" == "true" ]]; then
        echo "n8n files changed. Pulling configured n8n image..."
        docker_compose pull n8n
    elif [[ -n "${workflow_id}" ]]; then
        echo "No infra/n8n diff detected. Syncing workflow because N8N_WORKFLOW_ID is configured."
    else
        echo "No infra/n8n diff detected and N8N_WORKFLOW_ID is not configured."
        echo "Attempting to discover the existing n8n workflow by repository workflow name."
    fi

    echo "Ensuring n8n PostgreSQL and n8n are running..."
    docker_compose up -d postgres
    docker_compose up -d n8n

    port="$(n8n_host_port)"
    wait_for_url "n8n" "http://127.0.0.1:${port}/healthz/readiness" 30

    if [[ "${workflow_changed}" != "true" ]]; then
        echo "No n8n workflow JSON diff detected in this deployment."
        echo "Importing the current repository workflow anyway because n8n deployment ran."
    fi

    if [[ -z "${workflow_id}" ]]; then
        workflow_name="$(read_n8n_workflow_name)"
        webhook_path="$(read_n8n_workflow_webhook_path)"
        export_basename=".line-reputation-existing.${TARGET_SHA}.json"
        TEMP_N8N_WORKFLOW_EXPORT="${APP_DIR}/infra/n8n/workflows/${export_basename}"
        export_container_path="${N8N_WORKFLOW_CONTAINER_DIR}/${export_basename}"

        echo "Exporting existing n8n workflows to discover workflow ID."
        echo "Discovery name: ${workflow_name}"
        echo "Discovery webhook path: ${webhook_path}"
        n8n_cli export:workflow --all "--output=${export_container_path}"

        if ! workflow_id="$(discover_n8n_workflow_id "${workflow_name}" "${webhook_path}" "${TEMP_N8N_WORKFLOW_EXPORT}")"; then
            match_count="${workflow_id}"
            echo "ERROR: Could not discover exactly one existing n8n workflow by name or webhook path."
            echo "Matched workflow count: ${match_count:-unknown}"
            echo "Set N8N_WORKFLOW_ID in ${ENV_FILE} to the fixed production workflow ID."
            exit 1
        fi

        echo "Discovered n8n workflow ID: ${workflow_id}"
    fi

    if [[ ! "${workflow_id}" =~ ^[A-Za-z0-9_-]+$ ]]; then
        echo "ERROR: N8N_WORKFLOW_ID contains unsupported characters."
        exit 1
    fi

    if [[ -n "${project_id}" && -n "${user_id}" ]]; then
        echo "ERROR: Use only one of N8N_PROJECT_ID or N8N_USER_ID."
        exit 1
    fi

    import_basename=".reputation-optimization-flow.${TARGET_SHA}.json"
    TEMP_N8N_WORKFLOW_IMPORT="${APP_DIR}/infra/n8n/workflows/${import_basename}"
    import_container_path="${N8N_WORKFLOW_CONTAINER_DIR}/${import_basename}"

    echo "Preparing n8n workflow import file with fixed workflow ID: ${workflow_id}"
    prepare_n8n_workflow_import "${workflow_id}" "${TEMP_N8N_WORKFLOW_IMPORT}"

    import_args=(import:workflow "--input=${import_container_path}")
    if [[ -n "${project_id}" ]]; then
        import_args+=("--projectId=${project_id}")
    elif [[ -n "${user_id}" ]]; then
        import_args+=("--userId=${user_id}")
    fi

    echo "Importing n8n workflow into database..."
    n8n_cli "${import_args[@]}"

    echo "Publishing or activating n8n workflow..."
    publish_or_activate_n8n_workflow "${workflow_id}"

    echo "Restarting n8n so webhook and published workflow changes take effect..."
    docker_compose up -d --no-deps --force-recreate n8n

    port="$(n8n_host_port)"
    wait_for_url "n8n" "http://127.0.0.1:${port}/healthz/readiness" 30

    docker_compose ps
    N8N_SYNCED=true
}

cd "${APP_DIR}"

PREVIOUS_SHA="$(git rev-parse HEAD)"

echo "========================================"
echo "BI-RMP production deployment"
echo "Previous commit: ${PREVIOUS_SHA}"
echo "Target commit:   ${TARGET_SHA}"
echo "========================================"

echo "[1/8] Fetching origin/main..."
git fetch origin main

echo "[2/8] Validating target commit..."
git cat-file -e "${TARGET_SHA}^{commit}"

if ! git merge-base --is-ancestor "${TARGET_SHA}" origin/main; then
    echo "ERROR: ${TARGET_SHA} is not part of origin/main."
    exit 1
fi

N8N_CHANGED=false
N8N_WORKFLOW_CHANGED=false
DATABASE_CHANGED=false
BACKEND_CHANGED=false
N8N_SYNCED=false
SHOULD_DEPLOY_BACKEND=false
SHOULD_DEPLOY_N8N=false
SHOULD_RUN_MIGRATIONS=false

if ! git diff --quiet \
    "${PREVIOUS_SHA}" \
    "${TARGET_SHA}" \
    -- Backend; then

    BACKEND_CHANGED=true
fi

if ! git diff --quiet \
    "${PREVIOUS_SHA}" \
    "${TARGET_SHA}" \
    -- infra/n8n; then

    N8N_CHANGED=true
fi

if ! git diff --quiet \
    "${PREVIOUS_SHA}" \
    "${TARGET_SHA}" \
    -- infra/n8n/workflows; then

    N8N_WORKFLOW_CHANGED=true
fi

if ! git diff --quiet \
    "${PREVIOUS_SHA}" \
    "${TARGET_SHA}" \
    -- database; then

    DATABASE_CHANGED=true
fi

case "${DEPLOY_SCOPE}" in
    backend-only)
        SHOULD_DEPLOY_BACKEND=true
        SHOULD_DEPLOY_N8N=false
        SHOULD_RUN_MIGRATIONS=false
        ;;

    full)
        SHOULD_DEPLOY_BACKEND=true
        SHOULD_DEPLOY_N8N=true
        SHOULD_RUN_MIGRATIONS="${DATABASE_CHANGED}"
        ;;

    auto)
        SHOULD_DEPLOY_BACKEND="${BACKEND_CHANGED}"
        SHOULD_DEPLOY_N8N="${N8N_CHANGED}"
        SHOULD_RUN_MIGRATIONS="${DATABASE_CHANGED}"
        ;;
esac

echo "Deployment scope: ${DEPLOY_SCOPE}"
echo "Backend changed: ${BACKEND_CHANGED}"
echo "n8n changed: ${N8N_CHANGED}"
echo "n8n workflow changed: ${N8N_WORKFLOW_CHANGED}"
echo "Database changed: ${DATABASE_CHANGED}"
echo "Deploy backend: ${SHOULD_DEPLOY_BACKEND}"
echo "Deploy n8n: ${SHOULD_DEPLOY_N8N}"
echo "Run migrations: ${SHOULD_RUN_MIGRATIONS}"

if [[ "${DEPLOY_SCOPE}" == "backend-only" ]]; then
    if [[ "${N8N_CHANGED}" == "true" ]]; then
        echo "backend-only scope: n8n changes detected but will not be deployed."
    fi
    if [[ "${DATABASE_CHANGED}" == "true" ]]; then
        echo "backend-only scope: database changes detected but migrations will not run."
    fi
fi

if [[ "${SHOULD_RUN_MIGRATIONS}" == "true" ]]; then
    echo "ERROR: Database changes detected. Production migrations require manual MIGRATION_APPROVED confirmation and are not run by this script."
    exit 1
fi

echo "Creating production rollback point..."
create_backup

echo "[3/8] Updating production working tree..."
git switch main
git reset --hard "${TARGET_SHA}"

if [[ "${SHOULD_DEPLOY_BACKEND}" == "true" ]]; then
    echo "Validating production environment..."
    validate_liff_configuration

    echo "[4/8] Installing Python dependencies..."
    "${APP_DIR}/.venv/bin/python" \
        -m pip install \
        --disable-pip-version-check \
        -r requirements.txt

    echo "[5/8] Checking Python source..."
    "${APP_DIR}/.venv/bin/python" \
        -m compileall \
        -q Backend

    echo "[6/8] Restarting ${BACKEND_SERVICE}..."
    sudo systemctl restart "${BACKEND_SERVICE}"

    if ! sudo systemctl is-active --quiet "${BACKEND_SERVICE}"; then
        echo "ERROR: ${BACKEND_SERVICE} is not active."
        sudo systemctl status "${BACKEND_SERVICE}" --no-pager -l
        exit 1
    fi

    if ! wait_for_url \
        "BI-RMP Backend" \
        "http://127.0.0.1:${BACKEND_PORT}/health" \
        15; then

        sudo systemctl status "${BACKEND_SERVICE}" --no-pager -l
        exit 1
    fi

    if ! wait_for_url \
        "BI-RMP LIFF registration page" \
        "http://127.0.0.1:${BACKEND_PORT}/register" \
        5; then

        sudo systemctl status "${BACKEND_SERVICE}" --no-pager -l
        exit 1
    fi

    if ! wait_for_url \
        "BI-RMP LIFF configuration" \
        "http://127.0.0.1:${BACKEND_PORT}/api/liff/config" \
        5; then

        sudo systemctl status "${BACKEND_SERVICE}" --no-pager -l
        exit 1
    fi

    echo "Running deployed LINE Flex smoke test..."
    run_flex_smoke_test
else
    echo "[4/8] Backend deployment skipped by scope."
fi

if [[ "${SHOULD_DEPLOY_N8N}" == "true" ]]; then
    deploy_n8n "${N8N_CHANGED}" "${N8N_WORKFLOW_CHANGED}"
else
    echo "[7/8] n8n deployment skipped by scope."
fi

echo "[8/8] Deployment summary"
if [[ "${SHOULD_DEPLOY_BACKEND}" == "true" ]]; then
    echo "Backend deployed and healthy."
else
    echo "Backend deployment skipped."
fi

if [[ "${N8N_SYNCED}" == "true" ]]; then
    echo "n8n workflow imported with fixed workflow ID."
elif [[ "${N8N_CHANGED}" == "true" ]]; then
    echo "n8n changes were detected but n8n deployment was skipped."
else
    echo "n8n deployment skipped."
fi

echo "Migration result: skipped."
echo "Backup directory: ${BACKUP_DIR}"
echo "Deployment completed successfully."
echo "Commit: ${TARGET_SHA}"
