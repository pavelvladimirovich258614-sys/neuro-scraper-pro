"""Тесты чистого парсера ссылок на посты."""

import pytest

from utils.link_parser import parse_post_link, PostLinkInfo


def test_public_full_url():
    info = parse_post_link("https://t.me/durov/123")
    assert info == PostLinkInfo(is_private=False, username="durov", message_id=123)


def test_public_short_url():
    info = parse_post_link("t.me/some_channel/42")
    assert not info.is_private
    assert info.username == "some_channel"
    assert info.message_id == 42


def test_public_with_query_params():
    info = parse_post_link("https://t.me/chan/777?single&comment=5")
    assert info.message_id == 777
    assert info.username == "chan"


def test_public_trailing_slash():
    info = parse_post_link("https://t.me/chan/55/")
    assert info.message_id == 55


def test_private_channel():
    info = parse_post_link("https://t.me/c/1234567890/99")
    assert info.is_private
    assert info.channel_id == 1234567890
    assert info.message_id == 99
    assert info.username is None


def test_private_with_query():
    info = parse_post_link("https://t.me/c/1234567890/99?thread=12")
    assert info.channel_id == 1234567890
    assert info.message_id == 99


def test_http_scheme():
    info = parse_post_link("http://t.me/chan/1")
    assert info.message_id == 1


@pytest.mark.parametrize("bad", ["", "   ", "https://t.me/onlychannel", "t.me/c/123"])
def test_invalid_links_raise(bad):
    with pytest.raises(ValueError):
        parse_post_link(bad)


def test_non_numeric_message_id_raises():
    with pytest.raises(ValueError):
        parse_post_link("https://t.me/chan/abc")
