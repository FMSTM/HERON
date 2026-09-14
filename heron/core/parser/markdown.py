"""Общее окружение markdown-it и правило атрибутов заголовка.

Атрибуты `{#id .class}` в конце заголовка — не украшение синтаксиса, а то,
на чём стоит вся нарезка на секции. Готовые плагины атрибутов вешают их
отдельной строкой перед блоком, а контракт данных требует хвоста строки
(`## Коротко {#quick-facts}`), поэтому правило своё — двадцать строк вместо
зависимости, которая делает не то.

Сырой HTML по умолчанию запрещён (`build.allow_raw_html: false`): при переносе
контента из WordPress туда приезжает `<script>` от виджета, и лучше, чтобы
сборка на этом упала, чем молча вклеила.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

from heron.core.errors import HeronError

ATTRS = re.compile(r"\s*\{(?P<body>[^{}]*)\}\s*$")
RAW_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][a-zA-Z0-9:-]*(\s[^<>]*)?/?>")
ALLOWED_INLINE = re.compile(r"^\s*<(br|wbr)\s*/?>\s*$", re.I)


def parse_attrs(body: str) -> tuple[str | None, list[str], dict[str, str]]:
    """Разобрать `#id .class key=value` в идентификатор, классы и прочие атрибуты."""
    anchor: str | None = None
    classes: list[str] = []
    rest: dict[str, str] = {}
    for chunk in body.split():
        if chunk.startswith("#") and len(chunk) > 1:
            anchor = chunk[1:]
        elif chunk.startswith(".") and len(chunk) > 1:
            classes.append(chunk[1:])
        elif "=" in chunk:
            key, _, value = chunk.partition("=")
            if key:
                rest[key] = value.strip("\"'")
    return anchor, classes, rest


def _heading_attrs(state) -> None:
    """Снять `{...}` с хвоста заголовка и повесить атрибутами на сам заголовок.

    Работает между разбором блоков и разбором инлайна: содержимое заголовка
    уже известно строкой, но ещё не разобрано на токены, поэтому хвост можно
    просто отрезать — в вёрстку он не попадёт.
    """
    tokens = state.tokens
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or index + 1 >= len(tokens):
            continue
        inline = tokens[index + 1]
        if inline.type != "inline":
            continue
        match = ATTRS.search(inline.content)
        if not match:
            continue
        anchor, classes, rest = parse_attrs(match.group("body"))
        if anchor is None and not classes and not rest:
            continue
        inline.content = inline.content[: match.start()].rstrip()
        if anchor:
            token.attrSet("id", anchor)
        if classes:
            token.attrSet("class", " ".join(classes))
        for key, value in rest.items():
            token.attrSet(key, value)


def make(allow_raw_html: bool = False) -> MarkdownIt:
    """Собрать парсер markdown."""
    md = MarkdownIt("commonmark", {"html": allow_raw_html, "typographer": False})
    md.enable(["table", "strikethrough"])
    md.core.ruler.after("block", "heron_heading_attrs", _heading_attrs)
    return md


def guard_raw_html(body: str, path: str, allow: bool, offset: int = 0) -> None:
    """Остановить сборку, если в теле есть сырой HTML, а он запрещён."""
    if allow:
        return
    for number, line in enumerate(body.splitlines(), start=offset + 1):
        if RAW_HTML.search(line) and not ALLOWED_INLINE.match(line):
            raise HeronError(
                code="E015",
                message=f"сырой HTML в markdown: {line.strip()[:80]}",
                path=path,
                line=number,
                hint=(
                    "перепишите средствами markdown, или разрешите осознанно: "
                    "build.allow_raw_html: true в site.yaml"
                ),
            )
