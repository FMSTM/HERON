"""JSON-LD.

Ядро не знает, что страница процедуры размечается как `MedicalProcedure`.
Типы объявляет тема (`types.<тип>.jsonld`), значения организации приходят
из `site.yaml`, а страница может дополнить или переопределить всё блоком
`schema` во фронтматтере. Ядро строит то, что действительно знает:
адрес, язык, заголовок, описание, дату, хлебные крошки и вопросы-ответы.

Спецификация: docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

import json
from typing import Any

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.models import Page
from heron.core.urls import absolute


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


def build(page: Page, config: SiteConfig, theme: ThemeConfig) -> list[dict[str, Any]]:
    """Собрать граф разметки для страницы."""
    spec = theme.types.get(page.type)
    declared = list(spec.jsonld) if spec else []

    shared = config.extras.get("schema", {})
    shared = shared if isinstance(shared, dict) else {}
    own = page.meta.extra.get("schema", {})
    own = own if isinstance(own, dict) else {}

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
        graph.append(node)

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
