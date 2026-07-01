"""Stage 4 — send the infographic to a Telegram chat.

Uses the Bot API sendPhoto endpoint (multipart upload). The target is any
chat_id: a personal DM (the user must /start the bot first), a group, or a
channel (where the bot must be an admin). One retry on failure; raises if both
attempts fail so the scheduled run surfaces as failed.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from .config import get_telegram_chat_id, get_telegram_token

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendPhoto"
_CAPTION_LIMIT = 1024


def send_photo(image_path: str | Path, caption: str = "") -> dict:
    """Send a photo to the configured channel. Returns the Telegram API result."""
    token = get_telegram_token()
    chat_id = get_telegram_chat_id()
    url = _API.format(token=token)
    caption = caption[:_CAPTION_LIMIT]

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            with open(image_path, "rb") as fh:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": fh},
                    timeout=60,
                )
            body = resp.json()
            if resp.status_code == 200 and body.get("ok"):
                log.info("Sent infographic to %s", chat_id)
                return body
            raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")
        except Exception as exc:  # noqa: BLE001 - retry once, then re-raise
            last_exc = exc
            log.warning("sendPhoto attempt %d/2 failed: %s", attempt + 1, exc)
            if attempt == 0:
                time.sleep(2)

    assert last_exc is not None
    raise last_exc
