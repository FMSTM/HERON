"""JSON Schema контрактов и реестр кодов ошибок.

Чистые функции без click: `heron schema` (шов S2.T6) и scaffold (S2.T4)
берут отсюда готовые тексты. Вывод детерминирован: ключи отсортированы,
отступ 2, не-ASCII без экранирования, перевод строки в конце.

Спецификация: docs/ru/spec/21-engine.md, раздел 10 («heron schema»);
формат `$id` — docs/ru/spec/23-distribution.md, «Версия контракта».
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import heron
from heron.contracts.frontmatter import PageMeta
from heron.contracts.site import SiteConfig
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
    "как дополнительные. "
    "Правила, которых схема не выражает. "
    "slug: латиница, цифры, дефис; завершающий перевод строки (`\\Z`) в слаг не допускается. "
    "date — дата публикации, `ГГГГ-ММ-ДД`; updated — дата последней правки, "
    "`ГГГГ-ММ-ДД`. Дата позже момента сборки — предупреждение, при `--strict` — ошибка. "
    "Обновление раньше публикации — тоже предупреждение. "
    "redirect_from: список путей от корня, нормализация — раздел 2; "
    "путь не должен совпадать с существующим URL (`E009`)."
)


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
    return _finish(SiteConfig.model_json_schema(), "site.schema.json")


def theme_schema() -> dict[str, Any]:
    return _finish(ThemeConfig.model_json_schema(), "theme.schema.json")


def setup_schema() -> dict[str, Any]:
    return _finish(Answers.model_json_schema(), "setup.schema.json")


def frontmatter_schema() -> dict[str, Any]:
    data = PageMeta.model_json_schema()
    data["additionalProperties"] = True
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
