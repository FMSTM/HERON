"""Файловые операции не выходят за разрешённые папки.

Путь из фронтматтера, ссылка в static/, файл-ссылка в content/ — всё это
пишет сайт. Проверочные «секреты» создаются только во временных папках.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from heron.core import build as pipeline
from heron.core import paths
from heron.core.errors import HeronError
from heron.scaffold import create

SECRET = "секрет вне сайта"


@pytest.fixture
def layout(tmp_path):
    """Сайт в tmp/site и чужой файл рядом с ним, в tmp/outside.txt."""
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    (root / "media").mkdir(exist_ok=True)
    outside = tmp_path / "outside.txt"
    outside.write_text(SECRET, encoding="utf-8")
    return root, outside


def page(root: Path, front: str, body: str = "Text.\n", name: str = "a.md") -> None:
    (root / "content" / "en" / name).write_text(
        f"---\ntitle: A\nh1: A\ndescription: D\n{front}---\n\n{body}", encoding="utf-8"
    )


def leaked(tmp_path: Path, dist: Path) -> list[Path]:
    """Файлы с текстом секрета внутри сборки."""
    return [p for p in dist.rglob("*") if p.is_file() and SECRET.encode() in p.read_bytes()]


def codes(result) -> list[str]:
    return [e.code for e in result.collector.errors]


def test_media_traversal_is_neither_read_nor_written(layout, tmp_path):
    root, outside = layout
    page(root, "image: media/../../outside.txt\nimage_alt: x\n")
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    result = pipeline.run(root)
    assert "E024" in codes(result)
    assert outside.read_text(encoding="utf-8") == SECRET
    dist = root / "dist"
    if dist.exists():
        assert leaked(tmp_path, dist) == []
    after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    # вне папки сайта ничего не появилось
    assert {p for p in after if p.parts[0] != "site"} == {p for p in before if p.parts[0] != "site"}


def test_traversal_in_markdown_body_is_rejected(layout):
    root, _ = layout
    page(root, "", "![x](media/../../outside.txt)\n")
    result = pipeline.run(root)
    assert "E024" in codes(result)


def test_check_rejects_traversal_too(layout):
    root, _ = layout
    page(root, "image: media/../../outside.txt\nimage_alt: x\n")
    assert "E024" in codes(pipeline.check(root))


def test_symlink_inside_media_pointing_out(layout, tmp_path):
    root, outside = layout
    os.symlink(outside, root / "media" / "photo.png")
    page(root, "", "![x](media/photo.png)\n")
    result = pipeline.run(root)
    assert "E024" in codes(result)
    if (root / "dist").exists():
        assert leaked(tmp_path, root / "dist") == []


def test_static_symlink_out_is_not_copied(layout, tmp_path):
    root, outside = layout
    (root / "static").mkdir(exist_ok=True)
    os.symlink(outside, root / "static" / "leak.txt")
    with pytest.raises(HeronError) as error:
        pipeline.run(root)
    assert error.value.code == "E024"
    if (root / "dist").exists():
        assert leaked(tmp_path, root / "dist") == []


def test_static_symlinked_folder_out_is_not_copied(layout, tmp_path):
    root, _ = layout
    folder = tmp_path / "foreign"
    folder.mkdir()
    (folder / "x.txt").write_text(SECRET, encoding="utf-8")
    (root / "static").mkdir(exist_ok=True)
    os.symlink(folder, root / "static" / "shared")
    with pytest.raises(HeronError):
        pipeline.run(root)
    if (root / "dist").exists():
        assert leaked(tmp_path, root / "dist") == []


def test_static_symlink_inside_is_fine(layout):
    root, _ = layout
    (root / "static").mkdir(exist_ok=True)
    (root / "static" / "real.txt").write_text("ok", encoding="utf-8")
    os.symlink(root / "static" / "real.txt", root / "static" / "alias.txt")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert (root / "dist" / "alias.txt").read_text(encoding="utf-8") == "ok"


def test_content_symlink_out_is_not_read(layout, tmp_path):
    root, _ = layout
    stolen = tmp_path / "stolen.md"
    stolen.write_text(f"---\ntitle: S\nh1: S\ndescription: D\n---\n\n{SECRET}\n", "utf-8")
    os.symlink(stolen, root / "content" / "en" / "stolen.md")
    result = pipeline.run(root)
    assert "E024" in codes(result)
    if (root / "dist").exists():
        assert leaked(tmp_path, root / "dist") == []


def test_data_symlink_out_is_not_read(layout, tmp_path):
    root, _ = layout
    stolen = tmp_path / "stolen.yaml"
    stolen.write_text(f"text: {SECRET}\n", "utf-8")
    (root / "data").mkdir(exist_ok=True)
    os.symlink(stolen, root / "data" / "shared.yaml")
    result = pipeline.run(root)
    assert "E024" in codes(result)


@pytest.mark.parametrize("out", [".", "content", "content/en", "static", "theme", "media"])
def test_build_never_writes_into_sources(layout, out):
    root, _ = layout
    (root / "static").mkdir(exist_ok=True)
    with pytest.raises(HeronError) as error:
        pipeline.run(root, dist=root / out)
    assert error.value.code == "E024"


def test_site_inside_out_is_rejected(layout, tmp_path):
    root, _ = layout
    with pytest.raises(HeronError) as error:
        pipeline.run(root, dist=tmp_path)
    assert error.value.code == "E024"


def test_cache_inside_sources_is_rejected(tmp_path):
    root = tmp_path / "site"
    (root / "content").mkdir(parents=True)
    with pytest.raises(HeronError):
        paths.layout(root, tmp_path / "out", root / "content" / ".heron-cache", [root / "content"])
    with pytest.raises(HeronError):
        paths.layout(root, tmp_path / "out", tmp_path / "out" / "c", [root / "content"])


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("media/x.png", "media/x.png"),
        ("./media/x.png", "media/x.png"),
        ("/media/x.png", "media/x.png"),
        ("../x", "../x"),  # lstrip("./") превращал это в «x»
        ("media/a/../../x", "x"),
        ("media/a/../../../x", "../x"),
    ],
)
def test_normalize_keeps_the_way_out_visible(raw, clean):
    assert paths.normalize(raw) == clean


def test_target_rejects_escape_and_symlinked_folders(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    for bad in ("../x", "a/../../x", "//host/x"):
        with pytest.raises(HeronError):
            paths.target(dist, bad)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, dist / "jump")
    with pytest.raises(HeronError):
        paths.target(dist, "jump/x.html")
    assert paths.target(dist, "a/b/index.html") == dist / "a/b/index.html"
