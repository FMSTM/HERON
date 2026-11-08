"""Правка страницы без потерь: модель полей, чтение и запись markdown, проверка.

Одно ядро для консольного опросника, студии в браузере и агента (`--answers`):

    contract = describe.contract(theme, config, lang)
    page = edit.load(path, contract, rel="content/ru/about.md")
    for field in edit.fields(page): ...          # тот же список в консоли и в вебе
    page = edit.set(page, "title", "Новый заголовок")
    issues = edit.validate(page, site_root)
    edit.save(page, path)                           # байт в байт, кроме изменённого

Спецификация: docs/ru/spec/21-engine.md, «Модель правки страницы».
"""

from __future__ import annotations

from heron.edit.langs import LangFile, files, folder_type, key_of, missing, open_page, rel_for
from heron.edit.model import (
    Field,
    Page,
    add_section,
    dump,
    fields,
    get,
    groups,
    load,
    remove_section,
    save,
    set_field,
    site_changes,
    span,
)
from heron.edit.slots import EditError
from heron.edit.validate import Issue, validate

set = set_field  # noqa: A001 - имя из ТЗ: edit.set(page, путь, значение)

__all__ = [
    "EditError",
    "Field",
    "Issue",
    "LangFile",
    "Page",
    "add_section",
    "dump",
    "fields",
    "files",
    "folder_type",
    "get",
    "groups",
    "key_of",
    "load",
    "missing",
    "open_page",
    "rel_for",
    "remove_section",
    "save",
    "set",
    "set_field",
    "site_changes",
    "span",
    "validate",
]
