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
from heron.messages import Msg


def verify_engine(theme: ThemeConfig, theme_path: str = "theme.yaml") -> None:
    """Проверить, что движок даёт теме то, на что она рассчитывает.

    Тема живёт в репозитории сайта и обновляется отдельно от движка. Если
    она написана под новое поле контракта, а собирают её старым движком,
    без этой проверки сборка падает на каждой странице с сообщением про
    опечатку во фронтматтере — самым бесполезным из возможных. Здесь это
    ловится один раз, до рендера, и называется своим именем.
    """
    try:
        engine_ok = not theme.heron or version_contract.satisfies(__version__, theme.heron)
    except ValueError as exc:
        raise HeronError(
            code="E008",
            message=(
                exc.args[0]
                if exc.args and isinstance(exc.args[0], Msg)
                else Msg("version_raw", text=str(exc))
            ),
            path=theme_path,
            hint=Msg("version_bad_spec_hint"),
        ) from exc
    if not engine_ok:
        raise HeronError(
            code="E012",
            message=Msg(
                "version_wiring_engine_too_old",
                theme=theme.name,
                required=theme.heron,
                actual=__version__,
            ),
            path=theme_path,
            hint=Msg("version_wiring_engine_too_old_hint"),
        )

    known = set(PageMeta.model_fields)
    unknown = [name for name in theme.fields if name not in known]
    if unknown:
        raise HeronError(
            code="E023",
            message=Msg(
                "version_wiring_unknown_fields",
                theme=theme.name,
                actual=__version__,
                fields="\n    ".join(unknown),
            ),
            path=theme_path,
            hint=Msg("version_wiring_unknown_fields_hint"),
        )


def verify(theme: ThemeConfig, site: SiteConfig, site_path: str = "site.yaml") -> list[Warning_]:
    """Проверить, что сайт даёт теме всё, что она просит.

    Ошибка — тема просит блок, которого в `site.yaml` нет, или форму,
    которой нет в `forms`. Предупреждение — язык темы без строк перевода
    и прочее, что не ломает сборку.
    """
    # урезанный конфиг без языков (заглушка) смотрится как один безымянный язык
    langs: list[str] = list(getattr(getattr(site, "site", None), "languages", None) or [""])

    def view(lang: str) -> SiteConfig:
        return site.for_lang(lang) if lang else site
    missing: list[str] = []
    for path in theme.requires:
        bad = [
            lang for lang in langs if view(lang).get_path(path) in (None, "", [], {})
        ]
        if len(bad) == len(langs):
            missing.append(path)
        elif bad:
            missing.append(f"{path} ({', '.join(bad)})")
    if missing:
        raise HeronError(
            code="E011",
            message=Msg(
                "version_wiring_missing_values",
                theme=theme.name,
                values="\n    ".join(missing),
            ),
            path=site_path,
            hint=Msg("version_wiring_missing_values_hint"),
        )

    unknown_forms = [name for name in theme.forms if name not in site.forms]
    if unknown_forms:
        raise HeronError(
            code="E011",
            message=Msg(
                "version_wiring_unknown_forms",
                theme=theme.name,
                forms=", ".join(unknown_forms),
            ),
            path=site_path,
            hint=Msg("version_wiring_unknown_forms_hint"),
        )

    warnings: list[Warning_] = []
    unused = sorted(set(site.forms) - set(theme.forms))
    if unused:
        warnings.append(
            Warning_(
                Msg("version_wiring_unused_forms", forms=", ".join(unused)),
                path=site_path,
            )
        )
    return warnings
