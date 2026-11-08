"""Места значений в тексте: одно значение (`Slot`) и список (`Seq`).

`Slot` знает отрезок исходника, в котором лежит значение, и как его читать и
писать: одной строкой (заголовок, ключ факта, ячейка), со сдвигом строк
продолжения (текст пункта списка), с префиксом цитаты `> `. Пустое место
(второго абзаца нет, у пункта нет зачина) - отрезок нулевой длины с тем, что
дописать вокруг значения при вставке. Очистка значения убирает и оформление
вокруг него (`outer`): `**Термин.** ` уходит целиком.

`Seq` - пункты списка, группы `###`, строки фактов или таблицы. Замена списка
целиком переписывает только изменившиеся пункты: совпавшие по месту остаются
байт в байт вместе с промежутками между ними.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from heron.edit.text import native, plain
from heron.messages import Msg, MsgError


class EditError(MsgError):
    """Значение не записать: ключ сообщения и поля - в `args[0]` (`Msg`)."""


Edit = tuple[int, int, str]


@dataclass(slots=True)
class Slot:
    """Одно значение. `start == end` и `present` ложно - места ещё нет, `prefix`/`suffix` вокруг."""

    start: int
    end: int
    mode: str = "raw"  # raw | line | url | indent | quote | para
    indent: int = 0
    present: bool = True
    prefix: str = ""
    suffix: str = ""
    outer: tuple[int, int] | None = None
    readonly: str | None = None

    def read(self, text: str) -> str:
        if not self.present:
            return ""
        raw = plain(text[self.start : self.end])
        if self.mode in ("indent", "para") and self.indent:
            rows = raw.split("\n")
            raw = "\n".join([rows[0], *(_dedent(row, self.indent) for row in rows[1:])])
        elif self.mode == "quote":
            raw = "\n".join(_unquote(row) for row in raw.split("\n"))
        return raw

    def encode(self, value: str, nl: str) -> str:
        value = plain(str(value))
        if self.mode in ("line", "url") and "\n" in value:
            raise EditError("edit_single_line")
        if self.mode == "url" and any(ch.isspace() or ch in "()" for ch in value):
            raise EditError("edit_bad_path", value=value)
        if self.mode == "para" and _has_blank(value):
            raise EditError("edit_one_paragraph")
        rows = value.split("\n")
        if self.mode in ("indent", "para") and self.indent:
            pad = " " * self.indent
            rows = [rows[0], *((pad + row) if row.strip() else "" for row in rows[1:])]
        elif self.mode == "quote":
            rows = [("> " + row) if row.strip() else ">" for row in rows]
        return native("\n".join(rows), nl)

    def write(self, text: str, value: Any, nl: str) -> Edit | None:
        if self.readonly:
            raise EditError("edit_readonly", reason=Msg(self.readonly))
        value = plain("" if value is None else str(value)).strip("\n")
        if not value.strip():
            if not self.present:
                return None
            start, end = self.outer or (self.start, self.end)
            return start, end, ""
        if self.present and value == self.read(text):
            return None
        body = self.encode(value, nl)
        if not self.present:
            suffix = _suffix(text, self.start, self.suffix)
            return self.start, self.start, native(self.prefix, nl) + body + native(suffix, nl)
        return self.start, self.end, body


def _dedent(row: str, indent: int) -> str:
    spaces = len(row) - len(row.lstrip(" "))
    return row[min(spaces, indent) :]


def _unquote(row: str) -> str:
    stripped = row.lstrip(" ")
    if stripped.startswith(">"):
        stripped = stripped[1:]
        return stripped[1:] if stripped.startswith(" ") else stripped
    return row


def _has_blank(value: str) -> bool:
    rows = value.strip("\n").split("\n")
    return any(not row.strip() for row in rows)


@dataclass(slots=True)
class Entry:
    """Пункт списка: его отрезок и значение - место (`Slot`) или поля пункта."""

    start: int
    end: int
    slot: Slot | None = None
    fields: dict[str, Slot | Seq] = field(default_factory=dict)


@dataclass(slots=True)
class Seq:
    """Список значений. `render(значение, номер)` - новый пункт текстом с `\\n`."""

    entries: list[Entry]
    start: int
    end: int
    seps: list[str]
    sep: str
    render: Callable[[Any, int], str]
    names: list[str] | None = None  # имена полей пункта; None - пункт одно значение
    prefix: str = ""
    suffix: str = ""
    readonly: str | None = None
    # после записи: что ещё поправить (разделитель шапки таблицы)
    after: Callable[[int], Edit | None] | None = None

    @property
    def present(self) -> bool:
        return bool(self.entries)

    def write(self, text: str, value: Any, nl: str) -> Edit | None:
        if self.readonly:
            raise EditError("edit_readonly", reason=Msg(self.readonly))
        items = list(value or [])
        old = [entry_value(text, entry) for entry in self.entries]
        if _same(items, old):
            return None
        parts: list[str] = []
        for index, item in enumerate(items):
            if index:
                sep = self.seps[index - 1] if index - 1 < len(self.seps) else None
                parts.append(sep if sep is not None else native(self.sep, nl))
            if index < len(old) and _same(item, old[index]):
                entry = self.entries[index]
                parts.append(text[entry.start : entry.end])
            else:
                parts.append(native(self.render(item, index), nl))
        body = "".join(parts)
        if not self.entries:
            if not body:
                return None
            suffix = _suffix(text, self.start, self.suffix)
            return self.start, self.start, native(self.prefix, nl) + body + native(suffix, nl)
        return self.start, self.end, body


def _suffix(text: str, pos: int, suffix: str) -> str:
    """Вставка в самый конец файла без перевода строки в конце его и не добавляет."""
    if pos == len(text) and not text.endswith(("\n", "\r")) and not suffix.strip():
        return ""
    return suffix


def _same(new: Any, old: Any) -> bool:
    if isinstance(old, list):
        return isinstance(new, list) and len(new) == len(old) and all(map(_same, new, old))
    if isinstance(old, dict):
        if not isinstance(new, dict):
            return False
        return all(
            _same(new.get(key, "" if not isinstance(v, list) else []), v) for key, v in old.items()
        )
    return plain("" if new is None else str(new)).strip() == old.strip()


def entry_value(text: str, entry: Entry) -> Any:
    if entry.slot is not None:
        return entry.slot.read(text)
    return {name: node_value(text, node) for name, node in entry.fields.items()}


def node_value(text: str, node: Slot | Seq) -> Any:
    if isinstance(node, Slot):
        return node.read(text)
    return [entry_value(text, entry) for entry in node.entries]
