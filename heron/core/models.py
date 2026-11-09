"""Модели страницы и секции.

Парсер заполняет содержательную часть, резолв связей — родителей, детей,
переводы и крошки. Поэтому поля связей объявлены здесь, но остаются пустыми
до этапа 4 конвейера.

Спецификация: docs/spec/21-engine.md, раздел 6.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any

from heron.contracts.frontmatter import PageMeta
from heron.core import paths

# Чужой адрес: своя схема или протокол-относительная ссылка.
EXTERNAL_URL = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:)?//", re.I)

# Картинка в markdown: `![alt](src)` или `![alt](<src> "title")`. Нужна только
# ради alt: сам путь находит `media.REFERENCE`, как у сборки.
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)")
# Что из путей текста годится в обложку: картинка, а не pdf и не ролик.
COVER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif")


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

    # Страница, которой нет в контенте: движок достроил её сам (404 без
    # файла). В подсчёт «есть ли у сайта страницы» она не идёт.
    generated: bool = False

    # Боевая сборка не публикует страницу вместе с её категорией: ключ категории,
    # у которой перевод на этот язык не готов (`translation: pending`).
    held_by: str | None = None

    # Поля, которых у файла языка нет и которые сборка взяла у основного языка:
    # обложка, картинка для соцсетей, свои поля типа с `translatable: true`
    # (`build.inherit`, 20 §4.2). Значения уже в `meta`, здесь - только имена.
    inherited: set[str] = field(default_factory=set)

    # Дата из истории или из времени файла: то, что движок выяснил сам.
    # Рядом с meta.updated, а не вместо него: по нему всегда видно,
    # что дату поставили руками. Из git — время коммита с его поясом,
    # из файла — день.
    auto_updated: date | datetime | None = None

    # Ссылки тела страницы как их написал автор: номер строки и адрес.
    # Хранятся от обхода, потому что в отрендеренном HTML строк уже нет.
    links: list[tuple[int, str]] = field(default_factory=list)

    parent: Page | None = None
    children: list[Page] = field(default_factory=list)
    translations: dict[str, Page] = field(default_factory=dict)
    breadcrumbs: list[Page] = field(default_factory=list)
    related: dict[str, list[Page]] = field(default_factory=dict)

    # Как узнать обложку: ставит окружение шаблонов (`env.context`), потому
    # что размеры и варианты есть только в плане нарезки. Не поставили —
    # обложки нет.
    cover_of: Callable[[Page], dict[str, Any] | None] | None = field(
        default=None, repr=False, compare=False
    )

    @property
    def title(self) -> str:
        return self.meta.title

    @property
    def updated(self) -> date | None:
        """Дата обновления страницы — одна на всех потребителей.

        Подпись под текстом, `lastmod` карты сайта и `dateModified`
        разметки обязаны говорить одно и то же: разъехавшись, они
        превращаются в три разных ответа на один вопрос.
        """
        value = self.meta.updated or self.auto_updated
        return value.date() if isinstance(value, datetime) else value

    @property
    def updated_at(self) -> datetime | None:
        """То же обновление — моментом времени с поясом, для машин.

        `dateModified`, `lastmod` и Atom требуют полную дату со временем
        и поясом. Время коммита идёт как есть, день без времени — полночь
        UTC: в Европе она уже прошла, так что дата не попадёт в будущее.
        """
        return moment(self.meta.updated or self.auto_updated)

    @property
    def date(self) -> date | None:
        """Дата публикации из фронтматтера. Нет поля — нет даты."""
        return self.meta.date

    @property
    def date_at(self) -> datetime | None:
        """Дата публикации моментом времени: полночь UTC."""
        return moment(self.meta.date)

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
        return self.meta.nav_title or self.name or self.h1

    @property
    def video(self) -> Video | None:
        """Ролик страницы или ничего. Нет поля — блок не рисуется."""
        src = (self.meta.video or "").strip()
        if not src:
            return None
        external = bool(EXTERNAL_URL.match(src))
        poster = (self.meta.video_poster or "").strip()
        return Video(
            src=src if external else f"/{paths.normalize(src)}",
            poster=""
            if not poster
            else (poster if EXTERNAL_URL.match(poster) else f"/{paths.normalize(poster)}"),
            title=(self.meta.video_title or "").strip(),
            external=external,
        )

    @property
    def cover(self) -> dict[str, Any] | None:
        """Обложка страницы: src, url, width, height, alt. Нет — None.

        Одна картинка питает og:image, twitter:image, primaryImageOfPage и
        карту сайта: разойдясь, эти места дают поисковику разные ответы.
        """
        return self.cover_of(self) if self.cover_of is not None else None

    def cover_source(self, config: Any) -> tuple[str, str] | None:
        """Источник обложки и её alt — по порядку, без чтения файлов.

        og_image, затем image фронтматтера, затем первая картинка в intro и
        в секции hero (по исходному тексту, до рендера), затем
        `seo.og_default_image` языка страницы. `config` — конфиг сайта;
        модель берёт из него только картинку по умолчанию и название.
        """
        meta = self.meta
        og_image = (meta.og_image or "").strip()
        if og_image:
            alt = meta.extra.get("og_image_alt") or meta.image_alt or ""
            return self._cover_path(og_image), str(alt)
        image = (meta.image or "").strip()
        if image:
            return self._cover_path(image), meta.image_alt or ""
        hero = self.sections.get("hero")
        for chunk in (self.intro.raw if self.intro else "", hero.raw if hero else ""):
            found = _text_image(chunk)
            if found is not None:
                return found
        local = config.for_lang(self.lang)
        default = (local.seo.og_default_image or "").strip()
        if default:
            return self._cover_path(default), local.site.name or ""
        return None

    @staticmethod
    def _cover_path(src: str) -> str:
        return src if EXTERNAL_URL.match(src) else paths.normalize(src)

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
        """Последний сегмент адреса. Это про URL, не про личность страницы."""
        return self.url.rstrip("/").rsplit("/", 1)[-1]

    @property
    def name(self) -> str:
        """Имя файла без расширения — короткое имя страницы.

        Им страница названа в полях связей: `related: [roof-repair]`.
        Адрес для этого не годится — он меняется вместе со слагом и
        разный в разных языках, а связь между теми же двумя страницами
        от этого не становится другой связью.
        """
        return self.key.rsplit("/", 1)[-1]

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
    # Страницы с пометкой `translation: pending`, которые боевая сборка не
    # публикует: их нет ни в `pages`, ни в меню, sitemap и hreflang (20 §4.2).
    held: list[Page] = field(default_factory=list)
    # Страницы с `published: false` (без `--drafts`): не собираются, но `check` сверяет
    # по ним общие поля языков - `published` тоже одно на все языки.
    unpublished: list[Page] = field(default_factory=list)

    def of_lang(self, lang: str) -> list[Page]:
        return [p for p in self.pages if p.lang == lang]

    def at(self, path: str) -> Page | None:
        """Страница по адресу в любой форме: `/x/` и `/x` - один адрес.

        Адреса сайта - в одной форме (`urls.trailing_slash`), а путь, по
        которому ищут, часто собран в другой: родитель из адреса ребёнка,
        ссылка из текста. Нашлась одна форма - другой у сайта нет.
        """
        found = self.by_url.get(path)
        if found is not None or not path or path == "/":
            return found
        return self.by_url.get(path[:-1] if path.endswith("/") else path + "/")

    def page(self, key: str, lang: str) -> Page | None:
        """Страница по ключу на языке.

        Ключ — путь папок плюс имя файла без расширения: `services`,
        `services/design`. Ключ главной — `/`. Слеши по краям не важны:
        `/services/` и `services` — один ключ, так его удобнее писать там
        же, где пишут ссылки.
        """
        return self.by_key.get((lang, str(key).strip("/")))

    def of_type(self, page_type: str, lang: str | None = None) -> list[Page]:
        return [p for p in self.pages if p.type == page_type and (lang is None or p.lang == lang)]


def _text_image(chunk: str) -> tuple[str, str] | None:
    """Первая картинка исходного текста секции и её alt из `![alt](src)`."""
    if not chunk:
        return None
    # media импортирует модели: импорт здесь, а не наверху модуля.
    from heron.core import media
    from heron.core.parser import markdown

    text = markdown.without_code(chunk)
    for match in media.REFERENCE.finditer(text):
        src = paths.normalize(match.group(1))
        if not src.lower().endswith(COVER_SUFFIXES):
            continue
        alt = next(
            (
                found.group(1).strip()
                for found in MARKDOWN_IMAGE.finditer(text)
                if paths.normalize(found.group(2)) == src
            ),
            "",
        )
        return src, alt
    return None


def moment(value: date | datetime | None) -> datetime | None:
    """День или время — в момент с поясом. День становится полночью UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.combine(value, time(0), tzinfo=UTC)


def stamp(value: date | datetime | None) -> str | None:
    """Полная дата для машин: `2026-10-17T11:30:12+02:00`."""
    found = moment(value)
    return found.isoformat(timespec="seconds") if found else None
