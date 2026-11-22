"""JSON-LD.

Ядро не знает, каким типом schema.org размечается та или иная страница.
Типы объявляет тема (`types.<тип>.jsonld`), значения приходят из
`site.yaml`, а страница дополняет или переопределяет их блоком `schema`
во фронтматтере. Ядро строит то, что действительно знает: адрес, язык,
заголовок, описание, дату, хлебные крошки и вопросы-ответы.

Значения не дублируются руками: в блоке `schema` пишут подстановки вида
`{{ contact.city }}`, и движок берёт их из того же `site.yaml`, откуда их
берёт тема. Ключ с языковым хвостом ищется сам: на русской странице
`{{ contact.address }}` — это `address_ru`. Иначе адрес живёт в двух
местах и однажды расходится, а расхождение в разметке никто не видит
глазами.

Ключ, для которого значения нет, не выводится вовсе: пустое поле в
разметке хуже отсутствующего — поисковик считает его заявленным.

Спецификация: docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

from heron.contracts.frontmatter import PAGE_KEY
from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core import paths
from heron.core.models import Page, stamp
from heron.core.urls import absolute
from heron.messages import Msg

# Подстановка целиком в значении: {{ contact.city }}. Внутри строки тоже
# работает, но тогда результат всегда строка. Звенья пути - через точку;
# после `pages.` идёт ключ страницы по тому же правилу, что ключи и имена
# файлов (`PAGE_KEY`: сегменты с `-` и `_` через `/`), поэтому
# `{{ pages.about-us.url }}` и `{{ pages.services/roofing.url }}` - тоже
# подстановки. Раньше `-` и `/` не проходили, и значение молча пропадало.
_PART = r"[a-zA-Z0-9_.*]+"
HOLE = re.compile(rf"\{{\{{\s*(pages\.{PAGE_KEY}(?:\.{_PART})?|{_PART})\s*\}}\}}")

# Деньги в разметке этого движка не бывает по требованию сайта: цена не
# публикуется. Список — не забывчивость в данных, а запрет, поэтому
# проверяется на выходе, а не в момент записи конфига.
MONEY = (
    "offers",
    "price",
    "pricerange",
    "pricecurrency",
    "paymentaccepted",
    "lowprice",
    "highprice",
    "pricespecification",
)


def _at(data: Any, path: str, lang: str) -> Any:
    """Значение по пути `contact.city`, с языковым хвостом и индексами.

    `contact.address` на русской странице — это `address_ru`, если точного
    ключа нет. Так один и тот же блок `schema` работает для всех языков.
    """
    node = data
    for part in path.split("."):
        if isinstance(node, dict):
            # Сначала язык страницы, потом ключ без хвоста: `city_ru` — это
            # перевод `city`, а не что-то отдельное, и на русской странице
            # он должен побеждать.
            localized = f"{part}_{lang}"
            if localized in node:
                node = node[localized]
                continue
            if part in node:
                node = node[part]
                continue
            return None
        if isinstance(node, (list, tuple)):
            if part.isdigit() and int(part) < len(node):
                node = node[int(part)]
                continue
            if part == "*":
                # Список карт превращается в список значений: соцсети
                # объявлены один раз как {href, name}, а в разметку нужен
                # только href. Иначе их переписывают руками и забывают.
                # Список строк (`same_as: ["https://…"]`) и чисел остаётся
                # как есть: раньше `*` оставлял только карты, и ключ молча
                # пропадал из разметки.
                node = [item for item in node if isinstance(item, dict) or _scalar(item)]
                continue
            return None
        return None
    if isinstance(node, list) and node and all(isinstance(item, dict) for item in node):
        return node
    return node


def _scalar(item: Any) -> bool:
    """Строка или число - значение, которое `*` берёт из списка как есть."""
    return isinstance(item, (str, int, float)) and not isinstance(item, bool)


def _pluck(data: Any, path: str, lang: str) -> Any:
    """Значение по пути, где `*` разворачивает список.

    `contact.social.*.href` — список адресов из списка карт. Строка или
    число в том же списке - уже значение и берётся как есть.
    """
    if ".*." not in path:
        return _at(data, path, lang)
    head, tail = path.split(".*.", 1)
    items = _at(data, head, lang)
    if not isinstance(items, (list, tuple)):
        return None
    out = [item if _scalar(item) else _at(item, tail, lang) for item in items]
    out = [item for item in out if item not in (None, "")]
    return out or None


def _fill(
    value: Any,
    data: dict[str, Any],
    lang: str,
    dropped: list[tuple[str, str]] | None = None,
    at: str = "",
) -> Any:
    """Подставить значения и выбросить то, для чего значений нет.

    `dropped` собирает выброшенные из-за подстановки ключи: (путь ключа,
    подстановка). Выброшенное литеральное значение туда не попадает -
    пустое поле, написанное руками, не находка.
    """
    if isinstance(value, str):
        whole = HOLE.fullmatch(value.strip())
        if whole:
            # Подстановка на всё значение — отдаём как есть, числом или списком.
            got = _pluck(data, whole.group(1), lang)
            if got in (None, "", [], {}) and dropped is not None:
                dropped.append((at, value.strip()))
            return got
        if HOLE.search(value):
            missing = False

            def one(match: re.Match[str]) -> str:
                nonlocal missing
                found = _pluck(data, match.group(1), lang)
                if found is None:
                    missing = True
                    return ""
                return str(found)

            filled = HOLE.sub(one, value)
            if missing and dropped is not None:
                dropped.append((at, value.strip()))
            return None if missing else filled
        return value
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            filled = _fill(item, data, lang, dropped, f"{at}.{key}" if at else str(key))
            if filled not in (None, "", [], {}):
                out[key] = _year(str(key), filled)
        return out or None
    if isinstance(value, list):
        out_list = [
            _fill(item, data, lang, dropped, f"{at}.{i}" if at else str(i))
            for i, item in enumerate(value)
        ]
        out_list = [item for item in out_list if item not in (None, "", [], {})]
        return out_list or None
    return value


def _year(prop: str, value: Any) -> Any:
    """Год числом в свойстве-дате - строкой: 2011 → "2011".

    `since: 2011` в YAML - целое, и `foundingDate: "{{ organization.since }}"`
    отдаёт число. Дата в JSON-LD - строка ISO 8601, поэтому год выводится
    строкой. Какие свойства - даты, решает словарь schema.org (диапазон
    Date/DateTime без числового типа), а не список в коде; прочие числа
    остаются числами.
    """
    if prop.startswith("@"):
        return value
    from heron.schemaorg import vocab  # внутри: heron.schemaorg тянет heron.core

    v = vocab()
    if isinstance(value, list):
        return [str(item) if v.year_as_date(prop, item) else item for item in value]
    return str(value) if v.year_as_date(prop, value) else value


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def breadcrumbs(page: Page, config: SiteConfig) -> dict[str, Any] | None:
    if not page.breadcrumbs:
        return None
    items = [*page.breadcrumbs, page]
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": item.crumb_name,
                "item": absolute(config, item.url),
            }
            for index, item in enumerate(items, start=1)
        ],
    }


def faq(page: Page) -> dict[str, Any] | None:
    section = next((s for s in page.sections.values() if s.kind == "faq"), None)
    if section is None or not section.data:
        return None
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": pair["q"],
                "acceptedAnswer": {"@type": "Answer", "text": pair["a"]},
            }
            for pair in section.data
        ],
    }


# Типы-наследники WebPage: им добавляется primaryImageOfPage. До словаря
# schema.org в движке — списком; потом это проверка подтипа.
WEBPAGE_TYPES = frozenset(
    {
        "WebPage",
        "AboutPage",
        "CheckoutPage",
        "CollectionPage",
        "MediaGallery",
        "ImageGallery",
        "VideoGallery",
        "ContactPage",
        "FAQPage",
        "ItemPage",
        "MedicalWebPage",
        "ProfilePage",
        "QAPage",
        "RealEstateListing",
        "SearchResultsPage",
    }
)


def _cover(page: Page) -> dict[str, Any] | None:
    """Обложка страницы — та же, что у og:image (`page.cover`); нет — None.

    `page.cover` окружение шаблонов выставляет всем страницам сайта сразу,
    поэтому обложка соседа не зависит от порядка рендеринга.
    """
    got = getattr(page, "cover", None)
    return got if isinstance(got, dict) and got.get("url") else None


def _cover_data(cover: dict[str, Any] | None) -> dict[str, Any] | None:
    """Что из обложки доступно подстановкам: адрес и размеры."""
    if not cover:
        return None
    return {k: cover.get(k) for k in ("url", "width", "height")}


def _data(config: SiteConfig, lang: str, site=None) -> dict[str, Any]:
    """Что доступно подстановкам.

    Весь `site.yaml`, плюс две вещи, которых в нём нет и быть не может:
    базовый адрес сайта и адреса страниц по ключу. Без них узел сайта не
    может сослаться ни на страницу «о нас», ни на фотографию, и человек
    вписывает адрес руками — а он меняется вместе со слагом.
    """
    data = config.for_lang(lang).model_dump()
    data["site"] = {**(data.get("site") or {}), "base": absolute(config, "/")}
    if site is not None:
        pages: dict[str, Any] = {}
        for (page_lang, key), page in getattr(site, "by_key", {}).items():
            if page_lang != lang:
                continue
            entry = {
                "url": absolute(config, page.url),
                "title": page.meta.title,
                "description": page.meta.description,
                "h1": page.h1,
            }
            if page.meta.image:
                entry["image"] = absolute(config, "/" + paths.normalize(page.meta.image))
            cover_data = _cover_data(_cover(page))
            if cover_data:
                entry["cover"] = cover_data
            pages[key] = entry
        # В подстановке путь пишется через точки, и `/` в нём не напишешь,
        # поэтому главная доступна как `pages.home`. Это имя всегда за
        # главной: файл home.md в корне языка подстановкам недоступен.
        if "" in pages:
            pages["home"] = pages.pop("")
        data["pages"] = pages
    return data


def _related(page: Page, config: SiteConfig) -> dict[str, Any]:
    """Связи страницы для подстановок: `{{ related.topics.*.url }}`.

    Перечень связанных страниц уже собран движком по правилам темы.
    Переписывать те же ссылки руками во фронтматтере значит завести второй
    список, который разойдётся с первым на третьей правке.
    """
    out: dict[str, Any] = {}
    for field_name, targets in (page.related or {}).items():
        out[field_name] = [
            {
                "url": absolute(config, target.url),
                "h1": target.h1,
                "title": target.meta.title,
                "description": target.meta.description,
                "note": getattr(target, "note", ""),
            }
            for target in targets
        ]
    return out


def entity(
    config: SiteConfig, lang: str, site=None, dropped: list[tuple[str, str]] | None = None
) -> dict[str, Any] | None:
    """Сквозной узел сайта: человек, мастерская, магазин — что объявлено.

    Выводится на каждой индексируемой странице целиком, а не ссылкой:
    страницы независимы, и краулер не обязан сначала зайти на главную.
    `@id` один на весь сайт и на все языки — это одна сущность, а не три;
    различаются только языковые значения внутри.
    """
    shared = config.extras.get("schema", {})
    shared = shared if isinstance(shared, dict) else {}
    declared = shared.get("entity")
    if not isinstance(declared, dict) or not declared:
        return None
    node = _fill(declared, _data(config, lang, site), lang, dropped, "schema.entity")
    if not isinstance(node, dict):
        return None
    return _absolute_ids(node, config)


def _absolute_ids(node: Any, config: SiteConfig) -> Any:
    """Сделать якорные `@id` абсолютными.

    `"@id": "#owner"` внутри страницы — это не тот же адрес, что
    `#owner` на главной: относительный идентификатор разрешается от
    адреса документа, и на каждой странице получается своя сущность.
    Связь между узлами при этом молча распадается.
    """
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "@id" and isinstance(value, str) and value.startswith("#"):
                out[key] = absolute(config, "/") + value
            else:
                out[key] = _absolute_ids(value, config)
        return out
    if isinstance(node, list):
        return [_absolute_ids(item, config) for item in node]
    return node


def _may_have(kind: str, prop: str) -> bool:
    """Движок выводит базовое свойство, только если словарь разрешает его типу.

    Тип вне словаря не фильтруем: на него скажет SCH001 валидатор.
    """
    from heron.schemaorg import vocab  # внутри: heron.schemaorg тянет heron.core

    v = vocab()
    return v.allows(kind, prop) if v.is_type(kind) else True


def _is_article(kind: str) -> bool:
    """Article или его подтип (BlogPosting, NewsArticle, …) - по словарю, не списком."""
    from heron.schemaorg import vocab  # внутри: heron.schemaorg тянет heron.core

    v = vocab()
    return v.is_type(kind) and v.is_subtype(kind, "Article")


def _publisher_id(shared: dict[str, Any]) -> str | None:
    """`@id` сквозного узла сайта, если он организация или человек; иначе None.

    Своего `@id` по умолчанию у узла нет: без `@id` в `schema.entity`
    ссылаться не на что, и `publisher` не выводится.
    """
    from heron.schemaorg import vocab  # внутри: heron.schemaorg тянет heron.core

    declared = shared.get("entity")
    if not isinstance(declared, dict):
        return None
    mark = declared.get("@id")
    if not isinstance(mark, str) or not mark.strip():
        return None
    raw = declared.get("@type")
    types = [t for t in (raw if isinstance(raw, list) else [raw]) if isinstance(t, str)]
    v = vocab()
    if not any(
        v.is_type(t) and (v.is_subtype(t, "Organization") or v.is_subtype(t, "Person"))
        for t in types
    ):
        return None
    return mark.strip()


def _article_defaults(
    node: dict[str, Any], page: Page, cover: dict[str, Any] | None, shared: dict[str, Any]
) -> None:
    """Значения по умолчанию статьи: `headline`, `image`, `publisher`.

    Только то, что движок знает сам: заголовок страницы, её обложка (та же,
    что og:image) и ссылка на сквозной узел сайта. Автор - содержание, его
    движок не придумывает. Заданное темой, сайтом или страницей главнее -
    в том числе явное `null` или `""`: ключ есть, значение пустое, и
    `_fill` его выбросит (так значение по умолчанию выключают).
    """
    if "headline" not in node and page.h1:
        # Google не ограничивает длину headline (раньше - 110 символов):
        # заголовок идёт целиком.
        node["headline"] = page.h1
    if "image" not in node and cover:
        node["image"] = cover["url"]
    if "publisher" not in node:
        mark = _publisher_id(shared)
        if mark:
            # `#owner` станет абсолютным в _absolute_ids, как у самого узла.
            node["publisher"] = {"@id": mark}


def declared_kinds(
    page: Page, config: SiteConfig, theme: ThemeConfig
) -> tuple[list[str], list[str], dict[str, Any], dict[str, Any]]:
    """Типы разметки страницы: (от темы, все объявленные, свой блок, общий блок).

    Единственное место вычисления: порядок `declared` задаёт и граф build, и
    происхождение находок в heron.schemaorg.policy (по индексу узла).
    """
    spec = theme.types.get(page.type)
    from_theme = list(spec.jsonld) if spec else []
    declared = list(from_theme)

    shared = config.extras.get("schema", {})
    shared = shared if isinstance(shared, dict) else {}
    own = page.meta.extra.get("schema", {})
    own = own if isinstance(own, dict) else {}

    # Тип может объявить и сама страница: у неё свой блок `schema`, и тип
    # оттуда такой же настоящий, как объявленный темой. Иначе страница,
    # которая знает про себя больше типа, не может этого сказать.
    for kind in own:
        if kind != "entity" and isinstance(own[kind], dict) and kind not in declared:
            declared.append(kind)
    return from_theme, declared, own, shared


def _kind_class(kind: str) -> str:
    """Роль узла по словарю: website, page, article, subject или other (тип вне словаря)."""
    from heron.schemaorg import vocab  # внутри: heron.schemaorg тянет heron.core

    v = vocab()
    if not v.is_type(kind) or v.is_datatype(kind):
        return "other"
    if v.is_subtype(kind, "WebSite"):
        return "website"
    if v.is_subtype(kind, "WebPage"):
        return "page"
    if v.is_subtype(kind, "Article"):
        return "article"
    return "subject"


SUFFIXES = Path(__file__).resolve().parents[1] / "schemaorg" / "id-suffixes.json"


@functools.cache
def _suffixes() -> tuple[tuple[str, str], ...]:
    """Хвосты `@id` предметных узлов - данными словаря, не списком в коде.

    Какие типы schema.org - «предмет» и как их звать, решает таблица рядом
    со словарём (`heron/schemaorg/id-suffixes.json`): ядро предметной
    лексики не держит.
    """
    raw = json.loads(SUFFIXES.read_text(encoding="utf-8"))
    return tuple((str(base), str(tail)) for base, tail in raw["suffixes"])


def _suffix(kind: str) -> str:
    """Хвост `@id` предметного узла по таблице `id-suffixes.json`, иначе `<тип строчными>`."""
    from heron.schemaorg import vocab  # внутри: heron.schemaorg тянет heron.core

    v = vocab()
    for base, tail in _suffixes():
        if v.is_subtype(kind, base):
            return tail
    return kind.lower()


def _site_ref(config: SiteConfig, mark: str) -> str:
    """`#owner` - абсолютным адресом от корня сайта, как в _absolute_ids."""
    return absolute(config, "/") + mark if mark.startswith("#") else mark


# Последний вычисленный `@id` сайта: (сайт, конфиг, тема, значение). Сборка
# спрашивает его для каждой страницы, а ответ один на весь сайт.
_WEBSITE: list[tuple[Any, Any, Any, str | None]] = []


def _website_id(
    config: SiteConfig,
    theme: ThemeConfig,
    shared: dict[str, Any],
    own: dict[str, Any],
    site=None,
    page: Page | None = None,
) -> str | None:
    """`@id` узла WebSite, который сайт действительно выводит; нет такого - None.

    Решается по тем же правилам, по которым узлы попадают в граф (тема
    `types.<тип>.jsonld`, блок `schema` страницы), а `@id` - как у самого
    узла: блок `schema.WebSite` site.yaml и страницы, подстановки
    (`'{{ site.base }}#website'`), иначе `<корень>#website`. Страницы
    перебираются в одном порядке: главные по языкам `site.yaml`, затем
    остальные, - ответ не зависит от того, какая страница спросила. Явное
    `null` или `""` у `@id` - у этого узла идентификатора нет, ссылаться не
    на что. Без сайта (вызов на одной странице) смотрится только она.
    """
    if site is not None:
        for got_site, got_config, got_theme, value in _WEBSITE:
            if got_site is site and got_config is config and got_theme is theme:
                return value
        value = _find_website(config, theme, site, _site_order(config, site))
        _WEBSITE[:] = [(site, config, theme, value)]
        return value
    return _find_website(config, theme, None, [page] if page is not None else [])


def _site_order(config: SiteConfig, site) -> list[Page]:
    pages = list(getattr(site, "pages", []) or [])
    rank = {lang: i for i, lang in enumerate(config.site.languages)}
    homes = sorted((p for p in pages if p.key == ""), key=lambda p: rank.get(p.lang, len(rank)))
    return homes + [p for p in pages if p.key != ""]


def _find_website(config: SiteConfig, theme: ThemeConfig, site, pages: list[Page]) -> str | None:
    for candidate in pages:
        _t, declared, own, shared = declared_kinds(candidate, config, theme)
        for kind in declared:
            if _kind_class(kind) != "website":
                continue
            block: dict[str, Any] = {}
            for layer in (shared.get(kind), own.get(kind)):
                if isinstance(layer, dict):
                    block = _merge(block, layer)
            if "@id" not in block:
                return absolute(config, "/") + "#website"
            mark = block["@id"]
            if isinstance(mark, str) and HOLE.search(mark):
                data = {
                    **_data(config, candidate.lang, site),
                    "page": {
                        **candidate.meta.model_dump(),
                        "url": absolute(config, candidate.url),
                    },
                }
                mark = _fill(mark, data, candidate.lang)
            if isinstance(mark, str) and mark.strip():
                return _site_ref(config, mark.strip())
            # у этого узла идентификатора нет - ищем дальше
    return None


def _ref(node: dict[str, Any]) -> dict[str, str] | None:
    mark = node.get("@id")
    return {"@id": mark} if isinstance(mark, str) and mark else None


def build(
    page: Page,
    config: SiteConfig,
    theme: ThemeConfig,
    site=None,
    dropped: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Собрать граф разметки для страницы.

    `dropped` собирает ключи, выброшенные из-за пустой подстановки:
    (путь вида `schema.<тип>.<ключ>`, подстановка) - для предупреждения.

    Связи по умолчанию (0.3.1): у узла страницы `@id` - `<адрес>#webpage`, у
    WebSite - `<корень>#website`, у предметного узла - `<адрес>#service`,
    `#condition`, `#procedure` или `#<тип>`; страница - `isPartOf` сайта и
    `mainEntity`/`about` предметных узлов; WebSite и Service - `publisher` и
    `provider` сквозного узла. Заданное темой, сайтом или страницей главнее,
    явное `null` или `""` выключает значение по умолчанию.
    """
    _from_theme, declared, own, shared = declared_kinds(page, config, theme)

    cover = _cover(page)
    page_url = absolute(config, page.url)
    graph: list[dict[str, Any]] = []
    # Ключи, объявленные у узла до подстановок: явное null тоже ключ, и
    # значение по умолчанию на его место не встаёт.
    roles: list[tuple[str, str, dict[str, Any], set[str]]] = []
    used_ids: set[str] = set()
    # WebSite — это сайт, а не страница: его имя — название сайта на языке
    # страницы, а не h1 главной. Иначе поисковик подписывает сайт слоганом.
    site_name = config.for_lang(page.lang).site.name or config.site.domain
    alternate_names = config.for_lang(page.lang).site.alternate_names
    data = {
        **_data(config, page.lang, site),
        "page": {**page.meta.model_dump(), "cover": _cover_data(cover), "url": page_url},
        "related": _related(page, config),
    }
    first_page = True
    for kind in declared:
        role = _kind_class(kind)
        node: dict[str, Any] = {"@type": kind}
        if kind == "WebSite":
            node["name"] = site_name
        elif role == "subject":
            # Предмет страницы называется так, как его называет меню и крошки;
            # мета-описание написано для выдачи, предмету оно не описание.
            node["name"] = page.crumb_name
        else:
            node["name"] = page.h1
        if role != "subject":
            node["description"] = page.meta.description
        node["url"] = page_url
        if _may_have(kind, "inLanguage"):
            node["inLanguage"] = page.lang
        if kind == "WebSite" and alternate_names:
            node["alternateName"] = list(alternate_names)
        if page.date and _may_have(kind, "datePublished"):
            node["datePublished"] = stamp(page.date_at)
        if page.updated and _may_have(kind, "dateModified"):
            node["dateModified"] = stamp(page.updated_at)
        node = _merge(node, shared.get(kind, {}) if isinstance(shared.get(kind), dict) else {})
        node = _merge(node, own.get(kind, {}) if isinstance(own.get(kind), dict) else {})
        if _is_article(kind):
            _article_defaults(node, page, cover, shared)
        if "@id" not in node:
            if role == "website":
                node["@id"] = absolute(config, "/") + "#website"
            elif role in ("page", "article", "subject"):
                tail = "webpage" if role == "page" and first_page else _suffix(kind)
                mark = f"{page_url}#{tail}"
                if mark in used_ids:
                    mark = f"{page_url}#{kind.lower()}"
                n = 2
                while mark in used_ids:
                    mark = f"{page_url}#{kind.lower()}-{n}"
                    n += 1
                node["@id"] = mark
        if role == "page":
            first_page = False
        if isinstance(node.get("@id"), str):
            used_ids.add(node["@id"])
        # Картинка страницы для поисковика — та же обложка, что og:image.
        # Заданное сайтом или темой главнее; пустые размеры выбросит _fill.
        if kind in WEBPAGE_TYPES and cover and "primaryImageOfPage" not in node:
            node["primaryImageOfPage"] = {
                "@type": "ImageObject",
                "url": cover["url"],
                "width": cover.get("width"),
                "height": cover.get("height"),
                "caption": cover.get("alt"),
            }
        keys = set(node)
        node = _fill(node, data, page.lang, dropped, f"schema.{kind}")
        node = _absolute_ids(node or {}, config)
        roles.append((kind, role, node, keys))
        graph.append(node)

    _link(page, config, theme, shared, own, roles, site)

    # 404 - не страница сайта для поисковика: ни крошек, ни сквозного узла.
    lost = page.type == NOT_FOUND
    # Сквозной узел — только там, где его увидит поисковик. На закрытой
    # от индексации странице разметка бессмысленна.
    if not page.meta.noindex and not lost:
        shared_entity = entity(config, page.lang, site, dropped)
        if shared_entity:
            graph.append(shared_entity)

    crumbs = None if lost else breadcrumbs(page, config)
    if crumbs:
        graph.append(crumbs)
    questions = None if _faq_off(shared, own) else faq(page)
    if questions:
        questions["url"] = page_url
        questions["inLanguage"] = page.lang
        website = _website_id(config, theme, shared, own, site, page)
        if website:
            questions["isPartOf"] = {"@id": website}
        graph.append(questions)

    return graph


