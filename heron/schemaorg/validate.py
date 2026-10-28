"""Проверка узла JSON-LD по словарю schema.org (коды SCH001-SCH005).

Чистая функция: без ввода-вывода, без знания о сайте. Строгость, исключения и
тексты сообщений решает политика (heron.messages), здесь только код и подстановки.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from heron.schemaorg import Vocab, short
from heron.schemaorg import vocab as _load_vocab

_NO_REPLACEMENT = "нет замены, уберите"
_TEXTLIKE = ("Text", "Date", "DateTime", "Time")
_NUMBERLIKE = ("Number", "Integer", "Float")


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    path: str
    value: str
    fields: dict[str, str]


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    pending: set[str] = field(default_factory=set)


def _join(path: str, key: str | int) -> str:
    return f"{path}.{key}" if path else str(key)


def _is_foreign(key: str) -> bool:
    return ":" in key or key.startswith("http")


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


class _Validator:
    def __init__(self, v: Vocab) -> None:
        self.v = v
        self.found: dict[tuple[str, str], Finding] = {}
        self.pending: set[str] = set()

    def add(self, code: str, path: str, value: str, **fields: str) -> None:
        self.found.setdefault((code, path), Finding(code, path, value, fields))

    def _kind_in(self, names: list[str], bases: tuple[str, ...]) -> bool:
        v = self.v
        return any(v.is_datatype(n) and any(v.is_subtype(n, b) for b in bases) for n in names)

    def _datatypes(self, ranges: list[str]) -> set[str]:
        return {n for n in ranges if self.v.is_datatype(n)}

    def walk(self, node: Any, path: str, expected: list[str] | None) -> None:
        if isinstance(node, list):
            for i, item in enumerate(node):
                self.walk(item, _join(path, i), expected)
        elif isinstance(node, dict):
            self.node(node, path, expected)

    def node(self, node: dict[str, Any], path: str, expected: list[str] | None) -> None:
        v = self.v
        if "@graph" in node:
            self.walk(node["@graph"], _join(path, "@graph"), None)
        types = self.types(node.get("@type"), path)
        if not types:
            types = list(expected or [])
        if not types:
            return
        tstr = ", ".join(types)
        for prop, value in node.items():
            if prop.startswith("@") or _is_foreign(prop):
                continue
            ppath = _join(path, prop)
            if not v.is_property(prop):
                self.add(
                    "SCH002",
                    ppath,
                    prop,
                    types=tstr,
                    prop=prop,
                    domain="",
                    suggest=", ".join(v.suggest(prop, "property")),
                )
                continue
            if v.ext(prop) == "pending":
                self.pending.add(short(prop))
            if not v.allows(types, prop):
                domain = ", ".join(v.properties[short(prop)].get("domain", [])[:6])
                self.add("SCH002", ppath, prop, types=tstr, prop=prop, domain=domain, suggest="")
                continue
            dep, sup = v.deprecated(prop)
            if dep:
                repl = ", ".join(sup) or _NO_REPLACEMENT
                self.add("SCH005", ppath, prop, prop=prop, replacement=repl, release=v.release)
            self.value(prop, value, ppath)

    def types(self, raw: Any, path: str) -> list[str]:
        v = self.v
        if raw is None:
            return []
        is_list = isinstance(raw, list)
        names = raw if is_list else [raw]
        known: list[str] = []
        for i, name in enumerate(names):
            if not isinstance(name, str):
                continue
            tpath = _join(path, f"@type.{i}" if is_list else "@type")
            n = short(name)
            if not v.is_type(n):
                owners = v.members_of.get(n)
                if owners:
                    self.add(
                        "SCH001",
                        tpath,
                        name,
                        suggest="",
                        enum=owners[0],
                        hint=f"это значение перечисления {owners[0]}, не тип",
                    )
                else:
                    self.add("SCH001", tpath, name, suggest=", ".join(v.suggest(n, "type")))
                continue
            known.append(n)
            if v.ext(n) == "pending":
                self.pending.add(n)
            dep, sup = v.deprecated(n)
            if dep:
                self.add(
                    "SCH005",
                    tpath,
                    name,
                    replacement=", ".join(sup) or _NO_REPLACEMENT,
                    release=v.release,
                )
        return known

    def value(self, prop: str, value: Any, path: str) -> None:
        if isinstance(value, list):
            for i, item in enumerate(value):
                self.value(prop, item, _join(path, i))
            return
        if _empty(value):
            return
        v = self.v
        ranges = v.ranges(prop)
        rstr = " | ".join(ranges)
        if isinstance(value, bool):
            if "Boolean" not in ranges:
                self.add("SCH004", path, str(value), prop=prop, got="boolean", expected=rstr)
        elif isinstance(value, (int, float)):
            numeric = self._kind_in(ranges, _NUMBERLIKE + ("Text",))
            if not (numeric or "QuantitativeValue" in ranges):
                self.add("SCH004", path, str(value), prop=prop, got="число", expected=rstr)
        elif isinstance(value, str):
            self.string(prop, value, path, ranges, rstr)
        elif isinstance(value, dict):
            self.dict_value(prop, value, path, ranges, rstr)

    def string(self, prop: str, value: str, path: str, ranges: list[str], rstr: str) -> None:
        v = self.v
        if self._kind_in(ranges, _TEXTLIKE):
            return
        data = self._datatypes(ranges)
        if data and data <= {"Boolean"}:
            if value.strip().lower() not in ("true", "false"):
                self.add("SCH004", path, value, prop=prop, got="строка", expected=rstr)
            return
        if data and data <= set(_NUMBERLIKE):
            try:
                float(value)
            except ValueError:
                self.add("SCH004", path, value, prop=prop, got="строка", expected=rstr)
            return
        enums = [r for r in ranges if v.is_enum(r)]
        if enums and not any(v.is_member(e, value) for e in enums):
            self.add(
                "SCH003",
                path,
                value,
                prop=prop,
                enum=enums[0],
                members=", ".join(v.members(enums[0])[:10]),
                suggest=", ".join(v.suggest(value, "member", enums[0])),
            )

    def dict_value(
        self, prop: str, value: dict[str, Any], path: str, ranges: list[str], rstr: str
    ) -> None:
        v = self.v
        raw = value.get("@type")
        if raw is None:
            if set(value) <= {"@id"}:
                return
            classes = [
                r for r in ranges if r in v.classes and not v.is_datatype(r) and not v.is_enum(r)
            ]
            self.node(value, path, classes if len(classes) == 1 else None)
            return
        vtypes = [short(t) for t in (raw if isinstance(raw, list) else [raw]) if isinstance(t, str)]
        ok = "Thing" in ranges or any(
            v.is_subtype(t, r) or v.is_member(r, t) for t in vtypes for r in ranges
        )
        if not ok:
            got = ", ".join(vtypes)
            self.add("SCH004", path, got, prop=prop, got=got, expected=rstr)
        self.node(value, path, None)


def validate(node: Any, path: str = "", vocab: Vocab | None = None) -> Result:
    """Проверить узел или граф JSON-LD; находки отсортированы по (path, code)."""
    run = _Validator(vocab or _load_vocab())
    run.walk(node, path, None)
    findings = sorted(run.found.values(), key=lambda f: (f.path, f.code))
    return Result(findings=findings, pending=run.pending)
