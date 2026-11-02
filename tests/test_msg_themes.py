"""Сообщения установки темы на ключах texts/themes.py: ru новый, en равен прежнему тексту."""

import re

import pytest

from heron import themes
from heron.core.errors import HeronError
from heron.messages import Msg
from heron.texts import themes as texts

CYR = re.compile("[а-яА-ЯёЁ]")


def test_keys_parity_and_en_clean():
    assert texts.TEXT["ru"].keys() == texts.TEXT["en"].keys()
    assert not any(CYR.search(v) for v in texts.TEXT["en"].values())
    assert not any("—" in v or "–" in v for v in texts.TEXT["en"].values())


def test_download_refuses_http_in_both_languages():
    with pytest.raises(HeronError) as raised:
        themes._download("http://example.com/t.tgz")
    error = raised.value
    assert isinstance(error.message, Msg) and isinstance(error.hint, Msg)
    assert error.message.text("en") == "http://example.com/t.tgz: only https addresses"
    assert error.hint.text("en") == "a file on disk is taken as a path"
    assert error.message.text("ru") == "http://example.com/t.tgz: допустимы только адреса https"
    assert "a file on disk is taken as a path" in error.render("en")


def test_damaged_archive_texts():
    with pytest.raises(HeronError) as raised:
        themes._members(b"PK\x03\x04" + b"\x00" * 50)
    assert raised.value.message.text("en").startswith("the archive is damaged or truncated: ")
    assert raised.value.message.text("ru").startswith("архив повреждён или обрезан: ")
    assert raised.value.hint.text("ru") == "скачайте или упакуйте его заново"


def test_fields_substituted():
    msg = Msg("themes_wants_heron", wanted=">=9", current="1.0")
    assert msg.text("en") == "the theme wants HERON >=9, this is 1.0"
    assert msg.text("ru") == "тема требует HERON >=9, а это 1.0"
