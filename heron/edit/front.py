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

from heron.core import yamlsafe
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
    raw: str = ""


def read(text: str) -> Front:
    match = FRONTMATTER.match(text)
    head = 1 if text.startswith(BOM) else 0
    if not match:
        return Front(False, head, head, head, {}, None)
    start, end = match.span("body")
    raw = text[start:end]
    try:
        data = yamlsafe.load(raw)
        root = yaml.compose(raw)
    except yaml.YAMLError as exc:
        return Front(True, start, end, match.end(), {}, None, error=str(exc))
    if data is None:
        data, root = {}, None
    if not isinstance(data, dict) or (root is not None and not isinstance(root, MappingNode)):
        return Front(True, start, end, match.end(), {}, None, error="not a mapping", raw=raw)
    return Front(True, start, end, match.end(), data, root, raw=raw)


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
    return front.start + node.start_mark.index, front.start + _leaf_end(node, front.raw)


def shared(front: Front, path: list[str]) -> bool:
    """Значение по пути - якорь `&имя` или ссылка `*имя` (или лежит внутри такого узла).

    Правка такого значения меняет и другое поле, которое на него ссылается, или
    рвёт ссылку: поле только для чтения.
    """
    node: Node | None = front.root
    for key in path:
        if isinstance(node, SequenceNode) and key.isdigit() and int(key) < len(node.value):
            child = node.value[int(key)]
            if _anchored(front.raw, child) or _aliased(front.raw, child, None):
                return True
            node = child
            continue
        if not isinstance(node, MappingNode):
            return False
        found = _find(node, key)
        if found is None:
            return False
        key_node, child = found
        if _anchored(front.raw, child) or _aliased(front.raw, child, key_node):
            return True
        node = child
    return False


def _anchored(raw: str, node: Node) -> bool:
    return raw[node.start_mark.index : node.start_mark.index + 1] == "&"


def _aliased(raw: str, node: Node, key: ScalarNode | None) -> bool:
    """Ссылка `*имя`: `compose` отдаёт узел якоря, а он записан раньше ключа."""
    if raw[node.start_mark.index : node.start_mark.index + 1] == "*":
        return True
    return key is not None and node.start_mark.index < key.end_mark.index


def _pairs(node: MappingNode) -> list[tuple[ScalarNode, Node]]:
    return [(k, v) for k, v in node.value if isinstance(k, ScalarNode)]


def _find(node: MappingNode, key: str) -> tuple[ScalarNode, Node] | None:
    for k, v in _pairs(node):
        if str(k.value) == key:
            return k, v
    return None


