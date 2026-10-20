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
ALLOWED_INLINE = re.compile(r"^\s*<(br|wbr)\s*/?>\s*$", re.I)


COMMENT = re.compile(r"<!--.*?-->", re.S)
FENCE = re.compile(r"(^```.*?^```|^~~~.*?^~~~)", re.S | re.M)


def strip_comments(text: str) -> str:
    """Убрать комментарии автора из markdown.

    Контент пишут с пояснениями для себя: чем этот блок занят, что сюда
    добавить, чего не делать. Это заметки, а не текст страницы. Сырой HTML
    в контенте выключен по умолчанию, поэтому комментарий не исчезает, а
    экранируется и выезжает на страницу как видимая строка.

    Внутри блоков кода комментарии не трогаем: там они и есть содержимое.
    """
    parts = FENCE.split(text)
    return "".join(part if index % 2 else COMMENT.sub("", part) for index, part in enumerate(parts))


# Что можно повесить на заголовок хвостом `{…}` кроме `#id` и `.class`.
# Список закрытый: `onclick=…` в заголовке — это сценарий в странице, и
# запрет сырого HTML (`build.allow_raw_html: false`) не должен обходиться
# через атрибуты. Значения экранирует рендерер markdown-it.
ATTRIBUTES = {"lang", "dir", "title"}
DATA_ATTR = re.compile(r"^data-[a-z0-9][a-z0-9-]*$")
ID_OR_CLASS = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")


def allowed(key: str) -> bool:
    """Можно ли атрибут `key=…` на заголовке."""
    return key in ATTRIBUTES or bool(DATA_ATTR.match(key))


def parse_attrs(body: str) -> tuple[str | None, list[str], dict[str, str]]:
    """Разобрать `#id .class key=value` в идентификатор, классы и прочие атрибуты.

    Атрибуты вне разрешённого набора сюда не попадают — их отсекает
    `forbidden_attrs` раньше, с номером строки; здесь они молча
    отбрасываются, чтобы рендер не вывел их ни при каком пути.
    """
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
            if key and allowed(key.lower()):
                rest[key.lower()] = value.strip("\"'")
    return anchor, classes, rest


def forbidden_attrs(md: MarkdownIt, body: str, path: str, offset: int = 0) -> None:
    """E025 на атрибут заголовка вне разрешённого набора.

    Разбор токенами, а не строками: «заголовок» внутри блока кода — это
    код, и ругаться на него нельзя.
    """
    lines = body.splitlines()
    for token in md.parse(body):
        # Хвост `{…}` к этому моменту уже снят правилом заголовков, поэтому
        # смотрим исходную строку заголовка по карте токена.
        if token.type != "heading_open" or not token.map:
            continue
        match = ATTRS.search(lines[token.map[0]]) if token.map[0] < len(lines) else None
        if not match:
            continue
        for chunk in match.group("body").split():
            key = chunk.partition("=")[0].lower()
            bad = ("=" in chunk and not allowed(key)) or (
                chunk.startswith(("#", ".")) and not ID_OR_CLASS.match(chunk[1:])
            )
            if bad:
                line = offset + (token.map[0] if token.map else 0) + 1
                raise HeronError(
                    code="E025",
                    message=f"недопустимый атрибут заголовка: {chunk[:60]}",
                    path=path,
                    line=line,
                    hint="у заголовка бывают #id, .class, lang=, dir=, title= и data-*=; "
                    "обработчики событий и стили — нет",
                )


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


MEDIA_PATH = re.compile(r"^(?:\./)?(?:media|img)/", re.I)


def _media_paths(state) -> None:
    """`media/x.svg` в картинке и ссылке — от корня сайта: `/media/x.svg`.

    Контракт пишет пути к ресурсам от корня сайта, а браузер читает
    `media/x.svg` относительно страницы: на `/services/design/` это
    `/services/design/media/x.svg`, которого нет. Переписывается здесь, на
    токенах, — один раз и только у картинок и ссылок, а не в тексте.
    """
    for token in state.tokens:
        for child in token.children or []:
            name = "src" if child.type == "image" else "href" if child.type == "link_open" else ""
            value = child.attrGet(name) if name else None
            if isinstance(value, str) and MEDIA_PATH.match(value):
                child.attrSet(name, "/" + value.removeprefix("./"))


def make(allow_raw_html: bool = False) -> MarkdownIt:
    """Собрать парсер markdown."""
    md = MarkdownIt("commonmark", {"html": allow_raw_html, "typographer": False})
    md.enable(["table", "strikethrough"])
    md.core.ruler.after("block", "heron_heading_attrs", _heading_attrs)
    md.core.ruler.push("heron_media_paths", _media_paths)
    return md


# Разборщик только для поиска сырого HTML: с включённым HTML он отличает
# тег в тексте от `<div>` в блоке кода или в `инлайн-коде` — там это пример,
# а не разметка, и ругаться на него нельзя.
_HTML_FINDER = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])


CODE_SPAN = re.compile(r"(?<!`)(?P<fence>`+)(?!`)(?P<code>.+?)(?<!`)(?P=fence)(?!`)")


def without_code(text: str) -> str:
    """Тот же текст, где код — блоки и `инлайн` — заменён пробелами.

    Код в странице — пример, а не содержимое: `![фото](/media/x.jpg)` в
    таблице «как писать» не просит движок искать файл. Всё, что читает
    сырой markdown регулярками (пути к медиа, заметки), смотрит в текст
    через эту функцию. Длина строк и их число сохраняются — номера строк
    в отчёте остаются верными.

    Блоки находит тот же разборщик commonmark, что рендерит страницу:
    огороженные и с отступом, в том числе внутри списков и цитат.
    """
    lines = text.split("\n")
    for token in _HTML_FINDER.parse(text):
        if token.type in ("fence", "code_block") and token.map:
            start, end = token.map
            for index in range(start, min(end, len(lines))):
                lines[index] = " " * len(lines[index])
    out = "\n".join(lines)
    return CODE_SPAN.sub(lambda match: " " * len(match.group(0)), out)


def raw_html(body: str) -> list[tuple[int, str]]:
    """Сырой HTML вне кода: (строка от начала тела, фрагмент)."""
    lines = body.splitlines()
    found: list[tuple[int, str]] = []
    for token in _HTML_FINDER.parse(body):
        start = token.map[0] if token.map else 0
        if token.type == "html_block":
            text = token.content.strip()
            if text.startswith("<!--"):
                continue  # заметка автора, её снимает strip_comments
            found.append((start, text.splitlines()[0] if text else ""))
        elif token.type == "inline":
            for child in token.children or []:
                if child.type != "html_inline":
                    continue
                text = child.content
                if text.startswith("<!--") or ALLOWED_INLINE.match(text):
                    continue
                number = next((i for i in range(start, len(lines)) if text in lines[i]), start)
                found.append((number, text))
    return found


def guard_raw_html(body: str, path: str, allow: bool, offset: int = 0) -> None:
    """Остановить сборку, если в теле есть сырой HTML, а он запрещён.

    Разрешено без флага: `<br>` и `<wbr>` внутри строки, HTML-комментарии
    (заметки автора) и любой HTML внутри блоков кода и `инлайн-кода`.
    """
    if allow:
        return
    for number, text in raw_html(body):
        raise HeronError(
            code="E015",
            message=f"сырой HTML в markdown: {text.strip()[:80]}",
            path=path,
            line=offset + number + 1,
            hint=(
                "перепишите средствами markdown, или разрешите осознанно: "
                "build.allow_raw_html: true в site.yaml"
            ),
        )
