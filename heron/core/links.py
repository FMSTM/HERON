"""Резолв связей: каталоги, переводы, крошки, меню и объявленные темой ссылки.

Перелинковка не пишется руками в контенте. Она выводится из полей и структуры
папок, поэтому не разъезжается при добавлении и удалении страниц.

Ядро не знает, что значит «услуга относится к направлению». Оно знает, что тема
объявила поле `topics` со ссылками на страницы типа `topic`, умеет их найти,
проверить и построить обратную ссылку. Предметная область — в теме.

Спецификация: docs/spec/21-engine.md, раздел 4, этап 4.
"""

from __future__ import annotations

import difflib
import re
from urllib.parse import parse_qsl, urlsplit

from heron.contracts.site import SiteConfig, parse_gone
from heron.contracts.theme import ThemeConfig
from heron.core.errors import Collector
from heron.core.models import Linked, Page, Pair, Site
from heron.core.parser import blocks
from heron.core.urls import canonical_path
from heron.messages import Msg


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
            Msg("links_unresolved", href=href),
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
        if "links" in out:
            source = out.get("html") if isinstance(out.get("html"), str) else out.get("text")
            if isinstance(source, str):
                out["links"] = blocks.links_of(source)
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
                    Msg("links_fallback", path=path, lang=page.lang, found=found.lang),
                    path=page.source,
                    kind="ссылки",
                )
            return f'href="{found.url}{query_sep}{query}{sep}{tail}"'

        for section in (page.intro, *page.sections.values()):
            if section is None:
                continue
            # Каждое представление секции — отдельно отрендеренный кусок:
            # подводка, примечание, врезка, обещание вступления. Переписать
            # только html значило оставить в них адреса чужого языка.
            # Каждое поле переписывается ровно один раз, из исходного вида.
            for name in ("html", "lead", "note", "callout", "promise"):
                value = getattr(section, name)
                if value:
                    setattr(section, name, HREF.sub(localized, value))
            # Структурированные секции — списки, шаги, вопросы, таблицы —
            # хранят уже отрендеренные куски HTML, разобранные на этапе
            # парсинга. Ссылки живут и там
            section.data = _rewrite(section.data, localized)
            # Список ссылок секции выводится из уже переписанного html, а не
            # переписывается второй раз: двойная замена превращала бы
            # локализованный адрес в адрес третьей страницы.
            section.links = blocks.links_of(section.html)


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
                Msg("links_no_default", lang=page.lang, default=default),
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
                        Msg("links_field_empty", field=link.field, required=link.required),
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
                        Msg(
                            "links_missing_page",
                            field=link.field,
                            name=name,
                            of_type=Msg("links_of_type", type=link.type) if link.type else "",
                        ),
                        path=page.source,
                        hint=Msg("links_missing_page_hint"),
                    )
                    continue
                if len(found) > 1:
                    collector.error(
                        "E006",
                        Msg(
                            "links_ambiguous",
                            field=link.field,
                            name=name,
                            sources=", ".join(p.source for p in found),
                        ),
                        path=page.source,
                        hint=Msg("links_ambiguous_hint"),
                    )
                    continue
                if found[0] is page:
                    # Ссылка на себя ничего не связывает, а в карточках
                    # «смотрите также» выглядит как ошибка вёрстки.
                    collector.warn(
                        Msg("links_self", field=link.field, name=name),
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
                    Msg(
                        "links_too_few",
                        field=link.field,
                        count=len(targets),
                        required=link.required,
                    ),
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
                            Msg("links_menu_untranslated", group=group, key=key, lang=lang),
                            path="site.yaml",
                            kind="нет перевода",
                        )
                    else:
                        collector.warn(
                            Msg("links_menu_missing", group=group, key=key, lang=lang),
                            path="site.yaml",
                            kind="меню",
                        )
                    continue
                pages.append(page)
            site.nav[lang][group] = pages


# --- старые адреса: heron check --old-urls ------------------------------------------


def _stem(path: str) -> str:
    return path.rstrip("/") or "/"


