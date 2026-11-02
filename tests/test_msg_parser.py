"""Сообщения разбора страницы на Msg: ru как прежде, en без кириллицы (E15.S2.T9)."""

import re

import pytest

from heron.core.errors import HeronError
from heron.core.parser import frontmatter, markdown, sections
from heron.messages import Msg

CYR = re.compile("[А-Яа-яЁё]")


def _err(fn, *args, **kwargs) -> HeronError:
    with pytest.raises(HeronError) as info:
        fn(*args, **kwargs)
    return info.value


def _check(err: HeronError, ru_message: str, ru_hint: str | None, hint_msg: bool = True) -> None:
    assert isinstance(err.message, Msg)
    assert err.message.text("ru") == ru_message
    assert str(err.message) == ru_message
    assert not CYR.search(err.message.text("en"))
    if ru_hint is not None:
        assert isinstance(err.hint, Msg)
        assert err.hint.text("ru") == ru_hint
        assert not CYR.search(err.hint.text("en"))


def test_no_frontmatter():
    err = _err(frontmatter.split, "просто текст", "a.md")
    _check(
        err,
        "в начале файла нет блока фронтматтера",
        "файл должен начинаться со строки --- , затем YAML, затем снова ---",
    )


def test_bad_yaml():
    err = _err(frontmatter.split, "---\na: [\n---\nтело", "a.md")
    assert err.message.key == "parser_bad_yaml"
    assert err.message.text("ru").startswith("битый YAML во фронтматтере: ")
    assert not CYR.search(err.message.text("en"))
    assert (
        err.hint.text("ru")
        == "проверьте отступы и кавычки: значение с двоеточием берётся в кавычки"
    )


def test_not_mapping():
    err = _err(frontmatter.split, "---\n- a\n- b\n---\n", "a.md")
    _check(err, "фронтматтер должен быть набором ключей, а не list", None)
    assert err.message.text("en") == "the front matter must be a set of keys, not list"


def test_missing_fields():
    err = _err(frontmatter.parse_meta, {"title": "t"}, "a.md")
    _check(
        err,
        "нет обязательных полей: h1, description",
        "title пишется под выдачу, h1 под того, кто уже открыл страницу",
    )


def test_invalid_frontmatter_lines_joined():
    err = _err(
        frontmatter.parse_meta,
        {"title": "t", "h1": "h", "description": "d", "date": "не дата"},
        "a.md",
    )
    if err.message.key == "parser_frontmatter_invalid":
        assert err.message.text("ru").startswith("фронтматтер не проходит проверку:\n    ")
        assert not CYR.search(err.message.text("en").split("\n", 1)[0])


def test_not_utf8(tmp_path):
    path = tmp_path / "a.md"
    path.write_bytes(b"---\n\xff\xfe\n---\n")
    err = _err(frontmatter.read, path)
    _check(err, "файл не читается как UTF-8", "пересохраните файл в UTF-8 без BOM")
    assert err.hint.text("en") == "re-save the file as UTF-8 without BOM"


def test_bad_section_id():
    md = markdown.make()
    err = _err(sections.split, md, "## Тема {#Bad_Id}\n\nтекст\n", "a.md")
    _check(
        err,
        "недопустимый идентификатор секции 'Bad_Id'",
        "идентификатор - латиница, цифры и дефис: {#quick-facts}",
    )
    assert "{#quick-facts}" in err.hint.text("en")


def test_duplicate_section():
    md = markdown.make()
    err = _err(sections.split, md, "## A {#x}\n\nт\n\n## B {#x}\n\nт\n", "a.md")
    _check(
        err,
        "идентификатор секции 'x' встречается в файле дважды",
        "первый раз - строка 1",
    )
    assert err.hint.text("en") == "the first time is line 1"


def test_bad_heading_attr():
    md = markdown.make()
    err = _err(markdown.forbidden_attrs, md, "## Тема {onclick=evil()}\n", "a.md")
    assert err.message.key == "parser_bad_heading_attr"
    assert err.message.text("ru").startswith("недопустимый атрибут заголовка: ")
    assert not CYR.search(err.message.text("en"))
    assert not CYR.search(err.hint.text("en"))


def test_raw_html():
    err = _err(markdown.guard_raw_html, "текст <script>x</script>\n", "a.md", False)
    assert err.message.key == "parser_raw_html"
    assert err.message.text("ru").startswith("сырой HTML в markdown: ")
    assert err.hint.text("ru") == (
        "перепишите средствами markdown, или разрешите осознанно: "
        "build.allow_raw_html: true в site.yaml"
    )
    assert not CYR.search(err.hint.text("en"))
