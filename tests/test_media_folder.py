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


def test_as_is_paths_are_copied_whole(tmp_path):
    """Скан документа не иллюстрация: варианты ему не нужны."""
    from PIL import Image

    from heron.contracts.theme import ImagesSpec
    from heron.core import links

    files = {
        "uk/index.md": sites.page("Головна", image="media/diplomas/0002.png"),
        "uk/bio.md": sites.page("Біо", image="media/foto/portrait.png"),
    }
    content = sites.build(tmp_path, files)
    for rel in ("media/diplomas/0002.png", "media/foto/portrait.png"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (900, 900), (20, 60, 120)).save(path)

    site, collector = tree.scan(content, sites.config())
    links.resolve(site, sites.config(), sites.theme(), collector)
    media.build(
        site,
        tmp_path,
        tmp_path / "dist",
        ImagesSpec(ratios=["16:9"], widths=[400, 800], formats=["webp"], as_is=["media/diplomas/"]),
        collector,
        cache_dir=tmp_path / ".cache",
    )
    dist = tmp_path / "dist"
    # скан: только сам файл, без вариантов
    assert (dist / "media" / "diplomas" / "0002.png").is_file()
    assert sorted(p.name for p in (dist / "media" / "diplomas").iterdir()) == ["0002.png"]
    # обычная картинка режется как прежде
    assert len(list((dist / "media" / "foto").iterdir())) > 1
