"""Модели страницы и секции.

Парсер заполняет содержательную часть, резолв связей — родителей, детей,
переводы и крошки. Поэтому поля связей объявлены здесь, но остаются пустыми
до этапа 4 конвейера.

Спецификация: docs/spec/21-engine.md, раздел 6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from heron.contracts.frontmatter import PageMeta

# Чужой адрес: своя схема или протокол-относительная ссылка.
EXTERNAL_URL = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:)?//", re.I)


class Pair(str):
    """Пункт списка вида `**Термин.** Пояснение`.

    Значение строки — html пункта целиком, поэтому тема, написанная до
    этого правила (`{{ item|safe }}`), продолжает работать. Разобранные
    части доступны атрибутами: `term`, `text`, `links`.
    """

    __slots__ = ("term", "text", "links")

    def __new__(cls, html: str, term: str = "", text: str = "", links: Any = None):
        item = super().__new__(cls, html)
        item.term = term
        item.text = text
        item.links = links or []
        return item


@dataclass(slots=True)
class Section:
    """Блок контента с идентификатором.

    `id` — адрес для темы, его не правят. `title` — заголовок, который увидит
    посетитель, его правят свободно. Разделение принципиальное.

    Секция приезжает в тему разобранной: подводка до основного узла,
    сам узел, примечание после него и цитата-врезка. Макет рисует их
    по-разному, поэтому склеенный кусок html темe не годится.
    """

    id: str
    title: str
    level: int
    classes: list[str] = field(default_factory=list)
    raw: str = ""
    html: str = ""
    kind: str = "prose"
    data: Any = None
    line: int | None = None

    lead: str = ""
    note: str = ""
    note_title: str = ""
    callout: str = ""
    promise: str = ""
    links: list[dict[str, str]] = field(default_factory=list)

    @property
    def body(self) -> Any:
        """Основной узел секции: разобранные данные или проза."""
        return self.html if self.data is None else self.data

    @property
    def is_empty(self) -> bool:
        return not self.raw.strip()


@dataclass(frozen=True, slots=True)
class Video:
    """Ролик страницы — готовым объектом, а не тремя полями фронтматтера.

    Тема не должна разбирать схемы адресов: сегодня это ютуб, завтра свой
    файл, послезавтра третий хостинг, и каждая тема учила бы это заново.
    Движок решает один раз и отдаёт готовое.
    """

    src: str
    poster: str = ""
    title: str = ""
    external: bool = False

    def __bool__(self) -> bool:
        return bool(self.src)


@dataclass(slots=True)
class Page:
    """Страница сайта."""

    lang: str
    source: str
    key: str
    meta: PageMeta
    sections: dict[str, Section] = field(default_factory=dict)
    intro: Section | None = None

    url: str = ""
    type: str = "page"

    parent: Page | None = None
    children: list[Page] = field(default_factory=list)
    translations: dict[str, Page] = field(default_factory=dict)
    breadcrumbs: list[Page] = field(default_factory=list)
    related: dict[str, list[Page]] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.meta.title

    @property
    def h1(self) -> str:
        return self.meta.h1

    @property
    def nav_title(self) -> str:
        """Как страница называется в меню и хлебных крошках.

        Объявлено — берём объявленное. Не объявлено — имя файла: на
        одноязычном сайте с человеческими именами файлов этого хватает,
        и заполнять ничего не нужно.
        """
        return self.meta.nav_title or self.slug or self.h1

    @property
    def video(self) -> Video | None:
        """Ролик страницы или ничего. Нет поля — блок не рисуется."""
        src = (self.meta.video or "").strip()
        if not src:
            return None
        external = bool(EXTERNAL_URL.match(src))
        poster = (self.meta.video_poster or "").strip()
        return Video(
            src=src if external else f"/{src.lstrip('./')}",
            poster=""
            if not poster
            else (poster if EXTERNAL_URL.match(poster) else f"/{poster.lstrip('./')}"),
            title=(self.meta.video_title or "").strip(),
            external=external,
        )

    def section(self, section_id: str) -> Section | None:
        """Секция по идентификатору.

        `intro` живёт отдельным полем, потому что у него нет заголовка,
        но для темы и для отчёта это такая же секция, как остальные.
        """
        if section_id == "intro" and self.intro is not None:
            return self.intro
        return self.sections.get(section_id)

    def has(self, section_id: str) -> bool:
        section = self.section(section_id)
        return section is not None and not section.is_empty

    @property
    def slug(self) -> str:
        return self.url.rstrip("/").rsplit("/", 1)[-1]

    @property
    def is_index(self) -> bool:
        return self.source.endswith("_index.md") or self.key == ""


@dataclass(slots=True)
class Linked:
    """Страница в поле связи, с подписью.

    Тема обращается к ней как к обычной странице — `url`, `h1`, `nav_title`
    доезжают до неё насквозь, — а `note` добавляет подпись, которую автор
    написал рядом со слагом или которую движок взял со страницы-цели.
    """

    page: Page
    note: str = ""

    def __getattr__(self, name: str) -> Any:
        return getattr(self.page, name)


@dataclass(slots=True)
class Site:
    """Сайт целиком: страницы, справочники, меню."""

    pages: list[Page] = field(default_factory=list)
    by_url: dict[str, Page] = field(default_factory=dict)
    by_key: dict[tuple[str, str], Page] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    nav: dict[str, dict[str, list[Page]]] = field(default_factory=dict)

    def of_lang(self, lang: str) -> list[Page]:
        return [p for p in self.pages if p.lang == lang]

    def of_type(self, page_type: str, lang: str | None = None) -> list[Page]:
        return [p for p in self.pages if p.type == page_type and (lang is None or p.lang == lang)]
