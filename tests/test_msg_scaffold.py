"""Сообщения заготовки страницы на ключах texts/scaffold.py: ru прежний, en без кириллицы."""

import re

import pytest

from heron.core.errors import HeronError
from heron.messages import Msg
from heron.scaffold import _THEME_TITLE, _TYPE_HINTS, create
from heron.scaffold.page import write_page

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


def test_bad_slug(tmp_path):
    with pytest.raises(HeronError) as e:
        write_page(tmp_path, "page", "Bad Slug")
    _check(
        e.value,
        "недопустимый слаг 'Bad Slug'",
        "латиница, цифры и дефис: getting-started. Заголовок может быть любым",
    )


def test_exists_and_language_and_folder(tmp_path):
    root = _site(tmp_path)
    with pytest.raises(HeronError) as e:
        write_page(root, "page", "ok", lang="xx")
    _check(e.value, "языка 'xx' нет в site.languages")
    with pytest.raises(HeronError) as e:
        write_page(root, "page", "ok", folder="../up")
    _check(
        e.value,
        "папка '../up' выходит за пределы content/en/",
        "относительный путь без `..`: guides/intro",
    )
    with pytest.raises(HeronError) as e:
        write_page(root, "nonexistent-type", "ok")
    assert isinstance(e.value.message, Msg)
    assert not CYR.search(e.value.message.text("en"))
    assert e.value.message.text("ru").startswith("тема не знает тип страницы 'nonexistent-type'")


def test_tables_have_both_languages():
    assert set(_TYPE_HINTS) == {"ru", "en"}
    assert _THEME_TITLE["ru"].format(name="X") == "Тема сайта X"
    assert _THEME_TITLE["en"].format(name="X") == "Theme of X"
