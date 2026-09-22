"""Нарезка тела на секции.

Секция — заголовок с якорем и всё содержимое до следующего заголовка того же
или более высокого уровня с якорем. Заголовки без якоря секцию не начинают
и принадлежат текущей. Текст до первой секции доступен теме как `intro`.

Именно это правило делает markdown-файл именованным складом контента, а тему —
раскладкой: порядок секций в файле не влияет на порядок блоков на странице.

Спецификация: docs/spec/21-engine.md, раздел 5.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

from heron.core.errors import HeronError
from heron.core.models import Section
from heron.core.parser import markdown

SECTION_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _inline_text(tokens: list[Token], index: int) -> str:
    """Текст заголовка: следующий inline-токен после heading_open."""
    for token in tokens[index + 1 :]:
        if token.type == "inline":
            return token.content.strip()
        if token.type == "heading_close":
            break
    return ""


def _classes(token: Token) -> list[str]:
    raw = token.attrGet("class") or ""
    return [c for c in raw.split() if c]


def _render(md: MarkdownIt, tokens: list[Token], env: dict) -> str:
    return md.renderer.render(tokens, md.options, env).strip()


def _raw(lines: list[str], start: int | None, end: int | None) -> str:
    if start is None:
        return ""
    return "\n".join(lines[start : end if end is not None else len(lines)]).strip()


def split(
    md: MarkdownIt,
    body: str,
    path: str,
    offset: int = 0,
) -> tuple[Section | None, dict[str, Section]]:
    """Разрезать тело на вводную часть и секции по идентификаторам."""
    body = markdown.strip_comments(body)
    env: dict = {}
    tokens = md.parse(body, env)
    lines = body.splitlines()

    # Границы: индекс токена, уровень, id, классы, заголовок, строка
    marks: list[tuple[int, int, str, list[str], str, int]] = []
    base_level: int | None = None

    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        anchor = token.attrGet("id")
        if not anchor:
            continue
        level = int(token.tag[1:])
        if base_level is None:
            base_level = level
        elif level > base_level:
            continue  # вложенный заголовок с якорем принадлежит текущей секции
        line = (token.map[0] if token.map else 0) + offset + 1
        if not SECTION_ID.match(anchor):
            raise HeronError(
                code="E016",
                message=f"недопустимый идентификатор секции {anchor!r}",
                path=path,
                line=line,
                hint="идентификатор — латиница, цифры и дефис: {#quick-facts}",
            )
        marks.append((index, level, anchor, _classes(token), _inline_text(tokens, index), line))

    intro: Section | None = None
    if not marks:
        raw = body.strip()
        if raw:
            intro = Section(id="intro", title="", level=0, raw=raw, html=_render(md, tokens, env))
        return intro, {}

    first_token = marks[0][0]
    first_line = tokens[first_token].map[0] if tokens[first_token].map else 0
    if first_token > 0:
        raw = _raw(lines, 0, first_line)
        if raw:
            intro = Section(
                id="intro",
                title="",
                level=0,
                raw=raw,
                html=_render(md, tokens[:first_token], env),
                line=offset + 1,
            )

    sections: dict[str, Section] = {}
    for position, (index, level, anchor, classes, title, line) in enumerate(marks):
        next_index = marks[position + 1][0] if position + 1 < len(marks) else len(tokens)
        body_start = tokens[index].map[1] if tokens[index].map else None
        body_end = None
        if position + 1 < len(marks):
            following = tokens[marks[position + 1][0]]
            body_end = following.map[0] if following.map else None

        if anchor in sections:
            raise HeronError(
                code="E003",
                message=f"идентификатор секции {anchor!r} встречается в файле дважды",
                path=path,
                line=line,
                hint=f"первый раз — строка {sections[anchor].line}",
            )

        content = [t for t in tokens[index:next_index]]
        # выбросить сам заголовок секции: его рисует тема, а не содержимое
        content = content[3:] if len(content) >= 3 else []

        sections[anchor] = Section(
            id=anchor,
            title=title,
            level=level,
            classes=classes,
            raw=_raw(lines, body_start, body_end),
            html=_render(md, content, env),
            line=line,
        )

    return intro, sections
