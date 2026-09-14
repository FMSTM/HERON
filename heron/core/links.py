"""Резолв связей: каталоги, переводы, крошки, меню и объявленные темой ссылки.

Перелинковка не пишется руками в контенте. Она выводится из полей и структуры
папок, поэтому не разъезжается при добавлении и удалении страниц.

Ядро не знает, что процедура «лечит» состояние. Оно знает, что тема объявила
поле `treats` со ссылками на страницы типа `condition`, умеет их найти,
проверить и построить обратную ссылку. Предметная область — в теме.

Спецификация: docs/spec/21-engine.md, раздел 4, этап 4.
"""

from __future__ import annotations

import re

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.errors import Collector
from heron.core.models import Page, Site


def _parent_url(url: str) -> str | None:
    if url == "/":
        return None
    trimmed = url.rstrip("/")
    head = trimmed.rsplit("/", 1)[0]
    return (head + "/") if head else "/"


def _sort_key(page: Page) -> tuple[int, str]:
    return (page.meta.order, page.h1.lower())


def _home_of(site: Site, lang: str, config: SiteConfig) -> Page | None:
    url = "/" if lang == config.site.default_lang else f"/{lang}/"
    return site.by_url.get(url)


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


HREF = re.compile(r'href="(/[^"]*)"')
NOT_A_PAGE = ("/img/", "/static/", "/assets/", "/media/")


def resolve(site: Site, config: SiteConfig, theme: ThemeConfig, collector: Collector) -> None:
    """Заполнить связи всех страниц. Ссылка в никуда останавливает сборку."""
    _families(site)
    _translations(site, config)
    _breadcrumbs(site, config)
    _declared(site, theme, collector)
    _nav(site, config, collector)
    localize(site, config, collector)


def localize(site: Site, config: SiteConfig, collector: Collector) -> None:
    """Подставить языковой префикс во внутренние ссылки контента.

    Ссылка от корня внутри страницы относительна её языку: `/services/x/`
    на русской странице ведёт на `/ru/services/x/`, на украинской — на
    `/services/x/`. Автор пишет адрес один раз, перевод копируется как есть
    и не требует переписывания ссылок.

    Иначе перевод страницы означает ручную правку каждой ссылки в ней,
    и одна забытая — битая ссылка в проде.

    Не трогаются: внешние адреса, `mailto:`, `tel:`, якоря, пути к картинкам
    и статике. И отдельно — `redirect_from` во фронтматтере: там лежат
    реальные старые адреса, они не относительны языку, они историчны.
    """
    default = config.site.default_lang

    for page in site.pages:
        if page.lang == default:
            continue

        def localized(match: re.Match, page: Page = page) -> str:
            href = match.group(1)
            if href.startswith(NOT_A_PAGE):
                return match.group(0)

            path, sep, tail = href.partition("#")
            path, query_sep, query = path.partition("?")
            candidate = f"/{page.lang}{path}"

            if candidate in site.by_url:
                return f'href="{candidate}{query_sep}{query}{sep}{tail}"'

            if path in site.by_url:
                other = site.by_url[path]
                collector.warn(
                    f"ссылка {path} ведёт на страницу языка {other.lang!r}: "
                    f"на {page.lang!r} этой страницы нет",
                    path=page.source,
                )
            return match.group(0)

        for section in (page.intro, *page.sections.values()):
            if section is not None and section.html:
                section.html = HREF.sub(localized, section.html)


def _families(site: Site) -> None:
    for page in site.pages:
        parent_url = _parent_url(page.url)
        parent = site.by_url.get(parent_url) if parent_url else None
        if parent is not None and parent is not page:
            page.parent = parent
            parent.children.append(page)
    for page in site.pages:
        page.children.sort(key=_sort_key)


def _translations(site: Site, config: SiteConfig) -> None:
    for page in site.pages:
        for lang in config.site.languages:
            if lang == page.lang:
                continue
            other = site.by_key.get((lang, page.key))
            if other is not None:
                page.translations[lang] = other


def _breadcrumbs(site: Site, config: SiteConfig) -> None:
    for page in site.pages:
        chain: list[Page] = []
        node = page.parent
        seen: set[str] = {page.url}
        while node is not None and node.url not in seen:
            chain.append(node)
            seen.add(node.url)
            node = node.parent
        chain.reverse()
        home = _home_of(site, page.lang, config)
        if home is not None and page is not home and (not chain or chain[0] is not home):
            chain.insert(0, home)
        page.breadcrumbs = chain


def _declared(site: Site, theme: ThemeConfig, collector: Collector) -> None:
    by_slug: dict[tuple[str, str], list[Page]] = {}
    for page in site.pages:
        by_slug.setdefault((page.lang, page.slug), []).append(page)

    for link in theme.links:
        for page in site.pages:
            slugs = _as_list(page.meta.extra.get(link.field))
            if not slugs:
                # Пустое поле — повод для замечания только там, где тема
                # сказала, каким страницам оно положено. Иначе движок
                # не знает, обязано ли оно быть, и молчит.
                if link.required and link.on and page.type == link.on:
                    collector.warn(
                        f"поле {link.field!r} не заполнено, а тема ждёт минимум {link.required}",
                        path=page.source,
                    )
                continue

            targets: list[Page] = []
            for slug in slugs:
                found = [
                    candidate
                    for candidate in by_slug.get((page.lang, slug), [])
                    if link.type is None or candidate.type == link.type
                ]
                if not found:
                    collector.error(
                        "E006",
                        f"{link.field}: страницы {slug!r} не существует"
                        + (f" среди страниц типа {link.type!r}" if link.type else ""),
                        path=page.source,
                        hint="проверьте слаг или уберите ссылку",
                    )
                    continue
                if len(found) > 1:
                    collector.error(
                        "E006",
                        f"{link.field}: слаг {slug!r} неоднозначен — "
                        + ", ".join(p.source for p in found),
                        path=page.source,
                        hint="уточните тип связи в theme.yaml или переименуйте страницу",
                    )
                    continue
                targets.append(found[0])

            page.related.setdefault(link.field, []).extend(targets)
            if link.back:
                for target in targets:
                    target.related.setdefault(link.back, []).append(page)

            if link.required and len(targets) < link.required:
                collector.warn(
                    f"{link.field}: ссылок {len(targets)}, тема ждёт минимум {link.required}",
                    path=page.source,
                )

    for page in site.pages:
        for name, items in page.related.items():
            unique: list[Page] = []
            seen: set[str] = set()
            for item in items:
                if item.url not in seen:
                    seen.add(item.url)
                    unique.append(item)
            page.related[name] = sorted(unique, key=_sort_key)


def _nav(site: Site, config: SiteConfig, collector: Collector) -> None:
    groups = config.nav.model_dump()
    for lang in config.site.languages:
        site.nav[lang] = {}
        for group, keys in groups.items():
            if not isinstance(keys, list):
                continue
            pages: list[Page] = []
            for key in keys:
                page = site.by_key.get((lang, str(key)))
                if page is None:
                    collector.warn(
                        f"меню {group!r}: нет страницы {key!r} на языке {lang!r}",
                        path="site.yaml",
                    )
                    continue
                pages.append(page)
            site.nav[lang][group] = pages
