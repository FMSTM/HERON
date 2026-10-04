"""Кэш нарезок: вне dist, с уборкой и без лишнего кодирования."""

from pathlib import Path

from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import media, tree
from tests import sites


def master(path: Path, size: int = 900, colour=(120, 80, 40)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), colour).save(path)


def prepared(tmp_path, extra=None):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/bio.md": sites.page("Біографія", image="media/bio/portrait.png", image_alt="Фото"),
        **(extra or {}),
    }
    sites.build(tmp_path, files)
    master(tmp_path / "media" / "bio" / "portrait.png")
    site, collector = tree.scan(tmp_path / "content", sites.config())
    return site, collector


def spec(**over):
    return ImagesSpec.model_validate(
        {"widths": [400, 800], "ratios": ["1:1"], "formats": ["webp"], **over}
    )


def run(tmp_path, site, collector, images=None, workers=1):
    return media.build(
        site,
        tmp_path,
        tmp_path / "dist",
        images or spec(),
        collector,
        cache_dir=tmp_path / ".heron-cache",
        workers=workers,
    )


def slices(tmp_path) -> set[str]:
    root = tmp_path / ".heron-cache" / media.SLICES
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_second_build_encodes_nothing_and_gives_the_same_dist(tmp_path):
    site, collector = prepared(tmp_path)
    run(tmp_path, site, collector)
    first = {
        p.relative_to(tmp_path / "dist").as_posix(): p.read_bytes()
        for p in (tmp_path / "dist").rglob("*")
        if p.is_file()
    }
    stamps = {
        p: p.stat().st_mtime_ns
        for p in (tmp_path / ".heron-cache" / media.SLICES).rglob("*")
        if p.is_file()
    }

    # dist расходный: его стирают перед каждой сборкой
    import shutil

    shutil.rmtree(tmp_path / "dist")
    run(tmp_path, site, collector)

    again = {
        p.relative_to(tmp_path / "dist").as_posix(): p.read_bytes()
        for p in (tmp_path / "dist").rglob("*")
        if p.is_file()
    }
    assert again == first
    assert {p: p.stat().st_mtime_ns for p in stamps} == stamps


def test_changed_master_recodes_only_itself(tmp_path):
    extra = {"uk/about.md": sites.page("Про", image="media/bio/other.png", image_alt="Інше")}
    site, collector = prepared(tmp_path, extra)
    master(tmp_path / "media" / "bio" / "other.png", colour=(10, 90, 200))
    run(tmp_path, site, collector)
    keep = {
        name: (tmp_path / ".heron-cache" / media.SLICES / name).read_bytes()
        for name in slices(tmp_path)
        if "other" in name
    }
    before = (
        tmp_path / ".heron-cache" / media.SLICES / "media/bio/portrait-1x1-400.webp"
    ).read_bytes()

    master(tmp_path / "media" / "bio" / "portrait.png", colour=(0, 200, 0))
    run(tmp_path, site, collector)

    after = (
        tmp_path / ".heron-cache" / media.SLICES / "media/bio/portrait-1x1-400.webp"
    ).read_bytes()
    assert after != before
    assert {
        name: (tmp_path / ".heron-cache" / media.SLICES / name).read_bytes() for name in keep
    } == keep


def test_master_removed_from_content_leaves_no_slices(tmp_path):
    extra = {"uk/about.md": sites.page("Про", image="media/bio/other.png", image_alt="Інше")}
    site, collector = prepared(tmp_path, extra)
    master(tmp_path / "media" / "bio" / "other.png")
    run(tmp_path, site, collector)
    assert any("other" in name for name in slices(tmp_path))

    (tmp_path / "content" / "uk" / "about.md").unlink()
    site, collector = prepared(tmp_path)
    # dist расходный и стирается перед сборкой — движок его не чистит
    import shutil

    shutil.rmtree(tmp_path / "dist")
    run(tmp_path, site, collector)

    assert not any("other" in name for name in slices(tmp_path))
    assert not any("other" in p.name for p in (tmp_path / "dist").rglob("*"))
    assert any("portrait" in name for name in slices(tmp_path))


def test_width_dropped_from_the_theme_leaves_no_slices_of_it(tmp_path):
    site, collector = prepared(tmp_path)
    run(tmp_path, site, collector)
    assert any("-800." in name for name in slices(tmp_path))

    run(tmp_path, site, collector, images=spec(widths=[400]))
    assert not any("-800." in name for name in slices(tmp_path))
    assert any("-400." in name for name in slices(tmp_path))


def test_several_workers_give_the_same_result(tmp_path):
    site, collector = prepared(tmp_path)
    one = run(tmp_path, site, collector, workers=1)
    names = slices(tmp_path)

    import shutil

    shutil.rmtree(tmp_path / "dist")
    shutil.rmtree(tmp_path / ".heron-cache")
    many = run(tmp_path, site, collector, workers=4)
    assert slices(tmp_path) == names
    assert one.items.keys() == many.items.keys()


def test_dist_gets_a_copy_when_hard_links_are_impossible(tmp_path, monkeypatch):
    site, collector = prepared(tmp_path)
    monkeypatch.setattr(media.os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError("нельзя")))
    run(tmp_path, site, collector)
    out = tmp_path / "dist" / "media" / "bio" / "portrait-1x1-400.webp"
    assert out.is_file()
    assert out.stat().st_nlink == 1
