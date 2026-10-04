"""Резолв связей: каталоги, переводы, крошки, меню и объявленные темой ссылки.

Перелинковка не пишется руками в контенте. Она выводится из полей и структуры
папок, поэтому не разъезжается при добавлении и удалении страниц.

Ядро не знает, что значит «услуга относится к направлению». Оно знает, что тема
объявила поле `topics` со ссылками на страницы типа `topic`, умеет их найти,
проверить и построить обратную ссылку. Предметная область — в теме.

Спецификация: docs/spec/21-engine.md, раздел 4, этап 4.
"""

from __future__ import annotations

import re

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.errors import Collector
from heron.core.models import Linked, Page, Pair, Site
from heron.core.parser import blocks


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


TAGS = re.compile(r"<[^>]+>")


def _as_links(value: object) -> list[tuple[str, str]]:
    """Поле связи: слаги, карты `{slug, note}` или и то и другое вперемешку.

    Подпись рядом со слагом нужна там, где карточка связи несёт не только
    название: «основной способ, когда сроки горят» пишется в том
    файле, где эта связь объявлена, а не в теме.
    """
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[tuple[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            slug = str(item.get("slug") or "").strip()
            if slug:
                out.append((slug, str(item.get("note") or "").strip()))
        elif item is not None:
            out.append((str(item).strip(), ""))
    return [pair for pair in out if pair[0]]


def _default_note(page: Page) -> str:
    """Подпись по умолчанию: обещание страницы, иначе её описание."""
    promise = page.intro.promise if page.intro else ""
    if promise:
        return TAGS.sub("", promise).strip()
    return page.meta.description or ""


HREF = re.compile(r'href="(/[^"]*)"')
NOT_A_PAGE = ("/img/", "/static/", "/assets/", "/media/")


def resolve(site: Site, config: SiteConfig, theme: ThemeConfig, collector: Collector) -> None:
    """Заполнить связи всех страниц. Ссылка в никуда останавливает сборку."""
    _families(site)
    _translations(site, config, collector)
    _breadcrumbs(site, config)
    _declared(site, theme, collector)
    _nav(site, config, collector)
    localize(site, config, collector)
    check(site, config, collector)


def _path_of(href: str) -> str:
    """Адрес без якоря и параметров, всегда со слешем на конце."""
    path = href.partition("#")[0].partition("?")[0]
    if not path or path.endswith("/"):
        return path
    return path + "/"


def _not_a_page(href: str) -> bool:
    """Ссылки, которые к страницам отношения не имеют и не трогаются.

    Файлы ресурсов (`/media/`, `/static/`, `/assets/`), адреса без схемы
    (`//cdn…`) и пути к файлам с расширением (`/llms.txt`, `/feed.xml`):
    слаг страницы точки не содержит, значит это не страница.
    """
    if href.startswith(NOT_A_PAGE) or href.startswith("//"):
        return True
    last = href.partition("#")[0].partition("?")[0].rstrip("/").rsplit("/", 1)[-1]
    return "." in last


def target(site: Site, config: SiteConfig, lang: str, href: str) -> tuple[Page | None, bool]:
    """Страница, на которую ведёт ссылка из текста страницы языка `lang`.

    Возвращает страницу и признак «перевода на `lang` нет, взята другая
    версия». Порядок поиска:

    1. **ключ** — путь от корня без слешей по краям: `/services/x/` это
       ключ `services/x`, `/` — ключ главной. Нашёлся ключ — берётся
       версия языка страницы; её нет — версия языка по умолчанию; нет и
       её — первая по порядку `languages`;
    2. **адрес в языке страницы** — тот же путь с её префиксом;
    3. **адрес как написан** — адрес языка по умолчанию или полный адрес
       с префиксом. Найденная страница чужого языка заменяется своей
       версией по ключу, если она есть.

    Ключ сильнее адреса: ключ не меняется при переименовании слага, адрес
    меняется.
    """
    path = _path_of(href)
    if not path:
        return None, False
    default = config.site.default_lang
    key = path.strip("/")

    own = site.by_key.get((lang, key))
    if own is not None:
        return own, False
    for other in (default, *config.site.languages):
        found = site.by_key.get((other, key))
        if found is not None:
            return found, True

    prefixed = path if lang == default else f"/{lang}{path}"
    found = site.by_url.get(prefixed) or site.by_url.get(path)
    if found is None:
        return None, False
    if found.lang == lang:
        return found, False
    own = site.by_key.get((lang, found.key))
    if own is not None:
        return own, False
    return found, True


def unresolved(site: Site, config: SiteConfig) -> list[tuple[str, int, str]]:
    """Ссылки текста, которым не соответствует ни одна страница сайта.

    Файлы ресурсов пропускаются: `/media/…` это не страница, и проверять
    его наличие — работа медиа-конвейера, а не перелинковки.
    """
    out: list[tuple[str, int, str]] = []
    for page in site.pages:
        for line, href in page.links:
            if _not_a_page(href) or not _path_of(href):
                continue
            if target(site, config, page.lang, href)[0] is None:
                out.append((page.source, line, href))
    return out


def check(site: Site, config: SiteConfig, collector: Collector) -> None:
    """Сказать про каждую ссылку в никуда: файл, строка, сама ссылка.

    Это предупреждение, а не ошибка: битая ссылка внутри текста не рушит
    сборку и не должна останавливать выкат остального сайта. Но молчать
    нельзя — руками написанный адрес переживает переименование раздела
    и ведёт на 404 до тех пор, пока на него кто-нибудь не нажмёт.
    """
    for source, line, href in unresolved(site, config):
        collector.warn(
            f"ссылка {href} никуда не ведёт",
            path=source,
            line=line,
            kind="ссылки",
        )


def _rewrite(value, replace):
    """Пройти по разобранным данным секции и переписать ссылки в строках.

    Пара «термин — пояснение» — это строка с полями, поэтому её нельзя
    подменять обычной строкой: тема потеряет и термин, и список ссылок.
    """
    if isinstance(value, Pair):
        html = HREF.sub(replace, str(value))
        return Pair(
            html,
            term=HREF.sub(replace, value.term),
            text=HREF.sub(replace, value.text),
            links=blocks.links_of(html),
        )
    if isinstance(value, str):
        return HREF.sub(replace, value)
    if isinstance(value, list):
        return [_rewrite(item, replace) for item in value]
    if isinstance(value, dict):
        out = {key: _rewrite(item, replace) for key, item in value.items()}
        if "links" in out and isinstance(out.get("text"), str):
            out["links"] = blocks.links_of(out["text"])
        return out
    return value


def localize(site: Site, config: SiteConfig, collector: Collector) -> None:
    """Привести внутренние ссылки контента к адресам языка страницы.

    Ссылка от корня внутри страницы относительна её языку. Автор пишет
    `/services/x/` один раз; на украинской странице это украинский адрес,
    на русской — русский, со своими слагами и префиксом. Перевод
    копируется как есть и не требует переписывания ссылок.

    Префикс к написанному пути не приклеивается: при разных слагах
    `/ru` + украинский путь — адрес, которого нет. Ссылка разбирается в
    страницу (см. `target`: сначала ключ, потом адрес), и подставляется
    адрес её версии на языке страницы. Перевода нет — адрес версии языка
    по умолчанию и предупреждение. Не нашлось ничего — ссылка остаётся
    как есть, о ней скажет `check` с номером строки.

    Якорь и параметры сохраняются. Не трогаются внешние адреса, `mailto:`,
    `tel:`, `/media/`, `/static/`, `/assets/`, пути к файлам и отдельно
    `redirect_from` во фронтматтере: там лежат реальные старые адреса,
    они не относительны языку, они историчны.
    """
    for page in site.pages:
        # Одна и та же ссылка живёт и в html секции, и в её разобранных
        # данных, поэтому замена проходит по ней дважды. Сказать об этом
        # два раза — значит удвоить список на ровном месте.
        said: set[str] = set()

        def localized(match: re.Match, page: Page = page, said: set[str] = said) -> str:
            href = match.group(1)
            if _not_a_page(href):
                return match.group(0)

            path, sep, tail = href.partition("#")
            path, query_sep, query = path.partition("?")
            if not path:
                return match.group(0)

            found, fallback = target(site, config, page.lang, href)
            if found is None:
                return match.group(0)  # про такую ссылку скажет `check`

            if fallback and path not in said:
                said.add(path)
                collector.warn(
                    f"ссылка {path}: на {page.lang!r} этой страницы нет, "
                    f"ведёт на версию {found.lang!r}",
                    path=page.source,
                    kind="ссылки",
                )
            return f'href="{found.url}{query_sep}{query}{sep}{tail}"'

        for section in (page.intro, *page.sections.values()):
            if section is None:
                continue
            if section.html:
                section.html = HREF.sub(localized, section.html)
            # Структурированные секции — списки, шаги, вопросы, таблицы —
            # хранят уже отрендеренные куски HTML, разобранные на этапе
            # парсинга. Ссылки живут и там
            section.data = _rewrite(section.data, localized)


def _families(site: Site) -> None:
    for page in site.pages:
        parent_url = _parent_url(page.url)
        parent = site.by_url.get(parent_url) if parent_url else None
        # Корень языка родителя не имеет: над /ru/ лежит не украинская
        # главная, а ничего. Иначе крошки уводят читателя в другой язык
        if parent is not None and parent.lang != page.lang:
            parent = None
        if parent is not None and parent is not page:
            page.parent = parent
            parent.children.append(page)
    for page in site.pages:
        page.children.sort(key=_sort_key)


def _translations(site: Site, config: SiteConfig, collector: Collector) -> None:
    default = config.site.default_lang
    default_filled = bool(site.of_lang(default))
    for page in site.pages:
        for lang in config.site.languages:
            if lang == page.lang:
                continue
            other = site.by_key.get((lang, page.key))
            if other is not None:
                page.translations[lang] = other
        # Страница есть только не на основном языке. Собирается она как
        # обычно, но у неё нет версии для x-default, а ссылки на её ключ с
        # других языков вести некуда. Когда основной язык пуст целиком,
        # об этом уже сказано одной строкой — повторять на каждой странице
        # незачем.
        if page.lang != default and default not in page.translations and default_filled:
            collector.warn(
                f"страница есть на {page.lang!r}, но нет на языке по умолчанию {default!r}",
                path=page.source,
                kind="переводы",
            )


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
    """Поля связей, объявленные темой: `related`, `topics` и прочие.

    Страница называется в них именем файла, а не адресом. Адрес задаётся
    слагом, слаги у языков разные, и индекс по адресу означал бы, что
    украинская страница и её русский перевод связаны с разными вещами —
    хотя связь описывает предмет, а не URL. Задание одного `slug` рвало
    все входящие связи разом.
    """
    by_name: dict[tuple[str, str], list[Page]] = {}
    for page in site.pages:
        by_name.setdefault((page.lang, page.name), []).append(page)

    for link in theme.links:
        for page in site.pages:
            slugs = _as_links(page.meta.extra.get(link.field))
            if not slugs:
                # Пустое поле — повод для замечания только там, где тема
                # сказала, каким страницам оно положено. Иначе движок
                # не знает, обязано ли оно быть, и молчит.
                if link.required and link.on and page.type == link.on:
                    collector.warn(
                        f"поле {link.field!r} не заполнено, а тема ждёт минимум {link.required}",
                        path=page.source,
                        kind="связи",
                    )
                continue

            targets: list[Linked] = []
            for name, note in slugs:
                found = [
                    candidate
                    for candidate in by_name.get((page.lang, name), [])
                    if link.type is None or candidate.type == link.type
                ]
                if not found:
                    collector.error(
                        "E006",
                        f"{link.field}: страницы {name!r} не существует"
                        + (f" среди страниц типа {link.type!r}" if link.type else ""),
                        path=page.source,
                        hint="страница называется именем своего файла без расширения, "
                        "а не адресом: slug на неё ничего здесь не меняет",
                    )
                    continue
                if len(found) > 1:
                    collector.error(
                        "E006",
                        f"{link.field}: имя {name!r} неоднозначно — "
                        + ", ".join(p.source for p in found),
                        path=page.source,
                        hint="уточните тип связи в theme.yaml или переименуйте файл",
                    )
                    continue
                if found[0] is page:
                    # Ссылка на себя ничего не связывает, а в карточках
                    # «смотрите также» выглядит как ошибка вёрстки.
                    collector.warn(
                        f"{link.field}: страница ссылается на саму себя ({name!r}), пропущено",
                        path=page.source,
                        kind="связи",
                    )
                    continue
                targets.append(Linked(found[0], note or _default_note(found[0])))

            page.related.setdefault(link.field, []).extend(targets)
            if link.back:
                for target in targets:
                    target.page.related.setdefault(link.back, []).append(
                        Linked(page, _default_note(page))
                    )

            if link.required and len(targets) < link.required:
                collector.warn(
                    f"{link.field}: ссылок {len(targets)}, тема ждёт минимум {link.required}",
                    path=page.source,
                    kind="связи",
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
                page = site.page(str(key), lang)
                if page is None:
                    # Страница есть на основном языке — значит это не опечатка
                    # в site.yaml, а непереведённый раздел. Разные беды: одну
                    # правят сейчас, вторую переводчик закроет когда-нибудь.
                    elsewhere = any(
                        site.page(str(key), other) is not None
                        for other in config.site.languages
                        if other != lang
                    )
                    if elsewhere:
                        collector.warn(
                            f"меню {group!r}: {key!r} ещё не переведено на {lang!r}",
                            path="site.yaml",
                            kind="нет перевода",
                        )
                    else:
                        collector.warn(
                            f"меню {group!r}: нет страницы {key!r} на языке {lang!r}",
                            path="site.yaml",
                            kind="меню",
                        )
                    continue
                pages.append(page)
            site.nav[lang][group] = pages
