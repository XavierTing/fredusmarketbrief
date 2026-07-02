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


from pathlib import Path

import pytest

from src import telegram_sender


class _R:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def _img(tmp_path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"PNG")
    return p


def test_send_photo_uses_explicit_chat_id(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    seen = {}

    def fake_post(url, **kw):
        seen["chat_id"] = kw["data"]["chat_id"]
        return _R(200, {"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)
    telegram_sender.send_photo(_img(tmp_path), caption="hi", chat_id=999)
    assert seen["chat_id"] == 999


def test_send_photo_raises_blocked_on_403(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(
        telegram_sender.requests, "post",
        lambda *a, **k: _R(403, {"ok": False, "description": "Forbidden: bot was blocked by the user"}),
    )
    with pytest.raises(telegram_sender.TelegramBlockedError):
        telegram_sender.send_photo(_img(tmp_path), chat_id=5)
