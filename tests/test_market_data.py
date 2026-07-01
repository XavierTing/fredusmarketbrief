from pytest import approx

from src.market_data import _change_pct, fetch_assets, load_mock
from src.models import MarketSummary


def test_load_mock_parses_all_sections():
    s = load_mock()
    assert s.date == "2026-05-29"
    assert [i.symbol for i in s.indices] == ["^GSPC", "^IXIC", "^DJI"]
    assert [a.name for a in s.crypto] == ["Bitcoin", "Ethereum"]
    assert len(s.commodities) == 6
    assert {a.symbol for a in s.commodities} >= {"GC=F", "SI=F", "^TNX", "^VIX"}
    assert len(s.gainers) == 5
    assert len(s.losers) == 5
    assert s.narrative.summary_text
    assert len(s.narrative.headlines) == 2


def test_fetch_assets_normalizes_legacy_tnx(monkeypatch):
    import src.market_data as md

    # Yahoo legacy quoting: ^TNX reported as 10x the yield (42.50 == 4.25%).
    monkeypatch.setattr(
        md, "_quote_map",
        lambda symbols: {"^TNX": {"regularMarketPrice": 42.5, "regularMarketPreviousClose": 42.0}},
    )
    [q] = fetch_assets([("US 10Y Yield", "^TNX", "yield")])
    assert q.value == approx(4.25)
    assert q.change_abs == approx(0.05)  # 4.25 - 4.20, used to render +5 bps


def test_fetch_assets_keeps_modern_tnx(monkeypatch):
    import src.market_data as md

    # Modern quoting: ^TNX already in percent (4.25) — must NOT be divided.
    monkeypatch.setattr(
        md, "_quote_map",
        lambda symbols: {"^TNX": {"regularMarketPrice": 4.25, "regularMarketPreviousClose": 4.20}},
    )
    [q] = fetch_assets([("US 10Y Yield", "^TNX", "yield")])
    assert q.value == approx(4.25)


def test_change_pct_prefers_price_over_prev_close():
    assert _change_pct({"regularMarketPrice": 101.0, "regularMarketPreviousClose": 100.0}) == approx(1.0)


def test_change_pct_normalizes_fraction_from_price_endpoint():
    # price endpoint reports a fraction (0.0081 == +0.81%)
    assert _change_pct({"regularMarketChangePercent": 0.0081}) == approx(0.81)


def test_change_pct_keeps_screener_percent_as_is():
    # screener endpoint reports a percent (5.21 == +5.21%)
    assert _change_pct({"regularMarketChangePercent": 5.21}) == approx(5.21)


def test_change_pct_handles_missing_data():
    assert _change_pct({}) == 0.0


def test_market_summary_json_roundtrip():
    s = load_mock()
    s2 = MarketSummary.from_dict(s.to_dict())
    assert s2.indices[0].name == s.indices[0].name
    assert s2.narrative.headlines[0].url == s.narrative.headlines[0].url
