"""Структурированные секции: что за модуль и какие в нём данные.

Никакого своего синтаксиса. Всё, что ниже, — валидный markdown, читаемый
глазами и в любом редакторе; модуль определяется по форме содержимого,
а при неоднозначности — явным классом в якоре.

Правило важнее удобства: шесть статей различаются только набором модулей
внутри секций. Если зашивать это в шаблон, каждая новая статья потребует
правки темы. При этом правиле седьмая статья — один markdown-файл
и ноль строк кода.

Разбор ошибается мягко: не распознал формат — отдал прозой и записал
предупреждение. Валить сборку из-за пропущенной палочки в таблице нельзя.

Спецификация: docs/spec/20-data-contract.md, раздел 6.1.
"""

from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from heron.core.errors import Warning_
from heron.core.models import Section

BY_CLASS = {
    "alert": "alert-list",
    "callout": "callout",
    "checklist": "checklist",
    "facts": "facts",
    "faq": "faq",
    "gallery": "gallery",
    "list": "list",
    "prose": "prose",
    "steps": "steps",
    "table": "table",
    "timeline": "timeline",
    "two-lists": "two-lists",
}

PAIR = re.compile(r"^\s*(?P<key>[^|]+?)\s*\|\s*(?P<value>.+?)\s*$")
STEP_TITLE = re.compile(r"^\s*\*\*(?P<title>[^*]+?)\.?\*\*\.?\s*(?P<rest>.*)$", re.S)


def _render(md: MarkdownIt, tokens: list[Token], env: dict) -> str:
    return md.renderer.render(tokens, md.options, env).strip()


def _blocks(tokens: list[Token], open_type: str, close_type: str) -> list[tuple[int, int]]:
    """Пары индексов открывающего и закрывающего токена верхнего уровня."""
    out: list[tuple[int, int]] = []
    depth = 0
    start = 0
    for index, token in enumerate(tokens):
        if token.type == open_type:
            if depth == 0:
                start = index
            depth += 1
        elif token.type == close_type and depth:
            depth -= 1
            if depth == 0:
                out.append((start, index))
    return out


def _items(md: MarkdownIt, tokens: list[Token], env: dict) -> list[str]:
    """Содержимое пунктов списка как HTML."""
    return [
        _render(md, tokens[start + 1 : end], env)
        for start, end in _blocks(tokens, "list_item_open", "list_item_close")
    ]


def _headed_groups(md: MarkdownIt, tokens: list[Token], env: dict) -> list[dict[str, Any]]:
    """Группы `### Заголовок` с содержимым до следующего такого же."""
    starts = [i for i, t in enumerate(tokens) if t.type == "heading_open" and t.tag == "h3"]
    groups: list[dict[str, Any]] = []
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(tokens)
        title = tokens[index + 1].content.strip() if index + 1 < len(tokens) else ""
        content = tokens[index + 3 : end]
        groups.append(
            {
                "title": title,
                "html": _render(md, content, env),
                "items": _items(md, content, env),
                "has_list": any(t.type == "bullet_list_open" for t in content),
            }
        )
    return groups


def _facts(raw: str) -> list[dict[str, str]] | None:
    """Строки вида `Ключ | Значение`. Таблица без шапки, а не markdown-таблица."""
    rows: list[dict[str, str]] = []
    bad = 0
    for line in (line for line in raw.splitlines() if line.strip()):
        if set(line.strip()) <= set("|-: "):
            return None  # это markdown-таблица, у неё есть строка-разделитель
        match = PAIR.match(line)
        if match and "|" in line:
            rows.append({"key": match.group("key"), "value": match.group("value")})
        else:
            bad += 1
    if not rows or bad > len(rows):
        return None
    return rows


