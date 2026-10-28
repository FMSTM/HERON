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
from heron.contracts.frontmatter import PageMeta
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
)

# Английские описания. Ключ - файл и JSON Pointer русского текста в схеме; значение -
# (первые 10 знаков sha256 русского текста, английский текст). Хеш нужен тесту:
# правка русского докстринга без правки перевода его ломает, и английский комплект
# не отстаёт молча.
EN: dict[str, tuple[str, str]] = {
    "site.schema.json#/$defs/AnalyticsBlock/description": (
        "f791f7ad1f",
        "Public counter identifiers.\n\n"
        "These are not secrets: they are visible in the source of any page and are read\n"
        "by crawlers. That is why they belong here, next to the domain and the languages,\n"
        "and not in environment variables: otherwise the same site built on two machines\n"
        "would get different counters, and nobody would know why.\n\n"
        "They are inserted into pages only when the build environment allows it:\n"
        "on dev a counter must not spoil the statistics of the live site.",
    ),
    "site.schema.json#/$defs/FormSpec/description": (
        "4941079167",
        "Description of a form. The engine does not accept the form - heron-relay does.\n\n"
        "The engine needs the description to hand the theme the set of fields and to fail\n"
        "if the theme draws a form that is not in the config.",
    ),
    "site.schema.json#/$defs/NavBlock/description": (
        "80e6526d14",
        "The menu. Its content is free: the theme invents the names of the groups.",
    ),
    "site.schema.json#/$defs/NginxBlock/description": (
        "fc9c1d1733",
        "The nginx config that the engine builds together with the site.\n\n"
        "`hash_sizes` is obsolete and does nothing. 301 and 410 are now exact\n"
        "locations, not string maps: the hash tables of the maps that\n"
        "map_hash_bucket_size and map_hash_max_size were sized for are no longer built.\n"
        "The key is accepted so that existing site.yaml files build without changes.",
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
        "8955522567",
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
    "theme.schema.json#/$defs/LinkSpec/description": (
        "d96e07a712",
        "A relation between pages declared by the theme.\n\n"
        'The core does not know what "a service belongs to a direction" means - it knows\n'
        "that the field `topics` holds the names of pages of the type `topic`, and it can\n"
        "find them, check them and build the back reference. The subject area stays\n"
        "in the theme, the mechanics in the core.",
    ),
    "theme.schema.json#/$defs/TypeSpec/description": (
        "3d71382c00",
        "A page type: which sections it uses and what markup it gets.",
    ),
    "theme.schema.json#/description": (
        "a6b93a498e",
        "The key `on` in `links` is a string. YAML 1.1 (PyYAML) reads a bare `on:` as the "
        "boolean true, the engine takes this into account; an editor with YAML 1.2 reads "
        "`on` as a string.",
    ),
    "frontmatter.schema.json#/description": (
        "8172b25862",
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
        "a path must not coincide with an existing URL (`E009`).",
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
    "date — дата публикации, `ГГГГ-ММ-ДД`; updated — дата последней правки, "
    "`ГГГГ-ММ-ДД`. Дата позже момента сборки — предупреждение, при `--strict` — ошибка. "
    "Обновление раньше публикации — тоже предупреждение. "
    "redirect_from: список путей от корня, нормализация — `20` §2; "
    "путь не должен совпадать с существующим URL (`E009`)."
)

THEME_NOTE = (
    "Ключ `on` в `links` — строка. YAML 1.1 (PyYAML) читает голый `on:` как булево true, "
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


def theme_schema(lang: str = "ru") -> dict[str, Any]:
    data = ThemeConfig.model_json_schema()
    data["properties"]["version"] = _number_or(data["properties"]["version"])
    data["description"] = THEME_NOTE
    return _finish(data, "theme.schema.json", lang)


def setup_schema(lang: str = "ru") -> dict[str, Any]:
    return _finish(Answers.model_json_schema(), "setup.schema.json", lang)


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
    }


def export(target: Path, lang: str = "ru") -> list[str]:
    """Пишет пять файлов в `target` (создаётся), возвращает их имена."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for name, text in all_schemas(lang).items():
        (target / name).write_text(text, encoding="utf-8", newline="\n")
        names.append(name)
    return names
