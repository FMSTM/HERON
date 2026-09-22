"""Служебные записки heron-readme.md и мусор операционной системы.

Записка объясняет человеку, что класть в папку и чего не класть. Движок её
не замечает нигде: в content/ она не страница, в static/ не уезжает в сеть,
в media/ не ресурс. README.md эту роль исполнить не мог — в content/ он не
становился страницей по случайности, а из static/ уезжал по адресу /README.md.
"""

from __future__ import annotations

from heron.core import build as pipeline
from heron.core import notes, report, tree
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


def test_note_language_follows_the_site(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    assert "Site content" in (root / notes.NOTE).read_text(encoding="utf-8")


def test_unknown_language_falls_back_to_english(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["de"])
    assert (root / "media" / notes.NOTE).is_file()
    assert "Belongs here" in (root / "media" / notes.NOTE).read_text(encoding="utf-8")


def test_note_in_content_is_not_a_page(tmp_path):
    root = _demo(tmp_path)
    (root / "content" / "uk" / notes.NOTE).write_text("# записка", encoding="utf-8")
    site, _ = tree.scan(root / "content", sites.config())
    assert [p.key for p in site.pages] == [""]


def test_note_and_junk_never_reach_the_build(tmp_path):
    root = _demo(tmp_path)
    (root / "static" / "sub").mkdir(parents=True, exist_ok=True)
    (root / "static" / "ads.txt").write_text("ок", encoding="utf-8")
    (root / "static" / ".DS_Store").write_bytes(b"junk")
    (root / "static" / "sub" / "Thumbs.db").write_bytes(b"junk")
    (root / "static" / "sub" / "Heron-ReadMe.md").write_text("регистр", encoding="utf-8")

    pipeline.run(root)
    dist = root / "dist"
    assert (dist / "ads.txt").is_file()
    assert not list(dist.rglob(notes.NOTE))
    assert not list(dist.rglob("*.DS_Store"))
    assert not list(dist.rglob("Thumbs.db"))
    assert not list(dist.rglob("Heron-ReadMe.md"))


def test_note_in_media_is_not_an_unused_resource(tmp_path):
    root = _demo(tmp_path)
    (root / "media" / "foto").mkdir(parents=True, exist_ok=True)
    (root / "media" / "foto" / notes.NOTE).write_text("записка", encoding="utf-8")
    result = pipeline.run(root)
    assert not [p for p in result.report.unused_media if notes.is_note(p)]


def test_site_without_notes_builds_and_is_only_informed(tmp_path):
    root = _demo(tmp_path)
    for path in list(root.rglob(notes.NOTE)):
        path.unlink()
    result = pipeline.run(root)
    assert not result.collector.errors
    assert "корень" in result.report.notes_missing
    assert "media/" in result.report.notes_missing
    # это информация, а не предупреждение сборки
    assert not [w for w in result.collector.warnings if "записк" in w.message]


def test_report_is_quiet_when_notes_are_in_place(tmp_path):
    root = _demo(tmp_path)
    built = report.build(
        *_scanned(root),
        site_root=root,
    )
    assert built.notes_missing == []


def _scanned(root):
    config = sites.config()
    site, _ = tree.scan(root / "content", config)
    return site, config, sites.theme()
