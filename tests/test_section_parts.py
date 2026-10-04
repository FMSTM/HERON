"""Состав секции: подводка, основной узел, примечание, врезка, пары.

Макет режет страницу мельче, чем заголовок и текст под ним, поэтому
секция обязана приезжать в тему разобранной, а не одним куском html.
"""

import pytest

from heron.core.parser import blocks, markdown, sections


@pytest.fixture
def md():
    return markdown.make()


def one(md, body):
    _, found = sections.split(md, body, "a.md")
    blocks.apply(md, found)
    return next(iter(found.values()))


def test_lead_before_list_and_note_after(md):
    section = one(
        md,
        "## Кому {#who}\n\n"
        "Подводка в один абзац.\n\n"
        "- Первый\n- Второй\n\n"
        "**Сначала главное.** Примечание под списком.\n",
    )
    assert "Подводка в один абзац" in section.lead
    assert section.kind == "list"
    assert section.note_title == "Сначала главное"
    assert "Примечание под списком" in section.note
    assert "Сначала главное" not in section.note


def test_prose_section_has_no_lead_and_note(md):
    section = one(md, "## Что это {#what}\n\nОдин абзац.\n\nВторой абзац.\n")
    assert section.kind == "prose"
    assert section.lead == ""
    assert section.note == ""
    assert "Второй абзац" in section.body


def test_quote_becomes_callout_and_leaves_the_text(md):
    section = one(
        md,
        "## Возраст {#age}\n\nАбзац до.\n\n- Пункт\n\n> Возраст сам по себе не противопоказание.\n",
    )
    assert "не противопоказание" in section.callout
    assert "не противопоказание" not in section.note


def test_list_of_terms_becomes_pairs(md):
    section = one(
        md,
        "## Признаки {#red}\n\n"
        "- **Нарушилось мочеиспускание** — звоните 103.\n"
        "- **Слабость нарастает.** Нога подворачивается.\n",
    )
    first, second = section.data
    assert first.term == "Нарушилось мочеиспускание"
    assert "звоните 103" in first.text
    assert second.term == "Слабость нарастает"
    # строкой пара остаётся прежним html: тема, написанная раньше, работает
    assert "<strong>" in str(first)


def test_mixed_list_keeps_every_item(md):
    section = one(md, "## Список {#l}\n\n- **Термин.** Пояснение.\n- Обычный пункт.\n")
    assert [item.term for item in section.data] == ["Термин", ""]
    assert "Обычный пункт" in section.data[1].text


def test_list_without_bold_stays_strings(md):
    section = one(md, "## Список {#l}\n\n- Первый\n- Второй\n")
    assert section.data == ["Первый", "Второй"]


def test_links_survive_and_are_collected(md):
    section = one(
        md,
        "## Как {#how}\n\n1. **Подготовка.** Сдайте [анализы](/guides/preparation/).\n",
    )
    step = section.data[0]
    assert '<a href="/guides/preparation/">' in step["text"]
    assert step["links"] == [{"title": "анализы", "href": "/guides/preparation/"}]
