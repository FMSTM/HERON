"""SEO-блок страницы: значения с их местом в тексте и правка на месте.

YAML читается дважды: `safe_load` даёт значения (как их видит сборка),
`compose` - узлы с позициями. Правка заменяет только символы значения:
комментарии, пустые строки, порядок ключей и кавычки соседних полей остаются
как были. Нового ключа в файле нет - сначала ищется закомментированная
заготовка `# og_title:   # подсказка` (так пишет SEO-блок `heron new`/`page`)
и раскомментируется с сохранением подсказки, иначе ключ дописывается перед
закрывающей `---`. Сброс поля возвращает его в заготовку `# ключ:`.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from heron.core.parser.frontmatter import FRONTMATTER
from heron.edit.text import BOM

INDENT = 2


class FrontError(ValueError):
    """Значение не записать в это место SEO-блока: `args[0]` - ключ сообщения."""


@dataclass(slots=True)
class Front:
    """Положение SEO-блока в тексте.

    `start`/`end` - тело YAML между строками `---`; `body` - где начинается текст
    страницы. Блока нет - `present` ложно, `body` - начало текста после BOM.
    `error` - YAML не читается: поля SEO-блока только для чтения.
    """

    present: bool
    start: int
    end: int
    body: int
    data: dict[str, Any]
    root: MappingNode | None
    error: str | None = None


def read(text: str) -> Front:
    match = FRONTMATTER.match(text)
    head = 1 if text.startswith(BOM) else 0
    if not match:
        return Front(False, head, head, head, {}, None)
    start, end = match.span("body")
    raw = text[start:end]
    try:
        data = yaml.safe_load(raw)
        root = yaml.compose(raw)
    except yaml.YAMLError as exc:
        return Front(True, start, end, match.end(), {}, None, error=str(exc))
    if data is None:
        data, root = {}, None
    if not isinstance(data, dict) or (root is not None and not isinstance(root, MappingNode)):
        return Front(True, start, end, match.end(), {}, None, error="not a mapping")
    return Front(True, start, end, match.end(), data, root)


# --- значения ---------------------------------------------------------------------


def lookup(front: Front, path: list[str]) -> tuple[bool, Any]:
    """(есть ли ключ, значение) по пути ключей."""
    node: Any = front.data
    for key in path:
        if isinstance(node, list) and key.isdigit() and int(key) < len(node):
            node = node[int(key)]
            continue
        if not isinstance(node, dict) or key not in node:
            return False, None
        node = node[key]
    return True, node


def span(front: Front, path: list[str]) -> tuple[int, int] | None:
    """Отрезок значения по пути ключей (абсолютные смещения); нет ключа - None."""
    node: Node | None = front.root
    for key in path:
        if isinstance(node, SequenceNode) and key.isdigit() and int(key) < len(node.value):
            node = node.value[int(key)]
            continue
        if not isinstance(node, MappingNode):
            return None
        found = _find(node, key)
        if found is None:
            return None
        node = found[1]
    if node is None:
        return None
    return front.start + node.start_mark.index, front.start + _leaf_end(node)


def _pairs(node: MappingNode) -> list[tuple[ScalarNode, Node]]:
    return [(k, v) for k, v in node.value if isinstance(k, ScalarNode)]


def _find(node: MappingNode, key: str) -> tuple[ScalarNode, Node] | None:
    for k, v in _pairs(node):
        if str(k.value) == key:
            return k, v
    return None


def _leaf_end(node: Node) -> int:
    """Конец последнего значения узла (у блочных узлов `end_mark` захватывает хвост)."""
    if isinstance(node, MappingNode) and not node.flow_style and node.value:
        return _leaf_end(node.value[-1][1]) if node.value[-1][1] else node.end_mark.index
    if isinstance(node, SequenceNode) and not node.flow_style and node.value:
        return _leaf_end(node.value[-1])
    return node.end_mark.index


# --- запись значений YAML -----------------------------------------------------------

SPECIAL = set("-?:,[]{}#&*!|>'\"%@`")


def _plain_ok(value: str, flow: bool = False) -> bool:
    if not value or value != value.strip() or "\n" in value or "\r" in value:
        return False
    if value[0] in SPECIAL or ": " in value or " #" in value or value.endswith(":"):
        return False
    if flow and any(ch in value for ch in ",[]{}"):
        return False
    try:
        return yaml.safe_load(f"k: {value}") == {"k": value}
    except yaml.YAMLError:
        return False


def scalar(value: Any, style: str | None = None, flow: bool = False) -> str:
    """Значение одной строкой YAML. `style` - кавычки исходного значения, их сохраняем."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(scalar(item, flow=True) for item in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(
            f"{scalar(str(k), flow=True)}: {scalar(v, flow=True)}" for k, v in value.items()
        )
        return "{" + inner + "}"
    value = str(value)
    if style == "'" and "\n" not in value and "\r" not in value:
        return "'" + value.replace("'", "''") + "'"
    if style != '"' and _plain_ok(value, flow):
        return value
    return json.dumps(value, ensure_ascii=False)


