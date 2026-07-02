# Xavier US Market Brief → Telegram

A fully automated daily pipeline that fetches the day's US equity market data,
has Claude write a grounded narrative + headlines, renders a branded infographic,
and broadcasts it to a Telegram channel — on a schedule, with no manual work.

Built as a demo for an insurance agent who wants to send his customers a polished
daily market update.

## How it works

```
GitHub Actions cron (00:00 UTC ≈ 08:00 SGT) / manual trigger
        → src/main.py
   ┌────────────┬──────────────┬──────────────────┬─────────────────┐
   │ market_data│  narrative   │   infographic    │ telegram_sender │
   │ (yahooquery│ (Claude +    │ (Jinja2 HTML →   │ (Bot API        │
   │  no key)   │  web search) │  Playwright PNG) │  sendPhoto)     │
   └────────────┴──────────────┴──────────────────┴─────────────────┘
```

- **Data** — Yahoo Finance via `yahooquery` (no API key): S&P 500 / Nasdaq / Dow,
  the 11 SPDR sector ETFs, and top gainers/losers.
- **Narrative** — Claude (`claude-opus-4-8`) writes a 60–80 word recap using *only*
  the fetched numbers, and pulls 1–3 real headlines via the web search tool.
- **Infographic** — a branded HTML/CSS template rendered to a tall PNG with
  headless Chromium.
- **Delivery** — broadcast to **both** Telegram (Bot API `sendPhoto`) and WhatsApp
  (Meta Cloud API) on every run. The channels are independent: if one fails, the other
  still sends. Telegram goes to any chat (your own DM, a group, or a channel); WhatsApp
  goes to your own number.

Each stage degrades gracefully: if a section fails to fetch, it's omitted rather
than aborting the whole run.

## Local development

```bash
pip install -r requirements.txt
python -m playwright install chromium       # one-time: the headless browser

# Render from bundled sample data — no keys, no network, no send:
python -m src.main --mock --dry-run --out out/demo.png
open out/demo.png

# Live data + Claude narrative, but don't send:
cp .env.example .env   # fill in ANTHROPIC_API_KEY
python -m src.main --dry-run

# Full run (also needs Telegram creds in .env):
python -m src.main
```

Run the tests:

```bash
pytest
```

## Deploying the daily schedule (GitHub Actions)

1. **Create the bot** — message [@BotFather](https://t.me/BotFather), `/newbot`,
   copy the `TELEGRAM_BOT_TOKEN`.
2. **Pick a destination** (`TELEGRAM_CHAT_ID`):
   - **Your own account (simplest for a demo):** open your new bot in Telegram and tap
     **Start** (a bot can't message you until you message it first), then run
     `python tools/get_chat_id.py` to print your numeric chat id.
   - **A channel:** create one, add the bot as an **admin**, and use `@yourchannel`
     (public) or the numeric `-100…` id (private).
3. **Get an `ANTHROPIC_API_KEY`** from the Claude console.
4. **Set up WhatsApp** (Meta Cloud API): create an app at
   [developers.facebook.com](https://developers.facebook.com), add the **WhatsApp**
   product, and copy the **phone number id** and an **access token**. Add your own number
   as a verified **test recipient**, then message the WhatsApp number once to open the
   24-hour window (freeform image sends only deliver inside it — see the note below).
5. **Add repo secrets** (Settings → Secrets and variables → Actions → *Secrets*):
   `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
   `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_RECIPIENT`
   (your number in E.164 digits, no `+`). Optionally add a repo *Variable* `AGENT_NAME`.
6. **Run it** — the workflow runs daily at 00:00 UTC, or trigger it on demand from
   the **Actions** tab (Run workflow) — ideal for a live demo. The rendered PNG is
   also uploaded as a build artifact each run.

> **WhatsApp 24h window:** non-template image messages only deliver if the recipient
> messaged the WhatsApp number within the last 24 hours, so a scheduled daily send may be
> rejected until you reply in the thread. Reliable automation would use an approved
> image-header template (a larger, separate setup).

### Quickest DM demo (local)

```bash
# 1. In Telegram, open your bot and tap Start.
# 2. Put TELEGRAM_BOT_TOKEN in .env, then find your chat id:
python tools/get_chat_id.py
# 3. Put that id in .env as TELEGRAM_CHAT_ID, then send the sample image to yourself:
python -m src.main --mock        # uses sample data, real send to your DM
```

## Customizing the branding

The infographic is a single self-contained template at
[templates/infographic.html.j2](templates/infographic.html.j2) — edit the CSS
variables at the top (colors), the inline SVG logo, and set `AGENT_NAME` to swap
in the real agent name. Symbol lists and the disclaimer live in
[src/config.py](src/config.py).

## Project layout

```
src/
  config.py            symbol maps, model + branding, env loading
  models.py            typed pipeline data objects
  market_data.py       Yahoo Finance fetch + sample loader
  narrative.py         Claude narrative + web-search headlines
  infographic.py       Jinja2 + Playwright render
  telegram_sender.py   Bot API sendPhoto
  main.py              orchestrator (--mock / --dry-run / --out)
templates/infographic.html.j2
samples/sample_market_data.json
tests/
.github/workflows/daily.yml
```
