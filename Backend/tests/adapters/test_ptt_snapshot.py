from adapters.ptt import snapshot


def test_snapshot_saves_html(monkeypatch, tmp_path):
    monkeypatch.setattr(snapshot, "SNAPSHOT_ROOT", tmp_path)

    path = snapshot.save_html_snapshot("<html>ptt</html>", external_id="M.1.A.html")

    assert path is not None
    assert path.read_text(encoding="utf-8") == "<html>ptt</html>"


def test_snapshot_sanitizes_unsafe_filename_characters(monkeypatch, tmp_path):
    monkeypatch.setattr(snapshot, "SNAPSHOT_ROOT", tmp_path)

    path = snapshot.save_html_snapshot("<html>ptt</html>", external_id="../M:1/A?.html")

    assert path is not None
    assert path.name == "A_.html"
    assert path.parent.parent == tmp_path
