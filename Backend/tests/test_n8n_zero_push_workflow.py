import base64
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / "infra" / "n8n" / "workflows" / "reputation-optimization-flow.json"


def _workflow():
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_workflow_has_create_reply_run_order_and_no_push_endpoint():
    workflow = _workflow()
    connections = workflow["connections"]
    serialized = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert connections["Prepare Crawler Trigger Payload"]["main"][0][0]["node"] == "Create Background Crawl Job"
    assert connections["Create Background Crawl Job"]["main"][0][0]["node"] == "Format Crawl Accepted Response"
    assert connections["Send Crawl Accepted Response"]["main"][0][0]["node"] == "Trigger Background Crawler Run"
    assert "/v2/bot/message/push" not in serialized
    assert "Webhook - Button Business Registration" not in serialized
    assert '"path": "register-business"' not in serialized


def test_status_and_result_replies_use_current_interaction_reply_token():
    workflow = _workflow()
    nodes = {node["name"]: node for node in workflow["nodes"]}

    verify_code = nodes["Verify LINE Signature and Parse Intent"]["parameters"]["jsCode"]
    status_code = nodes["Format Crawl Status Response"]["parameters"]["jsCode"]
    accepted_code = nodes["Format Crawl Accepted Response"]["parameters"]["jsCode"]

    assert "crawl_status:" in verify_code
    assert "event.replyToken" in status_code
    assert "quickReply" in accepted_code
    assert "crawl_status:" in accepted_code


def test_status_endpoint_supports_explicit_and_latest_task_lookup():
    workflow = _workflow()
    status_node = next(node for node in workflow["nodes"] if node["name"] == "Fetch Crawl Job Status")
    url = status_node["parameters"]["url"]

    assert "/jobs/' + $json.taskId + '/status" in url
    assert "/jobs/status/latest" in url


def test_staging_allowlist_blocks_before_backend_or_message_logging():
    workflow = _workflow()
    connections = workflow["connections"]
    nodes = {node["name"]: node for node in workflow["nodes"]}

    allowlist_code = json.dumps(nodes["Check Staging LINE Allowlist"], ensure_ascii=False)
    blocked_code = nodes["Format Staging Restricted Response"]["parameters"]["jsCode"]

    assert "BI_RMP_LINE_ALLOWED_USER_IDS" in allowlist_code
    assert "APP_ENV" in allowlist_code
    assert "configured test users" not in blocked_code
    assert "此測試環境僅開放已授權的測試帳號使用。" in blocked_code

    assert connections["LINE Webhook"]["main"][0] == [
        {
            "node": "Verify LINE Signature and Parse Intent",
            "type": "main",
            "index": 0,
        }
    ]
    assert connections["Verify LINE Signature and Parse Intent"]["main"][0][0]["node"] == (
        "Check Staging LINE Allowlist"
    )

    allowed_targets = {
        item["node"]
        for item in connections["Check Staging LINE Allowlist"]["main"][0]
    }
    blocked_targets = {
        item["node"]
        for item in connections["Check Staging LINE Allowlist"]["main"][1]
    }

    assert allowed_targets == {"Log Incoming Message", "Identify Client and Business"}
    assert blocked_targets == {"Format Staging Restricted Response"}
    assert connections["Format Staging Restricted Response"]["main"][0][0]["node"] == (
        "Send General Message Response"
    )


def test_status_formatter_does_not_expose_raw_backend_errors(tmp_path):
    forbidden = [
        "DATABASE_URL",
        "postgres://",
        "user:pass",
        "db.supabase.co",
        "SELECT",
        "clients",
        "Traceback",
        "E:\\Ai study",
        "LINE_CHANNEL_ACCESS_TOKEN",
        "password",
        "service_role",
    ]
    malicious_statuses = [
        {
            "status": "failed",
            "task_id": 77,
            "error_type": "internal_error",
            "error_message": "DATABASE_URL=postgres://user:pass@db.supabase.co SELECT * FROM clients",
        },
        {
            "status": "timeout",
            "task_id": 77,
            "error_message": 'Traceback (most recent call last)\nFile "E:\\Ai study\\NCHU\\Backend\\api\\main.py"',
        },
        {
            "status": "cancelled",
            "task_id": 77,
            "error_message": "LINE_CHANNEL_ACCESS_TOKEN=abc123 password=secret service_role=xyz",
        },
        {
            "status": "failed",
            "task_id": 77,
            "error_type": "database_unavailable",
            "error_message": "psycopg2 could not connect to db.supabase.co",
        },
    ]

    status_code = _node_code("Format Crawl Status Response")
    assert "status.error_message" not in status_code

    for status in malicious_statuses:
        message = _run_status_formatter(tmp_path, status)
        text = message["text"]
        assert message["type"] == "text"
        assert all(value not in text for value in forbidden)
        assert text
        assert text != status["error_message"]


def test_status_formatter_preserves_success_and_running_paths(tmp_path):
    completed = _run_status_formatter(
        tmp_path,
        {
            "status": "completed",
            "task_id": 77,
            "articles_found": 2,
            "comments_found": 3,
        },
    )
    running = _run_status_formatter(
        tmp_path,
        {
            "status": "running",
            "task_id": 77,
            "platform_results": [{"platform": "ptt", "status": "running"}],
        },
    )

    assert "2" in completed["text"]
    assert "3" in completed["text"]
    assert running["quickReply"]["items"][0]["action"]["data"] == "crawl_status:77"
    assert "ptt" not in running["text"]
    assert "PTT" in running["text"]


def _node_code(node_name: str) -> str:
    workflow = _workflow()
    nodes = {node["name"]: node for node in workflow["nodes"]}
    return nodes[node_name]["parameters"]["jsCode"]


def _run_status_formatter(tmp_path: Path, status: dict[str, object]) -> dict[str, object]:
    code = _node_code("Format Crawl Status Response")
    event = {
        "replyToken": "reply-token",
        "lineUserId": "U-A",
        "taskId": status.get("task_id"),
    }
    runner = tmp_path / "run_status_formatter.js"
    encoded_code = base64.b64encode(code.encode("utf-8")).decode("ascii")
    runner.write_text(
        "const workflowCode = Buffer.from("
        + json.dumps(encoded_code)
        + ", 'base64').toString('utf8');\n"
        "globalThis.$json = " + json.dumps(status, ensure_ascii=False) + ";\n"
        "const event = " + json.dumps(event, ensure_ascii=False) + ";\n"
        "globalThis.$ = () => ({ item: { json: event } });\n"
        "const output = new Function(workflowCode)();\n"
        "process.stdout.write(JSON.stringify(output[0].json.messages[0]));\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(runner)],
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    return json.loads(result.stdout)
