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

import json
import re
from typing import Any

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.models import Page
from heron.core.urls import absolute

# Подстановка целиком в значении: {{ contact.city }}. Внутри строки тоже
# работает, но тогда результат всегда строка.
HOLE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")

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
        if isinstance(node, (list, tuple)) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
            continue
        return None
    return node


def _fill(value: Any, data: dict[str, Any], lang: str) -> Any:
    """Подставить значения и выбросить то, для чего значений нет."""
    if isinstance(value, str):
        whole = HOLE.fullmatch(value.strip())
        if whole:
            # Подстановка на всё значение — отдаём как есть, числом или списком.
            return _at(data, whole.group(1), lang)
        if HOLE.search(value):
            missing = False

            def one(match: re.Match[str]) -> str:
                nonlocal missing
                found = _at(data, match.group(1), lang)
                if found is None:
                    missing = True
                    return ""
                return str(found)

            filled = HOLE.sub(one, value)
            return None if missing else filled
        return value
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            filled = _fill(item, data, lang)
            if filled not in (None, "", [], {}):
                out[key] = filled
        return out or None
    if isinstance(value, list):
        out_list = [_fill(item, data, lang) for item in value]
        out_list = [item for item in out_list if item not in (None, "", [], {})]
        return out_list or None
    return value


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
                "name": item.h1,
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


def entity(config: SiteConfig, lang: str) -> dict[str, Any] | None:
    """Сквозной узел сайта: врач, мастерская, магазин — что объявлено.

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
    node = _fill(declared, config.model_dump(), lang)
    if not isinstance(node, dict):
        return None
    if "@id" in node:
        node["@id"] = absolute(config, "/") + str(node["@id"]).lstrip("/")
    return node


def build(page: Page, config: SiteConfig, theme: ThemeConfig) -> list[dict[str, Any]]:
    """Собрать граф разметки для страницы."""
    spec = theme.types.get(page.type)
    declared = list(spec.jsonld) if spec else []

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

    graph: list[dict[str, Any]] = []
    for kind in declared:
        node: dict[str, Any] = {
            "@type": kind,
            "name": page.h1,
            "description": page.meta.description,
            "url": absolute(config, page.url),
            "inLanguage": page.lang,
        }
        if page.meta.updated:
            node["dateModified"] = page.meta.updated.isoformat()
        node = _merge(node, shared.get(kind, {}) if isinstance(shared.get(kind), dict) else {})
        node = _merge(node, own.get(kind, {}) if isinstance(own.get(kind), dict) else {})
        node = _fill(node, {**config.model_dump(), "page": page.meta.model_dump()}, page.lang)
        graph.append(node or {})

    # Сквозной узел — только там, где его увидит поисковик. На закрытой
    # от индексации странице разметка бессмысленна.
    if not page.meta.noindex:
        shared_entity = entity(config, page.lang)
        if shared_entity:
            graph.append(shared_entity)

    crumbs = breadcrumbs(page, config)
    if crumbs:
        graph.append(crumbs)
    questions = faq(page)
    if questions:
        graph.append(questions)

    return graph


def render(page: Page, config: SiteConfig, theme: ThemeConfig) -> str:
    """Готовый текст для `<script type="application/ld+json">`."""
    graph = build(page, config, theme)
    if not graph:
        return ""
    payload: dict[str, Any] = {"@context": "https://schema.org"}
    if len(graph) == 1:
        payload.update(graph[0])
    else:
        payload["@graph"] = graph
    return json.dumps(payload, ensure_ascii=False, indent=2)


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


def verify(page: Page, config: SiteConfig, theme: ThemeConfig, collector) -> list[str]:
    """Проверить разметку страницы. Возвращает типы узлов для отчёта.

    Разметку не видно глазами: она либо есть и верна, либо её нет, и узнают
    об этом из чужой панели вебмастера через месяц. Поэтому проверяется на
    сборке, а не после выката.
    """
    graph = build(page, config, theme)
    try:
        json.loads(render(page, config, theme) or "{}")
    except ValueError as error:
        collector.error(
            "E020", f"разметка страницы не разбирается как JSON: {error}", path=page.source
        )
        return []

    kinds = [str(node.get("@type")) for node in graph if node.get("@type")]

    spec = theme.types.get(page.type)
    for want in list(spec.jsonld) if spec else []:
        if want not in kinds:
            collector.error(
                "E020",
                f"тема ждёт разметку {want}, а в графе её нет",
                path=page.source,
                hint="проверьте блок schema в site.yaml и во фронтматтере страницы",
            )

    declared = config.extras.get("schema", {})
    declared = declared.get("entity") if isinstance(declared, dict) else None
    if isinstance(declared, dict) and declared and not page.meta.noindex:
        mark = str(declared.get("@id", ""))
        node = next((n for n in graph if str(n.get("@id", "")).endswith(mark)), None)
        if node is None:
            collector.error("E020", "нет сквозного узла сайта", path=page.source)
        else:
            address = node.get("address") or {}
            locality = address.get("addressLocality") if isinstance(address, dict) else None
            if not locality or not node.get("geo"):
                collector.error(
                    "E020",
                    "в сквозном узле нет адреса или координат",
                    path=page.source,
                    hint="заполните contact.city и contact.geo в site.yaml",
                )

    money = sorted({key for key in _keys(graph) if key.lower() in MONEY})
    if money:
        collector.error(
            "E020",
            "в разметке есть поля про деньги: " + ", ".join(money),
            path=page.source,
            hint="стоимость на сайте не публикуется — уберите эти поля из блока schema",
        )

    return kinds
