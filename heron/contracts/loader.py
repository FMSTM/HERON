"""Чтение YAML и перевод жалоб pydantic на человеческий язык.

Конфиг сайта пишет не разработчик. Сообщение об ошибке обязано называть файл,
строку и что именно поправить, а не показывать трейсбек валидатора.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from heron.core.errors import HeronError
from heron.messages import Msg

FIELD_HINTS: dict[str, str] = {
    "missing": "loader_hint_missing",
    "extra_forbidden": "loader_hint_extra",
}


def read_yaml(path: Path, code: str = "E011") -> dict[str, Any]:
    """Прочитать YAML-файл в словарь. Битый YAML — остановка с номером строки."""
    if not path.is_file():
        raise HeronError(code=code, message=Msg("loader_file_missing"), path=str(path))
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise HeronError(
            code=code,
            message=Msg("loader_not_utf8"),
            path=str(path),
            hint=Msg("loader_not_utf8_hint"),
        ) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise HeronError(
            code=code,
            message=Msg("loader_bad_yaml", problem=str(getattr(exc, "problem", exc))),
            path=str(path),
            line=(mark.line + 1) if mark else None,
            hint=Msg("loader_bad_yaml_hint"),
        ) from exc
    if data is None:
        raise HeronError(code=code, message=Msg("loader_empty"), path=str(path))
    if not isinstance(data, dict):
        raise HeronError(
            code=code,
            message=Msg("loader_not_mapping", type=type(data).__name__),
            path=str(path),
        )
    return data


def describe(error: dict[str, Any]) -> Msg:
    """Одна жалоба pydantic одной строкой, понятной человеку."""
    path = ".".join(str(p) for p in error["loc"])
    where: str | Msg = path or Msg("loader_root")
    kind = error.get("type", "")
    cause = (error.get("ctx") or {}).get("error")
    reason: str | Msg
    if kind in FIELD_HINTS:
        reason = Msg(FIELD_HINTS[kind])
    elif kind == "value_error" and cause is not None and cause.args and isinstance(cause.args[0], Msg):
        reason = Msg("loader_value_error", reason=cause.args[0])
    else:
        reason = error.get("msg") or Msg("loader_bad_value")
    return Msg("loader_item", where=where, reason=reason)


def build(model: type[BaseModel], data: dict[str, Any], path: Path, code: str = "E011"):
    """Собрать модель из данных или остановить сборку с внятным перечнем жалоб."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        lines = [describe(e) for e in exc.errors()]
        message = (
            Msg("loader_invalid_one", lines=lines)
            if len(lines) == 1
            else Msg("loader_invalid_many", n=len(lines), lines=lines)
        )
        raise HeronError(code=code, message=message, path=str(path)) from exc