def _leaf_end(node: Node, raw: str) -> int:
    """Конец последнего значения узла (у блочных узлов `end_mark` захватывает хвост).

    Блочный скаляр (`|`, `|-`, `>+2`) кончается на последней строке своего текста:
    `end_mark` у него - начало следующей строки, после перевода строки и пустых
    строк, а там уже комментарий или следующий ключ.
    """
    if isinstance(node, MappingNode) and not node.flow_style and node.value:
        last = node.value[-1][1]
        return _leaf_end(last, raw) if last else node.end_mark.index
    if isinstance(node, SequenceNode) and not node.flow_style and node.value:
        return _leaf_end(node.value[-1], raw)
    if isinstance(node, ScalarNode) and node.style in ("|", ">"):
        start, end = node.start_mark.index, node.end_mark.index
        return start + len(raw[start:end].rstrip(" \t\r\n"))
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
        return yamlsafe.load(f"k: {value}") == {"k": value}
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
    if shared(front, path):
        raise FrontError("edit_front_alias")
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
            where = base + _leaf_end(node, front.raw)
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
                    yamlsafe.load(
                        text[base + value_node.start_mark.index : base + value_node.end_mark.index]
                    )
                    or {},
                    rest,
                    value,
                )
                return _replace(text, front, key_node, value_node, merged, nl)
            if (
                isinstance(value_node, ScalarNode)
                and value_node.value in ("", None)
                and value_node.tag.endswith(":null")
            ):
                return _replace(text, front, key_node, value_node, target, nl)
            raise FrontError("edit_front_not_mapping")
        return _replace(text, front, key_node, value_node, value, nl)
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
    text: str, front: Front, key_node: ScalarNode, value_node: Node, value: Any, nl: str
) -> Edit:
    base = front.start
    start = base + value_node.start_mark.index
    end = base + _leaf_end(value_node, front.raw)
    block_node = isinstance(value_node, MappingNode | SequenceNode) and not value_node.flow_style
    empty = isinstance(value_node, ScalarNode) and start == end
    indent = key_node.start_mark.column
    if isinstance(value, dict) and value:
        lines = [block(str(k), v, indent + INDENT, nl) for k, v in value.items()]
        colon = _colon(text, base + key_node.end_mark.index)
        return colon, end, nl + nl.join(lines)
    if isinstance(value, list) and value and block_node and isinstance(value_node, SequenceNode):
        kept = _seq_edit(text, front, value_node, value, nl)
        if kept is not None:
            return kept
        pad = " " * value_node.start_mark.column
        rows = [_item_text(text, base, value_node, index, item) for index, item in enumerate(value)]
        return start, end, (nl + pad).join(rows)
    if (
        isinstance(value, list)
        and value
        and isinstance(value_node, SequenceNode)
        and value_node.flow_style
        and not any(isinstance(item, dict | list) for item in value)
    ):
        # список в скобках: прежние пункты - как написаны (кавычки), новые - как обычно
        olds = [
            (yamlsafe.load(front.raw[i.start_mark.index : i.end_mark.index]), i)
            for i in value_node.value
            if isinstance(i, ScalarNode)
        ]
        parts = []
        for item in value:
            same = next((node for loaded, node in olds if loaded == item), None)
            if same is not None:
                parts.append(front.raw[same.start_mark.index : same.end_mark.index])
            else:
                parts.append(scalar(item, flow=True))
        return start, end, "[" + ", ".join(parts) + "]"
    style = value_node.style if isinstance(value_node, ScalarNode) else None
    if style in ("|", ">") and isinstance(value, str) and value:
        written = _block_scalar(text, front, value_node, value, nl)
        if written is not None:
            return start, end, written
    inline = scalar(value, style if style in ('"', "'") else None)
    if block_node or empty:
        colon = _colon(text, base + key_node.end_mark.index)
        return colon, end, (" " + inline) if inline else ""
    return start, end, inline


def _block_scalar(text: str, front: Front, node: ScalarNode, value: str, nl: str) -> str | None:
    """Новое значение блочного скаляра в том же стиле: `|-`, `|`, `>-` и строки с отступом.

    Отступ - как у прежнего текста. Значение, которое так не записать без потерь
    (ведущий пробел, хвост из нескольких переводов строки, `\r`), - None: тогда
    одной строкой в кавычках.
    """
    if "\r" in value or value.startswith((" ", "\t")) or value.endswith("\n\n"):
        return None
    raw = front.raw[node.start_mark.index : node.end_mark.index]
    lines = raw.splitlines()
    content = next((line for line in lines[1:] if line.strip()), None)
    column = len(content) - len(content.lstrip(" ")) if content else 0
    if column <= 0:
        return None
    body = value[:-1] if value.endswith("\n") else value
    chomp = "" if value.endswith("\n") else "-"
    folded = node.style == ">" and "\n" not in body
    header = (">" if folded else "|") + chomp
    pad = " " * column
    rows = [pad + row if row else "" for row in body.split("\n")]
    try:
        same = yamlsafe.load("k: " + header + "\n" + "\n".join(rows) + "\n") == {"k": value}
    except yaml.YAMLError:
        return None
    return nl.join([header, *rows]) if same else None


