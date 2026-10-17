"""Справочники из `data/`.

Перечням, таблицам и реквизитам не место в теле markdown: они не текст,
а данные, и правятся отдельно от прозы. Всё, что лежит в `data/`, приезжает
в шаблоны как `data.<имя файла>`, вложенные папки дают вложенные имена.

Спецификация: docs/spec/20-data-contract.md, раздел 1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from heron.contracts.loader import read_yaml
from heron.core import paths
from heron.core.errors import Collector, HeronError

SUFFIXES = (".yaml", ".yml")


def load(root: Path, collector: Collector | None = None) -> dict[str, Any]:
    """Собрать `data/` в дерево словарей. Нет папки — пустой словарь."""
    if not root.is_dir():
        return {}

    out: dict[str, Any] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        if not paths.inside(root, path):
            if collector is None:
                raise HeronError(
                    code=paths.CODE,
                    message="символическая ссылка ведёт за пределы data/",
                    path=str(path),
                )
            collector.error(
                paths.CODE,
                "символическая ссылка ведёт за пределы data/",
                path=str(path.relative_to(root.parent)),
                hint="положите сам файл в data/ вместо ссылки на него",
            )
            continue
        node = out
        for part in path.relative_to(root).parts[:-1]:
            node = node.setdefault(part, {})
        name = path.stem
        try:
            node[name] = read_yaml(path)
        except Exception as exc:  # noqa: BLE001 — ошибка одного файла не должна ронять обход
            if collector is None:
                raise
            collector.error(
                "E011",
                f"справочник не читается: {exc}",
                path=str(path.relative_to(root.parent)),
            )
    return out
