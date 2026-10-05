"""Служебные записки heron-readme.md и мусор операционной системы.

Записка объясняет человеку, что класть в папку и чего не класть. Движок её
не замечает нигде: в content/ она не страница, в static/ не уезжает в сеть,
в media/ не ресурс. README.md эту роль исполнить не мог — в content/ он не
становился страницей по случайности, а из static/ уезжал по адресу /README.md.
"""

from __future__ import annotations

from heron.core import notes
from heron.scaffold import create
from tests import sites


def _demo(tmp_path, languages=None):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=languages or ["uk"])
    (root / "content" / "uk" / "index.md").write_text(sites.page("Головна"), encoding="utf-8")
    return root


def test_new_site_gets_notes_everywhere(tmp_path):
    root = _demo(tmp_path)
    assert (root / notes.NOTE).is_file()
    for folder in ("content", "media", "theme", "data", "static", "plugins"):
        assert (root / folder / notes.NOTE).is_file(), folder


def test_note_language_follows_comments_not_site_languages(tmp_path):
    """Языки сайта и язык пояснений — разные вещи."""
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["de"], notes="en")
    assert "Site content" in (root / notes.NOTE).read_text(encoding="utf-8")
    assert "Belongs here" in (root / "media" / notes.NOTE).read_text(encoding="utf-8")


def test_notes_default_to_english(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["ru"])
    assert "Site content" in (root / notes.NOTE).read_text(encoding="utf-8")


def test_russian_notes_on_request(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["en"], notes="ru")
    assert "Контент сайта" in (root / notes.NOTE).read_text(encoding="utf-8")
