"""Схема `theme.yaml` — паспорта темы.

Паспорт служит документацией и основой отчёта `check`, а не жёстким валидатором:
секция, которую тема не использует, — не ошибка, а строка в отчёте.

Здесь же тема объявляет две вещи, которые ядру знать не положено:
`requires` — какие блоки `site.yaml` ей нужны (`contact.phone` и подобное),
`types[*].jsonld` — какой разметкой размечается тип страницы.

Отдельно тема объявляет, чего она ждёт от самого движка: `heron` — версию,
`fields` — поля фронтматтера, к которым обращаются её шаблоны. Без этого
тема, написанная под новый движок, запускается на старом и разваливается
на каждой странице сообщением про опечатку во фронтматтере — хотя опечатки
нет, а есть несовпадение версий.
Ядро проверяет наличие и подставляет, не вникая в предметную область.

Третья часть паспорта - контракт для людей и программ, которые заполняют
страницы: поля каждого модуля (`modules.<имя>.fields`), секции типа с
обязательностью (`types.<тип>.sections`), виды категорий (`views`) и подсказки
`hint`/`help` на языках темы (`hint_ru`, `help_en`, как в `site.yaml`). Его читают
`heron check`, `heron describe`, опросник и студия. Тема без `fields` работает как
раньше: секции - свободный markdown.

Спецификация: docs/spec/20-data-contract.md, раздел 8; контракт полей -
docs/spec/21-engine.md, «Контракт темы».
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from heron.contracts.loader import build, read_yaml
from heron.core.paths import NAME_RE
from heron.messages import MsgError

LANG_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?\Z")

# Все формы секций, которые знает ядро. Тема называет их в `theme.yaml`
# (`uses: ["how:steps"]`), отчёт сверяет с фактом.
KINDS = (
    "prose",
    "list",
    "alert-list",
    "checklist",
    "two-lists",
    "steps",
    "table",
    "facts",
    "faq",
    "timeline",
    "callout",
    "gallery",
    "tabs",
)

# Тема вправе назвать ожидаемый формат секции: `recovery:timeline`.
# Расхождение — не ошибка сборки, а строка в отчёте: одна и та же секция
# на разных страницах бывает то таблицей, то прозой, и это нормально.
USES_RE = re.compile(r"^(?P<id>[a-z0-9][a-z0-9-]*)(?::(?P<kind>[a-z0-9][a-z0-9-]*))?\Z")

# Звёздочка вместо перечня: страница принимает любые секции. Так устроены
# статьи — у каждой свой набор блоков, и перечислять их в теме нечем.
ANY = "*"


# --- контракт полей: типы значений, места в markdown, подсказки ----------------

# Типы значений поля. `flag` - да или нет: `noindex`, «в меню»; остальное - из ТЗ STUDIO.
FIELD_TYPES = ("text", "markdown", "list", "image", "link", "number", "date", "enum", "ref", "flag")
FieldType = Literal[
    "text", "markdown", "list", "image", "link", "number", "date", "enum", "ref", "flag"
]

# Где значение поля лежит в markdown секции. Словарь общий для всех тем: по нему
# редактор находит значение в файле и пишет его обратно на то же место. Каждое
# место - форма, которую уже понимает разбор секций (core/parser/blocks.py).
MD_PLACES = (
    "body",  # всё содержимое секции
    "first-paragraph",  # первый абзац вводного блока
    "second-paragraph",  # второй абзац вводного блока
    "lead",  # абзацы до основного узла: списка, таблицы, групп ###, строк «ключ | значение»
    "quote",  # цитата «> …»
    "items",  # пункты маркированного списка «- …»
    "numbered",  # пункты нумерованного списка «1. …»
    "bold",  # жирный зачин пункта «**Термин.**»
    "tag",  # метка шага «[МЕТКА]» в начале жирного зачина
    "text",  # текст пункта после зачина или весь пункт
    "more",  # блоки пункта после первого абзаца: код, второй абзац
    "groups",  # группы «### Заголовок» с содержимым
    "heading",  # текст заголовка «###»
    "heading-id",  # якорь «{#id}» заголовка «###»
    "content",  # всё под заголовком группы
    "pairs",  # строки «ключ | значение»
    "key",  # левая часть строки «ключ | значение»
    "value",  # правая часть
    "table-head",  # шапка таблицы
    "table-rows",  # строки таблицы после разделителя
    "cells",  # ячейки строки таблицы
    "image",  # путь картинки «![подпись](путь)»
    "alt",  # подпись картинки в квадратных скобках
)

HINT_RE = re.compile(r"^(?P<key>hint|help|example)_(?P<lang>[a-z]{2}(?:-[a-z]{2})?)\Z")
FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*\Z")


def _split_hints(data: Any) -> Any:
    """`hint_ru`, `help_en`, `example_uk` - в `i18n[ключ][язык]`. Прочее не трогать."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    texts: dict[str, dict[str, Any]] = {}
    for name in list(out):
        match = HINT_RE.match(str(name))
        if match:
            texts.setdefault(match.group("key"), {})[match.group("lang")] = out.pop(name)
    for key, by_lang in texts.items():
        for lang, value in by_lang.items():
            if not isinstance(value, str):
                raise MsgError("site_th_hint_text", key=f"{key}_{lang}")
    if texts:
        out["i18n"] = texts
    return out


