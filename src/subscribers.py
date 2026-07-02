"""Supabase-backed subscriber registry (pipeline side).

Talks to the Supabase REST API (PostgREST) with the service key. The Vercel
webhook writes rows on /start and /stop; the daily broadcast reads active rows
and prunes anyone who blocks the bot. Only `requests` is needed so this module
stays importable without the heavy pipeline dependencies.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from .config import get_supabase_service_key, get_supabase_url

log = logging.getLogger(__name__)

_TIMEOUT = 20


def _headers(extra: dict | None = None) -> dict:
    key = get_supabase_service_key()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _table_url() -> str:
    return f"{get_supabase_url()}/rest/v1/subscribers"


def upsert_subscriber(
    chat_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    start_payload: str | None = None,
) -> None:
    """Insert a subscriber, or re-activate an existing one (idempotent on chat_id)."""
    payload = {
        "chat_id": chat_id,
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
        "start_payload": start_payload,
        "active": True,
        "unsubscribed_at": None,
    }
    resp = requests.post(
        _table_url(),
        params={"on_conflict": "chat_id"},
        json=payload,
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        timeout=_TIMEOUT,
    )
    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"Supabase upsert failed {resp.status_code}: {resp.text}")


def deactivate(chat_id: int) -> None:
    """Mark a subscriber inactive (on /stop or after a detected block)."""
    resp = requests.patch(
        _table_url(),
        params={"chat_id": f"eq.{chat_id}"},
        json={"active": False, "unsubscribed_at": datetime.now(timezone.utc).isoformat()},
        headers=_headers({"Prefer": "return=minimal"}),
        timeout=_TIMEOUT,
    )
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Supabase deactivate failed {resp.status_code}: {resp.text}")


def list_active() -> list[dict]:
    """Return active subscribers as dicts with chat_id, first_name, username."""
    resp = requests.get(
        _table_url(),
        params={"select": "chat_id,first_name,username", "active": "eq.true"},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Supabase list failed {resp.status_code}: {resp.text}")
    return resp.json()