def _row(text: str, base: int, item: Node) -> tuple[int, int] | None:
    """Строка пункта блочного списка: (начало строки с `-`, начало значения); иначе None."""
    at = base + item.start_mark.index
    line_start = max(text.rfind("\n", 0, at), text.rfind("\r", 0, at)) + 1
    head = text[line_start:at]
    if head.strip() != "-":
        return None
    return line_start, at


def _seq_edit(text: str, front: Front, node: SequenceNode, value: list, nl: str) -> Edit | None:
    """Блочный список пунктами-строками: правка по пунктам, комментарии между ними на месте.

    Прежние пункты остаются как написаны (кавычки, комментарии в строке), новые
    дописываются после соседнего прежнего, убранные - уходят своей строкой.
    Список не из строк-скаляров - None: его пишут целиком.
    """
    from difflib import SequenceMatcher

    base = front.start
    items = node.value
    rows = []
    for item in items:
        if not isinstance(item, ScalarNode) or item.style in ("|", ">"):
            return None
        row = _row(text, base, item)
        if row is None:
            return None
        leaf = base + _leaf_end(item, front.raw)
        rows.append((row[0], row[1], leaf, _line_bounds(text, leaf)[1]))
    if any(isinstance(entry, dict | list) for entry in value):
        return None
    old = [yamlsafe.load(front.raw[i.start_mark.index : i.end_mark.index]) for i in items]
    pad = text[rows[0][0] : rows[0][1]].split("-")[0]
    region_start, region_end = rows[0][0], rows[-1][3]
    edits: list[tuple[int, int, str]] = []

    def line_after(pos: int) -> int:
        match = re.compile(r"\r\n|\r|\n").search(text, pos)
        return match.end() if match else len(text)

    def new_row(entry: Any) -> str:
        return f"{pad}- {scalar(entry)}"

    def drop(index: int) -> None:
        if index == len(rows) - 1 and index > 0:
            # последний пункт: вместе с переводом строки перед ним, хвост файла не трогаем
            begin = rows[index][0]
            begin -= 2 if text[begin - 2 : begin] == "\r\n" else 1
            edits.append((begin, rows[index][3], ""))
        else:
            stop = min(line_after(rows[index][3]), region_end)
            edits.append((rows[index][0], stop, ""))

    keys = [json.dumps(v, sort_keys=True, default=str) for v in old]
    wanted = [json.dumps(v, sort_keys=True, default=str) for v in value]
    for op, i1, i2, j1, j2 in SequenceMatcher(None, keys, wanted, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        pairs = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for k in range(pairs):
            item = items[i1 + k]
            style = item.style if item.style in ('"', "'") else None
            edits.append((rows[i1 + k][1], rows[i1 + k][2], scalar(value[j1 + k], style)))
        for k in range(i1 + pairs, i2):
            drop(k)
        extra = value[j1 + pairs : j2]
        if extra:
            if i1 + pairs > 0:
                at = rows[i1 + pairs - 1][3]
                edits.append((at, at, "".join(nl + new_row(e) for e in extra)))
            else:
                at = rows[0][0]
                edits.append((at, at, "".join(new_row(e) + nl for e in extra)))
    if not edits:
        return None
    out = text[region_start:region_end]
    for s, e, new in sorted(edits, key=lambda x: (x[0], x[1]), reverse=True):
        out = out[: s - region_start] + new + out[e - region_start :]
    return region_start, region_end, out


def _item_text(text: str, base: int, node: SequenceNode, index: int, item: Any) -> str:
    """Пункт блочного списка: прежний на том же месте - как был написан (кавычки, стиль)."""
    if index < len(node.value):
        old = node.value[index]
        if isinstance(old, ScalarNode):
            raw = text[base + old.start_mark.index : base + old.end_mark.index]
            if yamlsafe.load(raw) == item:
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
    if shared(front, path):
        raise FrontError("edit_front_alias")
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
    stop = base + _leaf_end(value_node, front.raw)
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
