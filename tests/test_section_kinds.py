"""Все двенадцать форм секций: валидный ввод, битый ввод, порядок распознавания.

Спецификация: docs/spec/20-data-contract.md, раздел 4.4.
"""

import pytest

from heron.contracts.theme import KINDS, ThemeConfig
from heron.core.parser import blocks, markdown, sections


@pytest.fixture
def md():
    return markdown.make()


def one(md, body):
    _, found = sections.split(md, body, "a.md")
    warnings = blocks.apply(md, found)
    return next(iter(found.values())), warnings


def test_twelve_forms_and_classes_cover_them():
    assert len(KINDS) == 12
    assert set(blocks.BY_CLASS.values()) == set(KINDS)


# --- валидный ввод: по содержимому или по классу ------------------------------

VALID = {
    "prose": ("## A {#a}\n\nПросто текст.\n", None),
    "list": ("## A {#a}\n\n- раз\n- два\n", None),
    "alert-list": ("## A {#a .alert}\n\n- раз\n- два\n", None),
    "checklist": (
        "## A {#a}\n\n### Д\n- паспорт\n\n### Е\n- договір\n\n### Є\n- копія\n",
        None,
    ),
    "two-lists": ("## A {#a}\n\n### Так\n- раз\n\n### Ні\n- два\n", None),
    "steps": ("## A {#a}\n\n1. **Заявка.** Текст\n2. **Дзвінок.** Текст\n", None),
    "table": ("## A {#a}\n\n| Що | Де |\n|---|---|\n| а | б |\n", None),
    "facts": ("## A {#a}\n\nФормат | очно\nСтрок | 4 тижні\n", None),
    "faq": ("## A {#a}\n\n### Питання?\nВідповідь.\n\n### Ще?\nТак.\n", None),
    "timeline": ("## A {#a .timeline}\n\n1 день | вдома\n2 тижні | робота\n", None),
    "callout": ("## A {#a}\n\n> Порада.\n", None),
    "gallery": ("## A {#a .gallery}\n\n- ![a](media/a.png)\n- ![b](media/b.png)\n", None),
}


@pytest.mark.parametrize("kind", KINDS)
def test_valid_input(md, kind):
    body, _ = VALID[kind]
    section, warnings = one(md, body)
    assert section.kind == kind
    assert not warnings


def test_shapes_the_theme_gets(md):
    s, _ = one(md, VALID["facts"][0])
    assert s.data == [{"key": "Формат", "value": "очно"}, {"key": "Строк", "value": "4 тижні"}]
    s, _ = one(md, VALID["timeline"][0])
    assert s.data[0] == {"key": "1 день", "value": "вдома"}
    s, _ = one(md, VALID["table"][0])
    assert s.data == {"head": ["Що", "Де"], "rows": [["а", "б"]]}
    s, _ = one(md, VALID["faq"][0])
    assert s.data[0]["q"] == "Питання?" and "Відповідь" in s.data[0]["a"]
    s, _ = one(md, VALID["steps"][0])
    assert {k: s.data[0][k] for k in ("n", "title", "tag", "top")} == {
        "n": 1,
        "title": "Заявка",
        "tag": "",
        "top": True,
    }
    s, _ = one(md, VALID["two-lists"][0])
    assert [g["title"] for g in s.data] == ["Так", "Ні"]
    assert "items" in s.data[0] and "html" in s.data[0]
    s, _ = one(md, VALID["callout"][0])
    assert "Порада" in s.data
    s, _ = one(md, "## A {#a}\n\n- **Термін.** Пояснення\n- просто\n")
    assert s.data[0].term == "Термін" and s.data[1].term == ""


# --- битый ввод: класс не подходит к содержимому -> проза и предупреждение ---

