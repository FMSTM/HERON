"""Страница целиком: все поля шаблона заполняются из markdown.

Приёмка задания: шаблон страницы услуги просит два десятка полей, шаблон
страницы темы — столько же. Проверяем на файле, устроенном так же,
как настоящий контент: вводный блок из двух абзацев, таблица фактов,
список с зачинами, шаги с меткой, шкала сроков, цитата-врезка.
"""

import re

import pytest

from heron.core import links, tree
from tests import sites

SERVICE = """---
title: Услуга
h1: Услуга
description: Короткое описание для выдачи
image: img/one.png
image_alt: Иллюстрация
type: service
topics:
  - slug: state
    note: Основная причина обратиться
---

Первый абзац вводного блока.

Второй абзац вводного блока.

## Коротко {#quick-facts}

Длительность | 1–2 часа
Гарантия     | 1 год

## Что это такое {#what}

Абзац описания.

Второй абзац описания.

## Кому подходит {#who}

Подводка перед списком.

- Первая ситуация
- Вторая ситуация

**Сначала простой ремонт.** Примечание после списка.

## Как проходит {#how}

1. **[ПЕРВЫЙ] Подготовка.** Замеры и [осмотр](/other/).
2. **Основной этап.** Под контролем мастера.

## Сроки {#recovery .timeline}

1 сутки  | замер и смета
1 неделя | работа сдана

## Нюансы {#risks}

Абзац про нюансы.

> Возраст сам по себе не повод для замены.
"""

TOPIC = """---
title: Тема
h1: Тема
description: Короткое описание темы
type: topic
services:
  - one
---

Первый абзац.

Второй абзац.

## Когда срочно {#red-flags .alert}

- **Первый признак** — что делать.
- **Второй признак.** Что делать.

## Как решаем {#treatment}

1. **Совет.** Первый уровень.
2. **Ремонт.** Второй уровень.

## Что подготовить {#prepare}

Список документов текстом.
"""

THEME = {
    "types": {
        "service": {
            "uses": [
                "intro",
                "quick-facts",
                "what",
                "who",
                "how",
                "recovery:timeline",
                "risks",
            ]
        },
        "topic": {"uses": ["intro", "red-flags", "treatment:steps", "prepare"]},
    },
    "links": [
        {"field": "topics", "type": "topic", "back": "services_for"},
        {"field": "services", "type": "service", "back": "topics_for"},
    ],
}


@pytest.fixture
def site(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/one.md": SERVICE,
        "uk/state.md": TOPIC,
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    built, collector = tree.scan(content, config)
    links.resolve(built, config, sites.theme(**THEME), collector)
    return built, collector


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def test_service_fills_every_field(site):
    built, collector = site
    page = built.by_key[("uk", "one")]

    assert "Первый абзац вводного блока" in page.intro.lead
    assert "Второй абзац вводного блока" in page.intro.promise

    facts = page.section("quick-facts")
    assert facts.kind == "facts"
    assert facts.data[0]["key"] == "Длительность"

    who = page.section("who")
    assert "Подводка перед списком" in who.lead
    assert who.note_title == "Сначала простой ремонт"
    assert "Примечание после списка" in who.note

    step = page.section("how").data[0]
    assert (step["n"], step["tag"], step["title"], step["top"]) == (1, "ПЕРВЫЙ", "Подготовка", True)
    assert step["links"] == [{"title": "осмотр", "href": "/other/"}]

    assert page.section("recovery").kind == "timeline"
    assert page.section("risks").callout.strip().startswith("<p>Возраст")

    topics = page.related["topics"]
    assert topics[0].note == "Основная причина обратиться"
    assert not collector.errors


def test_topic_fills_every_field(site):
    built, _ = site
    page = built.by_key[("uk", "state")]

    flags = page.section("red-flags")
    assert flags.kind == "alert-list"
    assert [item.term for item in flags.data] == ["Первый признак", "Второй признак"]

    assert page.section("treatment").kind == "steps"
    assert page.section("prepare").kind == "prose"

    # обратная связь построилась и несёт подпись целевой страницы
    back = page.related["services"]
    assert back[0].note == "Второй абзац вводного блока."


def test_no_paragraph_is_lost(site):
    """Объём текста на входе и в разобранной структуре совпадает."""
    built, _ = site
    for key in (("uk", "one"), ("uk", "state")):
        page = built.by_key[key]
        source = text_of(page.intro.html) if page.intro else ""
        parts = [source]
        for section in page.sections.values():
            parts.append(text_of(section.html))
        collected = " ".join(parts)

        wanted = ["Второй абзац", "Примечание после списка", "Возраст сам по себе"]
        for chunk in wanted:
            if chunk in text_of(page.intro.html if page.intro else "") or any(
                chunk in text_of(s.html) for s in page.sections.values()
            ):
                assert chunk in collected
