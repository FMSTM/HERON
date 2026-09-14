"""Карта редиректов.

Единственное, что защищает индекс при переезде. Старый адрес пишется рядом
с новым контентом, во фронтматтере страницы, а не в отдельной таблице,
которая разъедется с сайтом на второй неделе.

Отдельно от 301 живёт 410: сущностей вроде служебных типов записей старого
сайта или выключенного форума больше нет, и притворяться, что они временно
недоступны, смысла нет.

Спецификация: docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

from heron.core.errors import Collector
from heron.core.models import Site


def generate(site: Site, collector: Collector) -> dict[str, str]:
    moved: dict[str, str] = {}
    owner: dict[str, str] = {}
    gone: dict[str, str] = {}

    for page in site.pages:
        for old in page.meta.redirect_from:
            if old in site.by_url:
                collector.error(
                    "E009",
                    f"redirect_from {old!r} совпадает с существующим адресом",
                    path=page.source,
                    hint="страница по этому адресу уже есть, редирект перекрыл бы её",
                )
                continue
            if old in moved and moved[old] != page.url:
                collector.error(
                    "E009",
                    f"{old!r} ведёт сразу в два места: {moved[old]} и {page.url}",
                    path=page.source,
                    hint=f"первый раз объявлен в {owner[old]}",
                )
                continue
            moved[old] = page.url
            owner[old] = page.source

        for old in page.meta.gone:
            if old in site.by_url:
                collector.error(
                    "E009",
                    f"gone {old!r} совпадает с существующим адресом",
                    path=page.source,
                )
                continue
            gone[old] = page.source

    for old, target in moved.items():
        if target in moved:
            collector.error(
                "E009",
                f"цепочка редиректов: {old} ведёт на {target}, который сам перенаправляется",
                path=owner[old],
                hint="направьте сразу на конечный адрес",
            )

    overlap = sorted(set(moved) & set(gone))
    for old in overlap:
        collector.error(
            "E009",
            f"{old!r} объявлен и как redirect_from, и как gone",
            path=owner.get(old, gone[old]),
        )

    files = {
        "redirects.map": "".join(f"{old}  {target};\n" for old, target in sorted(moved.items()))
    }
    if gone:
        files["gone.map"] = "".join(f"{old}  1;\n" for old in sorted(gone))
    return files
