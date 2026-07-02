# tests/test_webhook.py
import importlib.util
from pathlib import Path

import pytest

WEBHOOK = Path(__file__).resolve().parents[1] / "webhook" / "api" / "telegram_webhook.py"


@pytest.fixture()
def mod(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s")
    spec = importlib.util.spec_from_file_location("telegram_webhook", WEBHOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _start_update(text="/start xavierspare"):
    return {"message": {"chat": {"id": 42}, "from": {"first_name": "Xavier", "username": "frednqy"}, "text": text}}


def test_start_registers_and_sends_welcome(mod, monkeypatch):
    actions = []
    monkeypatch.setattr(mod, "_upsert", lambda **kw: actions.append(("upsert", kw)))
    monkeypatch.setattr(mod, "_send_message", lambda cid, text: actions.append(("msg", cid)))
    monkeypatch.setattr(mod, "_fetch_latest", lambda: b"IMG")
    monkeypatch.setattr(mod, "_send_photo_bytes", lambda cid, img, cap: actions.append(("photo", cid)))

    mod.handle_update(_start_update())
    kinds = [a[0] for a in actions]
    assert "upsert" in kinds and "msg" in kinds and "photo" in kinds
    upsert_kw = actions[0][1]
    assert upsert_kw["chat_id"] == 42
    assert upsert_kw["start_payload"] == "xavierspare"


def test_start_without_sample_still_welcomes(mod, monkeypatch):
    actions = []
    monkeypatch.setattr(mod, "_upsert", lambda **kw: None)
    monkeypatch.setattr(mod, "_send_message", lambda cid, text: actions.append("msg"))
    monkeypatch.setattr(mod, "_fetch_latest", lambda: None)  # no sample yet
    monkeypatch.setattr(mod, "_send_photo_bytes", lambda *a: actions.append("photo"))
    mod.handle_update(_start_update())
    assert actions == ["msg"]  # welcome sent, no photo


def test_stop_deactivates(mod, monkeypatch):
    actions = []
    monkeypatch.setattr(mod, "_deactivate", lambda cid: actions.append(("deact", cid)))
    monkeypatch.setattr(mod, "_send_message", lambda cid, text: actions.append(("msg", cid)))
    mod.handle_update({"message": {"chat": {"id": 7}, "from": {}, "text": "/stop"}})
    assert ("deact", 7) in actions and ("msg", 7) in actions


def test_unknown_text_ignored(mod, monkeypatch):
    called = []
    monkeypatch.setattr(mod, "_upsert", lambda **kw: called.append("u"))
    monkeypatch.setattr(mod, "_deactivate", lambda cid: called.append("d"))
    monkeypatch.setattr(mod, "_send_message", lambda cid, text: called.append("m"))
    mod.handle_update({"message": {"chat": {"id": 1}, "from": {}, "text": "hello"}})
    assert called == []
