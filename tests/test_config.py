from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sirep.infra.config import settings
from sirep.shared.config import (
    AppConfig,
    DATETIME_DISPLAY_FORMAT,
    DATE_DISPLAY_FORMAT,
    DISPLAY_TIMEZONE,
    _resolve_timezone,
)


def teardown_module(_module) -> None:  # pragma: no cover - helper for cache cleanup
    _resolve_timezone.cache_clear()


def test_exported_formats_match_settings() -> None:
    assert DATE_DISPLAY_FORMAT == settings.DATE_FORMAT
    assert DATETIME_DISPLAY_FORMAT == settings.DATETIME_FORMAT


def test_app_config_caches_display_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_timezone.cache_clear()

    calls: dict[str, int] = {"count": 0}

    def fake_zoneinfo(name: str) -> timezone:
        calls["count"] += 1
        return timezone.utc

    monkeypatch.setattr("sirep.shared.config.ZoneInfo", fake_zoneinfo)

    cfg = AppConfig(
        timezone_name="UTC",
        timezone_fallback_offset_minutes=0,
        date_display_format="%d/%m/%Y",
        datetime_display_format="%d/%m/%Y %H:%M:%S",
    )

    first = cfg.display_timezone
    second = cfg.display_timezone

    assert first is second
    assert calls["count"] == 1


def test_resolve_timezone_uses_fallback_when_missing(caplog) -> None:
    _resolve_timezone.cache_clear()

    missing_zone = "Invalid/Zone/Test"
    fallback_minutes = -120

    with caplog.at_level("WARNING"):
        tzinfo = _resolve_timezone(missing_zone, fallback_minutes)

    assert tzinfo.utcoffset(None) == timedelta(minutes=fallback_minutes)
    assert missing_zone in caplog.text
    assert "UTC-02:00" in caplog.text


def test_display_timezone_is_available() -> None:
    sample = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert DISPLAY_TIMEZONE.utcoffset(sample) is not None
