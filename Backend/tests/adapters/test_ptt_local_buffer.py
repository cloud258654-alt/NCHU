import json

from adapters.ptt import local_buffer


def test_local_buffer_writes_valid_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(local_buffer, "BUFFER_ROOT", tmp_path)

    path = local_buffer.write_ptt_buffer(
        [{"source_url": "https://www.ptt.cc/bbs/Food/M.1.html", "title": "Demo"}],
        query="Demo",
        crawl_job_id="job-1",
        service_task_id="task-1",
    )

    assert path is not None
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["platform"] == "ptt"
    assert record["query"] == "Demo"
    assert record["crawl_job_id"] == "job-1"
    assert record["service_task_id"] == "task-1"
    assert record["payload"]["title"] == "Demo"


def test_local_buffer_preserves_traditional_chinese_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(local_buffer, "BUFFER_ROOT", tmp_path)

    path = local_buffer.write_ptt_buffer(
        [{"source_url": "https://www.ptt.cc/bbs/Food/M.2.html", "title": "台南牛肉湯"}],
        query="牛肉湯",
    )

    text = path.read_text(encoding="utf-8")
    assert "台南牛肉湯" in text
    assert json.loads(text)["payload"]["title"] == "台南牛肉湯"
