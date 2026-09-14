"""Окружение Jinja2 и макросы модулей.

Два правила, из которых растёт всё остальное.

`StrictUndefined`: обращение к несуществующей переменной валит сборку, а не
выводит пустоту. Опечатка в теме ловится на сборке, а не глазами посетителя.

`mod.<модуль>(<id секции>)`: секции нет — пустая строка, ничего не рендерится.
Пустой блок хуже отсутствующего, а обвязка условиями вокруг каждого вызова
превращает шаблон в лапшу. Поэтому условие живёт внутри макроса.

Спецификация: docs/spec/21-engine.md, раздел 7.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from markupsafe import Markup

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.errors import Collector, HeronError
from heron.core.models import Page, Site

MODULES = "modules"
TEMPLATES = "templates"
I18N = "i18n"


class Strings:
    """Строки интерфейса темы.

    Тексты, принадлежащие теме, а не контенту — «Записатися», «Читати далі» —
    живут в теме по языкам. Иначе они окажутся зашиты в шаблоны, и тема
    перестанет быть переносимой между языками и между сайтами.

    Отсутствие строки не валит сборку: это untranslated, а не опечатка.
    Возвращается имя ключа — его видно в вёрстке, значит заметят.
    """

    def __init__(self, values: dict[str, Any], lang: str, collector: Collector) -> None:
        self._values = values
        self._lang = lang
        self._collector = collector
        self._missed: set[str] = set()

    def __getattr__(self, key: str) -> Any:
        return self[key]

    def __getitem__(self, key: str) -> Any:
        if key in self._values:
            return self._values[key]
        if key not in self._missed:
            self._missed.add(key)
            self._collector.warn(f"нет строки перевода {key!r} для языка {self._lang!r}")
        return key

    def __contains__(self, key: str) -> bool:
        return key in self._values


class Modules:
    """Доступ к модулям темы из шаблона: `mod.facts('quick-facts')`.

    Шаблону модуля достаются `section` (сама секция), `items` (разобранные
    данные структурированной секции) и `html` (готовая вёрстка содержимого),
    плюс всё общее окружение страницы.
    """

    def __init__(self, env: Environment, context: dict[str, Any], collector: Collector) -> None:
        self._env = env
        self._context = context
        self._collector = collector

    def __getattr__(self, name: str):
        def render(section_id: str | None = None, **extra: Any) -> Markup:
            page: Page = self._context["page"]
            section = None
            if section_id is not None:
                section = page.section(section_id)
                if section is None or section.is_empty:
                    return Markup("")
            template_name = f"{MODULES}/{name.replace('_', '-')}.html"
            try:
                template = self._env.get_template(template_name)
            except TemplateNotFound as exc:
                raise HeronError(
                    code="E008",
                    message=f"тема вызывает модуль {name!r}, но {template_name} в ней нет",
                    path=page.source,
                    hint="добавьте шаблон модуля или уберите вызов из шаблона типа",
                ) from exc
            scope = dict(self._context)
            scope.update(
                section=section,
                items=(section.data if section is not None else None),
                html=Markup(section.html) if section is not None else Markup(""),
            )
            scope.update(extra)
            return Markup(template.render(**scope))

        return render


def load_strings(theme_dir: Path, lang: str, collector: Collector) -> Strings:
    """Прочитать `theme/i18n/<lang>.yaml`."""
    path = theme_dir / I18N / f"{lang}.yaml"
    values: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            values = loaded
    else:
        collector.warn(f"в теме нет строк интерфейса для языка {lang!r}", path=str(path))
    return Strings(values, lang, collector)


def make(theme_dir: Path, config: SiteConfig) -> Environment:
    """Собрать окружение Jinja2 для темы."""
    env = Environment(
        loader=FileSystemLoader(str(theme_dir)),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.globals["absolute"] = lambda url: f"https://{config.site.domain}{url}"
    env.filters["absolute"] = env.globals["absolute"]
    return env


def context(
    env: Environment,
    page: Page,
    site: Site,
    config: SiteConfig,
    theme: ThemeConfig,
    strings: Strings,
    collector: Collector,
) -> dict[str, Any]:
    """Всё, что видит шаблон страницы."""
    shared: dict[str, Any] = {
        "page": page,
        "site": config,
        "theme": theme,
        "data": site.data,
        "nav": site.nav.get(page.lang, {}),
        "pages": site,
        "t": strings,
        "lang": page.lang,
        "languages": config.site.languages,
    }
    shared["mod"] = Modules(env, shared, collector)
    return shared
