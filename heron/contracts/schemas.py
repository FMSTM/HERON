"""JSON Schema контрактов и реестр кодов ошибок.

Чистые функции без click: `heron schema` (шов S2.T6) и scaffold (S2.T4)
берут отсюда готовые тексты. Вывод детерминирован: ключи отсортированы,
отступ 2, не-ASCII без экранирования, перевод строки в конце.

Схема принимает то же, что модель. Осознанные расхождения:
- необязательные поля фронтматтера допускают null (пустой ключ модель отбрасывает);
- `type`, `children_type`, `slug` и `version` темы допускают число (модель приводит к строке);
- правила в регэкспах моделей (слаг, домен, язык) в схему не вынесены;
- значения по языкам в site.yaml (`name_ru`) описаны patternProperties из LOCALIZED.

Описания (`description`) и названия ошибок - на двух языках, ru и en: источник
(докстринги моделей) русский, английский текст лежит в таблице `EN` ниже; язык
выбирает вызывающий (`--notes`, `HERON_NOTES`, `build.notes`, `schema --lang`).
Структура, ключи, `$id` и порядок байт от языка не зависят.

Спецификация: docs/ru/spec/21-engine.md, раздел 10 («heron schema»);
формат `$id` — docs/ru/spec/23-distribution.md, «Версия контракта».
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import heron
from heron.contracts.frontmatter import TRANSLATION_STATES, PageMeta
from heron.contracts.site import LOCALIZED, SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.errors import ERRORS, SCHEMA_CODES
from heron.setup.answers import Answers

DRAFT = "https://json-schema.org/draft/2020-12/schema"
BASE = "https://sitebuilder.heron.software/schema"

LANGS = ("ru", "en")

FILES = (
    "site.schema.json",
    "theme.schema.json",
    "frontmatter.schema.json",
    "setup.schema.json",
    "errors.json",
    "describe.schema.json",
)

# Английские описания. Ключ - файл и JSON Pointer русского текста в схеме; значение -
# (первые 10 знаков sha256 русского текста, английский текст). Хеш нужен тесту:
# правка русского докстринга без правки перевода его ломает, и английский комплект
# не отстаёт молча.
EN: dict[str, tuple[str, str]] = {
    "site.schema.json#/$defs/AnalyticsBlock/description": (
        "55fa9d36cf",
        "Public counter identifiers.\n\n"
        "These are not secrets: they are visible in the source of any page and are read\n"
        "by crawlers. That is why they belong here, next to the domain and the languages,\n"
        "and not in environment variables: otherwise the same site built on two machines\n"
        "would get different counters, and nobody would know why.\n\n"
        "They are inserted into pages only when the build environment allows it:\n"
        "on dev a counter must not spoil the statistics of the live site.",
    ),
    "site.schema.json#/$defs/FormSpec/description": (
        "fbb8c7b0c3",
        "Description of a form. The engine does not accept the form - heron-relay does.\n\n"
        "The engine needs the description to hand the theme the set of fields and to fail\n"
        "if the theme draws a form that is not in the config.",
    ),
    "site.schema.json#/$defs/NavBlock/description": (
        "80e6526d14",
        "The menu. Its content is free: the theme invents the names of the groups.",
    ),
    "site.schema.json#/$defs/NginxBlock/description": (
        "592e4fb59e",
        "The nginx config that the engine builds together with the site.\n\n"
        "`hash_sizes` is obsolete and does nothing. 301 and 410 are now exact\n"
        "locations, not string maps: the hash tables of the maps that\n"
        "map_hash_bucket_size and map_hash_max_size were sized for are no longer built.\n"
        "The key is accepted so that existing site.yaml files build without changes.\n\n"
        "`cache` - browser cache times for theme files and resources.",
    ),
    "site.schema.json#/$defs/CacheBlock/description": (
        "ef38a53998",
        "Browser cache times for theme files and resources (22 §5).\n\n"
        "`versioned` - files with the content hash in the name (`site.0123abcdef.css`):\n"
        "under such a name the content never changes, so the time is long and\n"
        "comes with `immutable`. `assets` and `media` - the same files under their plain\n"
        "names, without a hash: kept for old pages in a cache and for external links.\n\n"
        "Pages are not here: they always get `no-cache`, otherwise an edit of the text and\n"
        "the new names of theme files would reach the visitor late.",
    ),
    "site.schema.json#/$defs/SchemaException/description": (
        "a8589520d1",
        "A deliberate human decision to keep a schema markup check finding on prod.",
    ),
    "site.schema.json#/$defs/SiteBlock/description": (
        "b900fe3389",
        "Who we are and in how many languages.",
    ),
    "site.schema.json#/description": (
        "cb75156a2b",
        "The whole `site.yaml`. Unknown top-level blocks are kept as they are. "
        "A rule the schema does not express: the language suffix of a key "
        "(`name_ru`, `title_suffix_ru`) must be one of `site.languages`, "
        "otherwise the error is `E011`.",
    ),
    "theme.schema.json#/$defs/ImagesSpec/description": (
        "18ab816db1",
        "What the theme wants from images.\n\n"
        "The theme asks for the proportions: it decides that a catalog card is square\n"
        "and an article cover is wide. The core fits the master into them, padding it\n"
        "with transparent margins, and cuts photographs by cropping.\n\n"
        "`crop` - exceptions: paths to crop anyway, even if they have transparency.\n"
        "Written as the beginning of a path: `media/bio/`.\n\n"
        "`as_is` - paths not to touch at all: the file is copied into the build as it is,\n"
        "with no variants and no conversions. A scan of a document is not an illustration:\n"
        "it is opened whole and in one form, it needs no responsive sizes, and two dozen\n"
        "variants of every scan are wasted work and minutes of build time.\n"
        "Written the same way, as the beginning of a path: `media/docs/`.",
    ),
    "theme.schema.json#/$defs/FieldSpec/description": (
        "b213c76d48",
        "A field of a block: name, value type, place in markdown, limits, schema.org property.\n\n"
        "`md` - where the value lies in markdown (the engine vocabulary of places, `MD_PLACES`).\n"
        "A list has `item` (the type of every item) or `fields` (the fields of every item).\n"
        "Limits - length (`min_length`, `max_length`), number of items (`min_items`,\n"
        "`max_items`), picture (`ratio`, `min_width`), allowed values (`values`),\n"
        "the page type of a link (`ref`). `schemaorg` - the markup property the value\n"
        "goes into: `Question.name`.\n\n"
        "`translatable` - only for an own field of a type (`types.<type>.fields`) without text\n"
        "(a picture, a number, a date, an enumeration, a link to a page, a flag): its own value\n"
        "in every language, no own value - the value of the main language. For a text field and\n"
        "a block field it changes nothing (they already have their own text in every language):\n"
        "`heron check` warns.",
    ),
    "theme.schema.json#/$defs/ModuleSpec/description": (
        "8863f03c91",
        "A module is the form of a block: which section forms it draws and which fields it has.\n\n"
        "`scope: section` - the module draws a section (`mod.list('why')`), `page` - it takes\n"
        "data from the page and the site (`mod.breadcrumbs()`), it has no fields.\n"
        "`kinds` - the section forms (`20` §4.4) the module draws; not set - the form\n"
        "with the name of the module, if there is one. `fields` not set - the theme has not\n"
        "described the fields.",
    ),
    "theme.schema.json#/$defs/SectionSpec/description": (
        "6262d12581",
        "A section of a page type: whether it is required and, if it has no form,\n"
        "its own fields.\n\n"
        'The key is an anchor from `uses` (`intro`, `faq`) or `"*"` for "any sections".\n'
        "The order of sections is the order of `uses`.",
    ),
    "theme.schema.json#/$defs/ViewSpec/description": (
        "1d6835f0f0",
        "A view of a category: how its page shows the pages inside.",
    ),
    "theme.schema.json#/$defs/ViewsSpec/description": (
        "61d7622500",
        "Views of a category: the front matter key that picks them and the default view.\n\n"
        "The theme invents the list of views: a grid, a list, a table - what its templates\n"
        "draw. The engine only checks that the default view is in the list.",
    ),
    "describe.schema.json#/$defs/Field/description": (
        "acd915cb0e",
        "A field of a theme block: type, place in markdown (`md`), limits, schema.org property.",
    ),
    "describe.schema.json#/$defs/Module/description": (
        "603801e450",
        "A theme module - the form of a block; `fields` null - the theme has not described fields.",
    ),
    "describe.schema.json#/$defs/Section/description": (
        "27702727d0",
        'A section of a type in the order of `uses`; `any` - "any blocks" (`*`).',
    ),
    "describe.schema.json#/$defs/ServiceField/description": (
        "df20cb79cd",
        "A service field of a page or a block: the engine describes it, "
        "it is the same for any theme.",
    ),
    "describe.schema.json#/$defs/Site/description": (
        "2af138b608",
        "Defaults from site.yaml in the language `lang`.",
    ),
    "describe.schema.json#/$defs/Type/description": (
        "2ede031c25",
        "A page type: the sections in the order of `uses` and own front matter fields "
        "(`fields`, without `md`).",
    ),
    "describe.schema.json#/$defs/Views/description": (
        "2446208419",
        "Category views: the front matter key, the default view, the list of the theme views.",
    ),
    "describe.schema.json#/description": (
        "2f36c81e2a",
        "The output of `heron describe --json`: the contract of the site theme and the service "
        "fields of the engine. Every key is always there; what is missing is null or an empty "
        "list. Hints (`hint`, `help`, `example`) are in the language `lang`.",
    ),
    "theme.schema.json#/$defs/LinkSpec/description": (
        "3bc9f9dcab",
        "A relation between pages declared by the theme.\n\n"
        'The core does not know what "a service belongs to a direction" means - it knows\n'
        "that the field `topics` holds the names of pages of the type `topic`, and it can\n"
        "find them, check them and build the back reference. The subject area stays\n"
        "in the theme, the mechanics in the core.",
    ),
    "theme.schema.json#/$defs/TypeSpec/description": (
        "3688368fd1",
        "A page type: which sections it uses and what markup it gets.\n\n"
        "`fields` - own front matter fields of pages of this type: what templates read\n"
        "via `page.meta` (`eyebrow`, `status`, `metrics`). The description is as for a block\n"
        "field, only without `md`: the value lives in the SEO block under the field name. The\n"
        "name does not coincide with engine fields (`title`, `slug`, `order`, …) - otherwise\n"
        "a contract error.",
    ),
    "theme.schema.json#/description": (
        "95cc13f8ff",
        "The key `on` in `links` is a string. YAML 1.1 (PyYAML) reads a bare `on:` as the "
        "boolean true, the engine takes this into account; an editor with YAML 1.2 reads "
        "`on` as a string.",
    ),
    "frontmatter.schema.json#/description": (
        "11cc3cff34",
        "Page front matter: YAML between `---`. `title`, `h1` and `description` are required. "
        "Relation fields declared by the theme and any fields of your own (`page.meta.<field>`) "
        "are allowed as additional ones. An optional field may be left empty: an empty value "
        'means "not filled in". '
        "Rules the schema does not express. "
        "slug: Latin letters, digits, hyphen; the whole slug consists of these characters, "
        "a trailing newline is not allowed. "
        "date is the publication date, `YYYY-MM-DD`; updated is the date of the last edit, "
        "`YYYY-MM-DD`. A date later than the moment of the build is a warning, with `--strict` "
        "an error. An update earlier than the publication is a warning too. "
        "redirect_from: a list of paths from the root, normalization is `20` §2; "
        "a path must not coincide with an existing URL (`E009`). "
        "translation: only `pending` - the translation is not ready: a draft build shows "
        "the page with a banner, a production build does not publish it in this language; "
        "when the translation is ready, there is no key.",
    ),
    "setup.schema.json#/$defs/CacheAnswers/description": (
        "55582526c1",
        "Browser cache times - the nginx.cache keys in site.yaml (22 §5).",
    ),
    "setup.schema.json#/$defs/AnalyticsAnswers/description": (
        "b4add0701c",
        "Public counter numbers: visible in the source of a page, they are not secrets.",
    ),
}

# Правила, которых схема не выражает, — словами контракта (20 §4.2).
FRONTMATTER_RULES = (
    "Фронтматтер страницы: YAML между `---`. Обязательны `title`, `h1`, `description`. "
    "Поля связей, объявленные темой, и любые свои поля (`page.meta.<поле>`) допускаются "
    "как дополнительные. Необязательное поле можно оставить пустым: пустое значение "
    "значит «не заполнено». "
    "Правила, которых схема не выражает. "
    "slug: латиница, цифры, дефис; слаг целиком из этих знаков, перевод строки "
    "в конце не допускается. "
    "date - дата публикации, `ГГГГ-ММ-ДД`; updated - дата последней правки, "
    "`ГГГГ-ММ-ДД`. Дата позже момента сборки - предупреждение, при `--strict` - ошибка. "
    "Обновление раньше публикации - тоже предупреждение. "
    "redirect_from: список путей от корня, нормализация - `20` §2; "
    "путь не должен совпадать с существующим URL (`E009`). "
    "translation: только `pending` - перевод не готов: черновая сборка показывает "
    "страницу с плашкой, боевая не публикует её на этом языке; перевод готов - ключа нет."
)

THEME_NOTE = (
    "Ключ `on` в `links` - строка. YAML 1.1 (PyYAML) читает голый `on:` как булево true, "
    "движок это учитывает; редактор с YAML 1.2 читает `on` строкой."
)

SITE_NOTE = (
    "Правило, которого схема не выражает: суффикс языка у ключа (`name_ru`, `title_suffix_ru`) "
    "должен быть из `site.languages`, иначе ошибка `E011`."
)

_META = ("title", "description", "default", "examples")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def check_lang(lang: str) -> str:
    if lang not in LANGS:
        raise ValueError(f"schema language {lang!r}: ru and en are available")
    return lang


def _translate(node: Any, name: str, path: str = "") -> Any:
    """Русские описания схемы `name` - английскими по таблице `EN`; прочее как есть.

    Строки без перевода остаются русскими: тест следит, чтобы таких не было.
    """
    if isinstance(node, dict):
        return {key: _translate(value, name, f"{path}/{key}") for key, value in node.items()}
    if isinstance(node, list):
        return [_translate(value, name, f"{path}/{i}") for i, value in enumerate(node)]
    if isinstance(node, str) and _CYRILLIC.search(node):
        found = EN.get(f"{name}#{path}")
        return found[1] if found else node
    return node


def _nullable(prop: dict[str, Any]) -> dict[str, Any]:
    """Свойство, которое можно оставить пустым (`ключ:` без значения)."""
    options = prop.get("anyOf")
    if options is not None and any(o.get("type") == "null" for o in options):
        return prop
    meta = {k: v for k, v in prop.items() if k in _META}
    rest = {k: v for k, v in prop.items() if k not in _META}
    return {**meta, "anyOf": [rest, {"type": "null"}]}


def _number_or(prop: dict[str, Any], kind: str = "number") -> dict[str, Any]:
    """Строка, которую модель принимает и числом: `type: 404`, `version: 0.1`."""
    meta = {k: v for k, v in prop.items() if k in _META}
    options = prop.get("anyOf") or [{k: v for k, v in prop.items() if k not in _META}]
    return {**meta, "anyOf": [*options, {"type": kind}]}


def _id_prefix() -> str:
    major, minor, *_ = heron.__version__.split(".")
    return f"{BASE}/{major}.{minor}"


def _finish(data: dict[str, Any], name: str, lang: str = "ru") -> dict[str, Any]:
    """Добавляет `$schema`, `$id` и `x-heron-version`; описания - на языке `lang`."""
    if check_lang(lang) == "en":
        data = _translate(data, name)
    data["$schema"] = DRAFT
    data["$id"] = f"{_id_prefix()}/{name}"
    data["x-heron-version"] = heron.__version__
    return data


def site_schema(lang: str = "ru") -> dict[str, Any]:
    """site.yaml. Значения по языкам (`name_ru`, 20 §5) — patternProperties из LOCALIZED."""
    data = SiteConfig.model_json_schema()
    for block, keys in LOCALIZED.items():
        owner = data["$defs"][{"site": "SiteBlock", "seo": "SeoBlock"}[block]]
        props = owner["properties"]
        props.pop("i18n", None)
        owner["patternProperties"] = {
            f"^{key}_[a-z]{{2}}(-[a-z]{{2}})?$": {
                k: v for k, v in props[key].items() if k not in _META
            }
            for key in keys
        }
    note = SITE_NOTE
    data["description"] = f"{data['description']} {note}" if data.get("description") else note
    return _finish(data, "site.schema.json", lang)


# Подсказки по языкам (`hint_ru`, `help_en`, `example_uk`) - как значения site.yaml:
# модель собирает их в `i18n`, схема описывает их так, как их пишет автор темы.
HINT_PATTERN = "^(hint|help|example)_[a-z]{2}(-[a-z]{2})?$"


def theme_schema(lang: str = "ru") -> dict[str, Any]:
    data = ThemeConfig.model_json_schema()
    for owner in data["$defs"].values():
        props = owner.get("properties", {})
        if "i18n" in props:
            props.pop("i18n")
            owner["patternProperties"] = {HINT_PATTERN: {"type": "string"}}
    data["properties"]["version"] = _number_or(data["properties"]["version"])
    data["description"] = THEME_NOTE
    return _finish(data, "theme.schema.json", lang)


def setup_schema(lang: str = "ru") -> dict[str, Any]:
    return _finish(Answers.model_json_schema(), "setup.schema.json", lang)


# --- describe.schema.json: вывод `heron describe --json` (21 §10) ----------------

_TEXT = {"type": ["string", "null"]}
_INT = {"type": ["integer", "null"]}
_STR_NULL = {"type": ["string", "null"]}
_STRINGS = {"type": "array", "items": {"type": "string"}}


def _object(props: dict[str, Any], description: str | None = None) -> dict[str, Any]:
    """Объект со всеми ключами обязательными: describe отдаёт каждый ключ всегда."""
    out: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(props),
        "properties": props,
    }
    if description:
        out["description"] = description
    return out


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/$defs/{name}"}


def _array(name: str) -> dict[str, Any]:
    return {"type": "array", "items": _ref(name)}


DESCRIBE_TEXT = (
    "Вывод `heron describe --json`: контракт темы сайта и служебные поля движка. "
    "Каждый ключ есть всегда; чего нет - null или пустой список. Подсказки (`hint`, "
    "`help`, `example`) - на языке `lang`."
)


def describe_schema(lang: str = "ru") -> dict[str, Any]:
    """Схема вывода `heron describe --json`. Модели нет: объект собирает core/describe.py."""
    from heron.contracts.fields import GROUPS, PLACES
    from heron.contracts.theme import FIELD_TYPES, MD_PLACES

    field_types = {"enum": list(FIELD_TYPES)}
    hints = {"hint": _TEXT, "help": _TEXT}
    field = _object(
        {
            "name": {"type": "string"},
            "type": field_types,
            "required": {"type": "boolean"},
            "md": {"anyOf": [{"enum": list(MD_PLACES)}, {"type": "null"}]},
            "min_length": _INT,
            "max_length": _INT,
            "min_items": _INT,
            "max_items": _INT,
            "ratio": _STR_NULL,
            "min_width": _INT,
            "values": _STRINGS,
            "ref": _STR_NULL,
            "schemaorg": _STR_NULL,
            "item": {"anyOf": [field_types, {"type": "null"}]},
            "fields": {"anyOf": [_array("Field"), {"type": "null"}]},
            "translatable": {"type": "boolean"},
            "example": _TEXT,
            **hints,
        },
        "Поле блока темы: тип, место в markdown (`md`), ограничения, свойство schema.org.",
    )
    service = _object(
        {
            "name": {"type": "string"},
            "type": field_types,
            "group": {"enum": list(GROUPS)},
            "scope": {"enum": ["page", "section"]},
            "where": {"enum": list(PLACES)},
            "key": _STR_NULL,
            "required": {"type": "boolean"},
            "max_length": _INT,
            "min_width": _INT,
            "item": {"anyOf": [field_types, {"type": "null"}]},
            "values": _STRINGS,
            "only": _STR_NULL,
            "default": {},
            "default_from": _STR_NULL,
            "inherits": {"type": "boolean"},
            "hint": {"type": "string"},
            "help": {"type": "string"},
        },
        "Служебное поле страницы или блока: его описывает движок, у любой темы одно и то же.",
    )
    section = _object(
        {
            "id": {"type": "string"},
            "any": {"type": "boolean"},
            "kind": _STR_NULL,
            "module": _STR_NULL,
            "required": {"type": "boolean"},
            "fields": {"anyOf": [_array("Field"), {"type": "null"}]},
            **hints,
        },
        "Секция типа в порядке `uses`; `any` - «любые блоки» (`*`).",
    )
    view = _object({"name": {"type": "string"}, **hints})
    views = _object(
        {
            "key": {"type": "string"},
            "default": {"type": "string"},
            "options": _array("View"),
            **hints,
        },
        "Виды категории: ключ фронтматтера, вид по умолчанию, перечень видов темы.",
    )
    page_type = _object(
        {
            "name": {"type": "string"},
            "template": {"type": "string"},
            "jsonld": _STRINGS,
            "children_type": _STR_NULL,
            "views": {"anyOf": [_ref("Views"), {"type": "null"}]},
            "fields": _array("Field"),
            "sections": _array("Section"),
            **hints,
        },
        "Тип страницы: секции по порядку `uses` и свои поля фронтматтера (`fields`, без `md`).",
    )
    kind = _object({"kind": {"type": "string"}, "class": _STR_NULL, "auto": {"type": "boolean"}})
    module = _object(
        {
            "name": {"type": "string"},
            "scope": {"enum": ["section", "page"]},
            "kinds": _array("Kind"),
            "schemaorg": _STR_NULL,
            "fields": {"anyOf": [_array("Field"), {"type": "null"}]},
            "example": _TEXT,
            **hints,
        },
        "Модуль темы - форма блока; `fields` null - тема полей не описала.",
    )
    site = _object(
        {
            "name": _STR_NULL,
            "languages": _STRINGS,
            "default_lang": {"type": "string"},
            "title_suffix": {"type": "string"},
            "og_default_image": _STR_NULL,
            "menu": _STRINGS,
            "updated_from": {"type": "string"},
        },
        "Значения по умолчанию из site.yaml на языке `lang`.",
    )
    theme = _object(
        {
            "name": {"type": "string"},
            "title": {"type": "string"},
            "version": {"type": "string"},
            "heron": _STR_NULL,
            "languages": _STRINGS,
            "described": {"type": "boolean"},
        }
    )
    data = _object(
        {
            "$schema": {"type": "string"},
            "heron": {"type": "string"},
            "lang": {"type": "string"},
            "selected": {
                "anyOf": [
                    _object({"kind": {"enum": ["type", "module"]}, "name": {"type": "string"}}),
                    {"type": "null"},
                ]
            },
            "site": {"anyOf": [_ref("Site"), {"type": "null"}]},
            "theme": _ref("Theme"),
            "groups": {
                "type": "array",
                "items": _object({"name": {"enum": list(GROUPS)}, "title": {"type": "string"}}),
            },
            "service": _object({"page": _array("ServiceField"), "section": _array("ServiceField")}),
            "md_places": {
                "type": "array",
                "items": _object({"name": {"enum": list(MD_PLACES)}, "hint": {"type": "string"}}),
            },
            "types": _array("Type"),
            "modules": _array("Module"),
        },
        DESCRIBE_TEXT,
    )
    data["$defs"] = {
        "Field": field,
        "Kind": kind,
        "Module": module,
        "Section": section,
        "ServiceField": service,
        "Site": site,
        "Theme": theme,
        "Type": page_type,
        "View": view,
        "Views": views,
    }
    return _finish(data, "describe.schema.json", lang)


def frontmatter_schema(lang: str = "ru") -> dict[str, Any]:
    data = PageMeta.model_json_schema()
    data["additionalProperties"] = True
    required = set(data.get("required", []))
    props = data["properties"]
    for name, prop in props.items():
        if name not in required:
            props[name] = _nullable(prop)
    for name in ("type", "children_type", "slug"):
        props[name] = _number_or(props[name], "integer")
    props["translation"] = {"anyOf": [{"enum": list(TRANSLATION_STATES)}, {"type": "null"}]}
    data["description"] = FRONTMATTER_RULES
    return _finish(data, "frontmatter.schema.json", lang)


def errors_registry(lang: str = "ru") -> dict[str, Any]:
    """Реестр кодов: названия на языке `lang` (английские - `messages.TITLES`)."""
    from heron.messages import title

    check_lang(lang)
    codes = [*ERRORS, *SCHEMA_CODES]
    errors = {code: {"title": title(lang, code), "hint": ""} for code in codes}
    return _finish({"errors": errors}, "errors.json", lang)


def dump(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def all_schemas(lang: str = "ru") -> dict[str, str]:
    """Имя файла -> текст на языке `lang`. Для export и scaffold.

    Ключи, структура и `$id` одинаковы на обоих языках, байты каждого языка
    детерминированы.
    """
    check_lang(lang)
    return {
        "site.schema.json": dump(site_schema(lang)),
        "theme.schema.json": dump(theme_schema(lang)),
        "frontmatter.schema.json": dump(frontmatter_schema(lang)),
        "setup.schema.json": dump(setup_schema(lang)),
        "errors.json": dump(errors_registry(lang)),
        "describe.schema.json": dump(describe_schema(lang)),
    }


def export(target: Path, lang: str = "ru") -> list[str]:
    """Пишет шесть файлов в `target` (создаётся), возвращает их имена."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for name, text in all_schemas(lang).items():
        (target / name).write_text(text, encoding="utf-8", newline="\n")
        names.append(name)
    return names
