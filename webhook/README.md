# Telegram subscription webhook (Vercel)

Standalone serverless function. **Deploy this folder as its own Vercel project**
(set the Vercel project's Root Directory to `webhook`).

- Endpoint: `POST /api/telegram_webhook`
- Env vars (Vercel → Settings → Environment Variables):
  `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`
- After deploy, register it with Telegram via `python scripts/set_webhook.py <vercel-url>`.

Shares the Supabase `subscribers` table + `briefs` bucket with the pipeline;
no shared Python code by design (keeps the serverless bundle to just `requests`).
