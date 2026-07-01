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