NOT_FOUND = "404"


def _faq_off(shared: dict[str, Any], own: dict[str, Any]) -> bool:
    """`schema: {FAQPage: null}` (или `false`) страницы или сайта - без FAQPage из секции."""
    for block in (own, shared):
        if "FAQPage" in block and block["FAQPage"] in (None, False, "", {}):
            return True
    return False


def _link(page, config, theme, shared, own, roles, site=None) -> None:
    """Связать узлы страницы между собой и с сайтом (ссылки `{"@id": …}`)."""
    website = _website_id(config, theme, shared, own, site, page)
    owner = _publisher_id(shared)
    owner_ref = {"@id": _site_ref(config, owner)} if owner else None
    # Предмет страницы - любой узел из словаря, который не страница и не сайт:
    # Service, предметные типы, SoftwareApplication, Product, Event и статья
    # (Article и подтипы, 0.3.2) - то, о чём страница. Порядок - порядок
    # объявления: первый - mainEntity, остальные - about.
    subjects = [_ref(node) for _k, role, node, _ in roles if role in ("subject", "article")]
    subjects = [ref for ref in subjects if ref]
    from heron.schemaorg import vocab  # внутри: heron.schemaorg тянет heron.core

    v = vocab()
    for kind, role, node, keys in roles:
        if not node:
            continue
        if role == "page":
            if website and "isPartOf" not in keys and _may_have(kind, "isPartOf"):
                node["isPartOf"] = {"@id": website}
            if subjects and "mainEntity" not in keys and _may_have(kind, "mainEntity"):
                node["mainEntity"] = subjects[0]
                rest = subjects[1:]
                if rest and "about" not in keys and _may_have(kind, "about"):
                    node["about"] = rest[0] if len(rest) == 1 else rest
        elif role == "website":
            if owner_ref and "publisher" not in keys and _may_have(kind, "publisher"):
                node["publisher"] = dict(owner_ref)
        elif role == "subject" and v.is_subtype(kind, "Service"):
            if owner_ref and "provider" not in keys and _may_have(kind, "provider"):
                node["provider"] = dict(owner_ref)


