# tests/test_subscribers.py
import pytest
from src import subscribers


class _Resp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else []
        self.text = text

    def json(self):
        return self._json


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")


def test_upsert_subscriber_posts_with_merge(monkeypatch):
    calls = {}

    def fake_post(url, **kw):
        calls["url"] = url
        calls["json"] = kw["json"]
        calls["params"] = kw["params"]
        calls["headers"] = kw["headers"]
        return _Resp(status_code=201)

    monkeypatch.setattr(subscribers.requests, "post", fake_post)
    subscribers.upsert_subscriber(123, first_name="Xavier", username="frednqy", start_payload="xavierspare")
    assert calls["url"].endswith("/rest/v1/subscribers")
    assert calls["params"]["on_conflict"] == "chat_id"
    assert calls["json"]["chat_id"] == 123
    assert calls["json"]["active"] is True
    assert "merge-duplicates" in calls["headers"]["Prefer"]


def test_upsert_raises_on_error(monkeypatch):
    monkeypatch.setattr(subscribers.requests, "post", lambda *a, **k: _Resp(status_code=500, text="boom"))
    with pytest.raises(RuntimeError):
        subscribers.upsert_subscriber(1)


def test_deactivate_patches_active_false(monkeypatch):
    calls = {}

    def fake_patch(url, **kw):
        calls["params"] = kw["params"]
        calls["json"] = kw["json"]
        return _Resp(status_code=204)

    monkeypatch.setattr(subscribers.requests, "patch", fake_patch)
    subscribers.deactivate(123)
    assert calls["params"]["chat_id"] == "eq.123"
    assert calls["json"]["active"] is False
    assert calls["json"]["unsubscribed_at"] is not None


def test_list_active_returns_rows(monkeypatch):
    rows = [{"chat_id": 1, "first_name": "A"}, {"chat_id": 2, "first_name": "B"}]

    def fake_get(url, **kw):
        assert kw["params"]["active"] == "eq.true"
        return _Resp(status_code=200, json_data=rows)

    monkeypatch.setattr(subscribers.requests, "get", fake_get)
    assert subscribers.list_active() == rows
