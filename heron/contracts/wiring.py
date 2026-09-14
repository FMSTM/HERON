"""Стыковка темы и сайта.

Ядро не знает, что такое `contact.phone` — но знает, что тема без него
не соберётся. Поэтому тема объявляет свои требования, а движок проверяет
их наличие: предметная область остаётся в теме, проверка в ядре.
"""

from __future__ import annotations

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.errors import HeronError, Warning_


def verify(theme: ThemeConfig, site: SiteConfig, site_path: str = "site.yaml") -> list[Warning_]:
    """Проверить, что сайт даёт теме всё, что она просит.

    Ошибка — тема просит блок, которого в `site.yaml` нет, или форму,
    которой нет в `forms`. Предупреждение — язык темы без строк перевода
    и прочее, что не ломает сборку.
    """
    missing = [path for path in theme.requires if site.get_path(path) in (None, "", [], {})]
    if missing:
        raise HeronError(
            code="E011",
            message=(
                f"тема {theme.name!r} требует значения, которых нет в site.yaml:\n    "
                + "\n    ".join(missing)
            ),
            path=site_path,
            hint="добавьте их в site.yaml или уберите из requires в theme.yaml",
        )

    unknown_forms = [name for name in theme.forms if name not in site.forms]
    if unknown_forms:
        raise HeronError(
            code="E011",
            message=(
                f"тема {theme.name!r} рисует формы, которых нет в site.yaml: "
                + ", ".join(unknown_forms)
            ),
            path=site_path,
            hint="опишите форму в блоке forms или уберите её из темы",
        )

    warnings: list[Warning_] = []
    unused = sorted(set(site.forms) - set(theme.forms))
    if unused:
        warnings.append(
            Warning_(
                "формы описаны в site.yaml, но тема их не рисует: " + ", ".join(unused),
                path=site_path,
            )
        )
    return warnings
