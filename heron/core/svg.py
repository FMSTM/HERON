"""SVG без исполняемого: проверка загрузки в студии и `heron check` (media/ и тема).

SVG из `media/` и из темы сайт отдаёт как есть, и открытый по прямой ссылке
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
   любой атрибут on*, ссылки javascript:/vbscript:/data: и внешние (http:, //),
   анимация, которая подменяет ссылку или обработчик, `@import`/`url(` в стилях.

Спецификация: docs/ru/spec/21-engine.md, «heron studio» (картинки) и `E043`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.parsers import expat

ELEMENTS = {"script", "foreignobject", "iframe", "embed", "object", "handler", "listener"}
ANIMATE = {"set", "animate", "animatetransform", "animatemotion", "animatecolor"}
LINKS = {"href", "src", "xlink:href", "action", "formaction", "from", "to", "values"}
SCHEMES = re.compile(r"^(javascript|vbscript|data|https?|ftp|file):|^//")
CSS = re.compile(r"url\s*\(|@import|expression\s*\(", re.I)
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
        if tag == "style" and CSS.search(element.text or ""):
            raise _Unsafe("url( or @import in <style>")
        for raw_name, value in element.attrib.items():
            name = _local(raw_name)
            if raw_name.endswith("}href"):
                name = "xlink:href" if "xlink" in raw_name else "href"
            plain = _plain_value(value)
            if name.startswith("on"):
                raise _Unsafe(f"attribute {name}")
            if name in LINKS and SCHEMES.search(plain):
                raise _Unsafe(f"link in {name}")
            if "javascript:" in plain or "vbscript:" in plain:
                raise _Unsafe(f"script link in {name}")
            if name == "style" and CSS.search(value):
                raise _Unsafe("url( or @import in style")
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
