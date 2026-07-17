import json
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
