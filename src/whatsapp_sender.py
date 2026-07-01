"""Stage 4 (alt channel) — send the infographic to WhatsApp via the Meta Cloud API.

Two-step Graph API flow: upload the local PNG to /media to get a media id, then
send an image message referencing that id. Delivery of a freeform (non-template)
image only succeeds inside an open 24-hour customer-service window — i.e. the
recipient must have messaged the business number within the last 24h. One retry
on failure; raises if both attempts fail so a scheduled run surfaces as failed.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from .config import (
    WHATSAPP_API_VERSION,
    get_whatsapp_phone_number_id,
    get_whatsapp_recipient,
    get_whatsapp_token,
)

log = logging.getLogger(__name__)

_BASE = "https://graph.facebook.com/{version}/{phone_number_id}"
_CAPTION_LIMIT = 1024


def _upload_media(base: str, token: str, image_path: Path) -> str:
    """Upload the PNG and return the media id."""
    with open(image_path, "rb") as fh:
        resp = requests.post(
            f"{base}/media",
            headers={"Authorization": f"Bearer {token}"},
            data={"messaging_product": "whatsapp", "type": "image/png"},
            files={"file": (image_path.name, fh, "image/png")},
            timeout=60,
        )
    body = resp.json()
    media_id = body.get("id") if isinstance(body, dict) else None
    if resp.status_code == 200 and media_id:
        return media_id
    raise RuntimeError(f"WhatsApp media upload error {resp.status_code}: {resp.text}")


def _send_message(base: str, token: str, recipient: str, media_id: str, caption: str) -> dict:
    """Send an image message referencing an uploaded media id."""
    resp = requests.post(
        f"{base}/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "image",
            "image": {"id": media_id, "caption": caption},
        },
        timeout=60,
    )
    body = resp.json()
    if resp.status_code == 200 and isinstance(body, dict) and body.get("messages"):
        return body
    raise RuntimeError(f"WhatsApp send error {resp.status_code}: {resp.text}")


def send_photo(image_path: str | Path, caption: str = "") -> dict:
    """Send a photo to the configured WhatsApp recipient. Returns the API result."""
    token = get_whatsapp_token()
    phone_number_id = get_whatsapp_phone_number_id()
    recipient = get_whatsapp_recipient()
    base = _BASE.format(version=WHATSAPP_API_VERSION, phone_number_id=phone_number_id)
    image_path = Path(image_path)
    caption = caption[:_CAPTION_LIMIT]

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            media_id = _upload_media(base, token, image_path)
            body = _send_message(base, token, recipient, media_id, caption)
            log.info("Sent infographic to WhatsApp %s", recipient)
            return body
        except Exception as exc:  # noqa: BLE001 - retry once, then re-raise
            last_exc = exc
            log.warning("WhatsApp send attempt %d/2 failed: %s", attempt + 1, exc)
            if attempt == 0:
                time.sleep(2)

    assert last_exc is not None
    raise last_exc
