"""Static configuration: symbol maps, model names, and env loading."""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load .env if present (no-op in CI, where secrets come from the environment).
load_dotenv()

# Major US indices: display name -> Yahoo symbol.
INDICES: dict[str, str] = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow Jones": "^DJI",
}

# Cross-asset specs: (display name, Yahoo symbol, display format).
# fmt drives how the value/change are rendered — see infographic._fmt_value.
CRYPTO: list[tuple[str, str, str]] = [
    ("Bitcoin", "BTC-USD", "usd_large"),
    ("Ethereum", "ETH-USD", "usd_large"),
]

COMMODITIES_MACRO: list[tuple[str, str, str]] = [
    ("Gold", "GC=F", "usd"),
    ("Silver", "SI=F", "usd"),
    ("Crude Oil (WTI)", "CL=F", "usd"),
    ("US 10Y Yield", "^TNX", "yield"),
    ("US Dollar Index", "DX-Y.NYB", "level"),
    ("Volatility (VIX)", "^VIX", "level"),
]

# How many top gainers/losers to show.
TOP_MOVERS_COUNT = 5

# Claude model + web search tool version for the narrative stage.
CLAUDE_MODEL = "claude-opus-4-8"
WEB_SEARCH_TOOL_VERSION = "web_search_20260209"

# WhatsApp Cloud API (Meta Graph API) version — bump as Meta deprecates versions.
WHATSAPP_API_VERSION = "v22.0"

# Branding (placeholder; override AGENT_NAME via env).
AGENT_NAME = os.environ.get("AGENT_NAME", "Jane Doe, Financial Services")
BRAND_TAGLINE = "Fred US Market Brief"
DISCLAIMER = "For informational purposes only. Not financial advice. Demo."


# --- Secrets (read lazily so --mock/--dry-run work without them) -------------

def get_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return key


def get_telegram_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


def get_telegram_chat_id() -> str:
    # Works for a personal DM chat, a group, or a channel — all are "chat ids".
    # Falls back to the older TELEGRAM_CHANNEL_ID name for compatibility.
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHANNEL_ID")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set")
    return chat_id


def get_whatsapp_token() -> str:
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN is not set")
    return token


def get_whatsapp_phone_number_id() -> str:
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if not phone_number_id:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID is not set")
    return phone_number_id


def get_whatsapp_recipient() -> str:
    # The destination number in E.164 form, digits only (no '+'), e.g. 6591234567.
    recipient = os.environ.get("WHATSAPP_RECIPIENT")
    if not recipient:
        raise RuntimeError("WHATSAPP_RECIPIENT is not set")
    return recipient
