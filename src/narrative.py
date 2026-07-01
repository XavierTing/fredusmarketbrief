"""Stage 2 — write the daily narrative + headlines with Claude.

Claude reads the fetched numbers (it does not invent figures) and uses the
server-side web search tool to pull 1-3 current, real headlines. Output is a
small JSON object that we parse into a ``Narrative``.

Structured outputs (output_config.format) are intentionally NOT used here:
they are incompatible with citations, and the web search tool returns
citations. Instead we instruct Claude to emit a bare JSON object and parse it.
"""

from __future__ import annotations

import json
import logging
import re

from anthropic import Anthropic

from .config import CLAUDE_MODEL, WEB_SEARCH_TOOL_VERSION, get_anthropic_key
from .models import Headline, MarketSummary, Narrative

log = logging.getLogger(__name__)

# Stable across every run → cache it (prefix-matched prompt caching).
SYSTEM_PROMPT = (
    "You are a financial writer producing a concise daily US market brief for a "
    "retail audience. You will be given the day's stock indices, crypto, "
    "commodities & macro indicators (gold, silver, oil, the 10-year Treasury "
    "yield, the US dollar, and volatility), and top stock movers. Write a tight, "
    "plain-English summary of what happened and why across these assets.\n\n"
    "Rules:\n"
    "- Use ONLY the numbers provided. Never invent or alter a figure.\n"
    "- Use the web_search tool to find 1-3 real, current headlines that "
    "explain the day's moves. Use real article titles and URLs from the "
    "search results.\n"
    "- The summary must be 60-80 words, neutral and factual, no hype, no "
    "advice, no price targets.\n\n"
    "Return ONLY a JSON object (no markdown fences, no prose around it) of "
    "exactly this shape:\n"
    '{"summary_text": "<60-80 words>", '
    '"headlines": [{"title": "<headline>", "url": "<source url>"}]}'
)

_MAX_SERVER_TOOL_TURNS = 6


def _format_data(summary: MarketSummary) -> str:
    """Compact, readable rendering of the numbers for the prompt."""
    lines = [f"Date: {summary.date}", "", "Indices:"]
    lines += [f"  {i.name}: {i.price:,.2f} ({i.change_pct:+.2f}%)" for i in summary.indices]
    lines += ["", "Crypto:"]
    lines += [f"  {a.name}: {a.value:,.2f} ({a.change_pct:+.2f}%)" for a in summary.crypto]
    lines += ["", "Commodities & macro:"]
    lines += [f"  {a.name}: {a.value:,.2f} ({a.change_pct:+.2f}%)" for a in summary.commodities]
    lines += ["", "Top gainers:"]
    lines += [f"  {m.symbol} {m.name}: {m.change_pct:+.2f}%" for m in summary.gainers]
    lines += ["", "Top losers:"]
    lines += [f"  {m.symbol} {m.name}: {m.change_pct:+.2f}%" for m in summary.losers]
    return "\n".join(lines)


def _final_text(content) -> str:
    return "".join(b.text for b in content if getattr(b, "type", None) == "text").strip()


def _parse(text: str) -> Narrative:
    """Parse the JSON object out of Claude's reply, tolerating stray text."""
    raw = text
    if not raw.lstrip().startswith("{"):
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)
    data = json.loads(raw)
    headlines = [
        Headline(title=h["title"], url=h["url"])
        for h in data.get("headlines", [])
        if h.get("title") and h.get("url")
    ]
    return Narrative(summary_text=data.get("summary_text", "").strip(), headlines=headlines)


def generate_narrative(summary: MarketSummary) -> Narrative:
    """Live call to Claude. Raises on hard failure; caller decides how to degrade."""
    client = Anthropic(api_key=get_anthropic_key())
    messages = [
        {
            "role": "user",
            "content": (
                "Here is today's US market data. Write the brief and find "
                "supporting headlines.\n\n" + _format_data(summary)
            ),
        }
    ]
    tools = [{"type": WEB_SEARCH_TOOL_VERSION, "name": "web_search"}]

    response = None
    for _ in range(_MAX_SERVER_TOOL_TURNS):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
        )
        if response.stop_reason == "pause_turn":
            # Server-side tool loop hit its limit; re-send to resume.
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    text = _final_text(response.content)
    return _parse(text)
