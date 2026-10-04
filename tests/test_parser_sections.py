"""Нарезка тела на секции по якорям."""

import pytest

from heron.core.errors import HeronError
from heron.core.parser import markdown, sections

BODY = """
Вступительный абзац.

## Что это {#what}

Описание. Абзац второй.

### Подзаголовок без якоря

Принадлежит секции what.

## Кому подходит {#who}

Текст.

## Красные флаги {#red-flags .alert}

- Первый
"""


@pytest.fixture
def md():
    return markdown.make()


def test_intro_is_text_before_first_section(md):
    intro, _ = sections.split(md, BODY, "a.md")
    assert intro is not None
    assert "Вступительный абзац" in intro.raw
    assert intro.id == "intro"


def test_sections_found_by_anchor(md):
    _, found = sections.split(md, BODY, "a.md")
    assert list(found) == ["what", "who", "red-flags"]


def test_nested_heading_belongs_to_its_section(md):
    _, found = sections.split(md, BODY, "a.md")
    assert "Подзаголовок без якоря" in found["what"].raw
    assert "Принадлежит секции what" in found["what"].raw


def test_section_title_and_classes(md):
    _, found = sections.split(md, BODY, "a.md")
    assert found["what"].title == "Что это"
    assert found["red-flags"].classes == ["alert"]
    assert found["what"].classes == []


def test_attrs_do_not_leak_into_html(md):
    _, found = sections.split(md, BODY, "a.md")
    assert "{#" not in found["red-flags"].html
    assert "{#" not in found["what"].html


def test_section_html_excludes_its_own_heading(md):
    _, found = sections.split(md, BODY, "a.md")
    assert "<h2" not in found["what"].html
    assert "Описание" in found["what"].html


def test_heading_without_anchor_does_not_start_a_section(md):
    body = "## Первый {#one}\n\nа\n\n## Без якоря\n\nб\n"
    _, found = sections.split(md, body, "a.md")
    assert list(found) == ["one"]
    assert "Без якоря" in found["one"].raw


def test_order_in_file_does_not_matter(md):
    straight = "## A {#a}\n\nтекст а\n\n## B {#b}\n\nтекст б\n"
    reversed_ = "## B {#b}\n\nтекст б\n\n## A {#a}\n\nтекст а\n"
    _, one = sections.split(md, straight, "a.md")
    _, two = sections.split(md, reversed_, "a.md")
    assert one["a"].raw == two["a"].raw
    assert one["b"].raw == two["b"].raw


def test_duplicate_anchor_is_e003(md):
    with pytest.raises(HeronError) as exc:
        sections.split(md, "## A {#same}\n\nа\n\n## B {#same}\n\nб\n", "a.md")
    assert exc.value.code == "E003"
    assert "same" in str(exc.value)


@pytest.mark.parametrize("bad", ["Quick_Facts", "ЯКІРЬ", "two--dash-", "-lead"])
def test_bad_anchor_is_e016(md, bad):
    with pytest.raises(HeronError) as exc:
        sections.split(md, f"## Заголовок {{#{bad}}}\n\nтекст\n", "a.md")
    assert exc.value.code == "E016"


def test_line_numbers_offset_by_frontmatter(md):
    _, found = sections.split(md, BODY, "a.md", offset=6)
    assert found["what"].line == 6 + 4


def test_body_without_sections_is_all_intro(md):
    intro, found = sections.split(md, "Просто текст без заголовков.\n", "a.md")
    assert found == {}
    assert intro is not None and "Просто текст" in intro.raw


def test_empty_body(md):
    intro, found = sections.split(md, "\n\n", "a.md")
    assert intro is None and found == {}


def test_deeper_anchored_heading_stays_inside(md):
    body = "## Секция {#s}\n\nа\n\n### Вложенная {#inner}\n\nб\n\n## Другая {#o}\n\nв\n"
    _, found = sections.split(md, body, "a.md")
    assert list(found) == ["s", "o"]
    assert "Вложенная" in found["s"].raw
