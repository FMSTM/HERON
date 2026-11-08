"""Комментарии автора в `site.yaml` переживают сохранение через конфигуратор.

Данные считает `merge` (PyYAML, комментариев не видит), текст `dump` их не
содержит. `carry` берёт старый текст и новый и переносит комментарии по пути
ключа: неизменённые по данным узлы остаются байт в байт, у изменённых
сохраняются комментарии над ключом и в конце строки. Способ и граничные
случаи: docs/architecture/setup-site-yaml-comments.md. Новых зависимостей нет.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

_KEY = re.compile(
    r"""^(?:"[^"]*"|'[^']*'|[^\s#'"\-\[\]{},&*!|>%@`][^:#]*?|-[^\s:][^:]*?):(?:\s|$)"""
)
_BLOCK_SCALAR = re.compile(r"[|>][+-]?\d*$")
_DOUBLE = re.compile(r'"(?:[^"\\]|\\.)*"')
_SINGLE = re.compile(r"'(?:[^']|'')*'")
_MARKER = re.compile(r"( *)-( +)(?=\S)")


@dataclass(slots=True)
class _Node:
    key: Any
    indent: int
    lead: list[str]
    span: list[str]
    item: bool = False
    children: bool = field(default=False)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _blank(line: str) -> bool:
    return not line.strip()


def _comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _split_comment(head: str) -> tuple[str, str]:
    """Строка без комментария в конце и сам комментарий (с пробелами перед ним)."""
    i = 0
    while i < len(head):
        char = head[i]
        before = head[:i].rstrip()
        if char in "\"'" and (not before or before[-1] in ":-,[{"):
            quoted = (_DOUBLE if char == '"' else _SINGLE).match(head, i)
            if quoted is None:  # кавычка закроется на следующих строках
                return head, ""
            i = quoted.end()
            continue
        if char == "#" and i and head[i - 1].isspace():
            return before, head[len(before) :].rstrip()
        i += 1
    return head, ""


def _value(head: str, item: bool) -> str:
    """Значение в строке заголовка узла: пусто — значит дальше вложенные строки."""
    text = _split_comment(head.strip())[0].strip()
    if item:
        return text[1:].strip() or ""
    match = _KEY.match(text + " ")
    if not match:
        return text
    return text[match.end() - 1 :].strip()


def _parse(lines: list[str]) -> tuple[list[_Node], list[str]]:
    """Соседние узлы одного уровня и хвост (комментарии после последнего)."""
    content = [_indent(x) for x in lines if not _blank(x) and not _comment(x)]
    if not content:
        return [], list(lines)
    base = min(content)
    nodes: list[_Node] = []
    pending: list[str] = []
    counter = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if _blank(line) or _comment(line):
            pending.append(line)
            i += 1
            continue
        if _indent(line) != base:
            raise ValueError("отступ не совпал")
        stripped = line.strip()
        item = stripped.startswith("- ") or stripped == "-"
        value = _value(line, item)
        block = bool(_BLOCK_SCALAR.search(_split_comment(stripped)[0].strip())) and not item
        last = i
        k = i + 1
        while k < len(lines):
            nxt = lines[k]
            if _blank(nxt):
                k += 1
                continue
            ind = _indent(nxt)
            if block and ind > base:
                last = k
            elif _comment(nxt):
                pass
            elif ind > base or (
                ind == base and not item and not value and nxt.lstrip().startswith("- ")
            ):
                last = k
            else:
                break
            k += 1
        if item:
            key: Any = ("i", counter)
            counter += 1
        else:
            match = _KEY.match(stripped + " ")
            key = stripped[: match.end() - 2].strip().strip("\"'") if match else ("n", i)
        nodes.append(_Node(key, base, pending, lines[i : last + 1], item, not value))
        pending = []
        i = last + 1
    return nodes, pending


def _shift(lines: list[str], delta: int) -> list[str]:
    if not delta:
        return lines
    out = []
    for line in lines:
        if _blank(line):
            out.append(line)
        elif delta > 0:
            out.append(" " * delta + line)
        else:
            out.append(line[min(-delta, _indent(line)) :])
    return out


def _same(old: list[str], new: list[str]) -> bool:
    try:
        return yaml.safe_load("\n".join(old) + "\n") == yaml.safe_load("\n".join(new) + "\n")
    except yaml.YAMLError:
        return False


def _orphan_lead(lead: list[str]) -> list[str]:
    """Комментарии отдалённого раздела (до последней пустой строки) остаются."""
    for pos in range(len(lead) - 1, -1, -1):
        if _blank(lead[pos]):
            return lead[: pos + 1]
    return []


def _item_data(node: _Node) -> Any:
    try:
        loaded = yaml.safe_load("\n".join(node.span) + "\n")
    except yaml.YAMLError:
        return None
    return loaded[0] if isinstance(loaded, list) and loaded else None


def _shared(old: Any, new: Any) -> int:
    if not isinstance(old, dict) or not isinstance(new, dict):
        return 0
    return sum(1 for key, value in new.items() if key in old and old[key] == value)


def _pair_items(old_nodes: list[_Node], new_nodes: list[_Node]) -> None:
    """Ключи новых элементов списка - ключи их пар в старом: сначала равные по
    данным, затем словари с общими полями, в последнюю очередь тот же индекс."""
    free = {node.key: _item_data(node) for node in old_nodes if node.item}
    keys: dict[int, Any] = {}
    data = [_item_data(node) for node in new_nodes]
    for pos, value in enumerate(data):
        match = next((key for key, old in free.items() if old == value), None)
        if match is not None:
            keys[pos] = match
            del free[match]
    for pos, value in enumerate(data):
        if pos in keys or not free:
            continue
        best = max(free, key=lambda key: _shared(free[key], value))
        if _shared(free[best], value):
            keys[pos] = best
            del free[best]
    for pos, node in enumerate(new_nodes):
        if pos in keys:
            node.key = keys[pos]
        elif node.key in free:
            del free[node.key]
        else:
            node.key = ("new", pos)


def _unitem(span: list[str]) -> list[str] | None:
    """Элемент-словарь как обычный блок без `- `; не словарь в блочном стиле - None."""
    text, comment = _split_comment(span[0])
    if text.strip() == "-":
        indent = " " * (_indent(span[0]) + 2)
        inner = ([indent + comment.strip()] if comment else []) + span[1:]
    else:
        marker = _MARKER.match(span[0])
        if marker is None:
            return None
        inner = [" " * marker.end() + span[0][marker.end() :], *span[1:]]
    first = next((x.strip() for x in inner if not _blank(x) and not _comment(x)), "")
    return inner if _KEY.match(first + " ") else None


def _merge_item(old_span: list[str], new_span: list[str]) -> list[str] | None:
    """Изменённый элемент-словарь: комментарии внутри него остаются на своих ключах."""
    old_inner, new_inner = _unitem(old_span), _unitem(new_span)
    if old_inner is None or new_inner is None:
        return None
    merged, tail = _merge(old_inner, new_inner, False)
    lines = merged + tail
    at = next(i for i, x in enumerate(lines) if not _blank(x) and not _comment(x))
    start = _indent(new_span[0])
    lines[at] = " " * start + "-" + lines[at][start + 1 :]
    return lines


def _merge(old_lines: list[str], new_lines: list[str], top: bool) -> tuple[list[str], list[str]]:
    """Слияние одного уровня: (строки, хвост старого уровня)."""
    old_nodes, old_tail = _parse(old_lines)
    new_nodes, _ = _parse(new_lines)
    if any(node.item for node in new_nodes):
        _pair_items(old_nodes, new_nodes)
    by_key = {n.key: n for n in old_nodes}
    used = {n.key for n in new_nodes}
    out: list[str] = []
    # осиротевшие комментарии идут перед ближайшим следующим оставшимся узлом
    lead_of: dict[Any, list[str]] = {}
    pending: list[str] = []
    for node in old_nodes:
        if node.key in used:
            lead_of[node.key] = pending + node.lead
            pending = []
        else:
            pending += _orphan_lead(node.lead)
    for new in new_nodes:
        old = by_key.get(new.key)
        if old is None:
            if top and out:
                out.append("")
            out += new.span
            continue
        delta = new.indent - old.indent
        lead = _shift(lead_of[new.key], delta)
        span = _shift(old.span, delta)
        if _same(old.span, new.span):
            out += lead + span
            continue
        head_new = new.span[0]
        _, old_comment = _split_comment(old.span[0])
        item = _merge_item(span, new.span) if old.item and new.item else None
        if item is not None:
            out += lead + item
        elif old.children and new.children and not new.item:
            body, nested_tail = _merge(span[1:], new.span[1:], False)
            head = head_new + (
                old_comment if old_comment and not _split_comment(head_new)[1] else ""
            )
            out += lead + [head] + body + nested_tail
        else:
            rest = new.span
            if old_comment and not _split_comment(rest[0])[1]:
                if len(rest) == 1:
                    rest = [rest[0] + old_comment]
                else:  # к первой из нескольких строк значения комментарий не приписать
                    lead = [*lead, " " * new.indent + old_comment.strip()]
            out += lead + rest
    tail = pending + old_tail
    return out, tail


def _has_comment(lines: list[str]) -> bool:
    return any(_comment(x) or _split_comment(x)[1] for x in lines)


def carry(old_text: str, new_body: str, header: str, data: dict[str, Any]) -> tuple[str, bool]:
    """Текст site.yaml с комментариями автора: (текст, комментарии потеряны).

    `new_body` - вывод `dump(new)`, `header` - шапка языка, `data` - ожидаемые
    данные. Нет старого файла или комментариев - шапка и `new_body`, как раньше.
    Данные важнее комментариев: если после слияния они разошлись с `data`,
    возвращается безкомментарный текст и флаг True.
    """
    plain = header + new_body
    if not old_text or not _has_comment(old_text.splitlines()):
        return plain, False
    try:
        old_lines = old_text.splitlines()
        old_nodes, _ = _parse(old_lines)
        if not old_nodes:
            return plain, False
        head = old_nodes[0].lead
        has_header = _has_comment(head)
        first = old_lines.index(old_nodes[0].span[0], len(head))
        merged, tail = _merge(old_lines[first:], new_body.splitlines(), True)
        lead = "\n".join(head) + "\n" if has_header else header
        text = lead + "\n".join(merged + tail) + "\n"
        if yaml.safe_load(text) != data:
            return plain, True
        return text, False
    except (ValueError, yaml.YAMLError, IndexError):
        return plain, True
