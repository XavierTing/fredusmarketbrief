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