class Hinted(BaseModel):
    """Подсказки к полю, секции, модулю, виду или типу.

    `hint` - одна строка для наведения; `help` - что это, на что влияет на сайте
    и в поиске, хороший пример, частые ошибки; `example` - образец markdown.
    По языкам - суффиксом, как в site.yaml: `hint_ru`, `help_en`. Ключ без
    суффикса - для языков, у которых своего текста нет.
    """

    model_config = ConfigDict(extra="forbid")

    hint: str | None = None
    help: str | None = None
    example: str | None = None
    # тексты по языкам: hint_ru → i18n["hint"]["ru"]. Пишут суффиксом.
    i18n: dict[str, dict[str, str]] = Field(default_factory=dict, repr=False)

    @model_validator(mode="before")
    @classmethod
    def _hints(cls, data: Any) -> Any:
        return _split_hints(data)

    def text(self, key: str, lang: str | None = None) -> str | None:
        """Текст `hint`/`help`/`example` на языке `lang`; нет своего - ключ без суффикса."""
        if lang:
            own = self.i18n.get(key, {}).get(lang)
            if own:
                return own
        return getattr(self, key) or None

    def text_langs(self) -> set[str]:
        """Языки, на которых у этой записи есть хоть один текст."""
        return {lang for by_lang in self.i18n.values() for lang in by_lang}


class FieldSpec(Hinted):
    """Поле блока: имя, тип значения, место в markdown, ограничения, свойство schema.org.

    `md` - где значение лежит в markdown (словарь мест движка, `MD_PLACES`).
    У списка - `item` (тип каждого пункта) или `fields` (поля каждого пункта).
    Ограничения - длина (`min_length`, `max_length`), число пунктов (`min_items`,
    `max_items`), картинка (`ratio`, `min_width`), допустимые значения (`values`),
    тип страниц ссылки (`ref`). `schemaorg` - свойство разметки, в которое уходит
    значение: `Question.name`.
    """

    name: str
    type: FieldType
    required: bool = False
    md: str | None = None
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, gt=0)
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, gt=0)
    ratio: str | None = None
    min_width: int | None = Field(default=None, gt=0)
    values: list[str] = Field(default_factory=list)
    ref: str | None = None
    schemaorg: str | None = None
    item: FieldType | None = None
    fields: list[FieldSpec] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not FIELD_NAME_RE.match(v):
            raise MsgError("site_th_field_name", name=repr(v))
        return v

    @field_validator("md")
    @classmethod
    def _md(cls, v: str | None) -> str | None:
        if v is not None and v not in MD_PLACES:
            raise MsgError("site_th_field_md", md=repr(v), places=", ".join(MD_PLACES))
        return v

    @field_validator("ratio")
    @classmethod
    def _ratio(cls, v: str | None) -> str | None:
        if v is not None:
            _check_ratio(v)
        return v

    @model_validator(mode="after")
    def _shape(self) -> FieldSpec:
        where = repr(self.name)
        if self.type == "list":
            if (self.item is None) == (self.fields is None):
                raise MsgError("site_th_field_list", name=where)
            if self.item == "list":
                raise MsgError("site_th_field_list_item", name=where)
        elif self.item is not None or self.fields is not None:
            raise MsgError("site_th_field_not_list", name=where, type=self.type)
        if self.type == "enum" and not self.values:
            raise MsgError("site_th_field_enum", name=where)
        if self.values and self.type != "enum":
            raise MsgError("site_th_field_values", name=where, type=self.type)
        if (self.ratio or self.min_width) and self.type != "image":
            raise MsgError("site_th_field_image", name=where, type=self.type)
        if self.fields is not None:
            _unique([f.name for f in self.fields], "site_th_field_dup")
        return self


