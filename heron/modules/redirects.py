"""Карта редиректов и список адресов, которых больше нет.

Единственное, что защищает индекс при переезде. Старый адрес пишется рядом
с новым контентом, во фронтматтере страницы (`redirect_from`), а не в
отдельной таблице, которая разъедется с сайтом на второй неделе.

Отдельно от 301 живёт 410 (`gone` в `site.yaml`): архивы, служебные пути
старой системы, дорвеи после взлома. Страницы у них нет и не будет, поэтому
и места у них нет нигде, кроме конфига сайта. Притворяться, что они временно
недоступны, смысла нет.

Обе карты уезжают в конфиг nginx, который движок собирает вместе с сайтом:
301 и 410 отдаются до обращения к файлам.

Спецификация: docs/spec/20-data-contract.md, разделы 2 и 5;
docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from heron.contracts.site import SiteConfig, parse_gone
from heron.core.errors import Collector
from heron.core.models import Site
from heron.core.urls import canonical_path


@dataclass(slots=True)
class Plan:
    """Всё, что сервер должен ответить до обращения к файлам."""

    moved: dict[str, str] = field(default_factory=dict)  # старый адрес → новый
    gone: list[str] = field(default_factory=list)  # точные адреса
    gone_prefixes: list[str] = field(default_factory=list)  # всё, что начинается с
    gone_queries: list[tuple[str, str, str | None]] = field(default_factory=list)
    # (путь, параметр, значение или None — любое значение)
    raw: set[str] = field(default_factory=set)
    # адреса, которые после декодирования не текст (слаг обрезан посреди
    # буквы): их сверяют с сырым адресом запроса, а не с `$uri`


def _covers(prefix: str, url: str) -> bool:
    return url.startswith(prefix)


def collect(site: Site, collector: Collector, config: SiteConfig | None = None) -> Plan:
    """Собрать карту 301 и список 410, проверив их друг против друга и против сайта."""
    plan = Plan()
    owner: dict[str, str] = {}

    for page in site.pages:
        for written in page.meta.redirect_from:
            old, ok = canonical_path(written)
            if not ok:
                plan.raw.add(old)
            if old in site.by_url:
                collector.error(
                    "E009",
                    f"redirect_from {written!r} совпадает с существующим адресом {old}",
                    path=page.source,
                    hint="страница по этому адресу уже есть, редирект перекрыл бы её",
                )
                continue
            if old in plan.moved and plan.moved[old] != page.url:
                collector.error(
                    "E009",
                    f"{written!r} ведёт сразу в два места: {plan.moved[old]} и {page.url}",
                    path=page.source,
                    hint=f"первый раз объявлен в {owner[old]}",
                )
                continue
            plan.moved[old] = page.url
            owner[old] = page.source

    for old, target in plan.moved.items():
        if target in plan.moved:
            collector.error(
                "E009",
                f"цепочка редиректов: {old} ведёт на {target}, который сам перенаправляется",
                path=owner[old],
                hint="направьте сразу на конечный адрес",
            )

    # Источники 410: ключ `gone` в site.yaml и — по старой памяти — поле
    # `gone` на странице. Второе устарело: у адреса, которого больше нет,
    # нет и страницы, к которой его честно было бы приписать.
    entries: list[tuple[str, str]] = [
        (entry, "site.yaml") for entry in (config.gone if config else [])
    ]
    for page in site.pages:
        if page.meta.gone:
            collector.warn(
                "поле gone на странице устарело: перенесите адреса в gone в site.yaml",
                path=page.source,
                kind="прочее",
            )
            entries += [(entry, page.source) for entry in page.meta.gone]

    seen: set[tuple[str, str, str, str | None]] = set()
    for entry, source in entries:
        kind, path, name, value = parse_gone(entry)
        path, ok = canonical_path(path, slash=kind != "prefix")
        if (kind, path, name, value) in seen:
            collector.warn(f"gone: {entry!r} указан дважды", path=source, kind="прочее")
            continue
        seen.add((kind, path, name, value))
        if not ok:
            plan.raw.add(path)
        if kind == "query":
            plan.gone_queries.append((path, name, value))
            continue

        if kind == "prefix":
            hit = sorted(url for url in site.by_url if _covers(path, url))
            moved = sorted(old for old in plan.moved if _covers(path, old))
        else:
            hit = [path] if path in site.by_url else []
            moved = [path] if path in plan.moved else []
        if hit:
            collector.error(
                "E022",
                f"gone {entry!r} закрывает существующую страницу {hit[0]}",
                path=source,
                hint="уберите адрес из gone или страницу из контента",
            )
            continue
        if moved:
            collector.error(
                "E022",
                f"gone {entry!r} пересекается с redirect_from {moved[0]} "
                f"(объявлен в {owner[moved[0]]})",
                path=source,
                hint="адрес либо переехал (301), либо исчез (410) — выберите одно",
            )
            continue
        (plan.gone_prefixes if kind == "prefix" else plan.gone).append(path)

    plan.gone.sort()
    plan.gone_prefixes.sort()
    plan.gone_queries.sort(key=lambda q: (q[0], q[1], q[2] or ""))
    return plan


def files(plan: Plan) -> dict[str, str]:
    """Человекочитаемые копии карт. Сервер берёт их из конфига nginx."""
    out = {
        "redirects.map": "".join(
            f"{old}  {target};\n" for old, target in sorted(plan.moved.items())
        )
    }
    lines = [f"{path}  1;\n" for path in plan.gone]
    lines += [f"{path}*  1;\n" for path in plan.gone_prefixes]
    lines += [f"{path}?{name}={value or '*'}  1;\n" for path, name, value in plan.gone_queries]
    if lines:
        out["gone.map"] = "".join(lines)
    return out


def generate(site: Site, collector: Collector, config: SiteConfig | None = None) -> dict[str, str]:
    return files(collect(site, collector, config))
