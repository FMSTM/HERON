"""Вводный блок надвое и шаги с метками.

Шаблон показывает ровно два абзаца до первого заголовка и рисует метку
шага отдельной плашкой — значит движок обязан отдать их по отдельности.
"""

import pytest

from heron.core import tree
from heron.core.parser import blocks, markdown, sections
from tests import sites


@pytest.fixture
def md():
    return markdown.make()


def intro_of(md, body):
    intro, _ = sections.split(md, body, "a.md")
    found = blocks.intro_parts(md, intro)
    return intro, found


def test_one_paragraph_is_lead_only(md):
    intro, warnings = intro_of(md, "Один абзац.\n\n## Что {#what}\n\nТекст.\n")
    assert "Один абзац" in intro.lead
    assert intro.promise == ""
    assert warnings == []


def test_second_paragraph_is_promise(md):
    intro, warnings = intro_of(md, "Первый.\n\nВторой.\n\n## Что {#what}\n\nТекст.\n")
    assert "Первый" in intro.lead
    assert "Второй" in intro.promise
    assert warnings == []


def test_third_paragraph_warns(md):
    intro, warnings = intro_of(md, "Раз.\n\nДва.\n\nТри.\n\n## Что {#what}\n\nТекст.\n")
    assert len(warnings) == 1
    assert "длиннее двух абзацев" in warnings[0].message
    assert "Три" in intro.html  # из полного текста абзац не пропадает


def test_warning_names_the_file(tmp_path):
    files = {"uk/index.md": sites.page("Головна").replace("Вступление.", "Раз.\n\nДва.\n\nТри.")}
    content = sites.build(tmp_path, files)
    _, collector = tree.scan(content, sites.config())
    assert [w.path for w in collector.warnings if "длиннее двух" in w.message] == ["uk/index.md"]


def one(md, body):
    _, found = sections.split(md, body, "a.md")
    blocks.apply(md, found)
    return next(iter(found.values()))


def test_step_tag_is_cut_out_of_the_title(md):
    section = one(
        md,
        "## Исходы {#outcome}\n\n"
        "1. **[ЧАЩЕ ВСЕГО] Операция не нужна.** Медикаменты и режим.\n"
        "2. **Малоинвазивная процедура.** Без большого разреза.\n",
    )
    first, second = section.data
    assert first["tag"] == "ЧАЩЕ ВСЕГО"
    assert first["title"] == "Операция не нужна"
    assert "Медикаменты" in first["text"]
    assert second["tag"] == ""
    assert [step["n"] for step in section.data] == [1, 2]


def test_lowercase_brackets_are_not_a_tag(md):
    section = one(md, "## Как {#how}\n\n1. **[см. ниже] Шаг.** Текст.\n")
    assert section.data[0]["tag"] == ""
    assert section.data[0]["title"] == "[см. ниже] Шаг"


def test_first_step_is_top_unless_marked(md):
    section = one(md, "## Как {#how}\n\n1. **Раз.** Текст.\n2. **Два.** Текст.\n")
    assert [step["top"] for step in section.data] == [True, False]
