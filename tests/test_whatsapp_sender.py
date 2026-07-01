import pytest

import src.whatsapp_sender as ws


class FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def _set_env(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "TOKEN123")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "PHONE999")
    monkeypatch.setenv("WHATSAPP_RECIPIENT", "6591234567")


def test_send_photo_success(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"PNGDATA")
    _set_env(monkeypatch)

    calls = []

    def fake_post(url, headers=None, data=None, files=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "data": data, "files": files, "json": json})
        if url.endswith("/media"):
            return FakeResp(200, {"id": "MEDIA_ABC"})
        return FakeResp(200, {"messages": [{"id": "wamid.XYZ"}]})

    monkeypatch.setattr(ws.requests, "post", fake_post)

    result = ws.send_photo(img, "caption")
    assert result["messages"][0]["id"] == "wamid.XYZ"

    # Two calls, in order: media upload then message send.
    assert len(calls) == 2
    upload, send = calls
    assert upload["url"].endswith("/PHONE999/media")
    assert upload["data"]["messaging_product"] == "whatsapp"
    assert upload["headers"]["Authorization"] == "Bearer TOKEN123"

    assert send["url"].endswith("/PHONE999/messages")
    assert send["json"]["to"] == "6591234567"
    assert send["json"]["type"] == "image"
    # The media id from step 1 is threaded into the send payload.
    assert send["json"]["image"]["id"] == "MEDIA_ABC"
    assert send["json"]["image"]["caption"] == "caption"


def test_send_photo_retries_then_raises(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    _set_env(monkeypatch)

    calls = {"n": 0}

    def fake_post(url, headers=None, data=None, files=None, json=None, timeout=None):
        calls["n"] += 1
        return FakeResp(500, {"error": {"message": "server error"}})

    monkeypatch.setattr(ws.requests, "post", fake_post)
    monkeypatch.setattr(ws.time, "sleep", lambda _s: None)

    with pytest.raises(Exception):
        ws.send_photo(img, "caption")
    # Two attempts (one retry); each attempt fails at the media-upload step.
    assert calls["n"] == 2


def test_caption_truncated_to_limit(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    _set_env(monkeypatch)

    captured = {}

    def fake_post(url, headers=None, data=None, files=None, json=None, timeout=None):
        if url.endswith("/media"):
            return FakeResp(200, {"id": "M"})
        captured["json"] = json
        return FakeResp(200, {"messages": [{"id": "w"}]})

    monkeypatch.setattr(ws.requests, "post", fake_post)

    ws.send_photo(img, "A" * 2000)
    assert len(captured["json"]["image"]["caption"]) == 1024
