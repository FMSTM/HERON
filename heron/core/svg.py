"""SVG без исполняемого: проверка загрузки в студии и `heron check` (media/, static/ и тема).

SVG из `media/`, `static/` и темы сайт отдаёт как есть, и открытый по прямой ссылке
файл - документ со своими скриптами. Поэтому SVG разбирается XML-парсером, а не
поиском по тексту (сущности и ссылки на символы уже раскрыты: `java&#x73;cript:` -
это `javascript:`), в два прохода:

1. expat - он видит то, что ElementTree молча выбрасывает: инструкции обработки
   (`<?xml-stylesheet type="text/xsl" …?>` запускает XSLT, и тот собирает
   `<script>` уже в браузере), DOCTYPE и объявления сущностей, пространства имён.
   Отказ - на любой инструкции, кроме объявления XML (`<?xml version…?>`, его
   expat инструкцией не считает), на DOCTYPE и ENTITY, на пространстве имён XSLT
   и атрибутах `xsl:`.
2. ElementTree - элементы и атрибуты: script/foreignObject/iframe/embed/object,
   любой атрибут on*, ссылки со схемой (`javascript:`, `data:`, `http:`…) и `//`,
   анимация, которая подменяет ссылку или обработчик, внешние `url(…)` и
   `@import` в стилях.

Что обычный редактор пишет сам, проходит: `url(#id)` в `style` и `<style>`
(градиенты Inkscape и Illustrator), `href="#id"`, картинка внутри файла
`data:image/png|jpeg|gif|webp` в `<image>` (не `svg+xml`), ссылка `http(s):` и
`mailto:` в `<a>`. `<use>` ссылается только на `#id` своего файла.

CSS перед сверкой читается так, как его читает браузер: экранирование
(`u\72l(` - это `url(`, `@\69mport` - `@import`) раскрыто, комментарии убраны,
строки в кавычках - строки (`/*` внутри них не комментарий).

Спецификация: docs/ru/spec/21-engine.md, «heron studio» (картинки) и `E043`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.parsers import expat

# Версия правил: кэш годных файлов (`.heron-cache/svg-safe.json`) другой версии не годится.
RULES = 3
ELEMENTS = {
    *("script", "foreignobject", "iframe", "frame", "frameset", "embed", "object", "applet"),
    *("portal", "handler", "listener", "meta", "link", "base"),
}
ANIMATE = {"set", "animate", "animatetransform", "animatemotion", "animatecolor"}
LINKS = {"href", "src", "xlink:href", "action", "formaction", "from", "to", "values", "base"}
# ссылка со схемой (`javascript:`, `blob:`, `https:`…) или на другой хост (`//`, `\\`)
SCHEMES = re.compile(r"^[a-z][a-z0-9+.\-]*:|^[/\\]{2}")
# что можно в `<a>`: обычная ссылка и почта
A_SCHEMES = re.compile(r"^(https?|mailto):")
# картинка внутри файла в `<image>`: только растр, не svg+xml (у того свои скрипты)
DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp)[;,]")
# CSS: подключение чужого файла и функции, которые грузят картинку по адресу
CSS_IMPORT = re.compile(r"@import|expression\s*\(|behavior\s*:|-moz-binding")
CSS_LOADERS = re.compile(r"(?<![\w-])(-webkit-)?(image-set|image|cross-fade|src)\s*\(")
CSS_URL = re.compile(r"(?<![\w-])url\s*\(")
XSLT = "http://www.w3.org/1999/XSL/Transform"
SEP = "\x1f"  # разделитель пространства имён и имени у expat


class _Unsafe(Exception):
    """Нашлось то, что SVG не пропускает: причина - в args[0]."""


def _local(name: str) -> str:
    """Имя без пространства имён: `{http://www.w3.org/2000/svg}script` - `script`."""
    return name.rsplit("}", 1)[-1].rsplit(SEP, 1)[-1].lower()


def _plain_value(value: str) -> str:
    """Значение атрибута, как его читает браузер: без пробелов и управляющих символов."""
    return re.sub(r"[\x00-\x20]+", "", value).lower()


def _css_text(css: str) -> str:
    """CSS так, как его разбирает браузер: экранирование раскрыто, комментариев нет.

    Проход по символам, а не замена по образцу: `/*` внутри строки в кавычках -
    не комментарий, `\\/*` - экранированная косая черта, а не начало комментария.
    Иначе `\\/* url(…) */` и `"/*" url(…) "*/"` прятали бы настоящий `url(`.
    """
    out: list[str] = []
    i, n = 0, len(css)
    quote: str | None = None
    while i < n:
        char = css[i]
        if char == "\\":
            i, decoded = _css_escape(css, i + 1)
            out.append(decoded)
            continue
        if quote is not None:
            if char == quote or char in "\n\r\f":
                quote = None
            out.append(char)
            i += 1
            continue
        if char == "/" and css.startswith("*", i + 1):
            end = css.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
            continue
        if char in "\"'":
            quote = char
        out.append(char)
        i += 1
    return "".join(out).lower()


def _css_escape(css: str, i: int) -> tuple[int, str]:
    """Экранирование CSS после `\\`: шестнадцатеричный код (до 6 цифр и пробел) или символ."""
    hexes = re.match(r"[0-9a-fA-F]{1,6}", css[i : i + 6])
    if hexes:
        end = i + len(hexes.group())
        code = int(hexes.group(), 16)
        if css.startswith("\r\n", end):
            end += 2
        elif end < len(css) and css[end] in " \t\n\r\f":
            end += 1
        if code == 0 or 0xD800 <= code <= 0xDFFF or code > 0x10FFFF:
            return end, "\ufffd"
        return end, chr(code)
    if i >= len(css):
        return i, "\ufffd"
    if css[i] in "\n\f":
        return i + 1, ""  # перенос строки внутри строки
    if css.startswith("\r\n", i):
        return i + 2, ""
    return i + 1, css[i]


def _css(css: str, where: str) -> None:
    """Стиль без чужого: `url(…)` только на `#id`, без `@import` и загрузки по адресу."""
    plain = _css_text(css)
    if CSS_IMPORT.search(plain):
        raise _Unsafe(f"@import or a script in {where}")
    if CSS_LOADERS.search(plain):
        raise _Unsafe(f"an image loaded by address in {where}")
    for match in CSS_URL.finditer(plain):
        rest = plain[match.end() :].lstrip(" \t\n\r\f")
        if rest[:1] in "\"'":
            rest = rest[1:]
        if not rest.startswith("#"):
            raise _Unsafe(f"url( to another file in {where}")


def _link(tag: str, name: str, plain: str) -> None:
    """Ссылка элемента: `#id` - всегда; `<a>` - ещё http(s) и почта; `<image>` - растр внутри."""
    if plain.startswith("#"):
        return
    if tag == "use" and name in ("href", "xlink:href"):
        raise _Unsafe("<use> outside this file")
    if tag == "a" and name in ("href", "xlink:href") and A_SCHEMES.match(plain):
        return
    if tag == "image" and name in ("href", "xlink:href") and DATA_IMAGE.match(plain):
        return
    if SCHEMES.search(plain):
        raise _Unsafe(f"link in {name}")


def _structure(data: bytes) -> None:
    """Проход expat: инструкции обработки, DOCTYPE, сущности, XSLT."""
    parser = expat.ParserCreate(namespace_separator=SEP)

    def pi(target: str, _data: str) -> None:
        raise _Unsafe(f"processing instruction <?{target}?>")

    def doctype(*_args) -> None:
        raise _Unsafe("DOCTYPE")

    def entity(*_args) -> None:
        raise _Unsafe("ENTITY")

    def namespace(_prefix: str | None, uri: str | None) -> None:
        if (uri or "").strip() == XSLT:
            raise _Unsafe("XSLT namespace")

    def start(name: str, attrs: dict[str, str]) -> None:
        for item in (name, *attrs):
            if item.split(SEP, 1)[0] == XSLT or item.lower().startswith("xsl:"):
                raise _Unsafe("XSLT")

    parser.ProcessingInstructionHandler = pi
    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = entity
    parser.UnparsedEntityDeclHandler = entity
    parser.NotationDeclHandler = entity
    parser.ExternalEntityRefHandler = lambda *_args: 0
    parser.StartNamespaceDeclHandler = namespace
    parser.StartElementHandler = start
    try:
        parser.Parse(data, True)
    except expat.ExpatError as error:
        raise _Unsafe(f"not XML: {error}") from error


def _elements(data: bytes) -> None:
    """Проход ElementTree: элементы, обработчики, ссылки, стили, анимация."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise _Unsafe(f"not XML: {error}") from error
    if _local(root.tag) != "svg":
        raise _Unsafe("the root element is not <svg>")
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        tag = _local(element.tag)
        if tag in ELEMENTS:
            raise _Unsafe(f"<{tag}>")
        if tag == "style":
            _css("".join(element.itertext()), "<style>")
        for raw_name, value in element.attrib.items():
            name = _local(raw_name)
            if raw_name.endswith("}href"):
                name = "xlink:href" if "xlink" in raw_name else "href"
            plain = _plain_value(value)
            if name.startswith("on"):
                raise _Unsafe(f"attribute {name}")
            if "javascript:" in plain or "vbscript:" in plain:
                raise _Unsafe(f"script link in {name}")
            if name in LINKS:
                _link(tag, name, plain)
            else:
                # style и атрибуты оформления (fill, filter, mask, clip-path) - это CSS
                _css(value, "style" if name == "style" else f"attribute {name}")
            if tag in ANIMATE and name == "attributename":
                target = plain.split(":")[-1]
                if target.startswith("on") or target in ("href", "src"):
                    raise _Unsafe(f"<{tag}> changes {target}")


def problem(data: bytes) -> str | None:
    """Что в SVG исполняется или тянет чужое (по-английски, коротко), или None - файл годен."""
    lower = data.lower()
    if b"<!doctype" in lower[:4096] or b"<!entity" in lower:
        return "DOCTYPE or ENTITY"
    try:
        _structure(data)
        _elements(data)
    except _Unsafe as error:
        return str(error.args[0])
    return None


def safe(data: bytes) -> bool:
    """SVG без исполняемого и без внешних ссылок."""
    return problem(data) is None


def files(*folders: Path) -> list[Path]:
    """Все `.svg` в папках (без ссылок наружу), по порядку путей."""
    found: list[Path] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() == ".svg" and path.is_file() and not path.is_symlink():
                found.append(path)
    return found
