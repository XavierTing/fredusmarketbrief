from pathlib import Path

import pytest

from src import main as app_main


def test_main_accepts_style_argument(monkeypatch, tmp_path):
    calls = {}

    def fake_render(summary, out_path, style="report"):
        calls["style"] = style
        calls["out_path"] = Path(out_path)
        return Path(out_path)

    monkeypatch.setattr(app_main, "render_png", fake_render)
    out = tmp_path / "compass.png"

    assert app_main.main(["--mock", "--dry-run", "--style", "compass", "--out", str(out)]) == 0
    assert calls == {"style": "compass", "out_path": out}


def test_main_defaults_to_compass_style(monkeypatch, tmp_path):
    calls = {}

    def fake_render(summary, out_path, style="report"):
        calls["style"] = style
        calls["out_path"] = Path(out_path)
        return Path(out_path)

    monkeypatch.setattr(app_main, "render_png", fake_render)
    out = tmp_path / "default.png"

    assert app_main.main(["--mock", "--dry-run", "--out", str(out)]) == 0
    assert calls == {"style": "compass", "out_path": out}


def _fake_channel(record, name, fail=False):
    def send(out_path, caption=""):
        record.append(name)
        if fail:
            raise RuntimeError(f"{name} down")
        return {"ok": True}

    return send


def test_deliver_broadcasts_to_all_channels(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(
        app_main,
        "_CHANNELS",
        [("Telegram", _fake_channel(sent, "Telegram")), ("WhatsApp", _fake_channel(sent, "WhatsApp"))],
    )

    app_main._deliver(tmp_path / "img.png", "cap")
    assert sent == ["Telegram", "WhatsApp"]


def test_deliver_one_channel_failing_does_not_block_the_other(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(
        app_main,
        "_CHANNELS",
        [
            ("Telegram", _fake_channel(sent, "Telegram", fail=True)),
            ("WhatsApp", _fake_channel(sent, "WhatsApp")),
        ],
    )

    # WhatsApp still runs and the run does not raise (at least one channel succeeded).
    app_main._deliver(tmp_path / "img.png", "cap")
    assert sent == ["Telegram", "WhatsApp"]


def test_deliver_raises_only_when_all_channels_fail(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(
        app_main,
        "_CHANNELS",
        [
            ("Telegram", _fake_channel(sent, "Telegram", fail=True)),
            ("WhatsApp", _fake_channel(sent, "WhatsApp", fail=True)),
        ],
    )

    with pytest.raises(RuntimeError):
        app_main._deliver(tmp_path / "img.png", "cap")
    assert sent == ["Telegram", "WhatsApp"]  # both were attempted


from pathlib import Path

from src import main as main_mod
from src.telegram_sender import TelegramBlockedError


def test_broadcast_fans_out_and_prunes(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    out = tmp_path / "i.png"
    out.write_bytes(b"PNG")

    monkeypatch.setattr(main_mod.storage, "upload_latest", lambda p: None)
    monkeypatch.setattr(main_mod.subscribers, "list_active",
                        lambda: [{"chat_id": 1}, {"chat_id": 2}, {"chat_id": 3}])
    deactivated = []
    monkeypatch.setattr(main_mod.subscribers, "deactivate", lambda cid: deactivated.append(cid))

    sent = []

    def fake_send(path, caption="", chat_id=None):
        if chat_id == 2:
            raise TelegramBlockedError("blocked")
        sent.append(chat_id)

    monkeypatch.setattr(main_mod, "telegram_send_photo", fake_send)
    main_mod._broadcast_telegram(out, caption="cap")
    assert sent == [1, 3]
    assert deactivated == [2]


def test_broadcast_falls_back_to_single_chat_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    out = tmp_path / "i.png"
    out.write_bytes(b"PNG")

    calls = []
    monkeypatch.setattr(main_mod, "telegram_send_photo",
                        lambda path, caption="", chat_id=None: calls.append(chat_id))
    main_mod._broadcast_telegram(out, caption="cap")
    assert calls == [None]  # single-chat send uses the env default (chat_id None)


def test_broadcast_falls_back_when_list_active_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    out = tmp_path / "i.png"
    out.write_bytes(b"PNG")

    monkeypatch.setattr(main_mod.storage, "upload_latest", lambda p: None)

    def boom():
        raise RuntimeError("supabase down")

    monkeypatch.setattr(main_mod.subscribers, "list_active", boom)

    calls = []
    monkeypatch.setattr(
        main_mod, "telegram_send_photo",
        lambda path, caption="", chat_id=None: calls.append(chat_id),
    )
    main_mod._broadcast_telegram(out, caption="cap")
    assert calls == [None]  # Supabase configured but unreachable → single-chat fallback
