"""Стыковка темы и сайта.

Ядро не знает, что такое `contact.phone` — но знает, что тема без него
не соберётся. Поэтому тема объявляет свои требования, а движок проверяет
их наличие: предметная область остаётся в теме, проверка в ядре.
"""

from __future__ import annotations

from heron import __version__
from heron.contracts import version as version_contract
from heron.contracts.frontmatter import PageMeta
from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.errors import HeronError, Warning_


def verify_engine(theme: ThemeConfig, theme_path: str = "theme.yaml") -> None:
    """Проверить, что движок даёт теме то, на что она рассчитывает.

    Тема живёт в репозитории сайта и обновляется отдельно от движка. Если
    она написана под новое поле контракта, а собирают её старым движком,
    без этой проверки сборка падает на каждой странице с сообщением про
    опечатку во фронтматтере — самым бесполезным из возможных. Здесь это
    ловится один раз, до рендера, и называется своим именем.
    """
    if theme.heron and not version_contract.satisfies(__version__, theme.heron):
        raise HeronError(
            code="E012",
            message=(f"тема {theme.name!r} требует движок {theme.heron}, а этот — {__version__}"),
            path=theme_path,
            hint="обновите образ движка или ослабьте требование `heron` в theme.yaml",
        )

    known = set(PageMeta.model_fields)
    unknown = [name for name in theme.fields if name not in known]
    if unknown:
        raise HeronError(
            code="E012",
            message=(
                f"тема {theme.name!r} обращается к полям, которых движок {__version__} "
                "не знает:\n    " + "\n    ".join(unknown)
            ),
            path=theme_path,
            hint=(
                "поле появилось в более новом движке — обновите образ; "
                "либо это опечатка в `fields` в theme.yaml"
            ),
        )


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
