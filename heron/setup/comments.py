"""Комментарии автора в `site.yaml` переживают сохранение через анкету.

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

_KEY = re.compile(r"""^(?:"[^"]*"|'[^']*'|[^\s#'"\-\[\]{},&*!|>%@`][^:#]*?|-[^\s:][^:]*?):(?:\s|$)""")
_BLOCK_SCALAR = re.compile(r"[|>][+-]?\d*$")


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
    for match in re.finditer(r"\s+#", head):
        before = head[: match.start()]
        if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
            return before, head[match.start() :].rstrip()
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


def _merge(old_lines: list[str], new_lines: list[str], top: bool) -> tuple[list[str], list[str]]:
    """Слияние одного уровня: (строки, хвост старого уровня)."""
    old_nodes, old_tail = _parse(old_lines)
    new_nodes, _ = _parse(new_lines)
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
        if old.children and new.children and not new.item:
            body = _merge(span[1:], new.span[1:], False)[0]
            head = head_new + (old_comment if old_comment and not _split_comment(head_new)[1] else "")
            out += lead + [head] + body
        else:
            rest = new.span
            if old_comment and not _split_comment(rest[0])[1] and not old.children:
                rest = [rest[0] + old_comment, *rest[1:]]
            out += lead + rest
    tail = pending + old_tail
    return out, tail


def _has_comment(lines: list[str]) -> bool:
    return any(_comment(x) for x in lines)


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
