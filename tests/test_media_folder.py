"""Папка ресурсов сайта: media/ вместо img/.

Имя `img` обещало только изображения, и видео класть было некуда.
Переименование — разовый проход по сайту, поэтому старое имя принимается
наравне с новым, но задвоение папок останавливает сборку: гадать, в какой
из них правда, дороже, чем остановиться.
"""

from __future__ import annotations

import pytest

from heron.core import media, tree
from heron.core.errors import Collector, HeronError
from heron.scaffold import create
from tests import sites


def test_new_site_gets_media_folder(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    assert (root / "media").is_dir()
    assert not (root / "img").exists()


def test_media_folder_is_silent(tmp_path):
    (tmp_path / "media").mkdir()
    collector = Collector()
    assert media.folder(tmp_path, collector) == "media"
    assert collector.warnings == []


def test_legacy_folder_builds_with_one_warning(tmp_path):
    (tmp_path / "img").mkdir()
    collector = Collector()
    assert media.folder(tmp_path, collector) == "img"
    assert len(collector.warnings) == 1
    assert "media" in collector.warnings[0].message


def test_two_folders_stop_the_build(tmp_path):
    (tmp_path / "media").mkdir()
    (tmp_path / "img").mkdir()
    with pytest.raises(HeronError) as exc:
        media.folder(tmp_path, Collector())
    assert exc.value.code == "E018"


def test_static_media_overlap_stops_the_build(tmp_path):
    """static/ копируется в корень: совпавшее имя молча затрёт файл."""
    (tmp_path / "media" / "video").mkdir(parents=True)
    (tmp_path / "media" / "video" / "x.mp4").write_bytes(b"1")
    (tmp_path / "static" / "media" / "video").mkdir(parents=True)
    (tmp_path / "static" / "media" / "video" / "x.mp4").write_bytes(b"2")
    with pytest.raises(HeronError) as exc:
        media.folder(tmp_path, Collector())
    assert exc.value.code == "E018"
    assert "video/x.mp4" in exc.value.message


def test_static_media_without_overlap_is_a_warning(tmp_path):
    """Пока имена не совпадают, файлы просто ложатся рядом — это не повод падать."""
    (tmp_path / "media" / "foto").mkdir(parents=True)
    (tmp_path / "media" / "foto" / "a.jpg").write_bytes(b"1")
    (tmp_path / "static" / "media").mkdir(parents=True)
    (tmp_path / "static" / "media" / "video.mp4").write_bytes(b"2")
    collector = Collector()
    assert media.folder(tmp_path, collector) == "media"
    assert len(collector.warnings) == 1


@pytest.mark.parametrize("prefix", ["media", "img"])
def test_paths_from_both_folders_are_read(tmp_path, prefix):
    files = {
        "uk/index.md": sites.page("Головна", image=f"{prefix}/a.png"),
        "uk/x.md": (
            "---\ntitle: X\nh1: X\ndescription: Опис\n---\n\n"
            f"## Що {{#what}}\n\n![Підпис]({prefix}/in-body.png)\n"
        ),
    }
    content = sites.build(tmp_path, files)
    site, _ = tree.scan(content, sites.config())
    assert media.references(site) == {f"{prefix}/a.png", f"{prefix}/in-body.png"}
