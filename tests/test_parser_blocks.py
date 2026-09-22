"""Определение модуля секции и разбор структурированных данных."""

import pytest

from heron.core.parser import blocks, markdown, sections


@pytest.fixture
def md():
    return markdown.make()


def parse(md, body):
    _, found = sections.split(md, body, "a.md")
    warnings = blocks.apply(md, found)
    return found, warnings


def one(md, body):
    found, warnings = parse(md, body)
    section = next(iter(found.values()))
    return section, warnings


def test_facts_from_pairs(md):
    section, _ = one(md, "## Коротко {#f}\n\nТривалість | 40 хвилин\nСтаціонар  | 1 доба\n")
    assert section.kind == "facts"
    assert section.data == [
        {"key": "Тривалість", "value": "40 хвилин"},
        {"key": "Стаціонар", "value": "1 доба"},
    ]


def test_table_is_not_mistaken_for_facts(md):
    body = "## Порівняння {#t}\n\n| Що | МРТ | КТ |\n|---|---|---|\n| Видно | диски | кістка |\n"
    section, _ = one(md, body)
    assert section.kind == "table"
    assert section.data["head"] == ["Що", "МРТ", "КТ"]
    assert section.data["rows"] == [["Видно", "диски", "кістка"]]


def test_steps_with_bold_titles(md):
    body = "## Як {#h}\n\n1. **Підготовка.** Аналізи.\n2. **Знеболення.** Вибір методу.\n"
    section, _ = one(md, body)
    assert section.kind == "steps"
    assert section.data[0]["title"] == "Підготовка"
    assert section.data[0]["text"] == "Аналізи."
    assert section.data[0]["n"] == 1
    assert section.data[0]["top"] is True


def test_steps_without_bold_still_steps(md):
    section, _ = one(md, "## Як {#h}\n\n1. Перший крок\n2. Другий крок\n")
    assert section.kind == "steps"
    assert section.data[0]["title"] == ""


def test_faq_from_h3_with_prose(md):
    body = "## Питання {#faq}\n\n### Боляче?\n\nДві доби.\n\n### За кермо?\n\nДва тижні.\n"
    section, _ = one(md, body)
    assert section.kind == "faq"
    assert section.data[0]["q"] == "Боляче?"
    assert "Дві доби" in section.data[0]["a"]


def test_two_lists(md):
    body = "## За і проти {#p}\n\n### За\n\n- раз\n\n### Проти\n\n- два\n"
    section, _ = one(md, body)
    assert section.kind == "two-lists"
    assert [g["title"] for g in section.data] == ["За", "Проти"]


def test_checklist_from_three_groups(md):
    body = (
        "## Взяти {#c}\n\n### Документи\n\n- паспорт\n\n"
        "### Обстеження\n\n- МРТ\n\n### Ліки\n\n- список\n"
    )
    section, _ = one(md, body)
    assert section.kind == "checklist"
    assert len(section.data) == 3


def test_plain_list(md):
    section, _ = one(md, "## Протипоказання {#c}\n\n- перше\n- друге\n")
    assert section.kind == "list"
    assert section.data == ["перше", "друге"]


def test_callout_from_quote(md):
    section, _ = one(md, "## Порада {#tip}\n\n> Скажіть про препарати.\n")
    assert section.kind == "callout"
    assert "препарати" in section.data


def test_prose_fallback(md):
    section, _ = one(md, "## Що це {#what}\n\nЗвичайний абзац тексту.\n")
    assert section.kind == "prose"
    assert "<p>" in section.data


def test_explicit_class_beats_autodetection(md):
    section, _ = one(md, "## Прапорці {#rf .alert}\n\n- перше\n- друге\n")
    assert section.kind == "alert-list"


def test_timeline_class_on_pairs(md):
    section, _ = one(
        md, "## Відновлення {#r .timeline}\n\nТиждень 1 | ходьба\nТиждень 2 | робота\n"
    )
    assert section.kind == "timeline"
    assert section.data[0]["key"] == "Тиждень 1"


def test_timeline_class_on_steps(md):
    section, _ = one(
        md, "## Відновлення {#r .timeline}\n\n1. **Тиждень 1.** ходьба\n2. **Тиждень 2.** робота\n"
    )
    assert section.kind == "timeline"
    assert section.data[0]["title"] == "Тиждень 1"


def test_unknown_class_warns_and_falls_back(md):
    section, warnings = one(md, "## Текст {#x .неведомый}\n\n- раз\n")
    assert section.kind == "list"
    assert any("неведомый" in w.message for w in warnings)


def test_class_that_does_not_fit_content_warns_and_goes_prose(md):
    section, warnings = one(md, "## Текст {#x .table}\n\nПросто абзац.\n")
    assert section.kind == "prose"
    assert any("не подходит" in w.message for w in warnings)


def test_broken_pair_line_does_not_break_the_build(md):
    section, _ = one(
        md, "## Коротко {#f}\n\nТривалість | 40 хвилин\nБез палочки\nСтаціонар | 1 доба\n"
    )
    assert section.kind == "facts"
    assert len(section.data) == 2


def test_step_body_is_rendered_markup(md):
    body = "## Как {#h}\n\n1. **Шаг.** Смотри [услуги](/services/) и **важное**\n"
    section, _ = one(md, body)
    assert section.kind == "steps"
    assert '<a href="/services/">' in section.data[0]["html"]
    assert "<strong>важное</strong>" in section.data[0]["html"]
