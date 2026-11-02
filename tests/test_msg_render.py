"""Сообщения отрисовки на ключах texts/render.py: ru прежний, en без кириллицы."""

import re
from pathlib import Path
from types import SimpleNamespace

import jinja2
import pytest

from heron.core.errors import Collector, HeronError
from heron.core.render import env as envmod
from heron.core.render import pages
from heron.messages import Msg

CYR = re.compile("[а-яА-ЯёЁ]")


def _check(err: HeronError) -> tuple[Msg, Msg]:
    assert isinstance(err.message, Msg) and isinstance(err.hint, Msg)
    assert not CYR.search(err.message.text("en"))
    assert not CYR.search(err.hint.text("en"))
    return err.message, err.hint


def _env(tmp_path: Path) -> jinja2.Environment:
    return jinja2.Environment(loader=jinja2.FileSystemLoader(str(tmp_path)))


def _render(tmp_path: Path, page_type: str = "page"):
    page = SimpleNamespace(type=page_type, source="a.md")
    theme = SimpleNamespace()
    return page, theme


def test_missing_template(tmp_path, monkeypatch):
    monkeypatch.setattr(pages, "template_name", lambda page, theme: "nope.html")
    page, theme = _render(tmp_path)
    with pytest.raises(HeronError) as ei:
        pages.render_page(_env(tmp_path), page, None, None, theme, None, Collector())
    msg, hint = _check(ei.value)
    assert msg == "для типа страницы 'page' нет шаблона nope.html"
    assert hint.text("ru") == "создайте nope.html в теме или задайте другой тип страницы"
    assert msg.text("en") == "there is no template nope.html for page type 'page'"


def test_template_syntax_error(tmp_path, monkeypatch):
    (tmp_path / "bad.html").write_text("{% if %}")
    monkeypatch.setattr(pages, "template_name", lambda page, theme: "bad.html")
    page, theme = _render(tmp_path)
    with pytest.raises(HeronError) as ei:
        pages.render_page(_env(tmp_path), page, None, None, theme, None, Collector())
    msg, hint = _check(ei.value)
    assert msg.text("ru").startswith("ошибка в шаблоне bad.html, строка 1:")
    assert msg.text("en").startswith("error in template bad.html, line 1:")
    assert hint.text("ru") == "проверьте разметку Jinja в этой строке шаблона темы"


def test_i18n_strings_missing_warns_in_msg(tmp_path):
    collector = Collector()
    strings = envmod.load_strings(tmp_path, "en", collector)
    assert strings.title == "title"
    texts = [w.message for w in collector.warnings]
    assert all(isinstance(t, Msg) and not CYR.search(t.text("en")) for t in texts)
    assert texts[0].text("ru").startswith("в теме нет строк интерфейса для языка 'en'")
    assert texts[1] == "нет строки перевода 'title' для языка 'en'"
    assert texts[1].text("en") == "no translation string 'title' for language 'en'"


def test_i18n_key_not_string(tmp_path):
    (tmp_path / "i18n").mkdir()
    (tmp_path / "i18n" / "ru.yaml").write_text("off: x\nok: y\n", encoding="utf-8")
    collector = Collector()
    envmod.load_strings(tmp_path, "ru", collector)
    (w,) = collector.warnings
    assert w.message == "ключ False прочитан как bool, а не как строка — возьмите его в кавычки"
    assert w.message.text("en") == "key False was read as bool, not as a string: put it in quotes"


def test_i18n_symlink_outside_theme(tmp_path):
    theme = tmp_path / "theme"
    (theme / "i18n").mkdir(parents=True)
    outside = tmp_path / "out.yaml"
    outside.write_text("a: b\n")
    (theme / "i18n" / "ru.yaml").symlink_to(outside)
    with pytest.raises(HeronError) as ei:
        envmod.load_strings(theme, "ru", Collector())
    msg, hint = _check(ei.value)
    assert msg == "i18n/ru.yaml ведёт за пределы темы через ссылку"
    assert msg.text("en") == "i18n/ru.yaml leads outside the theme through a link"
    assert hint.text("en") == "put the file itself into the theme instead of a link to it"
