"""Рендеринг страниц.

Каждая страница проходит через `theme/templates/<тип>.html`. Нет шаблона
для типа — остановка: страница, собранная не тем шаблоном, хуже несобранной.

Спецификация: docs/spec/21-engine.md, раздел 7.
"""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, TemplateNotFound, TemplateSyntaxError
from jinja2 import UndefinedError as JinjaUndefined
from jinja2.exceptions import SecurityError

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.environment import BuildEnv
from heron.core.errors import Collector, HeronError
from heron.core.media import Manifest
from heron.core.models import Page, Site
from heron.core.render import env as envmod
from heron.core.render import signature
from heron.messages import Msg, say

TEMPLATES = "templates"
BODY_OPEN = re.compile(r"<body\b[^>]*>", re.IGNORECASE)
# Плашка «перевод не готов» черновой сборки: свои стили, чтобы не зависеть от темы.
PENDING_BANNER = (
    '<div class="heron-pending" role="status" style="position:sticky;top:0;z-index:2147483647;'
    "margin:0;padding:.6em 1em;background:#fff3cd;color:#3d2e00;border-bottom:2px solid #c99a00;"
    'font:15px/1.4 system-ui,sans-serif">{text}</div>'
)


def pending_banner(html: str, page: Page, config: SiteConfig) -> str:
    """Плашка «перевод не готов» сразу после `<body>` (только черновая сборка, 20 §4.2)."""
    from markupsafe import escape

    notes = config.build.notes if config.build.notes in ("ru", "en") else "en"
    text = say(notes, "render_pending_banner", lang=page.lang, source=f"content/{page.source}")
    banner = PENDING_BANNER.format(text=escape(text))
    match = BODY_OPEN.search(html)
    if match is None:
        return banner + html
    return html[: match.end()] + banner + html[match.end() :]


def template_name(page: Page, theme: ThemeConfig) -> str:
    spec = theme.types.get(page.type)
    if spec is not None and spec.template:
        return f"{TEMPLATES}/{spec.template}"
    return f"{TEMPLATES}/{page.type}.html"


def render_page(
    env: Environment,
    page: Page,
    site: Site,
    config: SiteConfig,
    theme: ThemeConfig,
    strings: envmod.Strings,
    collector: Collector,
    media: Manifest | None = None,
    build_env: BuildEnv | None = None,
    seen: set[tuple[str, str, str | None]] | None = None,
) -> str:
    """Собрать HTML одной страницы. `seen` - запись нарисованных модулей (`env.Modules`)."""
    name = template_name(page, theme)
    try:
        template = env.get_template(name)
    except TemplateNotFound as exc:
        raise HeronError(
            code="E008",
            message=Msg("render_template_missing", type=page.type, name=name),
            path=page.source,
            hint=Msg("render_template_missing_hint", name=name),
        ) from exc
    except TemplateSyntaxError as exc:
        raise HeronError(
            code="E010",
            message=Msg(
                "render_template_syntax", name=exc.name or name, line=exc.lineno, detail=exc.message
            ),
            path=page.source,
            hint=Msg("render_template_syntax_hint"),
        ) from exc

    scope = envmod.context(
        env, page, site, config, theme, strings, collector, media, build_env, seen
    )
    try:
        return template.render(**scope)
    except TemplateNotFound as exc:
        # extends, include или import в теме указали на файл, которого нет.
        # Это опечатка темы, а не сбой движка, — и почти всегда одна и та же:
        # путь пишут от папки шаблона, а он считается от корня темы.
        missing = exc.name or str(exc)
        hint = Msg("render_include_missing_hint")
        loader = getattr(env, "loader", None)
        searched = getattr(loader, "searchpath", None) or []
        for root in searched:
            for folder in ("templates", "modules", "partials"):
                if (Path(root) / folder / missing).is_file():
                    hint = Msg("render_include_found_hint", folder=folder, missing=missing)
        raise HeronError(
            code="E008",
            message=Msg("render_include_missing", name=name, missing=missing),
            path=page.source,
            hint=hint,
        ) from exc
    except TemplateSyntaxError as exc:
        raise HeronError(
            code="E010",
            message=Msg(
                "render_template_syntax", name=exc.name or name, line=exc.lineno, detail=exc.message
            ),
            path=page.source,
            hint=Msg("render_template_syntax_hint"),
        ) from exc
    except SecurityError as exc:
        # Тема — недоверенный код, шаблоны собираются в песочнице. Сюда
        # приходит попытка достать служебные атрибуты, вызвать небезопасное
        # или изменить данные сайта из шаблона.
        raise HeronError(
            code="E033",
            message=Msg("render_sandbox", name=name, detail=str(exc)),
            path=page.source,
            hint=Msg("render_sandbox_hint"),
        ) from exc
    except JinjaUndefined as exc:
        raise HeronError(
            code="E010",
            message=Msg("render_undefined", name=name, detail=exc.message),
            path=page.source,
            hint=Msg("render_undefined_hint"),
        ) from exc
    except HeronError:
        raise
    except Exception as exc:
        raise HeronError(
            code="E010",
            message=Msg("render_theme_crash", name=name, kind=type(exc).__name__, detail=str(exc)),
            path=page.source,
            hint=Msg("render_theme_crash_hint"),
        ) from exc


def render_site(
    theme_dir: Path,
    site: Site,
    config: SiteConfig,
    theme: ThemeConfig,
    collector: Collector,
    media: Manifest | None = None,
    build_env: BuildEnv | None = None,
    progress=None,
    hooks=None,
    seen: set[tuple[str, str, str | None]] | None = None,
) -> dict[str, str]:
    """Собрать HTML всех страниц. Ключ — адрес страницы.

    `seen` - куда записать нарисованные модули (проверка демо и справка темы).

    `on_page_rendered(page, html)` плагина может вернуть новый HTML —
    он и идёт дальше; `None` — оставить как есть.
    """
    env = envmod.make(theme_dir, config, hooks)
    strings = {}
    for lang in config.site.languages:
        try:
            strings[lang] = envmod.load_strings(theme_dir, lang, collector)
        except HeronError as error:
            collector.errors.append(error)
    if len(strings) < len(config.site.languages):
        return {}

    out: dict[str, str] = {}
    for index, page in enumerate(site.pages, 1):
        if progress is not None:
            progress.tick(index, len(site.pages), page.url or "/")
        try:
            html = render_page(
                env,
                page,
                site,
                config,
                theme,
                strings[page.lang],
                collector,
                media,
                build_env,
                seen,
            )
            if page.meta.pending and build_env is not None and not build_env.is_prod:
                html = pending_banner(html, page, config)
            if hooks is not None:
                html = hooks.pipe("on_page_rendered", page, html)
            if config.build.generator:
                html = signature.sign(html)
            out[page.url] = html
        except HeronError as error:
            collector.errors.append(error)
    return out