def _unique(names: list[str], key: str) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise MsgError(key, name=repr(name))
        seen.add(name)


def _check_ratio(ratio: str) -> None:
    parts = ratio.split(":")
    if len(parts) != 2 or not all(p.isdigit() and int(p) > 0 for p in parts):
        raise MsgError("site_th_ratio", ratio=repr(ratio))


class ModuleSpec(Hinted):
    """Модуль - форма блока: какие формы секций рисует и из каких полей состоит.

    `scope: section` - модуль рисует секцию (`mod.list('why')`), `page` - берёт
    данные из страницы и сайта (`mod.breadcrumbs()`), полей у него нет.
    `kinds` - формы секций (`20` §4.4), которые рисует модуль; не задано - форма
    с именем модуля, если такая есть. `fields` не задано - тема полей не описала.
    """

    scope: Literal["section", "page"] = "section"
    kinds: list[str] | None = None
    schemaorg: str | None = None
    fields: list[FieldSpec] | None = None

    @field_validator("kinds")
    @classmethod
    def _kinds(cls, v: list[str] | None) -> list[str] | None:
        for kind in v or []:
            if kind not in KINDS:
                raise MsgError("site_th_module_kind", kind=repr(kind), kinds=", ".join(KINDS))
        return v

    @field_validator("fields")
    @classmethod
    def _fields(cls, v: list[FieldSpec] | None) -> list[FieldSpec] | None:
        if v:
            _unique([f.name for f in v], "site_th_field_dup")
        return v


class SectionSpec(Hinted):
    """Секция типа страницы: обязательна ли и, если формы нет, свои поля.

    Ключ - якорь из `uses` (`intro`, `faq`) или `"*"` для «любых секций».
    Порядок секций - порядок `uses`.
    """

    required: bool = False
    fields: list[FieldSpec] | None = None

    @field_validator("fields")
    @classmethod
    def _fields(cls, v: list[FieldSpec] | None) -> list[FieldSpec] | None:
        if v:
            _unique([f.name for f in v], "site_th_field_dup")
        return v


class ViewSpec(Hinted):
    """Вид отображения категории: как её страница показывает страницы внутри."""


class ViewsSpec(Hinted):
    """Виды категории: ключ фронтматтера, который их выбирает, и вид по умолчанию.

    Перечень видов придумывает тема: сетка, список, таблица - то, что рисуют её
    шаблоны. Движок проверяет только, что вид по умолчанию есть в перечне.
    """

    key: str = "view"
    default: str
    options: dict[str, ViewSpec]

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not FIELD_NAME_RE.match(v):
            raise MsgError("site_th_field_name", name=repr(v))
        return v

    @model_validator(mode="after")
    def _default(self) -> ViewsSpec:
        if not self.options:
            raise MsgError("site_th_views_empty")
        for name in self.options:
            if not NAME_RE.match(name):
                raise MsgError("site_th_view_name", view=repr(name))
        if self.default not in self.options:
            raise MsgError(
                "site_th_view_default", view=repr(self.default), views=", ".join(self.options)
            )
        return self


