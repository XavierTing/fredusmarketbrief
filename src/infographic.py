"""Stage 3 — render the MarketSummary into a branded PNG infographic.

Fills a self-contained Jinja2 HTML template (CSS + logo inlined), then
screenshots it with headless Chromium (Playwright) at a fixed portrait width.
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import AGENT_NAME, BRAND_TAGLINE, DISCLAIMER
from .models import MarketSummary

log = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_VIEWPORT_WIDTH = 1080
_TEMPLATE_BY_STYLE = {
    "report": "infographic.html.j2",
    "compass": "compass.html.j2",
}

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
)


def _cls(pct: float) -> str:
    return "up" if pct >= 0 else "down"


def _pct_str(pct: float) -> str:
    return f"{pct:+.2f}%"


def _date_display(iso_date: str) -> str:
    try:
        return _dt.date.fromisoformat(iso_date).strftime("%A, %B %d, %Y")
    except ValueError:
        return iso_date


def _truncate(name: str, limit: int = 22) -> str:
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def _fmt_value(value: float, fmt: str) -> str:
    if fmt == "usd_large":   # BTC/ETH — no cents on big numbers
        return f"${value:,.0f}"
    if fmt == "usd":         # gold/silver/oil
        return f"${value:,.2f}"
    if fmt == "yield":       # 10Y treasury — a level, in percent
        return f"{value:.2f}%"
    return f"{value:,.2f}"   # level (dollar index, VIX)


def _fmt_change(asset) -> str:
    if asset.fmt == "yield":  # express the move in basis points, not relative %
        return f"{round(asset.change_abs * 100):+d} bps"
    return _pct_str(asset.change_pct)


def _asset_card(asset) -> dict:
    return {
        "name": asset.name,
        "value_str": _fmt_value(asset.value, asset.fmt),
        "change_str": _fmt_change(asset),
        "cls": _cls(asset.change_abs),  # up/down by direction of the raw move
    }


def build_context(summary: MarketSummary) -> dict:
    """Shape a MarketSummary into the template's expected variables."""
    return {
        "brand_name": AGENT_NAME,
        "tagline": BRAND_TAGLINE,
        "date_display": _date_display(summary.date),
        "disclaimer": DISCLAIMER,
        "indices": [
            {
                "name": i.name,
                "price_str": f"{i.price:,.2f}",
                "change_str": _pct_str(i.change_pct),
                "cls": _cls(i.change_pct),
            }
            for i in summary.indices
        ],
        "narrative_text": summary.narrative.summary_text,
        "headlines": [{"title": h.title} for h in summary.narrative.headlines],
        "crypto": [_asset_card(a) for a in summary.crypto],
        "commodities": [_asset_card(a) for a in summary.commodities],
        "gainers": [
            {"symbol": m.symbol, "name": _truncate(m.name), "change_str": _pct_str(m.change_pct)}
            for m in summary.gainers
        ],
        "losers": [
            {"symbol": m.symbol, "name": _truncate(m.name), "change_str": _pct_str(m.change_pct)}
            for m in summary.losers
        ],
    }


def _template_name(style: str) -> str:
    try:
        return _TEMPLATE_BY_STYLE[style]
    except KeyError as exc:
        supported = ", ".join(sorted(_TEMPLATE_BY_STYLE))
        raise ValueError(f"Unsupported infographic style {style!r}. Supported styles: {supported}") from exc


def render_html(summary: MarketSummary, style: str = "compass") -> str:
    template = _env.get_template(_template_name(style))
    return template.render(**build_context(summary))


def _render_png_once(html: str, out_path: Path) -> None:
    """Single Chromium render attempt. Closes the browser even on failure."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": _VIEWPORT_WIDTH, "height": 1500},
                device_scale_factor=2,  # crisp on phone screens
            )
            page.set_content(html, wait_until="networkidle")
            page.screenshot(path=str(out_path), full_page=True, type="png")
        finally:
            browser.close()


def render_png(
    summary: MarketSummary,
    out_path: str | Path,
    style: str = "compass",
    attempts: int = 3,
) -> Path:
    """Render the infographic to a PNG file. Returns the output path.

    Chromium can hiccup transiently (launch timeout, a slow ``networkidle``);
    since the daily run happens once, retry a few times so a one-off render
    blip self-heals instead of dropping that day's brief.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(summary, style=style)

    for attempt in range(1, attempts + 1):
        try:
            _render_png_once(html, out_path)
            break
        except Exception:  # noqa: BLE001 - transient render failures are retried
            if attempt == attempts:
                raise
            log.warning("Render attempt %d/%d failed; retrying", attempt, attempts, exc_info=True)
            time.sleep(2 * attempt)  # brief linear backoff

    log.info("Wrote infographic to %s", out_path)
    return out_path
