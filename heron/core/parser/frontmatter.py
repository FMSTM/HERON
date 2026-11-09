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
from heron.core import yamlsafe
from heron.core.errors import HeronError, Warning_
from heron.messages import Msg

FRONTMATTER = re.compile(r"\A\ufeff?---[ \t]*\r?\n(?P<body>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)

REQUIRED = ("title", "h1", "description")


def split(text: str, path: str) -> tuple[dict[str, Any], str, int]:
    """Разделить файл на фронтматтер, тело и номер строки, с которой тело начинается."""
    match = FRONTMATTER.match(text)
    if not match:
        raise HeronError(
            code="E001",
            message=Msg("parser_no_frontmatter"),
            path=path,
            line=1,
            hint=Msg("parser_no_frontmatter_hint"),
        )

    raw = match.group("body")
    try:
        data = yamlsafe.load(raw)
    except yamlsafe.Expands as exc:
        raise HeronError(
            code="E001",
            message=Msg("loader_yaml_expands", limit=yamlsafe.MAX_NODES, depth=yamlsafe.MAX_DEPTH),
            path=path,
            line=2,
            hint=Msg("loader_yaml_expands_hint"),
        ) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise HeronError(
            code="E001",
            message=Msg("parser_bad_yaml", problem=str(getattr(exc, "problem", exc))),
            path=path,
            line=(mark.line + 2) if mark else 1,
            hint=Msg("parser_bad_yaml_hint"),
        ) from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise HeronError(
            code="E001",
            message=Msg("parser_not_mapping", type=type(data).__name__),
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
            message=Msg("parser_missing_fields", fields=", ".join(missing)),
            path=path,
            line=2,
            hint=Msg("parser_missing_fields_hint"),
        )
    try:
        return PageMeta.model_validate(data)
    except ValidationError as exc:
        lines = [describe(e) for e in exc.errors()]
        raise HeronError(
            code="E002",
            message=Msg("parser_frontmatter_invalid", lines=lines),
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
            message=Msg("parser_not_utf8"),
            path=where,
            hint=Msg("parser_not_utf8_hint"),
        ) from exc
    except OSError as exc:
        from heron.core import paths

        raise paths.unreadable(Path(where), exc) from exc

    data, body, body_line = split(text, where)
    meta = parse_meta(data, where)
    return meta, body, body_line, meta.lint(where)
