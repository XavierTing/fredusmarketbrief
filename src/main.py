"""Orchestrator: fetch → narrate → render → send.

Run modes:
  python -m src.main                         live data, narrate, render, SEND
  python -m src.main --dry-run               live data, narrate, render, NO send
  python -m src.main --mock --dry-run        sample data, render only (no keys/network)
  python -m src.main --mock                  sample data, render, SEND (needs Telegram creds)
  python -m src.main --out path/to/img.png   choose the output path
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import AGENT_NAME, supabase_configured
from .infographic import _date_display, render_png
from .market_data import fetch_market_data, load_mock
from .models import MarketSummary
from .narrative import generate_narrative
from . import storage, subscribers
from .telegram_sender import TelegramBlockedError, send_photo as telegram_send_photo
from .whatsapp_sender import send_photo as whatsapp_send_photo

log = logging.getLogger("daily_brief")


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


def _build_caption(summary: MarketSummary) -> str:
    parts = [f"{AGENT_NAME} — {_date_display(summary.date)}"]
    if summary.narrative.headlines:
        parts.append(summary.narrative.headlines[0].title)
    elif summary.narrative.summary_text:
        parts.append(summary.narrative.summary_text.split(". ")[0].strip() + ".")
    return "\n".join(parts)


def _deliver(out_path: Path, caption: str) -> None:
    """Broadcast the image to every channel. Raise only if all channels fail."""
    succeeded = 0
    for name, send in _CHANNELS:
        try:
            send(out_path, caption=caption)
            succeeded += 1
        except Exception:  # noqa: BLE001 - one channel's failure must not block others
            log.exception("%s delivery failed", name)
    if succeeded == 0:
        raise RuntimeError("All delivery channels failed")


def run(mock: bool = False, dry_run: bool = False, out: str | None = None, style: str = "compass") -> Path:
    # 1. Fetch
    summary = load_mock() if mock else fetch_market_data()
    log.info(
        "Fetched %d indices, %d crypto, %d commodities/macro, %d gainers, %d losers",
        len(summary.indices), len(summary.crypto), len(summary.commodities),
        len(summary.gainers), len(summary.losers),
    )

    # 2. Narrate (live only; mock data ships with a narrative). Degrade on failure.
    if not mock:
        try:
            summary.narrative = generate_narrative(summary)
            log.info("Generated narrative (%d headlines)", len(summary.narrative.headlines))
        except Exception:  # noqa: BLE001 - render without narrative rather than abort
            log.exception("Narrative generation failed; continuing without it")

    # 3. Render
    out_path = Path(out) if out else Path("out") / f"infographic-{summary.date}.png"
    render_png(summary, out_path, style=style)

    # 4. Send
    if dry_run:
        log.info("Dry run: skipping delivery. Image at %s", out_path)
    else:
        _deliver(out_path, caption=_build_caption(summary))

    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Xavier US Market Brief — US market infographic → Telegram/WhatsApp")
    parser.add_argument("--mock", action="store_true", help="Use bundled sample data (no network/keys)")
    parser.add_argument("--dry-run", action="store_true", help="Render but do not send to Telegram")
    parser.add_argument("--out", default=None, help="Output PNG path")
    parser.add_argument(
        "--style",
        default="compass",
        choices=["report", "compass"],
        help="Infographic visual style",
    )
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        path = run(mock=args.mock, dry_run=args.dry_run, out=args.out, style=args.style)
    except Exception:
        log.exception("Pipeline failed")
        return 1

    log.info("Done: %s", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