BROKEN = {
    "list": "## A {#a .list}\n\nТекст без списку.\n",
    "alert-list": "## A {#a .alert}\n\nТекст без списку.\n",
    "checklist": "## A {#a .checklist}\n\nТекст без груп.\n",
    "two-lists": "## A {#a .two-lists}\n\n### Одна\nбез списку\n",
    "steps": "## A {#a .steps}\n\n- маркований, а не нумерований\n",
    "table": "## A {#a .table}\n\nне таблиця\n",
    "facts": "## A {#a .facts}\n\nрядок без розділювача\nще один\n",
    "faq": "## A {#a .faq}\n\nНемає заголовків третього рівня.\n",
    "timeline": "## A {#a .timeline}\n\nпросто текст\n",
    "callout": "## A {#a .callout}\n\nНемає цитати.\n",
    "gallery": "## A {#a .gallery}\n\nНемає списку.\n",
}


@pytest.mark.parametrize("kind", sorted(BROKEN))
def test_broken_input_falls_back_to_prose_with_warning(md, kind):
    section, warnings = one(md, BROKEN[kind])
    assert section.kind == "prose"
    assert any("не подходит" in w.message for w in warnings)


def test_prose_cannot_be_broken(md):
    section, warnings = one(md, "## A {#a .prose}\n\n- навіть список\n")
    assert section.kind == "prose" and not warnings


def test_unknown_class_warns_and_detects(md):
    section, warnings = one(md, "## A {#a .wat}\n\n- раз\n")
    assert section.kind == "list"
    assert any("неизвестный класс" in w.message for w in warnings)


def test_facts_skip_stray_lines_with_warning(md):
    section, warnings = one(md, "## A {#a}\n\nФормат | очно\nСтрок | 4\nзайвий рядок\n")
    assert section.kind == "facts" and len(section.data) == 2
    assert any("без разделителя" in w.message for w in warnings)


# --- порядок распознавания на неоднозначных секциях -------------------------


def test_order_table_before_facts(md):
    # и строки с «|», и строка-разделитель — это таблица
    section, _ = one(md, "## A {#a}\n\nа | б\n---|---\nв | г\n")
    assert section.kind == "table"


def test_facts_and_timeline_differ_only_by_class(md):
    body = "## A {{#a{}}}\n\n1 день | вдома\n"
    assert one(md, body.format(""))[0].kind == "facts"
    assert one(md, body.format(" .timeline"))[0].kind == "timeline"


def test_steps_before_groups(md):
    section, _ = one(md, "## A {#a}\n\n1. раз\n2. два\n\n### Г\n- x\n\n### Д\n- y\n")
    assert section.kind == "steps"


def test_two_groups_vs_three_groups(md):
    two = "## A {#a}\n\n### Г\n- x\n\n### Д\n- y\n"
    three = two + "\n### Е\n- z\n"
    assert one(md, two)[0].kind == "two-lists"
    assert one(md, three)[0].kind == "checklist"
    # класс сильнее числа групп
    assert one(md, two.replace("{#a}", "{#a .checklist}"))[0].kind == "checklist"


def test_groups_without_lists_are_faq(md):
    assert one(md, "## A {#a}\n\n### Г?\nтак\n")[0].kind == "faq"


def test_list_with_quote_stays_list(md):
    section, _ = one(md, "## A {#a}\n\n- раз\n- два\n\n> Порада до списку.\n")
    assert section.kind == "list"
    assert "Порада" in section.callout


def test_quote_alone_is_callout(md):
    assert one(md, "## A {#a}\n\nВступ.\n\n> Порада.\n")[0].kind == "callout"


# --- theme.yaml называет только существующие формы ---------------------------


def test_theme_uses_known_kind():
    ThemeConfig.model_validate({"name": "t", "types": {"page": {"uses": ["how:steps"]}}})


def test_theme_uses_unknown_kind_fails():
    with pytest.raises(ValueError, match="формы"):
        ThemeConfig.model_validate({"name": "t", "types": {"page": {"uses": ["how:stepz"]}}})
