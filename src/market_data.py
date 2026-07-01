"""Stage 1 — fetch the day's US market data from Yahoo Finance (no API key).

Pulls major indices, crypto + commodities/macro cross-asset quotes, and top
gainers/losers, returning a ``MarketSummary`` with an empty narrative (filled by
the next stage). Designed to degrade gracefully: any section that fails to fetch
is left empty rather than raising, so the pipeline can still produce and send a
partial infographic.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path

from .config import CRYPTO, COMMODITIES_MACRO, INDICES, TOP_MOVERS_COUNT
from .models import AssetQuote, IndexQuote, MarketSummary, Mover

log = logging.getLogger(__name__)

_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "samples" / "sample_market_data.json"


# --- helpers -----------------------------------------------------------------

def _change_pct(quote: dict) -> float:
    """Daily % change. Prefer price/prev-close (unambiguous) over Yahoo's field,
    whose units differ between the quote and screener endpoints."""
    price = quote.get("regularMarketPrice")
    prev = quote.get("regularMarketPreviousClose")
    if isinstance(price, (int, float)) and isinstance(prev, (int, float)) and prev:
        return (price / prev - 1.0) * 100.0
    raw = quote.get("regularMarketChangePercent")
    if not isinstance(raw, (int, float)):
        return 0.0
    # The price endpoint returns a fraction (0.0081); the screener returns percent (0.81).
    return raw * 100.0 if abs(raw) < 1 else raw


def _name(quote: dict, fallback: str) -> str:
    return quote.get("shortName") or quote.get("longName") or fallback


def _quote_map(symbols: list[str]) -> dict[str, dict]:
    """Fetch the Yahoo ``price`` module for a list of symbols, skipping failures."""
    from yahooquery import Ticker

    tickers = Ticker(symbols)
    data = tickers.price
    if not isinstance(data, dict):
        return {}
    # yahooquery returns a string error message instead of a dict for bad symbols.
    return {sym: q for sym, q in data.items() if isinstance(q, dict)}


# --- public API --------------------------------------------------------------

def fetch_indices() -> list[IndexQuote]:
    quotes = _quote_map(list(INDICES.values()))
    out: list[IndexQuote] = []
    for name, symbol in INDICES.items():
        q = quotes.get(symbol)
        if not q:
            log.warning("No quote for index %s (%s)", name, symbol)
            continue
        out.append(
            IndexQuote(
                name=name,
                symbol=symbol,
                price=float(q.get("regularMarketPrice") or 0.0),
                change_pct=round(_change_pct(q), 2),
            )
        )
    return out


# Symbols that are sometimes empty on Yahoo → try an alternate first.
_FALLBACK_SYMBOLS = {"DX-Y.NYB": "DX=F"}


def _value_prev(quote: dict) -> tuple[float, float]:
    value = quote.get("regularMarketPrice")
    prev = quote.get("regularMarketPreviousClose")
    return (
        float(value) if isinstance(value, (int, float)) else 0.0,
        float(prev) if isinstance(prev, (int, float)) else 0.0,
    )


def fetch_assets(specs: list[tuple[str, str, str]]) -> list[AssetQuote]:
    """Fetch a list of (name, symbol, fmt) specs into AssetQuotes (in order)."""
    quotes = _quote_map([symbol for _, symbol, _ in specs])
    out: list[AssetQuote] = []
    for name, symbol, fmt in specs:
        q = quotes.get(symbol)
        if not q and symbol in _FALLBACK_SYMBOLS:
            alt = _FALLBACK_SYMBOLS[symbol]
            q = _quote_map([alt]).get(alt)
        if not q:
            log.warning("No quote for asset %s (%s)", name, symbol)
            continue

        value, prev = _value_prev(q)
        # Yahoo has historically quoted ^TNX as 10× the yield (43.0 == 4.30%).
        if symbol == "^TNX" and value > 15:
            value /= 10.0
            prev = prev / 10.0 if prev else prev

        change_abs = value - prev if prev else 0.0
        change_pct = (value / prev - 1.0) * 100.0 if prev else 0.0
        out.append(
            AssetQuote(
                name=name,
                symbol=symbol,
                value=round(value, 2),
                change_pct=round(change_pct, 2),
                change_abs=round(change_abs, 4),
                fmt=fmt,
            )
        )
    return out


def _movers_from(quotes: list[dict]) -> list[Mover]:
    movers: list[Mover] = []
    for q in quotes[:TOP_MOVERS_COUNT]:
        symbol = q.get("symbol")
        if not symbol:
            continue
        movers.append(
            Mover(
                symbol=symbol,
                name=_name(q, symbol),
                price=float(q.get("regularMarketPrice") or 0.0),
                change_pct=round(_change_pct(q), 2),
            )
        )
    return movers


def fetch_movers() -> tuple[list[Mover], list[Mover]]:
    """Return (gainers, losers) via Yahoo's predefined screeners."""
    from yahooquery import Screener

    screener = Screener()
    data = screener.get_screeners(
        ["day_gainers", "day_losers"], count=TOP_MOVERS_COUNT
    )
    if not isinstance(data, dict):
        return [], []
    gainers = _movers_from(data.get("day_gainers", {}).get("quotes", []))
    losers = _movers_from(data.get("day_losers", {}).get("quotes", []))
    return gainers, losers


def fetch_market_data(date: str | None = None) -> MarketSummary:
    """Live fetch. Each section degrades to empty on failure."""
    summary = MarketSummary(date=date or _dt.date.today().isoformat())

    try:
        summary.indices = fetch_indices()
    except Exception:  # noqa: BLE001 - demo resilience
        log.exception("Failed to fetch indices")
    try:
        summary.crypto = fetch_assets(CRYPTO)
    except Exception:  # noqa: BLE001
        log.exception("Failed to fetch crypto")
    try:
        summary.commodities = fetch_assets(COMMODITIES_MACRO)
    except Exception:  # noqa: BLE001
        log.exception("Failed to fetch commodities/macro")
    try:
        summary.gainers, summary.losers = fetch_movers()
    except Exception:  # noqa: BLE001
        log.exception("Failed to fetch movers")

    return summary


def load_mock() -> MarketSummary:
    """Load the bundled sample data — used by --mock and tests (no network)."""
    with _SAMPLE_PATH.open() as fh:
        return MarketSummary.from_dict(json.load(fh))
