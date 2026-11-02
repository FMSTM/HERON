"""Рендеринг страниц.

Каждая страница проходит через `theme/templates/<тип>.html`. Нет шаблона
для типа — остановка: страница, собранная не тем шаблоном, хуже несобранной.

Спецификация: docs/spec/21-engine.md, раздел 7.
"""

from __future__ import annotations

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
from heron.messages import Msg

TEMPLATES = "templates"


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
) -> str:
    """Собрать HTML одной страницы."""
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

    scope = envmod.context(env, page, site, config, theme, strings, collector, media, build_env)
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
) -> dict[str, str]:
    """Собрать HTML всех страниц. Ключ — адрес страницы.

    `on_page_rendered(page, html)` плагина может вернуть новый HTML —
    он и идёт дальше; `None` — оставить как есть.
    """
    env = envmod.make(theme_dir, config, hooks)
    strings = {
        lang: envmod.load_strings(theme_dir, lang, collector) for lang in config.site.languages
    }

    out: dict[str, str] = {}
    for index, page in enumerate(site.pages, 1):
        if progress is not None:
            progress.tick(index, len(site.pages), page.url or "/")
        try:
            html = render_page(
                env, page, site, config, theme, strings[page.lang], collector, media, build_env
            )
            if hooks is not None:
                html = hooks.pipe("on_page_rendered", page, html)
            if config.build.generator:
                html = signature.sign(html)
            out[page.url] = html
        except HeronError as error:
            collector.errors.append(error)
    return out