def render(page: Page, config: SiteConfig, theme: ThemeConfig, site=None) -> str:
    """Готовый текст для `<script type="application/ld+json">`."""
    graph = build(page, config, theme, site)
    if not graph:
        return ""
    payload: dict[str, Any] = {"@context": "https://schema.org"}
    if len(graph) == 1:
        payload.update(graph[0])
    else:
        payload["@graph"] = graph
    return safe_json(payload)


# Что нельзя оставить как есть внутри <script>. `</script>` в строке закрывает
# тег — дальше браузер исполняет то, что написал автор поля. `<!--` и `<script`
# переключают разборщик в режимы, где закрывающий тег ищется иначе. `&` — ради
# XHTML-разборщиков. U+2028 и U+2029 — разрывы строки для старых движков JS.
# Экранирование JSON-ом же (`\u003c`) оставляет данные теми же для любого
# разборщика JSON: строка «</script>» читается обратно буква в букву.
_UNSAFE = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", "\u2028": "\\u2028", "\u2029": "\\u2029"}


def safe_json(payload: Any) -> str:
    """JSON, который можно вставить в `<script>` без выхода из него."""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return "".join(_UNSAFE.get(char, char) for char in text)


def _keys(node: Any) -> list[str]:
    """Все ключи структуры, на любой глубине."""
    if isinstance(node, dict):
        out = list(node)
        for value in node.values():
            out.extend(_keys(value))
        return out
    if isinstance(node, list):
        out = []
        for value in node:
            out.extend(_keys(value))
        return out
    return []


