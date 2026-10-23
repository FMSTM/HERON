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

from pathlib import Path, PurePath
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from jinja2.sandbox import ImmutableSandboxedEnvironment
from markupsafe import Markup, escape
from pydantic import BaseModel

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core import paths
from heron.core.environment import BuildEnv
from heron.core.errors import Collector, HeronError
from heron.core.media import Manifest
from heron.core.models import Page, Site
from heron.modules import jsonld, sitemap

MODULES = "modules"
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
    if path.is_file() and not paths.inside(theme_dir, path):
        # Файл строк — ссылка за пределы темы: её текст ушёл бы в страницы.
        raise HeronError(
            code=paths.CODE,
            message=f"i18n/{lang}.yaml ведёт за пределы темы через ссылку",
            path=str(path),
            hint="положите сам файл в тему вместо ссылки на него",
        )
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


class ThemeLoader(FileSystemLoader):
    """Шаблоны только изнутри темы.

    `FileSystemLoader` идёт по символическим ссылкам: ссылка
    `theme/partials/x.html` на чужой файл вставляла бы его текст в
    публичные страницы. Политика чтения та же, что у `data/` и `static/`
    (`paths`): файл после разрешения ссылок обязан лежать в теме.
    """

    def __init__(self, root: Path) -> None:
        super().__init__(str(root))
        self.root = root

    def get_source(self, environment, template):
        source, filename, uptodate = super().get_source(environment, template)
        if filename and not paths.inside(self.root, Path(filename)):
            raise HeronError(
                code=paths.CODE,
                message=f"шаблон {template} ведёт за пределы темы через ссылку",
                path=str(filename),
                hint="положите сам файл в тему вместо ссылки на него",
            )
        return source, filename, uptodate


class ThemeSandbox(ImmutableSandboxedEnvironment):
    """Песочница для шаблонов темы.

    Тема — чужой код: её ставят из каталога, по ссылке или архивом. Обычный
    Environment исполнял бы из шаблона любой Python
    (`lipsum.__globals__.os.popen(...)`). Песочница Jinja закрывает служебные
    атрибуты и изменение списков и словарей; сверх неё закрыто то, что она
    пропускает, а из контекста страницы достижимо:

    - методы самого pydantic BaseModel у `site` и `theme` (`parse_file`
      читает произвольный файл, `model_construct` и подобные шаблону не
      нужны) — поля и собственные методы схем остаются;
    - любые атрибуты путей (`Path.write_text`, `read_text`);
    - методы `env`, которые строят окружение заново (`stamped` вызывает git
      в переданной папке).

    Фильтры и глобальные функции плагинов сайта — код самого сайта, ему
    доверяют так же, как `plugins/`.
    """

    def is_safe_attribute(self, obj: Any, attr: str, value: Any) -> bool:
        if isinstance(obj, PurePath):
            return False
        if isinstance(obj, (BaseModel, type)) and hasattr(BaseModel, attr):
            return False
        if isinstance(obj, BuildEnv) and attr in ("stamped", "named", "resolve"):
            return False
        return super().is_safe_attribute(obj, attr, value)


def make(theme_dir: Path, config: SiteConfig, hooks=None) -> Environment:
    """Собрать окружение Jinja2 для темы — в песочнице (`ThemeSandbox`).

    Фильтры и глобальные переменные плагинов (`hooks.filter`,
    `hooks.add_global`) добавляются последними, но встроенные не
    перекрывают: имя, которое уже есть, плагину не отдаётся.
    """
    env = ThemeSandbox(
        loader=ThemeLoader(theme_dir),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.globals["absolute"] = lambda url: f"https://{config.site.domain}{url}"
    env.filters["absolute"] = env.globals["absolute"]
    if hooks is not None:
        for name, handler in hooks.filters.items():
            env.filters.setdefault(name, handler)
        for name, value in hooks.globals.items():
            env.globals.setdefault(name, value)
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
        clean = paths.normalize(src)
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

        # Результат — Markup, автоэкранирование Jinja его не трогает, поэтому
        # всё, что пришло от сайта, экранируется здесь. Имя файла — тоже от
        # сайта: кавычка в имени мастера иначе разрывала бы атрибут src.
        parts: list[str] = ["<picture>"]
        for fmt, variants in rendition.sources.items():
            if fmt == "origin":
                continue
            srcset = ", ".join(f"/{escape(path)} {width}w" for width, path in variants)
            parts.append(f'<source type="image/{fmt}" srcset="{srcset}" sizes="{escape(sizes)}">')
        img = [
            f'src="/{escape(rendition.fallback)}"',
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
        # значения сайта уже на языке страницы: name_ru сильнее name
        "site": config.for_lang(page.lang),
        "theme": theme,
        "data": site.data,
        "nav": site.nav.get(page.lang, {}),
        "pages": site,
        "t": strings,
        "lang": page.lang,
        "languages": config.site.languages,
        "env": build_env or BuildEnv(),
    }
    # Страница по ключу, на языке текущей: `page_of('services')`,
    # `page_of('/')` — главная. Нет такой — None, тема решает сама.
    shared["page_of"] = lambda key, lang=None: site.page(key, lang or page.lang)
    shared["mod"] = Modules(env, shared, collector)
    shared["jsonld"] = lambda: Markup(jsonld.render(page, config, theme, site))
    # Языковые версии для <head>. Тот же набор, что уезжает в карту сайта:
    # разойтись они не имеют права, иначе поисковик считает набор
    # несогласованным и может отбросить его целиком.
    # На одноязычном сайте hreflang не нужен вовсе; на многоязычном он есть
    # у каждой страницы, даже без переводов: самоссылка говорит поисковику,
    # на каком языке страница, а x-default добавляется, только если есть
    # версия языка по умолчанию.
    shared["hreflang"] = sitemap.alternates(page, config) if len(config.site.languages) > 1 else []
    shared["picture"] = picture(media or Manifest(), collector)
    shared["media_url"] = media_url(media or Manifest(), collector)
    # Тот же адрес доступен и фильтром: в разметке чаще пишут
    # `{{ src|media_url }}`, чем вызов функции, и заставлять выбирать
    # одну из двух форм ради устройства движка незачем.
    env.filters["media_url"] = shared["media_url"]
    return shared