def _table(md: MarkdownIt, tokens: list[Token], env: dict) -> dict[str, Any] | None:
    """Обычная markdown-таблица: первая строка — шапка."""
    if not any(t.type == "table_open" for t in tokens):
        return None

    head: list[str] = []
    rows: list[list[str]] = []
    current: list[str] | None = None
    in_head = False

    for index, token in enumerate(tokens):
        if token.type == "thead_open":
            in_head = True
        elif token.type == "thead_close":
            in_head = False
        elif token.type == "tr_open":
            current = []
        elif token.type == "tr_close":
            if current is not None:
                if in_head:
                    head = current
                else:
                    rows.append(current)
            current = None
        elif token.type in ("th_open", "td_open") and current is not None:
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            current.append(following.content.strip() if following else "")

    return {"head": head, "rows": rows}


def _steps(md: MarkdownIt, tokens: list[Token], env: dict) -> list[dict[str, str]] | None:
    if not any(t.type == "ordered_list_open" for t in tokens):
        return None
    steps: list[dict[str, str]] = []
    for start, end in _blocks(tokens, "list_item_open", "list_item_close"):
        inner = tokens[start + 1 : end]
        text = next((t.content for t in inner if t.type == "inline"), "")
        match = STEP_TITLE.match(text)
        if match:
            steps.append(
                {"title": match.group("title").strip(), "html": match.group("rest").strip()}
            )
        else:
            steps.append({"title": "", "html": _render(md, inner, env)})
    return steps or None


def detect(md: MarkdownIt, section: Section) -> tuple[str, Any, list[Warning_]]:
    """Определить модуль секции и разобрать её данные."""
    warnings: list[Warning_] = []
    env: dict = {}
    tokens = md.parse(section.raw, env)

    explicit: str | None = None
    for name in section.classes:
        if name in BY_CLASS:
            explicit = BY_CLASS[name]
            break
        warnings.append(
            Warning_(f"секция {section.id!r}: неизвестный класс {name!r}, определяю по содержимому")
        )

    groups = _headed_groups(md, tokens, env)
    with_lists = [g for g in groups if g["has_list"]]

    def parse(kind: str) -> tuple[str, Any] | None:
        if kind == "facts":
            rows = _facts(section.raw)
            return ("facts", rows) if rows is not None else None
        if kind == "timeline":
            # шкала бывает и парами «период | событие», и нумерованными шагами
            rows = _facts(section.raw)
            if rows is not None:
                return "timeline", rows
            steps = _steps(md, tokens, env)
            return ("timeline", steps) if steps else None
        if kind == "table":
            table = _table(md, tokens, env)
            return ("table", table) if table else None
        if kind == "steps":
            steps = _steps(md, tokens, env)
            return ("steps", steps) if steps else None
        if kind == "faq":
            return ("faq", [{"q": g["title"], "a": g["html"]} for g in groups]) if groups else None
        if kind in ("two-lists", "checklist"):
            return (kind, with_lists) if with_lists else None
        if kind in ("list", "alert-list", "gallery"):
            items = _items(md, tokens, env)
            return (kind, items) if items else None
        if kind == "callout":
            quotes = _blocks(tokens, "blockquote_open", "blockquote_close")
            if quotes:
                start, end = quotes[0]
                return "callout", _render(md, tokens[start + 1 : end], env)
            return None
        if kind == "prose":
            return "prose", section.html
        return None

    if explicit:
        parsed = parse(explicit)
        if parsed:
            return parsed[0], parsed[1], warnings
        warnings.append(
            Warning_(
                f"секция {section.id!r}: класс {explicit!r} не подходит к содержимому, "
                "вывожу прозой"
            )
        )
        return "prose", section.html, warnings

    # автоопределение по форме содержимого
    order = ["table", "facts", "steps"]
    if len(with_lists) >= 3:
        order.append("checklist")
    elif len(with_lists) == 2:
        order.append("two-lists")
    if groups and not with_lists:
        order.append("faq")
    order += ["callout", "list"]

    for kind in order:
        parsed = parse(kind)
        if parsed:
            return parsed[0], parsed[1], warnings

    return "prose", section.html, warnings


def apply(md: MarkdownIt, sections: dict[str, Section]) -> list[Warning_]:
    """Проставить модуль и данные каждой секции."""
    warnings: list[Warning_] = []
    for section in sections.values():
        kind, data, found = detect(md, section)
        section.kind, section.data = kind, data
        warnings.extend(found)
    return warnings