def _declared_at(block: Any, path: list[str]) -> Any:
    """Значение блока по пути `a.b.0` (как пишет `_fill`), нет - None."""
    node = block
    for part in path:
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
    return node


def _warn_dropped(page: Page, collector, dropped: list[tuple[str, str]]) -> None:
    """Предупредить о ключах разметки, которые выбросила пустая подстановка.

    `sameAs: "{{ organization.same_as.* }}"` над пустым списком или
    `{{ contact.phone }}` без телефона в site.yaml - ключ молча пропадает
    из разметки, и узнают об этом только из панели вебмастера. Это не
    ошибка: данных может не быть по делу. И не предупреждение: сведение
    (`collector.note`), его не считает `--strict` - сайт, который собирался
    на прежнем движке, от новой находки не краснеет. Источник - тот, где подстановка
    написана: блок страницы или site.yaml; одно и то же из site.yaml
    называется один раз, а не на каждой странице.
    """
    if not dropped:
        return
    own = page.meta.extra.get("schema", {})
    own = own if isinstance(own, dict) else {}
    for key, hole in dropped:
        parts = key.split(".")
        declared = _declared_at(own, parts[1:]) if parts[:1] == ["schema"] else None
        in_page = isinstance(declared, str) and declared.strip() == hole
        source = str(page.source) if in_page else "site.yaml"
        message = Msg("markup_placeholder_empty", key=key, hole=hole, lang=page.lang)
        if any(w.message == message and w.path == source for w in collector.notes):
            continue
        collector.note(message, path=source, kind="разметка")


