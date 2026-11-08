"""Сообщения заготовки и команд страниц на ключах texts/: ru прежний, en без кириллицы."""

import re

import pytest

from heron.core.errors import HeronError
from heron.edit import entity as ops
from heron.messages import Msg
from heron.scaffold import _THEME_TITLE, _TYPE_HINTS, create

CYR = re.compile("[а-яА-ЯёЁ]")


def _site(tmp_path):
    root = tmp_path / "site"
    create(root, name="Demo", languages=["en"], notes="en")
    return root


def _check(err: HeronError, ru_message: str, ru_hint: str | None = None):
    assert isinstance(err.message, Msg)
    assert not CYR.search(err.message.text("en"))
    assert err.message.text("ru") == ru_message
    if ru_hint is not None:
        assert isinstance(err.hint, Msg)
        assert not CYR.search(err.hint.text("en"))
        assert err.hint.text("ru") == ru_hint


def test_bad_key():
    with pytest.raises(HeronError) as e:
        ops.norm_key("Bad Slug")
    assert e.value.code == "E005"
    _check(
        e.value,
        "ключ 'Bad Slug': части через /, в каждой латиница в нижнем регистре, цифры и дефис",
        "например about-agency или services/roofing",
    )


def test_unknown_type(tmp_path):
    ctx = ops.context(_site(tmp_path), "en")
    with pytest.raises(HeronError) as e:
        ops.open_entity(ctx, "ok", page_type="nonexistent-type")
    assert e.value.code == "E008"
    assert isinstance(e.value.message, Msg)
    assert not CYR.search(e.value.message.text("en"))
    assert e.value.message.text("ru").startswith("тема не знает тип страницы 'nonexistent-type'")


def test_tables_have_both_languages():
    assert set(_TYPE_HINTS) == {"ru", "en"}
    assert _THEME_TITLE["ru"].format(name="X") == "Тема сайта X"
    assert _THEME_TITLE["en"].format(name="X") == "Theme of X"
