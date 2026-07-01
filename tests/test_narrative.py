from src.market_data import load_mock
from src.narrative import _format_data, _parse


def test_parse_clean_json():
    n = _parse('{"summary_text": "hi", "headlines": [{"title": "t", "url": "u"}]}')
    assert n.summary_text == "hi"
    assert n.headlines[0].title == "t"
    assert n.headlines[0].url == "u"


def test_parse_tolerates_surrounding_text():
    n = _parse('Sure! Here is the brief:\n{"summary_text": "x", "headlines": []}\nLet me know.')
    assert n.summary_text == "x"
    assert n.headlines == []


def test_parse_drops_headlines_missing_url():
    n = _parse('{"summary_text": "s", "headlines": [{"title": "a"}, {"title": "b", "url": "u"}]}')
    assert len(n.headlines) == 1
    assert n.headlines[0].title == "b"


def test_format_data_includes_key_numbers():
    txt = _format_data(load_mock())
    assert "S&P 500" in txt
    assert "NVDA" in txt
    assert "Bitcoin" in txt
    assert "Gold" in txt
    assert "Crypto" in txt
