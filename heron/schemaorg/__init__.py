"""Словарь schema.org 29.3 как данные пакета (индекс без сети и зависимостей).

API запросов к индексу: ``vocab()`` возвращает ``Vocab``. Модуль ничего не
импортирует из ``heron.*``.
"""

from __future__ import annotations

import difflib
import functools
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

RELEASE = "29.3"
DATA = Path(__file__).parent / f"schemaorg-{RELEASE}.json"

_PREFIXES = ("https://schema.org/", "http://schema.org/", "schema:")


def short(name: str) -> str:
    """Имя без префикса schema.org (``schema:``, http/https URL) и без пробелов."""
    name = str(name).strip()
    for prefix in _PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix) :].strip()
    return name


def _as_list(types: str | list[str]) -> list[str]:
    return [types] if isinstance(types, str) else list(types)


@dataclass(frozen=True)
class Vocab:
    release: str
    classes: dict[str, Any]
    properties: dict[str, Any]
    enums: dict[str, list[str]]
    members_of: dict[str, list[str]]
    datatypes: dict[str, list[str]]

    def is_type(self, name: str) -> bool:
        n = short(name)
        return n in self.classes or n in self.datatypes

    def is_property(self, name: str) -> bool:
        return short(name) in self.properties

    def is_datatype(self, name: str) -> bool:
        return short(name) in self.datatypes

    def _parents(self, name: str) -> list[str]:
        if name in self.classes:
            return list(self.classes[name].get("parents", []))
        return list(self.datatypes.get(name, []))

    def ancestors(self, name: str) -> frozenset[str]:
        start = short(name)
        if not self.is_type(start):
            return frozenset()
        seen = {start}
        queue = deque([start])
        while queue:
            for parent in self._parents(queue.popleft()):
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)
        return frozenset(seen)

    def is_subtype(self, name: str, of: str) -> bool:
        return short(of) in self.ancestors(name)

    def descendants(self, name: str) -> list[str]:
        n = short(name)
        return sorted(c for c in self.classes if c != n and n in self.ancestors(c))

    def allows(self, types: str | list[str], prop: str) -> bool:
        meta = self.properties.get(short(prop))
        if meta is None:
            return False
        domain = set(meta.get("domain", []))
        if not domain:
            return True
        union: set[str] = set()
        for t in _as_list(types):
            union |= self.ancestors(t)
        return bool(domain & union)

    def properties_of(self, types: str | list[str]) -> list[str]:
        return sorted(p for p in self.properties if self.allows(types, p))

    def ranges(self, prop: str) -> list[str]:
        meta = self.properties.get(short(prop))
        return list(meta.get("range", [])) if meta else []

    def is_enum(self, name: str) -> bool:
        return short(name) in self.enums

    def members(self, enum: str) -> list[str]:
        root = short(enum)
        if root not in self.enums:
            return []
        result: set[str] = set()
        for e, values in self.enums.items():
            if e == root or root in self.ancestors(e):
                result.update(values)
        return sorted(result)

    def is_member(self, enum: str, value: str) -> bool:
        return short(value) in self.members(enum)

    def deprecated(self, name: str) -> tuple[bool, list[str]]:
        n = short(name)
        meta = self.classes.get(n) or self.properties.get(n)
        if not meta:
            return (False, [])
        superseded = list(meta.get("superseded_by", []))
        return (bool(meta.get("attic")) or bool(superseded), superseded)

    def ext(self, name: str) -> str:
        n = short(name)
        meta = self.classes.get(n) or self.properties.get(n)
        return str(meta.get("ext", "")) if meta else ""

    def suggest(
        self,
        name: str,
        pool: Literal["type", "property", "member"],
        enum: str | None = None,
    ) -> list[str]:
        if pool == "type":
            names = sorted(set(self.classes) | set(self.datatypes))
        elif pool == "property":
            names = sorted(self.properties)
        else:
            names = self.members(enum) if enum else sorted(self.members_of)
        query = short(name)
        exact = [x for x in names if x.lower() == query.lower()]
        close = difflib.get_close_matches(query, names, n=3, cutoff=0.75)
        return exact + [x for x in close if x not in exact]


@functools.cache
def vocab() -> Vocab:
    raw = json.loads(DATA.read_text("utf-8"))
    return Vocab(
        release=raw["release"],
        classes=raw["classes"],
        properties=raw["properties"],
        enums=raw["enums"],
        members_of=raw["members"],
        datatypes=raw["datatypes"],
    )
