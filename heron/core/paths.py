"""Границы файловых операций: что сборка вправе читать, писать и удалять.

Сайт — чужие данные. Путь из фронтматтера, файл в `static/`, символическая
ссылка в теме — всё это пишет не движок, и проверять такой путь строкой
(«нет ли в нём `../`») нельзя: `media/a/../../x` строковую проверку
проходит, символическая ссылка не содержит точек вовсе. Поэтому правило
одно и для всех операций — путь сначала нормализуется, потом разрешается
файловой системой (`resolve`, со всеми ссылками), и только результат
сравнивается с разрешённым корнем.

    читать    — исходники сайта: content/, data/, media/, static/, тема
    писать    — только папка сборки и кэш
    удалять   — только то, чем сборщик владеет: файлы своего манифеста
                в папке сборки и записи кэша

Папки сборки, кэша и исходников не пересекаются: сборка, которая пишет в
папку контента, однажды сотрёт контент, а кэш внутри сборки уезжает в сеть.

Спецификация: docs/spec/21-engine.md, раздел 4, «Границы файлов».
"""

from __future__ import annotations

import os
import posixpath
from collections.abc import Iterator
from pathlib import Path

from heron.core.errors import HeronError

CODE = "E024"


def normalize(value: str) -> str:
    """Путь из текста сайта в вид `media/x.png` — без потери `..`.

    `./media/x` и `/media/x` — тот же файл, что `media/x`. Префикс снимается
    ровно один раз, а не набором символов: `"../x".lstrip("./")` превращал
    выход наружу в безобидное `x`, и проверять потом было нечего.
    """
    text = value.strip().replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    elif text.startswith("/") and not text.startswith("//"):
        text = text[1:]
    if not text:
        return ""
    return posixpath.normpath(text)


def escapes(rel: str) -> bool:
    """Выходит ли нормализованный относительный путь из своего корня."""
    return rel.startswith("/") or rel == ".." or rel.startswith("../")


def inside(root: Path, path: Path) -> bool:
    """Лежит ли путь внутри корня — после разрешения всех ссылок."""
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def overlaps(a: Path, b: Path) -> bool:
    """Одна папка внутри другой (или это одна и та же)."""
    a, b = a.resolve(), b.resolve()
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def source(root: Path, rel: str, *, where: str | None = None) -> Path:
    """Файл исходников по относительному пути — или E024.

    Проверка двойная: нормализованный путь не уходит вверх, и разрешённый
    файловой системой путь остаётся в корне (символическая ссылка внутри
    `media/` на `/etc` строку не меняет, а результат — меняет).
    """
    clean = normalize(rel)
    if not clean or escapes(clean) or not inside(root, root / clean):
        raise HeronError(
            code=CODE,
            message=f"путь {rel!r} выходит за пределы {root.name}/",
            path=where or str(root),
            hint="файлы сайта берутся только из его собственных папок; "
            "уберите `..` и символические ссылки наружу",
        )
    return root / clean


def target(root: Path, rel: str) -> Path:
    """Куда писать результат: путь внутри папки сборки или кэша — или E024.

    Пишет движок, но имя файла часто приходит от сайта (адрес страницы,
    имя файла в `static/`, имя от плагина), и папка назначения могла
    оказаться символической ссылкой наружу.
    """
    clean = normalize(rel)
    if not clean or clean == "." or escapes(clean):
        raise HeronError(
            code=CODE,
            message=f"результат {rel!r} оказался бы вне папки сборки",
            path=str(root),
            hint="имя выходного файла должно быть относительным путём без `..`",
        )
    out = root / clean
    # Сам файл ещё может не существовать — проверяем ближайшую папку.
    parent = out.parent
    while not parent.exists() and parent != root:
        parent = parent.parent
    if not inside(root, parent) or (out.is_symlink() and not inside(root, out)):
        raise HeronError(
            code=CODE,
            message=f"результат {clean} ведёт за пределы папки сборки через ссылку",
            path=str(out),
            hint="уберите символические ссылки из папки сборки",
        )
    return out


def files(root: Path, *, where: str) -> Iterator[tuple[str, Path]]:
    """Все файлы папки как (относительный путь, путь) — без выхода наружу.

    Символическая ссылка внутри папки допустима, пока ведёт внутрь неё же:
    так раскладывают общие файлы. Ссылка наружу — E024, а не молчаливое
    копирование чужого файла в публичную сборку. Папки-ссылки обходятся,
    если они внутри; петли отсекаются по реальному пути.
    """
    if not root.is_dir():
        return
    base = root.resolve()
    seen: set[Path] = set()
    stack = [root]
    while stack:
        folder = stack.pop()
        real = folder.resolve()
        if real in seen:
            continue
        seen.add(real)
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink() and not inside(base, path):
                raise HeronError(
                    code=CODE,
                    message=f"символическая ссылка {path.relative_to(root).as_posix()} "
                    "ведёт за пределы папки",
                    path=where,
                    hint="положите сам файл в папку сайта вместо ссылки на него",
                )
            if entry.is_dir():
                stack.append(path)
            elif entry.is_file():
                yield path.relative_to(root).as_posix(), path


def layout(site_root: Path, dist: Path, cache: Path, sources: list[Path]) -> None:
    """Папки сборки, кэша и исходников не должны пересекаться.

    Сборка по умолчанию лежит в `dist/` внутри папки сайта — это нормально:
    она не пересекается ни с одной папкой исходников. Ненормально — сборка
    в корень сайта, в `content/`, в тему; кэш внутри сборки; сборка внутри
    кэша.
    """

    def fail(message: str, path: Path) -> None:
        raise HeronError(
            code=CODE,
            message=message,
            path=str(path),
            hint="укажите --out в отдельную папку: не корень сайта, не папку исходников и не кэш",
        )

    root = site_root.resolve()
    out = dist.resolve()
    if out == root or root.is_relative_to(out):
        fail("папка сборки совпадает с папкой сайта или содержит её", dist)
    for folder in sources:
        if folder.exists() and overlaps(out, folder):
            fail(f"папка сборки пересекается с исходниками: {folder.name}/", dist)
        if folder.exists() and overlaps(cache, folder):
            fail(f"кэш пересекается с исходниками: {folder.name}/", cache)
    if overlaps(out, cache):
        fail("кэш и папка сборки пересекаются", cache)
