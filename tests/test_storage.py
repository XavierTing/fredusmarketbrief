# tests/test_storage.py
import pytest
from src import storage


class _Resp:
    def __init__(self, status_code=200, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")


def test_upload_latest_posts_bytes(monkeypatch, tmp_path):
    png = tmp_path / "img.png"
    png.write_bytes(b"PNGDATA")
    seen = {}

    def fake_post(url, **kw):
        seen["url"] = url
        seen["data"] = kw["data"]
        seen["headers"] = kw["headers"]
        return _Resp(status_code=200)

    monkeypatch.setattr(storage.requests, "post", fake_post)
    storage.upload_latest(png)
    assert seen["url"].endswith("/storage/v1/object/briefs/latest.png")
    assert seen["data"] == b"PNGDATA"
    assert seen["headers"]["x-upsert"] == "true"


def test_fetch_latest_returns_bytes(monkeypatch):
    monkeypatch.setattr(storage.requests, "get", lambda *a, **k: _Resp(status_code=200, content=b"IMG"))
    assert storage.fetch_latest() == b"IMG"


def test_fetch_latest_missing_returns_none(monkeypatch):
    monkeypatch.setattr(storage.requests, "get", lambda *a, **k: _Resp(status_code=404, text="not found"))
    assert storage.fetch_latest() is None


def test_upload_raises_on_error(monkeypatch, tmp_path):
    png = tmp_path / "img.png"
    png.write_bytes(b"X")
    monkeypatch.setattr(storage.requests, "post", lambda *a, **k: _Resp(status_code=500, text="boom"))
    with pytest.raises(RuntimeError):
        storage.upload_latest(png)
