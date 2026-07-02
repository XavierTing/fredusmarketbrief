# tests/test_config.py
import pytest
from src import config


def test_supabase_getters_raise_when_unset(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.get_supabase_url()
    with pytest.raises(RuntimeError):
        config.get_supabase_service_key()


def test_supabase_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co/")
    assert config.get_supabase_url() == "https://x.supabase.co"


def test_supabase_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert config.supabase_configured() is False
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    assert config.supabase_configured() is True


def test_webhook_secret_getter(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    assert config.get_telegram_webhook_secret() == "s3cret"
