"""Print the chat id(s) that have messaged your bot.

Use this to find the chat id for the DM demo:
  1. In Telegram, open your bot and tap Start (or send it any message).
  2. Run:  python tools/get_chat_id.py
  3. Copy the printed id into TELEGRAM_CHAT_ID (in .env or your GitHub secret).

Reads TELEGRAM_BOT_TOKEN from the environment / .env.
"""

from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set (put it in .env or export it).", file=sys.stderr)
        return 1

    resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
    body = resp.json()
    if not body.get("ok"):
        print(f"Telegram API error: {body}", file=sys.stderr)
        return 1

    seen: dict[str, str] = {}
    for update in body.get("result", []):
        chat = (update.get("message") or update.get("channel_post") or {}).get("chat")
        if chat:
            label = chat.get("title") or " ".join(
                filter(None, [chat.get("first_name"), chat.get("last_name"), chat.get("username")])
            )
            seen[str(chat["id"])] = f"{chat.get('type')}: {label}".strip()

    if not seen:
        print("No chats found. Send your bot a message first (tap Start), then re-run.")
        return 0

    print("Found these chats — use the id of the one you want as TELEGRAM_CHAT_ID:\n")
    for chat_id, desc in seen.items():
        print(f"  {chat_id}\t{desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
