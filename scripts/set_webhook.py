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
