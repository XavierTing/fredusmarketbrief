"""Vercel serverless webhook for Telegram /start and /stop.

Standalone (only `requests`): registers subscribers in Supabase and sends a
welcome + an instant sample of the latest infographic. Shares the Supabase data
contract with the pipeline, not Python code. Always returns HTTP 200 quickly so
Telegram does not retry.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

import requests

_TIMEOUT = 20

WELCOME = (
    "\U0001F4C8 You're subscribed to the daily US Market Brief.\n"
    "You'll get a clean infographic each morning — indices, crypto, "
    "commodities, and the day's movers.\n\nSend /stop anytime to unsubscribe."
)
GOODBYE = "You've been unsubscribed from the daily US Market Brief. Send /start to rejoin anytime."


def _env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"{name} is not set")
    return val


def _sb_headers(extra: dict | None = None) -> dict:
    key = _env("SUPABASE_SERVICE_KEY")
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _sb_url() -> str:
    return _env("SUPABASE_URL").rstrip("/")


def _upsert(chat_id, first_name=None, last_name=None, username=None, start_payload=None) -> None:
    payload = {
        "chat_id": chat_id, "first_name": first_name, "last_name": last_name,
        "username": username, "start_payload": start_payload,
        "active": True, "unsubscribed_at": None,
    }
    requests.post(
        f"{_sb_url()}/rest/v1/subscribers",
        params={"on_conflict": "chat_id"}, json=payload,
        headers=_sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        timeout=_TIMEOUT,
    ).raise_for_status()


def _deactivate(chat_id) -> None:
    from datetime import datetime, timezone
    requests.patch(
        f"{_sb_url()}/rest/v1/subscribers",
        params={"chat_id": f"eq.{chat_id}"},
        json={"active": False, "unsubscribed_at": datetime.now(timezone.utc).isoformat()},
        headers=_sb_headers({"Prefer": "return=minimal"}),
        timeout=_TIMEOUT,
    ).raise_for_status()


def _fetch_latest() -> bytes | None:
    r = requests.get(
        f"{_sb_url()}/storage/v1/object/briefs/latest.png",
        headers={"apikey": _env("SUPABASE_SERVICE_KEY"),
                 "Authorization": f"Bearer {_env('SUPABASE_SERVICE_KEY')}"},
        timeout=_TIMEOUT,
    )
    return r.content if r.status_code == 200 else None


def _tg(method: str) -> str:
    return f"https://api.telegram.org/bot{_env('TELEGRAM_BOT_TOKEN')}/{method}"


def _send_message(chat_id, text: str) -> None:
    # Best-effort (no raise_for_status): a lost welcome/goodbye must not abort the
    # handler or roll back a successful DB write. The DB writes (_upsert/_deactivate)
    # DO raise, so we never message "you're subscribed" when the write actually failed.
    requests.post(_tg("sendMessage"), json={"chat_id": chat_id, "text": text}, timeout=_TIMEOUT)


def _send_photo_bytes(chat_id, image: bytes, caption: str = "") -> None:
    requests.post(
        _tg("sendPhoto"),
        data={"chat_id": chat_id, "caption": caption[:1024]},
        files={"photo": ("latest.png", image, "image/png")},
        timeout=60,
    )


def handle_update(update: dict) -> None:
    """Route a Telegram update. Only /start and /stop act; everything else is ignored."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    if chat_id is None or not text:
        return

    if text.startswith("/start"):
        frm = message.get("from", {})
        payload = text[len("/start"):].strip() or None
        _upsert(
            chat_id=chat_id,
            first_name=frm.get("first_name"),
            last_name=frm.get("last_name"),
            username=frm.get("username"),
            start_payload=payload,
        )
        _send_message(chat_id, WELCOME)
        sample = _fetch_latest()
        if sample:
            _send_photo_bytes(chat_id, sample, "Here's the latest brief \U0001F447")
    elif text.startswith("/stop"):
        _deactivate(chat_id)
        _send_message(chat_id, GOODBYE)
    # anything else: ignore


def _authorized(provided: str | None) -> bool:
    """True only when a non-empty secret is configured AND the header matches it."""
    expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    return bool(expected) and provided == expected


class handler(BaseHTTPRequestHandler):  # Vercel entrypoint
    def do_POST(self):  # noqa: N802
        if not _authorized(self.headers.get("X-Telegram-Bot-Api-Secret-Token")):
            self.send_response(403)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            handle_update(json.loads(raw))
        except Exception as exc:  # noqa: BLE001 - never 500 back to Telegram (avoids retry storms)
            # Swallow to keep returning 200, but log to stderr so Vercel captures it.
            print(f"webhook: handle_update failed: {exc!r}", file=sys.stderr)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):  # noqa: N802 - health check
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
