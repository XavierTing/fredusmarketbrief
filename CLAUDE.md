# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A companion `AGENTS.md` covers project structure, coding style, and commit conventions — read it too. This file focuses on the runtime architecture and the non-obvious details that span multiple files.

## Commands

```bash
pip install -r requirements.txt
python -m playwright install chromium              # one-time: headless browser for PNG rendering

python -m src.main --mock --dry-run --out out/demo.png   # sample data, render only — no keys/network/send
python -m src.main --dry-run                             # live data + Claude narrative, no Telegram send
python -m src.main                                       # full run: fetch → narrate → render → SEND
python -m src.main --style report                        # switch template (default is "compass")

pytest                                             # full suite
pytest tests/test_infographic.py::test_fmt_change_yield_in_bps   # single test
```

## Pipeline architecture

A four-stage linear pipeline orchestrated by [src/main.py](src/main.py), all state carried in a single `MarketSummary` dataclass ([src/models.py](src/models.py)) that each stage reads and augments:

1. **fetch** ([src/market_data.py](src/market_data.py)) → populates indices, crypto, commodities/macro, gainers/losers via Yahoo Finance (`yahooquery`, no API key). Leaves `narrative` empty.
2. **narrate** ([src/narrative.py](src/narrative.py)) → fills `narrative` using Claude + the server-side web search tool. **Live runs only** — `--mock` data ships with its own narrative in the sample JSON.
3. **render** ([src/infographic.py](src/infographic.py)) → Jinja2 HTML template → PNG via headless Chromium (Playwright).
4. **send** — `main._deliver` fans the rendered PNG out to **every channel in `_CHANNELS`**, currently Telegram ([src/telegram_sender.py](src/telegram_sender.py), Bot API `sendPhoto`) and WhatsApp ([src/whatsapp_sender.py](src/whatsapp_sender.py), Meta Cloud API). Channels are independent — each is called in its own `try/except`, and `_deliver` raises only if *all* channels fail. Skipped entirely when `--dry-run`.

**Graceful degradation is the core design principle.** Every fetch section is wrapped so a failure leaves that section empty rather than aborting; narrative failure is caught in `main.run` and rendering proceeds without it. The pipeline is built to always produce *something* to send. Preserve this when editing — don't let one failing section break the whole run.

`MarketSummary` supports JSON round-tripping (`to_dict`/`from_dict`), which is what makes `--mock` and offline tests possible via `load_mock()` reading `samples/sample_market_data.json`.

## Run modes

`--mock` and `--dry-run` are independent flags. Secrets are read **lazily** (the `get_*` functions in [src/config.py](src/config.py) only raise when actually called), so mock/dry-run paths run with no `.env`:

| Command | Data | Narrative | Send | Needs keys |
|---|---|---|---|---|
| `--mock --dry-run` | sample | from sample | no | none |
| `--dry-run` | live | Claude | no | `ANTHROPIC_API_KEY` |
| `--mock` | sample | from sample | **yes** | Telegram only |
| (none) | live | Claude | **yes** | all |

## Non-obvious details

- **Narrative deliberately avoids structured outputs.** `output_config.format` is incompatible with citations, and the web search tool returns citations — so the code instructs Claude to emit a bare JSON object and parses it defensively with a regex fallback (`_parse`). Don't "improve" this by switching to structured outputs. The call also handles the server-tool `pause_turn` loop (re-sending to resume, up to `_MAX_SERVER_TOOL_TURNS`).
- **Model + tool versions live in [src/config.py](src/config.py):** `CLAUDE_MODEL = "claude-opus-4-8"`, `WEB_SEARCH_TOOL_VERSION = "web_search_20260209"`.
- **Yahoo data quirks** (in `market_data.py`): `^TNX` is sometimes quoted at 10× the yield (43.0 → 4.30%) and is divided down; `DX-Y.NYB` (dollar index) falls back to `DX=F` when empty; `change_pct` is computed from price/prev-close because Yahoo's own field uses fractions on the price endpoint but percents on the screener endpoint.
- **Two templates**, selected by `--style`: `compass.html.j2` (default) and `infographic.html.j2` (`report`), mapped in `_TEMPLATE_BY_STYLE`. Both are self-contained (inline CSS + SVG logo). Asset cards use per-format value rendering (`_fmt_value`) and yield moves shown in bps (`_fmt_change`).
- **Telegram target** is any `chat_id` — DM, group, or channel; `get_telegram_chat_id` also accepts the legacy `TELEGRAM_CHANNEL_ID` env name. `sendPhoto` retries once before raising.
- **WhatsApp** uses the Meta Cloud API in **two steps**: upload the local PNG to `/media` → get a media id → send an image message referencing that id (`get_whatsapp_*` in config, `WHATSAPP_API_VERSION` bumpable). Freeform image sends only deliver inside an open **24h customer-service window** (recipient must have messaged the number in the last 24h); outside it you'd need an approved image-header template. Both sender modules share the same `send_photo(image_path, caption) -> dict` interface and one-retry-then-raise pattern, so adding a third channel is just appending to `_CHANNELS`.

## Testing

Tests mirror source modules and are offline-first: use `load_mock()`, `monkeypatch` for env vars and `requests.post`, and `tmp_path`. Playwright/rendering tests call `pytest.importorskip("playwright")` and skip cleanly when Chromium is unavailable — never require network or real credentials for a normal `pytest` run. `conftest.py` makes the repo root importable as `src`.

## Deployment

`.github/workflows/daily.yml` runs the full pipeline on a daily cron (00:00 UTC ≈ 08:00 SGT) and on manual `workflow_dispatch`. Secrets come from repo Actions secrets (`ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`); `AGENT_NAME` is an optional repo *variable* for branding. The rendered PNG is uploaded as a build artifact every run.
