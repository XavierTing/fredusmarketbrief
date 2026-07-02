# Self-Serve Telegram Subscription + Daily Broadcast — Design

**Date:** 2026-07-02
**Status:** Approved (design), pending implementation plan

## Context

The Fred US Market Brief pipeline currently renders a daily infographic and sends it to a **single** hardcoded Telegram `chat_id` (`TELEGRAM_CHAT_ID`), plus WhatsApp. The owner (a financial advisor) wants to deliver the brief to **many customers** and let each customer **self-subscribe**.

The blocker is a Telegram platform rule: a **bot cannot message anyone who hasn't messaged it first** — usernames and phone numbers are not valid send targets. Bulk-messaging from a personal account (MTProto) was rejected because daily-identical broadcast is the highest-risk spam pattern and would endanger the owner's personal account.

The chosen path is the compliant one: customers **opt in** by tapping a deep link / scanning a QR (one tap → bot `/start`), the bot registers them, and the daily job broadcasts to the whole subscriber list.

**Deployment reality:** the project runs only as a **GitHub Actions daily cron** — nothing is ever "listening." Capturing `/start` therefore requires a separate always-available listener. The repo is **public**, so subscriber data (chat_ids, names) must live in **private** external storage, never committed.

## Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Listener runtime | **Vercel serverless function (Python)** — instant `/start` handling, scales to zero |
| Storage | **Supabase** — Postgres `subscribers` table + private Storage bucket for `latest.png` |
| Subscribe UX | **Welcome message + instant sample (latest infographic) + `/stop` unsubscribe**; auto-prune on block |
| Onboarding assets | Deep link with attribution payload + QR code + invite message (QR generator already added: `segno`) |

## Architecture

```
Customer taps deep link ──▶ Telegram ──▶ [Vercel webhook (Python)]
                                              │  upsert subscriber, welcome + sample
                                              ▼
                                       [Supabase]  ← Postgres `subscribers` + Storage `latest.png`
                                              ▲
   GitHub Actions daily cron ───────────────┘
   fetch → narrate → render → upload latest.png → read active subscribers → send to each (prune on block)
```

Three cooperating pieces around one Supabase project:

1. **Vercel webhook** — receives Telegram updates, handles `/start` and `/stop`, writes to Supabase, sends welcome + latest infographic.
2. **Supabase** — `subscribers` table + private Storage bucket holding `latest.png`.
3. **Daily broadcast** — the existing GitHub Actions job, extended to upload the rendered PNG and fan out to all active subscribers.

## Data flow

- **Onboard:** deep link → Telegram POSTs update to webhook → verify secret header → upsert `{chat_id, first_name, last_name, username, start_payload, active=true}` → send welcome text → fetch `latest.png` from Storage → `sendPhoto`. If `latest.png` doesn't exist yet, send welcome only.
- **Daily:** cron renders PNG → uploads it as `latest.png` → queries active subscribers → `sendPhoto` to each; a `403` (user blocked bot) flips `active=false`. WhatsApp path unchanged.
- **Unsubscribe:** `/stop` → `active=false`, set `unsubscribed_at` → confirmation text.

## Components

### New files
- `api/telegram_webhook.py` — Vercel serverless function. Parses the Telegram update; routes `/start` (register + welcome + sample) and `/stop` (deactivate + confirm); ignores everything else. Verifies the secret token. Always returns HTTP 200 quickly.
- `src/subscribers.py` — Supabase wrapper using `requests` (no heavy SDK): `upsert_subscriber(...)`, `deactivate(chat_id)`, `list_active() -> list[dict]`. Hits the Supabase REST endpoint with the service key.
- `src/storage.py` — `upload_latest(png_path)` and `fetch_latest() -> bytes | None` against the private Supabase Storage bucket.
- `scripts/set_webhook.py` — one-time helper calling Telegram `setWebhook` with the Vercel URL + `secret_token`.
- `scripts/make_qr.py` — regenerate the subscribe QR for a given `start` payload (generalizes the one-off already produced at `out/subscribe-qr.png`).
- `vercel.json` — routes `/api/telegram_webhook` and pins the Python runtime.
- `db/subscribers.sql` — the table migration (run once in the Supabase SQL editor).

