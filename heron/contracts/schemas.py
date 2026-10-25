"""JSON Schema контрактов и реестр кодов ошибок.

Чистые функции без click: `heron schema` (шов S2.T6) и scaffold (S2.T4)
берут отсюда готовые тексты. Вывод детерминирован: ключи отсортированы,
отступ 2, не-ASCII без экранирования, перевод строки в конце.

Схема принимает то же, что модель. Осознанные расхождения:
- необязательные поля фронтматтера допускают null (пустой ключ модель отбрасывает);
- `type`, `children_type`, `slug` и `version` темы допускают число (модель приводит к строке);
- правила в регэкспах моделей (слаг, домен, язык) в схему не вынесены;
- значения по языкам в site.yaml (`name_ru`) описаны patternProperties из LOCALIZED.

Спецификация: docs/ru/spec/21-engine.md, раздел 10 («heron schema»);
формат `$id` — docs/ru/spec/23-distribution.md, «Версия контракта».
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import heron
from heron.contracts.frontmatter import PageMeta
from heron.contracts.site import LOCALIZED, SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.errors import ERRORS
from heron.setup.answers import Answers

DRAFT = "https://json-schema.org/draft/2020-12/schema"
BASE = "https://sitebuilder.heron.software/schema"

FILES = (
    "site.schema.json",
    "theme.schema.json",
    "frontmatter.schema.json",
    "setup.schema.json",
    "errors.json",
)

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

_META = ("title", "description", "default", "examples")


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


def _finish(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Добавляет `$schema`, `$id` и `x-heron-version`."""
    data["$schema"] = DRAFT
    data["$id"] = f"{_id_prefix()}/{name}"
    data["x-heron-version"] = heron.__version__
    return data


def site_schema() -> dict[str, Any]:
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
    return _finish(data, "site.schema.json")


def theme_schema() -> dict[str, Any]:
    data = ThemeConfig.model_json_schema()
    data["properties"]["version"] = _number_or(data["properties"]["version"])
    data["description"] = THEME_NOTE
    return _finish(data, "theme.schema.json")


def setup_schema() -> dict[str, Any]:
    return _finish(Answers.model_json_schema(), "setup.schema.json")


def frontmatter_schema() -> dict[str, Any]:
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
    return _finish(data, "frontmatter.schema.json")


def errors_registry() -> dict[str, Any]:
    errors = {code: {"title": title, "hint": ""} for code, title in ERRORS.items()}
    return _finish({"errors": errors}, "errors.json")


def dump(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def all_schemas() -> dict[str, str]:
    """Имя файла -> текст. Для export и scaffold."""
    return {
        "site.schema.json": dump(site_schema()),
        "theme.schema.json": dump(theme_schema()),
        "frontmatter.schema.json": dump(frontmatter_schema()),
        "setup.schema.json": dump(setup_schema()),
        "errors.json": dump(errors_registry()),
    }


def export(target: Path) -> list[str]:
    """Пишет пять файлов в `target` (создаётся), возвращает их имена."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for name, text in all_schemas().items():
        (target / name).write_text(text, encoding="utf-8", newline="\n")
        names.append(name)
    return names