def block(key: str, value: Any, indent: int, nl: str) -> str:
    """Пара `ключ: значение` строками с отступом; вложенные блоки - на 2 глубже."""
    pad = " " * indent
    head = f"{pad}{scalar(key)}:"
    if isinstance(value, dict) and value:
        rows = [block(str(k), v, indent + INDENT, nl) for k, v in value.items()]
        return nl.join([head, *rows])
    if isinstance(value, list) and value and any(isinstance(i, dict | list) for i in value):
        rows = [f"{pad}{' ' * INDENT}- {scalar(item)}" for item in value]
        return nl.join([head, *rows])
    text = scalar(value)
    return f"{head} {text}" if text else head


def _nest(path: list[str], value: Any) -> Any:
    for key in reversed(path):
        value = {key: value}
    return value


# --- правка ----------------------------------------------------------------------

Edit = tuple[int, int, str]


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    """Начало строки и конец её содержимого (до перевода строки)."""
    start = text.rfind("\n", 0, pos) + 1
    cr = text.rfind("\r", 0, pos) + 1
    start = max(start, cr)
    match = re.compile(r"\r\n|\r|\n").search(text, pos)
    return start, (match.start() if match else len(text))


def _placeholder(text: str, front: Front, key: str) -> tuple[int, int, str] | None:
    """Заготовка `# key: пример   # подсказка` верхнего уровня: (начало, конец, подсказка)."""
    pattern = re.compile(
        r"^#[ \t]?" + re.escape(key) + r":(?P<rest>[^\r\n]*)(?=\r\n|\r|\n|\Z)", re.M
    )
    match = pattern.search(text, front.start, front.end)
    if not match:
        return None
    rest = match.group("rest")
    hint = re.search(r"[ \t]#", rest)
    if hint is None:
        return match.start(), match.end(), ""
    column = match.start("rest") - match.start() + hint.start() + 1
    return match.start(), match.end(), " " * column + rest[hint.start() + 1 :]


def _with_hint(line: str, hint: str) -> str:
    """Строка ключа и подсказка заготовки на прежнем столбце (или через пробел)."""
    if not hint:
        return line
    column = len(hint) - len(hint.lstrip(" "))
    gap = max(1, column - len(line))
    return line + " " * gap + hint.lstrip(" ")


def _indent_of(text: str, node: MappingNode) -> int:
    first = node.value[0][0]
    return first.start_mark.column


def set_value(text: str, front: Front, path: list[str], value: Any, nl: str) -> Edit:
    """Отрезок и замена, которые записывают `value` по пути ключей."""
    if front.error is not None:
        raise FrontError("edit_front_broken")
    if not front.present:
        head = 1 if text.startswith(BOM) else 0
        entry = block(path[0], _nest(path[1:], value), 0, nl)
        return head, head, f"---{nl}{entry}{nl}---{nl}{nl}"
    base = front.start
    node: Node | None = front.root
    for depth, key in enumerate(path):
        rest = path[depth + 1 :]
        if node is None:
            # пустой SEO-блок: ключа нет вовсе
            return _insert_top(text, front, path, value, nl)
        if isinstance(node, MappingNode) and node.flow_style:
            raise FrontError("edit_front_flow")
        if not isinstance(node, MappingNode):
            raise FrontError("edit_front_not_mapping")
        found = _find(node, key)
        if found is None:
            if depth == 0:
                return _insert_top(text, front, path, value, nl)
            indent = _indent_of(text, node)
            where = base + _leaf_end(node)
            _, line_end = _line_bounds(text, where)
            entry = block(key, _nest(rest, value), indent, nl)
            return line_end, line_end, nl + entry
        key_node, value_node = found
        block_map = isinstance(value_node, MappingNode) and not value_node.flow_style
        if rest and block_map and value_node.value:
            node = value_node
            continue
        if rest:
            target = _nest(rest, value)
            if isinstance(value_node, MappingNode) and value_node.flow_style:
                merged = _merge(
                    yaml.safe_load(
                        text[base + value_node.start_mark.index : base + value_node.end_mark.index]
                    )
                    or {},
                    rest,
                    value,
                )
                return _replace(text, base, key_node, value_node, merged, nl)
            if (
                isinstance(value_node, ScalarNode)
                and value_node.value in ("", None)
                and value_node.tag.endswith(":null")
            ):
                return _replace(text, base, key_node, value_node, target, nl)
            raise FrontError("edit_front_not_mapping")
        return _replace(text, base, key_node, value_node, value, nl)
    raise FrontError("edit_front_not_mapping")  # pragma: no cover - путь не пуст