def _old_path(url: str) -> tuple[str, list[tuple[str, str]]]:
    """Путь и параметры старого адреса: относительного или абсолютного.

    Схема и хост отбрасываются, якорь серверу не приходит. Путь приводится
    к форме nginx (`canonical_path`): percent-encoding раскрыт, кириллица в NFC.
    Регистр сохраняется: `/About/` и `/about/` - разные адреса.
    """
    parts = urlsplit(url.strip())
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    return canonical_path(path)[0], parse_qsl(parts.query, keep_blank_values=True)


def _is_gone(path: str, query: list[tuple[str, str]], config: SiteConfig) -> bool:
    """Адрес закрыт записью `gone` из site.yaml (точной, префиксом или с параметром)."""
    for entry in config.gone:
        kind, gone_path, name, value = parse_gone(entry)
        gone_path = canonical_path(gone_path, slash=kind != "prefix")[0]
        if kind == "prefix":
            if path.startswith(gone_path):
                return True
        elif _stem(path) == _stem(gone_path):
            if kind == "exact":
                return True
            if any(k == name and (value is None or v == value) for k, v in query):
                return True
    return False


def resolve_old(url: str, site: Site, config: SiteConfig) -> Page | None:
    """Страница, на которую ведёт старый адрес, или None.

    Адрес «ведёт», если это адрес страницы или один из её `redirect_from`.
    Варианты, которые сервер считает одним адресом, сравниваются как равные:
    со слешем и без, `%XX` и кириллица. Языковой префикс вариантом НЕ
    считается: `/x/` и `/ru/x/` для nginx разные адреса, и редирект с
    `/ru/x/` старый `/x/` не обслуживает. Регистр - точное совпадение.
    Адрес из `gone` отвечает 410 и страницей не является: см. `is_old_gone`.
    """
    path, _ = _old_path(url)
    stem = _stem(path)
    for page in site.pages:
        if _stem(page.url) == stem:
            return page
    for page in site.pages:
        for written in page.meta.redirect_from:
            if _stem(canonical_path(written)[0]) == stem:
                return page
    return None


def old_key(url: str) -> str:
    """Старый адрес так, как его видит сервер: путь в форме nginx без конечного слеша.

    Параметры остаются в ключе: `gone` умеет закрывать адрес по параметру.
    """
    path, query = _old_path(url)
    tail = "&".join(f"{k}={v}" for k, v in query)
    return f"{_stem(path)}?{tail}" if tail else _stem(path)


def is_old_gone(url: str, config: SiteConfig) -> bool:
    path, query = _old_path(url)
    return _is_gone(path, query, config)


def _lang_of(path: str, config: SiteConfig) -> tuple[str, str]:
    """Язык по префиксу адреса и адрес без префикса."""
    default = config.site.default_lang
    for lang in config.site.languages:
        if lang != default and (path == f"/{lang}" or path.startswith(f"/{lang}/")):
            return lang, path[len(lang) + 1 :] or "/"
    return default, path


def suggest_target(url: str, site: Site, config: SiteConfig) -> Page:
    """Куда ставить 301: ближайшая страница по слагу и заголовку, иначе главная языка.

    Сравнивается последний сегмент старого адреса (без языкового префикса)
    со слагами и заголовками страниц; страницы языка адреса идут первыми.
    """
    path, _ = _old_path(url)
    lang, rest = _lang_of(path, config)
    wanted = rest.rstrip("/").rsplit("/", 1)[-1].lower()
    pool = [p for p in site.of_lang(lang) if not p.is_index and p.url != "/"]
    if wanted and pool:
        candidates: dict[str, Page] = {}
        for page in pool:
            candidates.setdefault(page.slug.lower(), page)
        for page in pool:
            candidates.setdefault(page.h1.lower(), page)
        found = difflib.get_close_matches(wanted.replace("_", "-"), list(candidates), 1, 0.6)
        if found:
            return candidates[found[0]]
    home = _home_of(site, lang, config)
    if home is None:
        home = site.by_url.get("/") or site.pages[0]
    return home
