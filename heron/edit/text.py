"""Текст файла как он есть: строки со смещениями, переводы строк, маска разбора.

Модель правки никогда не пересобирает файл целиком. Она держит исходный текст
(с BOM, `\\r\\n`, без перевода строки в конце - как было) и знает, в каких
символах лежит каждое значение. Правка - замена одного отрезка, всё остальное
остаётся байт в байт.

Разбор markdown идёт по маске: тот же текст той же длины, где `\\r` убран из
концов строк, а комментарии `<!-- … -->` вне кода заменены пробелами. Строки
и столбцы маски совпадают с исходником, поэтому карты строк markdown-it
переводятся в смещения исходного текста без пересчёта.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from heron.core.parser.markdown import COMMENT, without_code

BOM = "﻿"
LINE_END = re.compile(r"\r\n|\r|\n")


@dataclass(frozen=True, slots=True)
class Line:
    """Строка исходника: начало, конец содержимого (без перевода строки), конец с ним."""

    start: int
    end: int
    stop: int


def lines_of(text: str, start: int = 0, stop: int | None = None) -> list[Line]:
    """Строки отрезка `text[start:stop]` с абсолютными смещениями.

    Последняя строка без перевода - тоже строка (возможно, пустая), как у `split`.
    """
    stop = len(text) if stop is None else stop
    out: list[Line] = []
    pos = start
    for match in LINE_END.finditer(text, start, stop):
        out.append(Line(pos, match.start(), match.end()))
        pos = match.end()
    out.append(Line(pos, stop, stop))
    return out


def newline_of(text: str) -> str:
    """Перевод строки файла: им пишутся новые строки."""
    match = LINE_END.search(text)
    return match.group(0) if match else "\n"


def plain(raw: str) -> str:
    """Значение без `\\r`: наружу значения отдаются с `\\n`."""
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def native(value: str, nl: str) -> str:
    """Значение с переводами строк файла."""
    return plain(value).replace("\n", nl)


def mask(text: str, lines: list[Line]) -> list[str]:
    """Строки для разбора: содержимое строк, комментарии вне кода - пробелами."""
    rows = [text[line.start : line.end] for line in lines]
    joined = "\n".join(rows)
    if "<!--" not in joined:
        return rows
    hidden = without_code(joined)
    chars = list(joined)
    for match in COMMENT.finditer(hidden):
        for index in range(match.start(), match.end()):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars).split("\n")


def blank(row: str) -> bool:
    return not row.strip()