class TypeSpec(Hinted):
    """Тип страницы: какие секции использует и чем размечается.

    `fields` - свои поля фронтматтера страниц этого типа: то, что шаблоны читают
    через `page.meta` (`eyebrow`, `status`, `metrics`). Описание - как у поля блока,
    только без `md`: значение лежит в SEO-блоке под именем поля. Имя не совпадает
    с полями движка (`title`, `slug`, `order`, …) - иначе ошибка контракта.
    """

    uses: list[str] = Field(default_factory=list)
    jsonld: list[str] = Field(default_factory=list)
    template: str | None = None
    sections: dict[str, SectionSpec] = Field(default_factory=dict)
    children_type: str | None = None
    views: ViewsSpec | None = None
    fields: list[FieldSpec] | None = None

    @field_validator("fields")
    @classmethod
    def _own_fields(cls, v: list[FieldSpec] | None) -> list[FieldSpec] | None:
        if not v:
            return v
        _unique([f.name for f in v], "site_th_field_dup")
        taken = reserved_fields()
        for spec in v:
            if spec.md is not None:
                raise MsgError("site_th_type_field_md", name=repr(spec.name))
            if spec.name in taken:
                raise MsgError(
                    "site_th_type_field_reserved",
                    name=repr(spec.name),
                    names=", ".join(sorted(taken)),
                )
        return v

    @field_validator("children_type", mode="before")
    @classmethod
    def _number_is_a_name(cls, v):
        return str(v) if isinstance(v, int) and not isinstance(v, bool) else v

    @model_validator(mode="after")
    def _sections_in_uses(self) -> TypeSpec:
        known = {
            section if section == ANY else USES_RE.match(section).group("id")  # type: ignore[union-attr]
            for section in self.uses
        }
        for name in self.sections:
            if name not in known:
                raise MsgError(
                    "site_th_section_unused", section=repr(name), uses=", ".join(self.uses)
                )
        return self

    @field_validator("uses")
    @classmethod
    def _uses(cls, v: list[str]) -> list[str]:
        names = []
        for section in v:
            if section == ANY:
                names.append(section)
                continue
            match = USES_RE.match(section)
            if not match:
                raise MsgError("site_th_section_name", section=repr(section))
            kind = match.group("kind")
            if kind and kind not in KINDS:
                raise MsgError(
                    "site_th_section_kind",
                    section=repr(section),
                    kind=repr(kind),
                    kinds=", ".join(KINDS),
                )
            names.append(match.group("id"))
        if len(set(names)) != len(names):
            raise MsgError("site_th_section_dup")
        return v


