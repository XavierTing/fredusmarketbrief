# Telegram Subscription + Daily Broadcast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let customers self-subscribe to the daily US market brief by tapping a Telegram deep link (`/start`), and broadcast the daily infographic to every active subscriber.

**Architecture:** A standalone **Vercel Python webhook** receives Telegram `/start` and `/stop` updates and writes subscribers to **Supabase** (Postgres table + private Storage bucket for the "instant sample" image). The existing **GitHub Actions** pipeline is extended to upload the rendered PNG to Storage and fan the infographic out to all active subscribers, pruning anyone who blocked the bot. The webhook and the pipeline are separate deploy targets that share the Supabase data contract, not Python code.

**Tech Stack:** Python 3.12, `requests` (HTTP to Supabase REST/Storage + Telegram Bot API), Supabase (Postgres + Storage), Vercel (serverless Python), pytest (offline tests with monkeypatched `requests`).

**Spec:** `docs/superpowers/specs/2026-07-02-telegram-subscription-broadcast-design.md`

**Pre-done (already completed manually):**
- Supabase project created; `subscribers` table + private `briefs` bucket exist and are verified.
- `.env` has `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `TELEGRAM_WEBHOOK_SECRET`; `.env.example` documents them.
- QR onboarding asset generated at `out/subscribe-qr.png` via `segno`.
- Vercel account created and repo connected (deploy happens in Task 11).

---

## Supabase data contract (shared by both deploy targets)

`subscribers` table columns: `id` (uuid pk), `chat_id` (bigint unique), `first_name`, `last_name`, `username`, `start_payload`, `subscribed_at` (default now()), `unsubscribed_at`, `active` (default true).

REST base: `{SUPABASE_URL}/rest/v1/subscribers`. Storage object: `{SUPABASE_URL}/storage/v1/object/briefs/latest.png`. Auth headers on every call: `apikey: <service_key>` and `Authorization: Bearer <service_key>`.

---

### Task 1: Config getters for Supabase + webhook secret

**Files:**
- Modify: `src/config.py` (append after `get_whatsapp_recipient`)
- Test: `tests/test_config.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from src import config


