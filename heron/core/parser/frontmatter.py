"""Отделение фронтматтера от тела файла.

Фронтматтер — YAML между `---` в самом начале файла. Ошибки собираются
с номером строки в исходном файле, а не в вырезанном куске: человек правит
файл, а не наше представление о нём.

Спецификация: docs/spec/20-data-contract.md, раздел 4.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from heron.contracts.frontmatter import PageMeta
from heron.contracts.loader import describe
from heron.core.errors import HeronError, Warning_

FRONTMATTER = re.compile(r"\A\ufeff?---[ \t]*\r?\n(?P<body>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)

REQUIRED = ("title", "h1", "description")


def split(text: str, path: str) -> tuple[dict[str, Any], str, int]:
    """Разделить файл на фронтматтер, тело и номер строки, с которой тело начинается."""
    match = FRONTMATTER.match(text)
    if not match:
        raise HeronError(
            code="E001",
            message="в начале файла нет блока фронтматтера",
            path=path,
            line=1,
            hint="файл должен начинаться со строки --- , затем YAML, затем снова ---",
        )

    raw = match.group("body")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise HeronError(
            code="E001",
            message=f"битый YAML во фронтматтере: {getattr(exc, 'problem', exc)}",
            path=path,
            line=(mark.line + 2) if mark else 1,
            hint="проверьте отступы и кавычки: значение с двоеточием берётся в кавычки",
        ) from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise HeronError(
            code="E001",
            message=f"фронтматтер должен быть набором ключей, а не {type(data).__name__}",
            path=path,
            line=2,
        )

    body = text[match.end() :]
    body_line = text[: match.end()].count("\n") + 1
    return data, body, body_line


def parse_meta(data: dict[str, Any], path: str) -> PageMeta:
    """Собрать модель страницы из фронтматтера."""
    missing = [f for f in REQUIRED if not str(data.get(f, "")).strip()]
    if missing:
        raise HeronError(
            code="E002",
            message="нет обязательных полей: " + ", ".join(missing),
            path=path,
            line=2,
            hint="title пишется под выдачу, h1 под того, кто уже открыл страницу",
        )
    try:
        return PageMeta.model_validate(data)
    except ValidationError as exc:
        lines = [describe(e) for e in exc.errors()]
        raise HeronError(
            code="E002",
            message="фронтматтер не проходит проверку:\n    " + "\n    ".join(lines),
            path=path,
            line=2,
        ) from exc


def read(path: Path, rel: str | None = None) -> tuple[PageMeta, str, int, list[Warning_]]:
    """Прочитать файл страницы: метаданные, тело, номер первой строки тела, замечания."""
    where = rel or str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HeronError(
            code="E001",
            message="файл не читается как UTF-8",
            path=where,
            hint="пересохраните файл в UTF-8 без BOM",
        ) from exc

    data, body, body_line = split(text, where)
    meta = parse_meta(data, where)
    return meta, body, body_line, meta.lint(where)