def verify(
    page: Page, config: SiteConfig, theme: ThemeConfig, collector, site=None, schema_check=None
) -> list[str]:
    """Проверить разметку страницы. Возвращает типы узлов для отчёта.

    Разметку не видно глазами: она либо есть и верна, либо её нет, и узнают
    об этом из чужой панели вебмастера через месяц. Поэтому проверяется на
    сборке, а не после выката.
    """
    dropped: list[tuple[str, str]] = []
    graph = build(page, config, theme, site, dropped)
    _warn_dropped(page, collector, dropped)
    try:
        json.loads(render(page, config, theme, site) or "{}")
    except ValueError as error:
        collector.error("E020", Msg("markup_json_unparsable", error=error), path=page.source)
        return []

    kinds = [str(node.get("@type")) for node in graph if node.get("@type")]

    spec = theme.types.get(page.type)
    for want in list(spec.jsonld) if spec else []:
        if want not in kinds:
            collector.error(
                "E020",
                Msg("markup_theme_expects", want=want),
                path=page.source,
                hint=Msg("markup_theme_expects_hint"),
            )

    declared = config.extras.get("schema", {})
    declared = declared.get("entity") if isinstance(declared, dict) else None
    if isinstance(declared, dict) and declared and not page.meta.noindex and page.type != NOT_FOUND:
        mark = str(declared.get("@id", ""))
        shared_node = entity(config, page.lang, site)
        if mark and shared_node is not None:
            # По равенству со сквозным узлом, а не по хвосту `@id`: у узлов
            # страницы теперь свои `@id` (`…#service`), и хвост мог бы совпасть.
            node = next((n for n in graph if n == shared_node), None)
        elif mark:
            node = next((n for n in graph if str(n.get("@id", "")).endswith(mark)), None)
        else:
            # Без @id узел ищем по равенству со сквозным узлом сайта,
            # а не по пустому суффиксу, которому подходит любой первый узел.
            node = next((n for n in graph if shared_node is not None and n == shared_node), None)
        if node is None:
            collector.error("E020", Msg("markup_no_entity"), path=page.source)
        else:
            # Адрес и координаты проверяются, только если узел их объявил:
            # объявленное, но пустое — это данные, которые забыли заполнить,
            # и подстановка молча выбросила ключ. Узел без адреса вовсе —
            # сайт без офиса, это не ядру решать.
            address = node.get("address") or {}
            locality = address.get("addressLocality") if isinstance(address, dict) else None
            wants_address = isinstance(declared.get("address"), dict) and (
                "addressLocality" in declared["address"]
            )
            geo = node.get("geo")
            geo_empty = not geo or (
                isinstance(geo, dict) and not (geo.get("latitude") and geo.get("longitude"))
            )
            if (wants_address and not locality) or ("geo" in declared and geo_empty):
                collector.error(
                    "E020",
                    Msg("markup_entity_empty"),
                    path=page.source,
                    hint=Msg("markup_entity_empty_hint"),
                )

    if not config.seo.allow_prices:
        money = sorted({key for key in _keys(graph) if key.lower() in MONEY})
        if money:
            collector.error(
                "E020",
                Msg("markup_money", fields=", ".join(money)),
                path=page.source,
                hint=Msg("markup_money_hint"),
            )

    if schema_check is not None:
        schema_check.page(page, graph, config, theme)

    return kinds