def test_supabase_getters_raise_when_unset(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.get_supabase_url()
    with pytest.raises(RuntimeError):
        config.get_supabase_service_key()


def test_supabase_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co/")
    assert config.get_supabase_url() == "https://x.supabase.co"


def test_supabase_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert config.supabase_configured() is False
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    assert config.supabase_configured() is True


def test_webhook_secret_getter(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    assert config.get_telegram_webhook_secret() == "s3cret"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: module 'src.config' has no attribute 'get_supabase_url'`

- [ ] **Step 3: Add the getters**

Append to `src/config.py`:

```python
def get_supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    return url.rstrip("/")


def get_supabase_service_key() -> str:
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_KEY is not set")
    return key


def get_telegram_webhook_secret() -> str:
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is not set")
    return secret


def supabase_configured() -> bool:
    """True when both Supabase env vars are present (enables the broadcast path)."""
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add Supabase + webhook-secret config getters"
```

---

### Task 2: Supabase subscribers module (pipeline side)

**Files:**
- Create: `src/subscribers.py`
- Test: `tests/test_subscribers.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_subscribers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.subscribers'`

- [ ] **Step 3: Create `src/subscribers.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_subscribers.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/subscribers.py tests/test_subscribers.py
git commit -m "feat: add Supabase subscriber registry module"
```

---

### Task 3: Supabase Storage module (latest infographic)

**Files:**
- Create: `src/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.storage'`

- [ ] **Step 3: Create `src/storage.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/storage.py tests/test_storage.py
git commit -m "feat: add Supabase Storage helper for latest infographic"
```

---

### Task 4: Telegram sender — per-recipient chat_id + block detection

**Files:**
- Modify: `src/telegram_sender.py`
- Test: `tests/test_telegram_sender.py` (append; file exists)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_telegram_sender.py`:

```python
from pathlib import Path

import pytest

from src import telegram_sender


class _R:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def _img(tmp_path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"PNG")
    return p


def test_send_photo_uses_explicit_chat_id(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    seen = {}

    def fake_post(url, **kw):
        seen["chat_id"] = kw["data"]["chat_id"]
        return _R(200, {"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)
    telegram_sender.send_photo(_img(tmp_path), caption="hi", chat_id=999)
    assert seen["chat_id"] == 999


def test_send_photo_raises_blocked_on_403(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(
        telegram_sender.requests, "post",
        lambda *a, **k: _R(403, {"ok": False, "description": "Forbidden: bot was blocked by the user"}),
    )
    with pytest.raises(telegram_sender.TelegramBlockedError):
        telegram_sender.send_photo(_img(tmp_path), chat_id=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_telegram_sender.py -v -k "explicit_chat_id or blocked"`
Expected: FAIL with `AttributeError: module 'src.telegram_sender' has no attribute 'TelegramBlockedError'`

- [ ] **Step 3: Modify `src/telegram_sender.py`**

Add the exception class after `_CAPTION_LIMIT`:

```python
_CAPTION_LIMIT = 1024

# 400 (chat not found) and 403 (blocked / deactivated) mean the recipient is
# permanently unreachable — the broadcast prunes them instead of retrying.
_PERMANENT_STATUS = {400, 403}


class TelegramBlockedError(RuntimeError):
    """Recipient can no longer be reached (blocked the bot, deactivated, or gone)."""
```

Replace the `send_photo` signature and body with:

```python
def send_photo(image_path: str | Path, caption: str = "", chat_id: str | int | None = None) -> dict:
    """Send a photo to a chat. Defaults to the configured chat_id when none is given.

    Raises TelegramBlockedError (no retry) when the recipient is unreachable, so
    the broadcast can prune them. Retries once on transient errors, then re-raises.
    """
    token = get_telegram_token()
    chat_id = chat_id if chat_id is not None else get_telegram_chat_id()
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
            if resp.status_code in _PERMANENT_STATUS:
                raise TelegramBlockedError(f"{resp.status_code}: {body.get('description')}")
            raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")
        except TelegramBlockedError:
            raise  # permanent — do not retry
        except Exception as exc:  # noqa: BLE001 - retry once, then re-raise
            last_exc = exc
            log.warning("sendPhoto attempt %d/2 failed: %s", attempt + 1, exc)
            if attempt == 0:
                time.sleep(2)

    assert last_exc is not None
    raise last_exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram_sender.py -v`
Expected: PASS (existing tests + 2 new)

- [ ] **Step 5: Commit**

```bash
git add src/telegram_sender.py tests/test_telegram_sender.py
git commit -m "feat: support per-recipient chat_id and block detection in sender"
```

---

### Task 5: Broadcast in main.py (fan out to subscribers, prune blocked, fallback)

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main.py` (append; file exists)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v -k broadcast`
Expected: FAIL with `AttributeError: module 'src.main' has no attribute '_broadcast_telegram'`

- [ ] **Step 3: Modify `src/main.py`**

Update imports near the top (replace the telegram import line and add the new modules):

```python
from .config import AGENT_NAME, supabase_configured
from .infographic import _date_display, render_png
from .market_data import fetch_market_data, load_mock
from .models import MarketSummary
from .narrative import generate_narrative
from . import storage, subscribers
from .telegram_sender import TelegramBlockedError, send_photo as telegram_send_photo
from .whatsapp_sender import send_photo as whatsapp_send_photo
```

Replace the `_CHANNELS` definition with:

```python
def _broadcast_telegram(out_path: Path, caption: str = "") -> None:
    """Broadcast to every active subscriber; fall back to the single configured chat.

    Best-effort uploads the PNG so the webhook can send new subscribers an instant
    sample. Blocked recipients are pruned; other per-recipient errors are logged
    and skipped. If Supabase is unconfigured or unreachable, sends to the legacy
    single TELEGRAM_CHAT_ID so the brief still ships (graceful degradation).
    """
    try:
        storage.upload_latest(out_path)
    except Exception:  # noqa: BLE001 - sample upload is best-effort
        log.exception("Failed to upload latest infographic to storage")

    if supabase_configured():
        try:
            recipients = subscribers.list_active()
        except Exception:  # noqa: BLE001 - degrade to single chat
            log.exception("Failed to list subscribers; falling back to single chat")
        else:
            if not recipients:
                log.info("No active subscribers; nothing to broadcast on Telegram")
                return
            sent = 0
            for row in recipients:
                chat_id = row["chat_id"]
                try:
                    telegram_send_photo(out_path, caption=caption, chat_id=chat_id)
                    sent += 1
                except TelegramBlockedError:
                    log.info("Pruning unreachable subscriber %s", chat_id)
                    try:
                        subscribers.deactivate(chat_id)
                    except Exception:  # noqa: BLE001
                        log.exception("Failed to deactivate %s", chat_id)
                except Exception:  # noqa: BLE001 - one recipient must not block others
                    log.exception("Failed to send to subscriber %s", chat_id)
            log.info("Broadcast to %d/%d subscribers", sent, len(recipients))
            return

    # Fallback: legacy single-chat send.
    telegram_send_photo(out_path, caption=caption)


# Delivery channels, each broadcast every run. Independent by design: a failure
# in one (e.g. a closed WhatsApp 24h window) must not block the others.
_CHANNELS = [
    ("Telegram", _broadcast_telegram),
    ("WhatsApp", whatsapp_send_photo),
]
```

Note: `_deliver` is unchanged — it already calls `send(out_path, caption=caption)` for each channel, which matches `_broadcast_telegram(out_path, caption=caption)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS (existing + 2 new). Then run full suite: `pytest -v` → all green.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: broadcast infographic to all active subscribers"
```

---

### Task 6: Update requirements + daily workflow secrets

**Files:**
- Modify: `requirements.txt`
- Modify: `.github/workflows/daily.yml`

- [ ] **Step 1: Add `segno` to `requirements.txt`**

Under the `# dev / test` section, add:

```
segno>=1.6.0  # QR generation for scripts/make_qr.py
```

- [ ] **Step 2: Add Supabase env to the workflow**

In `.github/workflows/daily.yml`, inside the `env:` block of the "Generate and broadcast the infographic" step (after the `TELEGRAM_CHAT_ID` line), add:

```yaml
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
```

- [ ] **Step 3: Verify the workflow file still parses**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .github/workflows/daily.yml
git commit -m "chore: add segno dep and Supabase secrets to daily workflow"
```

---

### Task 7: Standalone Vercel webhook

**Files:**
- Create: `webhook/api/telegram_webhook.py`
- Create: `webhook/requirements.txt`
- Create: `webhook/README.md`
- Test: `tests/test_webhook.py`

The webhook is self-contained (only `requests`) and imports nothing from `src`. Core logic lives in a pure `handle_update(update)` function so it is testable without an HTTP server.

- [ ] **Step 1: Write the failing test**

```python
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
    upsert_kw = dict(a for a in actions if a[0] == "upsert")["upsert"] if False else actions[0][1]
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_webhook.py -v`
Expected: FAIL with `FileNotFoundError` / spec load error (webhook file doesn't exist yet)

- [ ] **Step 3: Create `webhook/api/telegram_webhook.py`**

```python
"""Vercel serverless webhook for Telegram /start and /stop.

Standalone (only `requests`): registers subscribers in Supabase and sends a
welcome + an instant sample of the latest infographic. Shares the Supabase data
contract with the pipeline, not Python code. Always returns HTTP 200 quickly so
Telegram does not retry.
"""

from __future__ import annotations

import json
import os
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
            _send_photo_bytes(chat_id, sample, caption="Here's the latest brief \U0001F447")
    elif text.startswith("/stop"):
        _deactivate(chat_id)
        _send_message(chat_id, GOODBYE)
    # anything else: ignore


class handler(BaseHTTPRequestHandler):  # Vercel entrypoint
    def do_POST(self):  # noqa: N802
        if self.headers.get("X-Telegram-Bot-Api-Secret-Token") != os.environ.get("TELEGRAM_WEBHOOK_SECRET"):
            self.send_response(403)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            handle_update(json.loads(raw))
        except Exception:  # noqa: BLE001 - never 500 back to Telegram (avoids retry storms)
            pass
        self.send_response(200)
        self.end_headers()

    def do_GET(self):  # noqa: N802 - health check
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
```

- [ ] **Step 4: Create `webhook/requirements.txt`**

```
requests>=2.31.0
```

- [ ] **Step 5: Create `webhook/README.md`**

```markdown
# Telegram subscription webhook (Vercel)

Standalone serverless function. **Deploy this folder as its own Vercel project**
(set the Vercel project's Root Directory to `webhook`).

- Endpoint: `POST /api/telegram_webhook`
- Env vars (Vercel → Settings → Environment Variables):
  `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`
- After deploy, register it with Telegram via `python scripts/set_webhook.py <vercel-url>`.

Shares the Supabase `subscribers` table + `briefs` bucket with the pipeline;
no shared Python code by design (keeps the serverless bundle to just `requests`).
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_webhook.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add webhook/ tests/test_webhook.py
git commit -m "feat: standalone Vercel webhook for /start and /stop"
```

---

### Task 8: set_webhook helper script

**Files:**
- Create: `scripts/set_webhook.py`

- [ ] **Step 1: Create the script**

```python
"""Register the Vercel webhook URL with Telegram (one-time, re-run on URL change).

Usage:
  python scripts/set_webhook.py https://your-project.vercel.app

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET from the environment / .env.
The secret is sent as `secret_token`; Telegram then includes it as the
X-Telegram-Bot-Api-Secret-Token header on every delivery, which the webhook verifies.
"""

from __future__ import annotations

import sys

import requests
from dotenv import load_dotenv

load_dotenv()

import os  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/set_webhook.py <vercel-base-url>", file=sys.stderr)
        return 1
    base = sys.argv[1].rstrip("/")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not token or not secret:
        print("TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET must be set.", file=sys.stderr)
        return 1

    webhook_url = f"{base}/api/telegram_webhook"
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": webhook_url, "secret_token": secret, "allowed_updates": ["message"]},
        timeout=30,
    )
    body = resp.json()
    if body.get("ok"):
        print(f"Webhook set to {webhook_url}")
        return 0
    print(f"Failed: {body}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the usage guard (no network)**

Run: `python scripts/set_webhook.py`
Expected: prints the usage line and exits non-zero.

- [ ] **Step 3: Commit**

```bash
git add scripts/set_webhook.py
git commit -m "feat: add set_webhook helper script"
```

---

### Task 9: make_qr helper script (per-campaign QR)

**Files:**
- Create: `scripts/make_qr.py`

- [ ] **Step 1: Create the script**

```python
"""Generate a subscribe QR code for the bot deep link.

Usage:
  python scripts/make_qr.py                 # generic subscribe link
  python scripts/make_qr.py xavierspare     # with a ?start= attribution payload

Writes out/subscribe-qr[-<payload>].png. Requires the bot username; set
BOT_USERNAME in the environment or edit the default below.
"""

from __future__ import annotations

import os
import sys

import segno
from dotenv import load_dotenv

load_dotenv()

BOT_USERNAME = os.environ.get("BOT_USERNAME", "xavier_market_demo_bot")


def main() -> int:
    payload = sys.argv[1] if len(sys.argv) > 1 else ""
    link = f"https://t.me/{BOT_USERNAME}"
    if payload:
        link += f"?start={payload}"
    out = f"out/subscribe-qr{'-' + payload if payload else ''}.png"
    os.makedirs("out", exist_ok=True)
    segno.make(link, error="h").save(out, scale=8, border=3)
    print(f"QR for {link}\nwritten to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it**

Run: `python scripts/make_qr.py demo`
Expected: prints the link + `written to out/subscribe-qr-demo.png`; file exists.

- [ ] **Step 3: Commit**

```bash
git add scripts/make_qr.py
git commit -m "feat: add make_qr helper for campaign deep links"
```

---

### Task 10: Record the DB schema in-repo

**Files:**
- Create: `db/subscribers.sql`

- [ ] **Step 1: Create `db/subscribers.sql`** (documents what was already applied in Supabase)

```sql
-- Applied once in the Supabase SQL editor. Kept here for repo record / re-provisioning.
create table if not exists subscribers (
  id uuid primary key default gen_random_uuid(),
  chat_id bigint unique not null,
  first_name text,
  last_name text,
  username text,
  start_payload text,
  subscribed_at timestamptz not null default now(),
  unsubscribed_at timestamptz,
  active boolean not null default true
);

alter table subscribers enable row level security;
-- No policies: only the server-side service key (which bypasses RLS) may access.
```

- [ ] **Step 2: Commit**

```bash
git add db/subscribers.sql
git commit -m "docs: record subscribers table schema in-repo"
```

---

### Task 11: Deploy + manual end-to-end verification

This task is operational (no unit tests) — a checklist to run once the code is merged.

- [ ] **Step 1: Full test suite green**

Run: `pytest -v`
Expected: all tests pass, including the new `test_config`, `test_subscribers`, `test_storage`, `test_webhook`, and the broadcast tests.

- [ ] **Step 2: Fallback still works offline**

Run: `python -m src.main --mock --dry-run --out out/demo.png`
Expected: renders without touching Supabase (mock path), exits 0.

- [ ] **Step 3: Deploy the webhook to Vercel**
  - Vercel → your project → **Settings → General → Root Directory** = `webhook`.
  - **Settings → Environment Variables:** add `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (copy values from `.env`).
  - Trigger a deploy (push the branch or click Redeploy). Confirm `GET https://<project>.vercel.app/api/telegram_webhook` returns `ok`.

- [ ] **Step 4: Register the webhook with Telegram**

Run: `python scripts/set_webhook.py https://<project>.vercel.app`
Expected: `Webhook set to https://<project>.vercel.app/api/telegram_webhook`

- [ ] **Step 5: Add GitHub Actions secrets**
  - Repo → Settings → Secrets and variables → Actions → New repository secret:
    `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (values from `.env`).

- [ ] **Step 6: Onboard the test customer (Xavier Spare)**
  - From the Xavier Spare account, open `https://t.me/xavier_market_demo_bot?start=xavierspare` and tap **Start**.
  - Verify in Supabase → Table editor → `subscribers`: a row with `chat_id`, `username`, `start_payload="xavierspare"`, `active=true`.
  - Verify the account received the welcome message (and, if a `latest.png` already exists in the bucket, the sample image).

- [ ] **Step 7: Broadcast a live run**

Run: `python -m src.main`
Expected: logs "Broadcast to N/N subscribers"; every active subscriber (incl. Xavier Spare) receives the infographic; `briefs/latest.png` is updated.

- [ ] **Step 8: Unsubscribe + prune**
  - From Xavier Spare, send `/stop`. Verify the row flips to `active=false` and a goodbye message arrives.
  - Run `python -m src.main` again; confirm the log shows the reduced count and the unsubscribed account is skipped.

- [ ] **Step 9: Final commit / open PR**

```bash
git add -A
git commit -m "chore: complete subscription + broadcast feature" --allow-empty
git push -u origin feat/telegram-subscriptions
```

Then open a PR from `feat/telegram-subscriptions` to `main`.

---

## Self-review notes

- **Spec coverage:** onboarding webhook (Task 7), subscriber registry (Task 2), Storage sample (Task 3), broadcast + prune + fallback (Task 5), chat_id sender (Task 4), config (Task 1), schema (Task 10), deploy/E2E (Task 11), workflow secrets (Task 6), onboarding assets/QR (Task 9). All spec sections map to a task.
- **Deviation from spec:** the webhook is a *standalone* Vercel project (`webhook/`) instead of importing `src/subscribers.py`, because `src` pulls heavy deps (`pandas` via `yahooquery`, `playwright`, `anthropic`) that would bloat/break the serverless bundle. The two targets share the Supabase contract; the small HTTP-call duplication is the intended isolation cost.
- **Type consistency:** `upsert_subscriber(chat_id, first_name, last_name, username, start_payload)`, `deactivate(chat_id)`, `list_active() -> list[dict]`, `send_photo(image_path, caption="", chat_id=None)`, `TelegramBlockedError`, `_broadcast_telegram(out_path, caption="")`, `handle_update(update)` — names used consistently across tasks.