### Modified files
- `src/telegram_sender.py` — add an optional `chat_id` argument to `send_photo(image_path, caption, chat_id=None)`; default to `get_telegram_chat_id()` for backward compatibility. Keep the one-retry-then-raise behavior.
- `src/main.py` — replace the single Telegram send with a broadcast step: after render, `storage.upload_latest(out_path)`, then `subscribers.list_active()` and `sendPhoto` per subscriber, pruning on block. **Fallback:** if Supabase is not configured, keep sending to the legacy single `TELEGRAM_CHAT_ID` so `--mock`/`--dry-run` and un-provisioned runs still work. WhatsApp unchanged. `--dry-run` still skips all sending.
- `src/config.py` — lazy getters `get_supabase_url()`, `get_supabase_service_key()`, `get_telegram_webhook_secret()` (raise only when called, matching the existing lazy-secrets pattern).
- `.github/workflows/daily.yml` — add `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` to the job env from repo secrets.
- `.env.example` — document the new vars.
- `requirements.txt` — no new runtime dep for the pipeline (reuse `requests`); `segno` (already installed) added for the QR script. Vercel function may declare its own minimal `requirements.txt` under `api/`.

## Data model — Supabase `subscribers`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | pk, default `gen_random_uuid()` |
| `chat_id` | bigint | unique, not null |
| `first_name` | text | nullable |
| `last_name` | text | nullable |
| `username` | text | nullable |
| `start_payload` | text | nullable — lead attribution from the deep link (`?start=...`) |
| `subscribed_at` | timestamptz | default `now()` |
| `unsubscribed_at` | timestamptz | nullable |
| `active` | boolean | default `true` |

`/start` upserts on `chat_id` and re-activates (`active=true`, clear `unsubscribed_at`) if returning.

## Security

- **Telegram webhook secret token:** set via `setWebhook`'s `secret_token`; the webhook rejects any request whose `X-Telegram-Bot-Api-Secret-Token` header doesn't match.
- **Supabase service_role key:** only in Vercel env vars + a GitHub Actions secret. Never client-side, never committed. Table has RLS on; the service key is used server-side.
- **Storage bucket private:** daily job uploads with the service key; webhook downloads with the service key (or a short-lived signed URL).
- **Bot token:** remains a secret in both Vercel and GitHub.

## Error handling / graceful degradation

Preserves the pipeline's core principle — always produce and ship *something*.

- **Webhook:** always returns 200 fast to avoid Telegram retry storms; internal errors are logged, not surfaced. Missing `latest.png` → welcome only.
- **Broadcast:** each subscriber send wrapped in try/except; `403`/blocked → mark inactive and continue; other errors logged, loop continues. If Supabase is unreachable, fall back to the legacy single `TELEGRAM_CHAT_ID`.
- **Mock/dry-run:** no Supabase calls in mock; `--dry-run` skips all delivery.

## Testing

- **Offline unit tests** (mock `requests`, `tmp_path`, monkeypatched env — matching the existing suite):
  - `src/subscribers.py`: upsert / deactivate / list_active build correct requests and parse responses.
  - `src/telegram_sender.py`: `chat_id` arg overrides the env default; omitted → env default.
  - `src/main.py` broadcast: iterates subscribers, prunes on simulated `403`, and falls back to single-chat when Supabase is unset.
  - `api/telegram_webhook.py`: a sample `/start` update triggers upsert + welcome; `/stop` triggers deactivate; unknown text is ignored; bad secret is rejected.
- **Manual E2E:** deploy webhook to Vercel → `python scripts/set_webhook.py` → tap the deep link from the Xavier Spare test account → verify a row appears in Supabase + welcome + sample infographic arrive → run a broadcast (`python -m src.main`) and confirm delivery → send `/stop` → confirm the row goes `active=false` and the next broadcast skips it.

## Out of scope (YAGNI)

Paid/premium tiers, a custom admin dashboard (Supabase's own dashboard suffices), per-user scheduling, and analytics beyond the `start_payload` attribution column.

## Verification

End-to-end acceptance:
1. `pytest` passes (all new offline tests green).
2. `python -m src.main --mock --dry-run` still renders without touching Supabase (fallback path intact).
3. Deployed webhook: a fresh `/start` from a test account creates an active subscriber and delivers welcome + sample.
4. A live `python -m src.main` broadcasts the day's infographic to all active subscribers; a blocked user is auto-pruned.
5. `/stop` deactivates and is excluded from the next broadcast.
