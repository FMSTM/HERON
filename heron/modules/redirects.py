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
from heron.messages import Msg


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


def _stem(path: str) -> str:
    """Адрес без завершающего слеша: конфиг отвечает и на `/x`, и на `/x/`.

    Сверять 301 и 410 между собой, со страницами и со служебными адресами
    надо по этой форме: иначе `/a.html` и `/a.html/` проходят проверку
    порознь и дают в конфиге дважды один `location`.
    """
    return path.rstrip("/") or "/"


CONTROL = {chr(code) for code in range(32)} | {"\x7f"}


def collect(site: Site, collector: Collector, config: SiteConfig | None = None) -> Plan:
    """Собрать карту 301 и список 410, проверив их друг против друга и против сайта."""
    plan = Plan()
    owner: dict[str, str] = {}
    pages = {_stem(url) for url in site.by_url}
    moved_stems: dict[str, str] = {}

    for page in site.pages:
        for written in page.meta.redirect_from:
            old, ok = canonical_path(written)
            if CONTROL & set(old):
                collector.error(
                    "E009",
                    Msg("redirects_from_control", written=written),
                    path=page.source,
                    hint=Msg("redirects_control_hint"),
                )
                continue
            if not ok:
                plan.raw.add(old)
            if old in site.by_url or _stem(old) in pages:
                collector.error(
                    "E009",
                    Msg("redirects_from_exists", written=written, old=old),
                    path=page.source,
                    hint=Msg("redirects_from_exists_hint"),
                )
                continue
            twin = moved_stems.get(_stem(old))
            if twin is not None and (twin != old or plan.moved[twin] != page.url):
                collector.error(
                    "E009",
                    Msg(
                        "redirects_two_targets",
                        written=written,
                        first=plan.moved[twin],
                        second=page.url,
                    )
                    if twin == old
                    else Msg("redirects_slash_twin", written=written, twin=twin),
                    path=page.source,
                    hint=Msg("redirects_first_declared", owner=owner[twin]),
                )
                continue
            plan.moved[old] = page.url
            owner[old] = page.source
            moved_stems[_stem(old)] = old

    for old, target in plan.moved.items():
        if target in plan.moved:
            collector.error(
                "E009",
                Msg("redirects_chain", old=old, target=target),
                path=owner[old],
                hint=Msg("redirects_chain_hint"),
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
                Msg("redirects_page_gone"),
                path=page.source,
                kind="прочее",
            )
            entries += [(entry, page.source) for entry in page.meta.gone]

    seen: set[tuple[str, str, str, str | None]] = set()
    for entry, source in entries:
        kind, path, name, value = parse_gone(entry)
        path, ok = canonical_path(path, slash=kind != "prefix")
        if CONTROL & set(path):
            collector.error(
                "E022",
                Msg("redirects_gone_control", entry=entry),
                path=source,
                hint=Msg("redirects_control_hint"),
            )
            continue
        if (
            kind == "exact"
            and _stem(path) in {_stem(g) for g in plan.gone}
            and path not in plan.gone
        ):
            collector.error(
                "E022",
                Msg("redirects_gone_twin", entry=entry),
                path=source,
                hint=Msg("redirects_gone_twin_hint"),
            )
            continue
        if (kind, path, name, value) in seen:
            collector.warn(Msg("redirects_gone_twice", entry=entry), path=source, kind="прочее")
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
            hit = [path] if path in site.by_url or _stem(path) in pages else []
            moved = [moved_stems[_stem(path)]] if _stem(path) in moved_stems else []
        if hit:
            collector.error(
                "E022",
                Msg("redirects_gone_hides", entry=entry, page=hit[0]),
                path=source,
                hint=Msg("redirects_gone_hides_hint"),
            )
            continue
        if moved:
            collector.error(
                "E022",
                Msg("redirects_gone_overlap", entry=entry, moved=moved[0], owner=owner[moved[0]]),
                path=source,
                hint=Msg("redirects_gone_overlap_hint"),
            )
            continue
        (plan.gone_prefixes if kind == "prefix" else plan.gone).append(path)

    _reserved(plan, collector, config)
    plan.gone.sort()
    plan.gone_prefixes.sort()
    plan.gone_queries.sort(key=lambda q: (q[0], q[1], q[2] or ""))
    return plan


def reserved(config: SiteConfig | None) -> tuple[set[str], set[str]]:
    """Адреса, которые конфиг nginx уже занял своими location.

    Префиксы — папки ресурсов, `.well-known` и языки; точные — служебные
    страницы 404. Совпадение с 301 или 410 — «duplicate location», и nginx
    не стартует: это ловит сборка, а не сервер.
    """
    prefixes = {"/", "/media/", "/assets/", "/.well-known/"}
    exact = {"/404.html"}
    if config is not None:
        for lang in config.site.languages:
            if lang != config.site.default_lang:
                prefixes.add(f"/{lang}/")
                exact.add(f"/{lang}/404/index.html")
    return prefixes, exact


def _reserved(plan: Plan, collector: Collector, config: SiteConfig | None) -> None:
    prefixes, exact = reserved(config)
    for path in list(plan.gone_prefixes):
        if path in prefixes:
            plan.gone_prefixes.remove(path)
            collector.error(
                "E022",
                Msg("redirects_reserved_prefix", path=path),
                path="site.yaml",
                hint=Msg("redirects_reserved_prefix_hint"),
            )
    stems = {_stem(path) for path in exact}
    for path in [*plan.gone, *plan.moved]:
        if _stem(path) in stems:
            collector.error(
                "E022",
                Msg("redirects_reserved_exact", path=path),
                path="site.yaml",
                hint=Msg("redirects_reserved_exact_hint"),
            )


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
