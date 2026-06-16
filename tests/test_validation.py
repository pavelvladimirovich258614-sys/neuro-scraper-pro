"""Тесты валидации в ParsingService (чистые статические методы)."""

import pytest

from services.parsing_service import ParsingService


@pytest.mark.parametrize("link", [
    "https://t.me/channel",
    "http://t.me/channel",
    "@channel",
    "t.me/channel",
    "https://telegram.me/channel",
])
def test_validate_link_accepts_valid(link):
    ok, err = ParsingService.validate_link(link)
    assert ok is True
    assert err is None


@pytest.mark.parametrize("link", ["", "   ", "example.com/channel", "ftp://t.me/x"])
def test_validate_link_rejects_invalid(link):
    ok, err = ParsingService.validate_link(link)
    assert ok is False
    assert err is not None


def test_validate_time_filter_known():
    for key, expected in [("day", 1), ("week", 7), ("month", 30), ("3months", 90)]:
        ok, days = ParsingService.validate_time_filter(key)
        assert ok is True
        assert days == expected


def test_validate_time_filter_alltime():
    ok, days = ParsingService.validate_time_filter("alltime")
    assert ok is True
    assert days is None


def test_validate_time_filter_unknown():
    ok, days = ParsingService.validate_time_filter("decade")
    assert ok is False
    assert days is None


def test_get_time_days_from_filter():
    assert ParsingService.get_time_days_from_filter("week") == 7
    assert ParsingService.get_time_days_from_filter("alltime") is None
