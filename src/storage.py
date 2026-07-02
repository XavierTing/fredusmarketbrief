"""Supabase Storage helper for the 'latest infographic' sample.

The daily pipeline uploads the freshly rendered PNG here; the Vercel webhook
downloads it to send a new subscriber an instant sample. Private bucket, so
every request is authenticated with the service key.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from .config import get_supabase_service_key, get_supabase_url

log = logging.getLogger(__name__)

_BUCKET = "briefs"
_OBJECT = "latest.png"
_TIMEOUT = 30


def _auth() -> dict:
    key = get_supabase_service_key()
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _object_url() -> str:
    return f"{get_supabase_url()}/storage/v1/object/{_BUCKET}/{_OBJECT}"


def upload_latest(png_path: str | Path) -> None:
    """Overwrite briefs/latest.png with the given PNG file."""
    data = Path(png_path).read_bytes()
    headers = {**_auth(), "Content-Type": "image/png", "x-upsert": "true"}
    resp = requests.post(_object_url(), data=data, headers=headers, timeout=_TIMEOUT)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase storage upload failed {resp.status_code}: {resp.text}")


def fetch_latest() -> bytes | None:
    """Return briefs/latest.png bytes, or None if it doesn't exist yet."""
    resp = requests.get(_object_url(), headers=_auth(), timeout=_TIMEOUT)
    if resp.status_code == 200:
        return resp.content
    if resp.status_code in (400, 404):
        return None
    raise RuntimeError(f"Supabase storage fetch failed {resp.status_code}: {resp.text}")
