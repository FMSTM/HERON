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
from markupsafe import Markup, escape

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.environment import BuildEnv
from heron.core.errors import Collector, HeronError
from heron.core.media import Manifest
from heron.core.models import Page, Site
from heron.modules import jsonld

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
            self._collector.warn(
                f"нет строки перевода {key!r} для языка {self._lang!r}", kind="переводы"
            )
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
            # YAML читает голые off, on, yes, no как булевы значения, и строка
            # 'off' тихо теряется. Молчать нельзя: в вёрстке останется имя
            # ключа, а причина будет неочевидна до самого осмотра страницы.
            for key in [k for k in loaded if not isinstance(k, str)]:
                collector.warn(
                    f"ключ {key!r} прочитан как {type(key).__name__}, а не как строка — "
                    "возьмите его в кавычки",
                    path=str(path),
                    kind="переводы",
                )
                del loaded[key]
            values = loaded
    else:
        collector.warn(
            f"в теме нет строк интерфейса для языка {lang!r}", path=str(path), kind="переводы"
        )
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


def media_url(
    manifest: Manifest,
    collector: Collector,
) -> Any:
    """Адрес файла в сборке — для ссылки, скачивания и разметки соцсетей.

    Тема умела получить от движка только готовый `<picture>`, а адрес нужен
    постоянно: «открыть скан», `href` модального окна, og:image, ссылка на
    памятку из текста. Без этого файл приходилось дублировать в `static/` —
    полтора мегабайта мусора и два места, которые надо не забыть поправить
    вместе.

    Без параметров отдаётся сам файл, с `ratio` — конкретный нарезанный
    вариант. `width` выбирает ближайший вариант не меньше запрошенного:
    отдать картинку крупнее и дать браузеру её сжать честнее, чем показать
    мыло.
    """

    def render(src: str, ratio: str = "", width: int = 0, format: str = "") -> str:
        clean = src.lstrip("./")
        if not ratio and not width and not format:
            return f"/{clean}"

        rendition = manifest.get(clean, ratio or "1:1")
        if rendition is None:
            # Молча отдать пустоту нельзя: именно на этом теряются картинки,
            # и замечают это глазами, через неделю после выката.
            collector.warn(
                f"нет нарезанного варианта {ratio or '1:1'} для {clean}", kind="картинки"
            )
            return f"/{clean}"

        variants = rendition.sources.get(format) if format else None
        if variants is None:
            variants = rendition.sources.get("origin") or next(iter(rendition.sources.values()), [])
        if not variants:
            collector.warn(f"нет файлов варианта {ratio} для {clean}", kind="картинки")
            return f"/{clean}"

        chosen = next((path for w, path in variants if w >= width), variants[-1][1])
        return f"/{chosen}"

    return render


def picture(
    manifest: Manifest,
    collector: Collector,
) -> Any:
    """Готовый `<picture>` по нарезанным вариантам.

    `width` и `height` проставляются всегда: без них вёрстка прыгает при
    загрузке и растёт CLS. `loading="lazy"` — на всё, кроме первого экрана.
    """

    def render(
        src: str,
        ratio: str = "1:1",
        alt: str = "",
        sizes: str = "100vw",
        lazy: bool = True,
        classes: str = "",
        attrs: str = "",
    ) -> Markup:
        rendition = manifest.get(src, ratio)
        if rendition is None:
            collector.warn(f"нет нарезанного варианта {ratio} для {src}", kind="картинки")
            return Markup("")

        parts: list[str] = ["<picture>"]
        for fmt, variants in rendition.sources.items():
            if fmt == "origin":
                continue
            srcset = ", ".join(f"/{path} {width}w" for width, path in variants)
            parts.append(f'<source type="image/{fmt}" srcset="{srcset}" sizes="{sizes}">')
        img = [
            f'src="/{rendition.fallback}"',
            f'width="{rendition.width}"',
            f'height="{rendition.height}"',
            f'alt="{escape(alt)}"',
            'decoding="async"',
        ]
        if lazy:
            img.append('loading="lazy"')
        if classes:
            img.append(f'class="{escape(classes)}"')
        if attrs:
            # Тема переносит вёрстку из макета один в один, вместе с
            # инлайновыми стилями и data-атрибутами. Их некуда девать,
            # кроме как отдать сюда: собирать <picture> руками в шаблоне
            # значит потерять нарезанные варианты.
            img.append(attrs)
        parts.append("<img " + " ".join(img) + ">")
        parts.append("</picture>")
        return Markup("".join(parts))

    return render


def context(
    env: Environment,
    page: Page,
    site: Site,
    config: SiteConfig,
    theme: ThemeConfig,
    strings: Strings,
    collector: Collector,
    media: Manifest | None = None,
    build_env: BuildEnv | None = None,
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
        "env": build_env or BuildEnv(),
    }
    shared["mod"] = Modules(env, shared, collector)
    shared["jsonld"] = lambda: Markup(jsonld.render(page, config, theme))
    shared["picture"] = picture(media or Manifest(), collector)
    shared["media_url"] = media_url(media or Manifest(), collector)
    # Тот же адрес доступен и фильтром: в разметке чаще пишут
    # `{{ src|media_url }}`, чем вызов функции, и заставлять выбирать
    # одну из двух форм ради устройства движка незачем.
    env.filters["media_url"] = shared["media_url"]
    return shared
