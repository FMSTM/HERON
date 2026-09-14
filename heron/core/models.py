"""Модели страницы и секции.

Парсер заполняет содержательную часть, резолв связей — родителей, детей,
переводы и крошки. Поэтому поля связей объявлены здесь, но остаются пустыми
до этапа 4 конвейера.

Спецификация: docs/spec/21-engine.md, раздел 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from heron.contracts.frontmatter import PageMeta


@dataclass(slots=True)
class Section:
    """Блок контента с идентификатором.

    `id` — адрес для темы, его не правят. `title` — заголовок, который увидит
    посетитель, его правят свободно. Разделение принципиальное.
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

    @property
    def is_empty(self) -> bool:
        return not self.raw.strip()


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

    def section(self, section_id: str) -> Section | None:
        return self.sections.get(section_id)

    def has(self, section_id: str) -> bool:
        section = self.sections.get(section_id)
        return section is not None and not section.is_empty

    @property
    def slug(self) -> str:
        return self.url.rstrip("/").rsplit("/", 1)[-1]

    @property
    def is_index(self) -> bool:
        return self.source.endswith("_index.md") or self.key == ""


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