class LinkSpec(BaseModel):
    """Связь между страницами, объявленная темой.

    Ядро не знает, что значит «услуга относится к направлению». Оно знает,
    что поле `topics` содержит имена страниц типа `topic`, и умеет их найти,
    проверить и построить обратную ссылку. Предметная область остаётся
    в теме, механика в ядре.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    type: str | None = None
    back: str | None = None
    on: str | None = None
    required: int = 0

    @field_validator("field", "back", "on")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is not None and not NAME_RE.match(v):
            raise MsgError("site_th_relation_name")
        return v


class ImagesSpec(BaseModel):
    """Что тема хочет от картинок.

    Пропорции просит тема: это она решает, что карточка каталога квадратная,
    а обложка статьи широкая. Ядро вписывает в них мастер, добивая
    прозрачными полями, а фотографии режет кропом.

    `crop` - исключения: пути, которые кропать всё равно, даже если
    прозрачность у них есть. Пишутся началом пути: `media/bio/`.

    `as_is` - пути, которые не трогать вовсе: файл копируется в сборку как
    есть, без вариантов и конвертаций. Скан документа не иллюстрация: его
    открывают целиком и в одном виде, адаптивные размеры ему не нужны, а
    два десятка вариантов на каждый скан - работа впустую и минуты сборки.
    Пишется так же, началом пути: `media/docs/`.
    """

    model_config = ConfigDict(extra="forbid")

    widths: list[int] = Field(default_factory=lambda: [400, 800, 1200, 1600])
    ratios: list[str] = Field(default_factory=lambda: ["1:1", "16:9", "4:3"])
    formats: list[str] = Field(default_factory=lambda: ["avif", "webp"])
    crop: list[str] = Field(default_factory=list)
    as_is: list[str] = Field(default_factory=list)
    # Ширина запасного файла в исходном формате (png/jpg) — того, что идёт
    # в `<img src>` для браузеров без avif и webp. Он один на пропорцию и не
    # шире этого: современный браузер его не грузит вовсе, а PNG иллюстрации
    # на 1600 px весит полтора мегабайта мёртвого груза в каждой сборке.
    fallback_width: int = Field(default=800, gt=0)
    # Ширина запасного файла для обложек (og:image, JSON-LD): Google советует
    # от 1200 px и хорошо понимает JPEG. Режется только у мастеров-обложек и
    # не шире самого кадра.
    cover_width: int = Field(default=1200, gt=0)

    @field_validator("ratios")
    @classmethod
    def _ratios(cls, v: list[str]) -> list[str]:
        for ratio in v:
            _check_ratio(ratio)
        return v

    @field_validator("widths")
    @classmethod
    def _widths(cls, v: list[int]) -> list[int]:
        if not v or any(width <= 0 for width in v):
            raise MsgError("site_th_widths")
        return sorted(set(v))


class ThemeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    version: str = "0.1"
    title: str = ""
    # Языки подсказок темы (`hint_ru`, `help_en`). Не задано - языки суффиксов,
    # которые встречаются в подсказках.
    languages: list[str] = Field(default_factory=list)
    # Список имён (как раньше) или описание каждого модуля с полями.
    modules: list[str] | dict[str, ModuleSpec] = Field(default_factory=list)
    types: dict[str, TypeSpec] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    heron: str | None = None
    fields: list[str] = Field(default_factory=list)
    links: list[LinkSpec] = Field(default_factory=list)
    images: ImagesSpec = Field(default_factory=ImagesSpec)
    forms: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _human_yaml(cls, data):
        """`version: 0.1` и `404:` — не ошибки автора, а особенности YAML.

        Число превращаем в строку, числовые ключи типов — тоже: падать
        на этом значит воевать с человеком вместо того, чтобы ему помогать.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "version" in data and not isinstance(data["version"], str):
            data["version"] = str(data["version"])
        types = data.get("types")
        if isinstance(types, dict):
            data["types"] = {str(key): value for key, value in types.items()}
        # YAML 1.1 читает голый ключ `on:` как булево true. В связях это
        # ключ «у страниц какого типа поле ожидается», и без этой правки
        # `on: service` в theme.yaml падал бы непонятной ошибкой про ключи.
        links = data.get("links")
        if isinstance(links, list):
            data["links"] = [
                {("on" if key is True else key): value for key, value in item.items()}
                if isinstance(item, dict)
                else item
                for item in links
            ]
        return data

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise MsgError("site_th_name")
        return v

    @field_validator("modules")
    @classmethod
    def _modules(cls, v: list[str] | dict[str, ModuleSpec]) -> list[str] | dict[str, ModuleSpec]:
        for module in v:
            if not NAME_RE.match(module):
                raise MsgError("site_th_module_name", module=repr(module))
        return v

    @field_validator("languages")
    @classmethod
    def _languages(cls, v: list[str]) -> list[str]:
        for lang in v:
            if not LANG_RE.match(lang):
                raise MsgError("site_th_language", lang=repr(lang))
        return v

    @model_validator(mode="after")
    def _references(self) -> ThemeConfig:
        """Тип страниц внутри категории и тип ссылки - из `types` этой темы."""
        for name, spec in self.types.items():
            if spec.children_type and spec.children_type not in self.types:
                raise MsgError(
                    "site_th_children_type",
                    type=repr(name),
                    children=repr(spec.children_type),
                    known=", ".join(self.types),
                )
        for where, spec in _all_fields(self):
            if spec.type == "ref" and spec.ref and spec.ref not in self.types:
                raise MsgError(
                    "site_th_field_ref",
                    field=where,
                    ref=repr(spec.ref),
                    known=", ".join(self.types),
                )
        return self

    @property
    def module_specs(self) -> dict[str, ModuleSpec]:
        """Модули с описанием; тема со списком имён - описания пустые."""
        if isinstance(self.modules, dict):
            return self.modules
        return {name: ModuleSpec() for name in self.modules}

    @property
    def described(self) -> bool:
        """Тема описала поля: хотя бы у одного модуля или типа есть `fields`."""
        modules = isinstance(self.modules, dict) and any(
            spec.fields is not None for spec in self.modules.values()
        )
        return modules or any(spec.fields for spec in self.types.values())

    def hint_langs(self) -> list[str]:
        """Языки подсказок: `languages`, иначе суффиксы, встречающиеся в подсказках."""
        if self.languages:
            return list(self.languages)
        found: set[str] = set()
        for _, item in hinted(self):
            found |= item.text_langs()
        return sorted(found)

    def module_for(self, kind: str) -> str | None:
        """Модуль, который рисует форму секции `kind`."""
        for name, spec in self.module_specs.items():
            if kind in kinds_of(name, spec):
                return name
        return None

    def sections_of(self, page_type: str) -> list[str]:
        spec = self.types.get(page_type)
        if not spec:
            return []
        return [
            USES_RE.match(name).group("id")  # type: ignore[union-attr]
            for name in spec.uses
            if name != ANY
        ]

    def any_sections(self, page_type: str) -> bool:
        """Тема согласна на любые секции этого типа страниц."""
        spec = self.types.get(page_type)
        return bool(spec) and ANY in spec.uses

    def formats_of(self, page_type: str) -> dict[str, str]:
        """Какой формат секции тема считает ожидаемым. Пусто — любой."""
        spec = self.types.get(page_type)
        if not spec:
            return {}
        out: dict[str, str] = {}
        for name in spec.uses:
            if name == ANY:
                continue
            match = USES_RE.match(name)
            if match and match.group("kind"):
                out[match.group("id")] = match.group("kind")
        return out


