"""Демо темы: каждый тип, блок и вид раздела показан хотя бы на одной странице.

Демо - это не украшение архива, а «эффективная структура подачи под нишу»,
которую автор темы продумывает один раз: какие страницы нужны, какие блоки на
них и в каком порядке. По нему новичок видит, что тема умеет, а справка темы
(`render/themeref.py`) берёт из него живые примеры. Поэтому демо обязано
показывать всё, что объявил контракт темы:

- у каждого типа из `types` - хотя бы одна страница;
- каждый модуль из `modules` что-то нарисовал хотя бы на одной странице;
- каждый вид раздела из `views` показан на странице раздела: странице с
  детьми, у которой ключ вида (`view`) равен виду, а без ключа - вид по
  умолчанию. Вид считается по ключу и имени: у главной и у обычной страницы
  стартовой темы один набор видов, и показать `list` достаточно на одной из них.

«Нарисовал» - по настоящему рендеру: страницы демо собираются шаблонами темы,
и `Modules` записывает каждый вызов `mod.<имя>()`, вернувший не пустоту.
Догадка по разбору markdown не знает, что шаблон делает с секцией, а модули
страницы (крошки, список детей) из markdown не видны вовсе.

Демо - это контент сайта, из которого тему упаковывают (`heron theme pack`) и
проверяют (`heron check --theme`). Тема с описанием полей (`fields`) и неполным
демо - ошибка E037; старая тема без `fields` - предупреждение с тем же списком.

Спецификация: docs/ru/spec/21-engine.md, «Демо темы».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig, kinds_of
from heron.core.environment import BuildEnv
from heron.core.errors import Collector, HeronError, Warning_
from heron.core.models import Page, Site
from heron.core.render import pages as renderer
from heron.messages import Msg

CODE = "E037"

Seen = set[tuple[str, str, str | None]]


@dataclass(slots=True)
class Shown:
    """Что показывает демо: страницы, модули на них и виды разделов."""

    pages: list[Page] = field(default_factory=list)
    # модуль → [(страница, id секции или None для модуля страницы)]
    modules: dict[str, list[tuple[Page, str | None]]] = field(default_factory=dict)
    # (ключ вида, вид) → страницы разделов, которые его показывают
    views: dict[tuple[str, str], list[Page]] = field(default_factory=dict)
    # ошибки рендера демо: шаблон темы упал на странице
    errors: list[HeronError] = field(default_factory=list)

    def types(self) -> set[str]:
        return {page.type for page in self.pages}


def real_pages(site: Site) -> list[Page]:
    """Страницы из файлов: достроенная движком 404 демо не считается."""
    return [page for page in site.pages if not page.generated]


def view_of(page: Page, theme: ThemeConfig) -> tuple[str, str] | None:
    """(ключ, вид) раздела, который показывает страница; None - тип без видов или детей нет."""
    spec = theme.types.get(page.type)
    if spec is None or spec.views is None:
        return None
    if not [child for child in page.children if not child.generated]:
        return None
    value = page.meta.get(spec.views.key)
    view = str(value) if value not in (None, "") else spec.views.default
    return spec.views.key, view


def shown(site: Site, theme: ThemeConfig, seen: Seen, errors: list[HeronError] = ()) -> Shown:
    """Сложить запись рендера (`seen`) в то, что показано на каких страницах."""
    out = Shown(pages=real_pages(site), errors=list(errors))
    by_source = {str(page.source): page for page in out.pages}
    for source, module, section_id in sorted(
        seen, key=lambda item: (item[0], item[1], item[2] or "")
    ):
        page = by_source.get(source)
        if page is not None:
            out.modules.setdefault(module, []).append((page, section_id))
    for page in out.pages:
        view = view_of(page, theme)
        if view is not None:
            out.views.setdefault(view, []).append(page)
    # порядок примеров: страницы в порядке обхода сайта, а не по алфавиту путей
    order = {id(page): index for index, page in enumerate(out.pages)}
    for found in out.modules.values():
        found.sort(key=lambda item: order[id(item[0])])
    return out


def render(
    theme_dir: Path,
    site: Site,
    config: SiteConfig,
    theme: ThemeConfig,
    hooks=None,
) -> Shown:
    """Собрать демо шаблонами темы, ничего не записывая, и вернуть, что показано.

    Предупреждения рендера (нет нарезки картинки, нет строки перевода) здесь не
    нужны: о них скажет сборка. Ошибки шаблонов возвращаются в `Shown.errors`.
    """
    seen: Seen = set()
    scratch = Collector()
    renderer.render_site(
        theme_dir, site, config, theme, scratch, None, BuildEnv(), hooks=hooks, seen=seen
    )
    return shown(site, theme, seen, scratch.errors)


def gaps(theme: ThemeConfig, found: Shown) -> list[Msg]:
    """Что контракт темы объявил, а демо не показало - строки для человека."""
    out: list[Msg] = []
    types = found.types()
    for name in theme.types:
        if name not in types:
            out.append(Msg("demo_gap_type", type=name))
    for name, spec in theme.module_specs.items():
        if found.modules.get(name):
            continue
        kinds = kinds_of(name, spec)
        if kinds:
            out.append(Msg("demo_gap_module", module=name, kinds=", ".join(kinds)))
        else:
            out.append(Msg("demo_gap_page_module", module=name))
    offered: dict[tuple[str, str], list[str]] = {}
    defaults: set[tuple[str, str]] = set()
    for name, spec in theme.types.items():
        if spec.views is None:
            continue
        for view in spec.views.options:
            offered.setdefault((spec.views.key, view), []).append(name)
            if view == spec.views.default:
                defaults.add((spec.views.key, view))
    for (key, view), types in offered.items():
        if found.views.get((key, view)):
            continue
        gap = "demo_gap_view_default" if (key, view) in defaults else "demo_gap_view"
        out.append(Msg(gap, types=", ".join(types), view=view, key=key))
    return out


def verify(
    theme: ThemeConfig,
    theme_dir: Path,
    site: Site,
    config: SiteConfig,
    collector: Collector,
    hooks=None,
) -> Shown:
    """Проверить демо темы: E037 у темы с `fields`, предупреждение у старой темы.

    Ошибки рендера демо идут в `collector` как есть: шаблон, упавший на
    демо-странице, упадёт и на сборке.
    """
    found = render(theme_dir, site, config, theme, hooks)
    collector.errors.extend(found.errors)
    missing = gaps(theme, found)
    if not missing:
        return found
    where = str(theme_dir / "theme.yaml")
    if theme.described:
        collector.errors.append(
            HeronError(
                code=CODE,
                message=Msg("demo_incomplete", theme=theme.name, count=len(missing), gaps=missing),
                path=where,
                hint=Msg("demo_incomplete_hint"),
            )
        )
    else:
        collector.warnings.append(
            Warning_(
                Msg("demo_incomplete_old", theme=theme.name, count=len(missing), gaps=missing),
                path=where,
            )
        )
    return found
