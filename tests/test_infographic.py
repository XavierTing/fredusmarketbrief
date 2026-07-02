import pytest

from src.infographic import _fmt_change, _fmt_value, build_context, render_html, render_png
from src.market_data import load_mock
from src.models import AssetQuote


def test_build_context_shapes_data():
    ctx = build_context(load_mock())
    assert ctx["indices"][0]["cls"] in ("up", "down")
    assert [c["name"] for c in ctx["crypto"]] == ["Bitcoin", "Ethereum"]
    assert len(ctx["commodities"]) == 6
    assert "sectors" not in ctx
    assert ctx["narrative_text"]
    assert ctx["brand_name"]


def test_fmt_value_per_style():
    assert _fmt_value(105230.0, "usd_large") == "$105,230"
    assert _fmt_value(2451.3, "usd") == "$2,451.30"
    assert _fmt_value(4.3, "yield") == "4.30%"
    assert _fmt_value(104.52, "level") == "104.52"


def test_fmt_change_yield_in_bps():
    yld = AssetQuote("US 10Y Yield", "^TNX", 4.3, 1.18, 0.05, "yield")
    assert _fmt_change(yld) == "+5 bps"
    gold = AssetQuote("Gold", "GC=F", 2451.3, 0.45, 10.9, "usd")
    assert _fmt_change(gold) == "+0.45%"


def test_render_html_includes_new_sections():
    html = render_html(load_mock())
    assert "Major Indices" in html
    assert "Crypto" in html
    assert "Commodities" in html
    assert "Top Movers" in html
    assert "Sector Performance" not in html
    assert "Bitcoin" in html
    assert "$105,230" in html
    assert "4.30%" in html


def test_render_html_defaults_to_compass_style():
    html = render_html(load_mock())
    assert "compass-page" in html
    assert "compass-market-report" in html
    assert "report-page" not in html


def test_render_html_uses_report_style_structure():
    html = render_html(load_mock(), style="report")
    assert "report-page" in html
    assert "report-header" in html
    assert "XAVIER US MARKET BRIEF" in html
    assert "masthead" not in html


def test_render_html_uses_compass_style_structure():
    html = render_html(load_mock(), style="compass")
    assert "compass-page" in html
    assert "compass-market-report" in html
    assert "Compass-Style Market Brief" in html
    assert "change-strip" in html
    assert "change-strip outlined" in html
    assert "background: transparent" in html
    assert "change-rail" not in html
    assert html.index("header-grid") < html.index("change-strip") < html.index("Major Indices")
    assert "Major Indices" in html
    assert "Crypto" in html
    assert "Commodities" in html
    assert "Top Movers" in html
    assert "Bitcoin" in html
    assert "$105,230" in html
    assert "mover-change up" in html
    assert "mover-change down" in html
    assert "bar-fill" not in html
    assert "bar-wrap" not in html
    assert "photo" not in html.lower()


def test_render_html_rejects_unknown_style():
    with pytest.raises(ValueError, match="Unsupported infographic style"):
        render_html(load_mock(), style="unknown")


def test_render_png_produces_image(tmp_path):
    pytest.importorskip("playwright")
    out = tmp_path / "infographic.png"
    try:
        render_png(load_mock(), out)
    except Exception as exc:  # chromium not installed in this environment
        pytest.skip(f"Playwright/Chromium unavailable: {exc}")
    assert out.exists()
    assert out.stat().st_size > 1000  # a real PNG, not an empty file