def reserved_fields() -> set[str]:
    """Ключи фронтматтера, которые знает движок: своё поле типа их не повторяет."""
    from heron.contracts import fields as service
    from heron.contracts.frontmatter import PageMeta

    names = set(PageMeta.model_fields)
    names |= {spec.key for spec in service.SERVICE if spec.where == "frontmatter" and spec.key}
    names |= {spec.name for spec in service.SERVICE}
    names |= {"view", "schema", "translation", "redirect_from", "gone", "extra", "lang", "key"}
    names |= {"og_image_alt", "twitter_title", "twitter_description", "twitter_image"}
    names |= {"canonical", "robots", "main", "additional", "total"}
    return names


def kinds_of(name: str, spec: ModuleSpec) -> list[str]:
    """Формы секций, которые рисует модуль: `kinds`, иначе форма с его именем."""
    if spec.kinds is not None:
        return list(spec.kinds)
    if spec.scope == "section" and name in KINDS:
        return [name]
    return []


def _walk_fields(prefix: str, fields: list[FieldSpec] | None):
    for spec in fields or []:
        where = f"{prefix}.fields.{spec.name}"
        yield where, spec
        yield from _walk_fields(where, spec.fields)


def _all_fields(theme: ThemeConfig):
    for name, module in theme.module_specs.items():
        yield from _walk_fields(f"modules.{name}", module.fields)
    for type_name, spec in theme.types.items():
        yield from _walk_fields(f"types.{type_name}", spec.fields)
        for section, info in spec.sections.items():
            yield from _walk_fields(f"types.{type_name}.sections.{section}", info.fields)


def hinted(theme: ThemeConfig):
    """Всё, чему положена подсказка: (путь в theme.yaml, запись)."""
    for name, spec in theme.types.items():
        yield f"types.{name}", spec
        for section, info in spec.sections.items():
            yield f"types.{name}.sections.{section}", info
        if spec.views:
            for view, option in spec.views.options.items():
                yield f"types.{name}.views.options.{view}", option
    if isinstance(theme.modules, dict):
        for name, module in theme.modules.items():
            yield f"modules.{name}", module
    yield from _all_fields(theme)


def missing_hints(theme: ThemeConfig) -> list[str]:
    """Чему не хватает `hint` на каком из языков темы: `modules.faq.fields.items.fields.q (en)`.

    Проверяется только тема с описанием полей: у старой темы подсказок нет вовсе,
    и это не ошибка, а предупреждение `heron check`.
    """
    if not theme.described:
        return []
    langs = theme.hint_langs() or [None]
    out: list[str] = []
    for where, item in hinted(theme):
        lacking = [lang for lang in langs if not item.text("hint", lang)]
        if lacking:
            tail = ", ".join(lang for lang in lacking if lang)
            out.append(f"{where} ({tail})" if tail else where)
    return out


def load_theme(path: Path) -> ThemeConfig:
    """Прочитать и проверить `theme.yaml`."""
    data = read_yaml(path, code="E041")
    _engine_fields(data, path)
    return build(ThemeConfig, data, path, code="E041")


def _engine_fields(data: Any, path: Path) -> None:
    """`fields` верхнего уровня - имена полей движка (строки), не описание полей блока.

    Автор темы 0.3 по ошибке пишет туда описание полей блока (`- name: … type: …`):
    вместо «Input should be a valid string» - E023 с объяснением, куда это перенести.
    """
    from heron.core.errors import HeronError
    from heron.messages import Msg

    if not isinstance(data, dict) or "fields" not in data:
        return
    value = data["fields"]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return
    raise HeronError(
        code="E023",
        message=Msg("site_th_fields_shape"),
        path=str(path),
        hint=Msg("site_th_fields_shape_hint"),
    )