def _merge(data: dict, path: list[str], value: Any) -> dict:
    out = dict(data)
    node = out
    for key in path[:-1]:
        child = node.get(key)
        node[key] = dict(child) if isinstance(child, dict) else {}
        node = node[key]
    node[path[-1]] = value
    return out


def _replace(
    text: str, base: int, key_node: ScalarNode, value_node: Node, value: Any, nl: str
) -> Edit:
    start = base + value_node.start_mark.index
    end = base + _leaf_end(value_node)
    block_node = isinstance(value_node, MappingNode | SequenceNode) and not value_node.flow_style
    empty = isinstance(value_node, ScalarNode) and start == end
    indent = key_node.start_mark.column
    if isinstance(value, dict) and value:
        lines = [block(str(k), v, indent + INDENT, nl) for k, v in value.items()]
        colon = _colon(text, base + key_node.end_mark.index)
        return colon, end, nl + nl.join(lines)
    if isinstance(value, list) and value and block_node and isinstance(value_node, SequenceNode):
        pad = " " * value_node.start_mark.column
        rows = [_item_text(text, base, value_node, index, item) for index, item in enumerate(value)]
        return start, end, (nl + pad).join(rows)
    style = value_node.style if isinstance(value_node, ScalarNode) else None
    inline = scalar(value, style if style in ('"', "'") else None)
    if block_node or empty:
        colon = _colon(text, base + key_node.end_mark.index)
        return colon, end, (" " + inline) if inline else ""
    return start, end, inline


def _item_text(text: str, base: int, node: SequenceNode, index: int, item: Any) -> str:
    """Пункт блочного списка: прежний на том же месте - как был написан (кавычки, стиль)."""
    if index < len(node.value):
        old = node.value[index]
        if isinstance(old, ScalarNode):
            raw = text[base + old.start_mark.index : base + old.end_mark.index]
            if yaml.safe_load(raw) == item:
                return "- " + raw
            return "- " + scalar(item, old.style if old.style in ('"', "'") else None)
    return f"- {scalar(item)}"


def _colon(text: str, after_key: int) -> int:
    """Позиция сразу после `:` ключа."""
    return text.index(":", after_key) + 1


def _insert_top(text: str, front: Front, path: list[str], value: Any, nl: str) -> Edit:
    entry = block(path[0], _nest(path[1:], value), 0, nl)
    found = _placeholder(text, front, path[0])
    if found is not None:
        start, end, hint = found
        first, *more = entry.split(nl)
        return start, end, nl.join([_with_hint(first, hint), *more])
    return front.end, front.end, nl + entry


def unset(text: str, front: Front, path: list[str], nl: str) -> Edit | None:
    """Убрать ключ: верхний уровень - обратно в заготовку `# ключ:`, вложенный - строки прочь.

    Ключа нет - None. Пустой после этого родитель убирается тоже.
    """
    if front.error is not None:
        raise FrontError("edit_front_broken")
    node: Node | None = front.root
    chain: list[tuple[MappingNode, ScalarNode, Node]] = []
    for key in path:
        if not isinstance(node, MappingNode) or node.flow_style:
            if isinstance(node, MappingNode) and node.flow_style:
                raise FrontError("edit_front_flow")
            return None
        found = _find(node, key)
        if found is None:
            return None
        chain.append((node, *found))
        node = found[1]
    # пустой родитель уходит вместе с последним ключом
    while len(chain) > 1 and len(chain[-1][0].value) == 1:
        chain.pop()
    parent, key_node, value_node = chain[-1]
    base = front.start
    start, _ = _line_bounds(text, base + key_node.start_mark.index)
    stop = base + _leaf_end(value_node)
    _, line_end = _line_bounds(text, stop)
    tail = text[stop:line_end]
    hint = tail[tail.index("#") :] if "#" in tail else ""
    if len(chain) == 1:
        line = f"# {key_node.value}:"
        _, key_end = _line_bounds(text, base + key_node.end_mark.index)
        if key_end < stop:
            # значение со следующих строк: подсказка - на строке самого ключа
            after = text[base + key_node.end_mark.index : key_end]
            hint = after[after.index("#") :] if "#" in after else ""
            column = base + key_node.end_mark.index + after.index("#") - start if hint else 0
        elif hint:
            last_start, _ = _line_bounds(text, stop)
            column = stop + tail.index("#") - last_start
        if not hint:
            return start, line_end, line
        return start, line_end, _with_hint(line, " " * column + hint)
    # вложенный: строки ключа целиком, с переводом строки перед ними
    previous = start - 1
    if previous > 0 and text[previous] == "\n" and text[previous - 1] == "\r":
        previous -= 1
    return max(previous, front.start), line_end, ""
