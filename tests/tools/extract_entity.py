"""Узел врача из собранной страницы и сравнение двух узлов.

    python3 tests/tools/extract_entity.py <index.html> > node.json
    python3 tests/tools/extract_entity.py --compare a.json b.json

Сравнение нормализует то, что по задаче не считается отличием: `@id`, `image`,
`url` (если его нет в первом узле), список из одного элемента, порядок
`medicalSpecialty`, тип числа.
"""

from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

TYPE = "IndividualPhysician"


class _Blocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._on = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._on = True
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._on:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._on:
            self._on = False
            self.blocks.append("".join(self._buf))


def _has_type(node: dict[str, Any]) -> bool:
    kind = node.get("@type")
    return kind == TYPE or (isinstance(kind, list) and TYPE in kind)


def _find(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        if _has_type(data):
            return data
        for item in data.get("@graph", []) or []:
            found = _find(item)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find(item)
            if found:
                return found
    return None


def extract(html_path: str | Path) -> dict[str, Any]:
    """Первый узел с @type IndividualPhysician из JSON-LD страницы."""
    parser = _Blocks()
    parser.feed(Path(html_path).read_text(encoding="utf-8"))
    for block in parser.blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        found = _find(data)
        if found:
            return found
    raise LookupError(f"в {html_path} нет узла {TYPE}")


def _walk(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        out = {k: _walk(v, k) for k, v in value.items() if k not in ("@id", "image")}
        return out
    if isinstance(value, list):
        items = [_walk(v, key) for v in value]
        if key == "medicalSpecialty":
            items = sorted(items, key=str)
        return items[0] if len(items) == 1 else items
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


def normalize(node: dict[str, Any], keep_url: bool = True) -> dict[str, Any]:
    """Привести узел к виду, в котором допустимые различия исчезают."""
    out = _walk(node)
    if not keep_url:
        out.pop("url", None)
    return out


def _diff(a: Any, b: Any, path: str, out: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            where = f"{path}.{key}" if path else key
            if key not in a:
                out.append(f"{where}: нет в первом, во втором {b[key]!r}")
            elif key not in b:
                out.append(f"{where}: в первом {a[key]!r}, нет во втором")
            else:
                _diff(a[key], b[key], where, out)
    elif a != b:
        out.append(f"{path or '.'}: {a!r} != {b!r}")


def compare(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Различия двух узлов после normalize; пустой список - совпадают."""
    out: list[str] = []
    _diff(normalize(a, keep_url="url" in a), normalize(b, keep_url="url" in a), "", out)
    return out


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "--compare":
        diffs = compare(
            json.loads(Path(argv[2]).read_text(encoding="utf-8")),
            json.loads(Path(argv[3]).read_text(encoding="utf-8")),
        )
        if not diffs:
            print("совпадает")
            return 0
        print("\n".join(diffs))
        return 1
    if len(argv) == 2:
        print(json.dumps(extract(argv[1]), ensure_ascii=False, indent=2))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
