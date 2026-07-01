import pytest

import src.telegram_sender as ts


class FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def test_send_photo_success(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"PNGDATA")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOKEN123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@mychannel")

    captured = {}

    def fake_post(url, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return FakeResp(200, {"ok": True, "result": {"message_id": 7}})

    monkeypatch.setattr(ts.requests, "post", fake_post)

    result = ts.send_photo(img, "caption")
    assert result["ok"] is True
    assert captured["data"]["chat_id"] == "@mychannel"
    assert captured["data"]["caption"] == "caption"
    assert "TOKEN123" in captured["url"]


def test_send_photo_retries_then_raises(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@c")

    calls = {"n": 0}

    def fake_post(url, data=None, files=None, timeout=None):
        calls["n"] += 1
        return FakeResp(500, {"ok": False, "description": "server error"})

    monkeypatch.setattr(ts.requests, "post", fake_post)
    monkeypatch.setattr(ts.time, "sleep", lambda _s: None)

    with pytest.raises(Exception):
        ts.send_photo(img, "caption")
    assert calls["n"] == 2  # tried twice (one retry)


def test_caption_truncated_to_limit(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@c")

    captured = {}

    def fake_post(url, data=None, files=None, timeout=None):
        captured["data"] = data
        return FakeResp(200, {"ok": True})

    monkeypatch.setattr(ts.requests, "post", fake_post)

    ts.send_photo(img, "A" * 2000)
    assert len(captured["data"]["caption"]) == 1024
