"""Корпус страниц для проверки правки без потерь (ST6).

Все markdown-страницы, которые движок кладёт или показывает как образец:
демо стартовой темы на каждом языке и с пояснениями ru/en, сайт `heron new`
с демо и без, архив темы (`theme pack`), заготовки `heron page` всех типов,
образец `docs/<язык>/templates/page.md`, исходники демо без SEO-блока и
страницы-фикстуры из тестов (строковые литералы, начинающиеся с `---`).
"""

from __future__ import annotations

import ast
import os
import tarfile
from functools import cache
from pathlib import Path

from heron.contracts.theme import load_theme
from heron.core import describe
from heron.scaffold import DEMO, create, starter_theme
from heron.scaffold.page import write_page

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"


def _site(root: Path, notes: str, demo: bool) -> None:
    create(root, name="Demo", languages=["uk", "ru", "en", "de"], notes=notes, demo=demo)


@cache
def corpus(tmp: str) -> list[tuple[str, bytes]]:
    """(имя, байты) каждой страницы корпуса. `tmp` - папка для разложенных сайтов."""
    base = Path(tmp)
    out: list[tuple[str, bytes]] = []
    old = os.environ.pop("HERON_NOTES", None)
    try:
        for notes in ("ru", "en"):
            stage = base / f"starter-{notes}"
            starter_theme(stage, ["uk", "ru", "en", "de"], notes)
            for path in sorted((stage / "demo").rglob("*.md")):
                out.append(
                    (f"starter-{notes}/{path.relative_to(stage).as_posix()}", path.read_bytes())
                )
            for demo in (True, False):
                root = base / f"site-{notes}-{demo}"
                _site(root, notes, demo)
                for path in sorted((root / "content").rglob("*.md")):
                    if path.name == "heron-readme.md":
                        continue
                    name = f"site-{notes}-{demo}/{path.relative_to(root).as_posix()}"
                    out.append((name, path.read_bytes()))
                if demo:
                    theme = load_theme(root / "theme" / "theme.yaml")
                    for page_type in theme.types:
                        made = write_page(root, page_type, f"made-{page_type}", lang="ru")
                        out.append((f"page-{notes}/{page_type}", made.read_bytes()))
                    out.extend(_pack(root, base / f"pack-{notes}"))
    finally:
        if old is not None:
            os.environ["HERON_NOTES"] = old
    for lang in ("ru", "en"):
        sample = REPO / "docs" / lang / "templates" / "page.md"
        out.append((f"docs/{lang}/templates/page.md", sample.read_bytes()))
    for path in sorted(DEMO.rglob("*.md")):
        out.append((f"demo-source/{path.relative_to(DEMO).as_posix()}", path.read_bytes()))
    out.extend(fixtures())
    return out


def _pack(root: Path, out: Path) -> list[tuple[str, bytes]]:
    """Страницы демо из архива темы - то, что разложит `theme get`."""
    from heron.themes import pack

    out.mkdir(parents=True, exist_ok=True)
    archive = pack(root, out / "theme.tar.gz")
    pages: list[tuple[str, bytes]] = []
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if member.isfile() and member.name.endswith(".md") and "/content/" in member.name:
                handle = tar.extractfile(member)
                if handle is not None:
                    pages.append((f"pack/{member.name}", handle.read()))
    return pages


def fixtures() -> list[tuple[str, bytes]]:
    """Страницы-фикстуры тестов: строковые литералы с SEO-блоком."""
    out = []
    for path in sorted(TESTS.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value.lstrip("﻿").startswith("---")
                and "title" in node.value
            ):
                out.append((f"tests/{path.name}:{node.lineno}", node.value.encode("utf-8")))
    return out


def unique(pages: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Без повторов: демо приходит в корпус несколькими путями с одними и теми же байтами."""
    seen: set[bytes] = set()
    out = []
    for name, raw in pages:
        if raw not in seen:
            seen.add(raw)
            out.append((name, raw))
    return out


def contract(lang: str = "en"):
    """Контракт стартовой темы - объект `heron describe`."""
    return describe.contract(_theme(), None, lang)


@cache
def _theme():
    import tempfile

    stage = Path(tempfile.mkdtemp(prefix="heron-edit-"))
    starter_theme(stage, ["en"], "en")
    return load_theme(stage / "theme" / "theme.yaml")
