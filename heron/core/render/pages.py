"""Рендеринг страниц.

Каждая страница проходит через `theme/templates/<тип>.html`. Нет шаблона
для типа — остановка: страница, собранная не тем шаблоном, хуже несобранной.

Спецификация: docs/spec/21-engine.md, раздел 7.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, TemplateNotFound, TemplateSyntaxError
from jinja2 import UndefinedError as JinjaUndefined

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.environment import BuildEnv
from heron.core.errors import Collector, HeronError
from heron.core.media import Manifest
from heron.core.models import Page, Site
from heron.core.render import env as envmod

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
            message=f"для типа страницы {page.type!r} нет шаблона {name}",
            path=page.source,
            hint=f"создайте {name} в теме или задайте другой тип страницы",
        ) from exc
    except TemplateSyntaxError as exc:
        raise HeronError(
            code="E010",
            message=f"ошибка в шаблоне {exc.name or name}, строка {exc.lineno}: {exc.message}",
            path=page.source,
            hint="проверьте разметку Jinja в этой строке шаблона темы",
        ) from exc

    scope = envmod.context(env, page, site, config, theme, strings, collector, media, build_env)
    try:
        return template.render(**scope)
    except TemplateNotFound as exc:
        # extends, include или import в теме указали на файл, которого нет.
        # Это опечатка темы, а не сбой движка, — и почти всегда одна и та же:
        # путь пишут от папки шаблона, а он считается от корня темы.
        missing = exc.name or str(exc)
        hint = "пути в extends, include и import считаются от корня темы: templates/…, modules/…"
        loader = getattr(env, "loader", None)
        searched = getattr(loader, "searchpath", None) or []
        for root in searched:
            for folder in ("templates", "modules", "partials"):
                if (Path(root) / folder / missing).is_file():
                    hint = f"файл есть как {folder}/{missing} — пути считаются от корня темы"
        raise HeronError(
            code="E008",
            message=f"шаблон {name} ссылается на {missing!r}, а такого файла в теме нет",
            path=page.source,
            hint=hint,
        ) from exc
    except TemplateSyntaxError as exc:
        raise HeronError(
            code="E010",
            message=f"ошибка в шаблоне {exc.name or name}, строка {exc.lineno}: {exc.message}",
            path=page.source,
            hint="проверьте разметку Jinja в этой строке шаблона темы",
        ) from exc
    except JinjaUndefined as exc:
        raise HeronError(
            code="E010",
            message=f"шаблон {name} обращается к тому, чего нет: {exc.message}",
            path=page.source,
            hint="опечатка в имени переменной или поле не заполнено во фронтматтере",
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
) -> dict[str, str]:
    """Собрать HTML всех страниц. Ключ — адрес страницы."""
    env = envmod.make(theme_dir, config)
    strings = {
        lang: envmod.load_strings(theme_dir, lang, collector) for lang in config.site.languages
    }

    out: dict[str, str] = {}
    for index, page in enumerate(site.pages, 1):
        if progress is not None:
            progress.tick(index, len(site.pages), page.url or "/")
        try:
            out[page.url] = render_page(
                env, page, site, config, theme, strings[page.lang], collector, media, build_env
            )
        except HeronError as error:
            collector.errors.append(error)
    return out
