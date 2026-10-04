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

FIELD_HINTS: dict[str, str] = {
    "missing": "поле обязательно, его нет в файле",
    "extra_forbidden": "такого поля нет в контракте — опечатка в имени?",
}


def read_yaml(path: Path, code: str = "E011") -> dict[str, Any]:
    """Прочитать YAML-файл в словарь. Битый YAML — остановка с номером строки."""
    if not path.is_file():
        raise HeronError(code=code, message="файл не найден", path=str(path))
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise HeronError(
            code=code,
            message=f"битый YAML: {getattr(exc, 'problem', exc)}",
            path=str(path),
            line=(mark.line + 1) if mark else None,
            hint="проверьте отступы и двоеточия — YAML не прощает табуляцию",
        ) from exc
    if data is None:
        raise HeronError(code=code, message="файл пуст", path=str(path))
    if not isinstance(data, dict):
        raise HeronError(
            code=code,
            message=f"ожидался набор ключей, а в файле {type(data).__name__}",
            path=str(path),
        )
    return data


def describe(error: dict[str, Any]) -> str:
    """Одна жалоба pydantic одной строкой, понятной человеку."""
    where = ".".join(str(p) for p in error["loc"]) or "<корень>"
    kind = error.get("type", "")
    reason = FIELD_HINTS.get(kind, error.get("msg", "значение не подходит"))
    return f"{where}: {reason}"


def build(model: type[BaseModel], data: dict[str, Any], path: Path, code: str = "E011"):
    """Собрать модель из данных или остановить сборку с внятным перечнем жалоб."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        lines = [describe(e) for e in exc.errors()]
        head = "не проходит проверку" if len(lines) == 1 else f"не проходит проверку ({len(lines)})"
        raise HeronError(
            code=code,
            message=head + ":\n    " + "\n    ".join(lines),
            path=str(path),
        ) from exc
