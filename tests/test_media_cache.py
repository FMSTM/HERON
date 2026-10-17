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
    """Файлы нарезок в кэше (без служебных отметок)."""
    root = tmp_path / ".heron-cache" / media.SLICES
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not p.name.startswith(".") and p.name != "shape.json"
    }


def cached(tmp_path, src: str) -> Path:
    """Запись кэша мастера — по содержимому, а не по имени."""
    return media.store(tmp_path / ".heron-cache") / media.digest(tmp_path / src)


def dist_files(tmp_path) -> dict[str, bytes]:
    return {
        p.relative_to(tmp_path / "dist").as_posix(): p.read_bytes()
        for p in (tmp_path / "dist").rglob("*")
        if p.is_file() and not p.name.startswith(".")
    }


def test_second_build_encodes_nothing_and_gives_the_same_dist(tmp_path):
    site, collector = prepared(tmp_path)
    run(tmp_path, site, collector)
    first = dist_files(tmp_path)
    root = tmp_path / ".heron-cache" / media.SLICES
    stamps = {p: p.stat().st_mtime_ns for p in root.rglob("*.webp")}

    import shutil

    shutil.rmtree(tmp_path / "dist")
    run(tmp_path, site, collector)

    assert dist_files(tmp_path) == first
    assert {p: p.stat().st_mtime_ns for p in stamps} == stamps


def test_changed_master_gets_new_bytes_and_others_keep_theirs(tmp_path):
    extra = {"uk/about.md": sites.page("Про", image="media/bio/other.png", image_alt="Інше")}
    site, collector = prepared(tmp_path, extra)
    master(tmp_path / "media" / "bio" / "other.png", colour=(10, 90, 200))
    run(tmp_path, site, collector)
    other = cached(tmp_path, "media/bio/other.png")
    keep = {p.name: p.read_bytes() for p in other.glob("*.webp")}
    before = (tmp_path / "dist/media/bio/portrait-1x1-400.webp").read_bytes()

    master(tmp_path / "media" / "bio" / "portrait.png", colour=(0, 200, 0))
    run(tmp_path, site, collector)

    after = (tmp_path / "dist/media/bio/portrait-1x1-400.webp").read_bytes()
    assert after != before
    assert {p.name: p.read_bytes() for p in other.glob("*.webp")} == keep
    # в сборке — ровно файл записи нового мастера
    fresh = cached(tmp_path, "media/bio/portrait.png") / "crop-1x1-400.webp"
    assert after == fresh.read_bytes()


def test_entries_nobody_used_for_a_long_time_are_swept(tmp_path):
    import time

    extra = {"uk/about.md": sites.page("Про", image="media/bio/other.png", image_alt="Інше")}
    site, collector = prepared(tmp_path, extra)
    master(tmp_path / "media" / "bio" / "other.png", colour=(1, 2, 3))
    run(tmp_path, site, collector)
    other = cached(tmp_path, "media/bio/other.png")
    portrait = cached(tmp_path, "media/bio/portrait.png")

    later = time.time() + (media.KEEP_DAYS + 1) * 86400
    import os

    os.utime(portrait / media.USED, (later, later))  # его отметила «живая» сборка
    removed = media.sweep(tmp_path / ".heron-cache", now=later)
    assert other in removed and not other.exists()
    assert portrait.exists()


def test_sweep_never_touches_what_a_build_already_placed(tmp_path):
    import time

    site, collector = prepared(tmp_path)
    run(tmp_path, site, collector)
    out = tmp_path / "dist/media/bio/portrait-1x1-400.webp"
    data = out.read_bytes()
    media.sweep(tmp_path / ".heron-cache", now=time.time() + 400 * 86400)
    assert out.read_bytes() == data  # жёсткая ссылка пережила удаление записи


def test_width_dropped_from_the_theme_leaves_the_build(tmp_path):
    site, collector = prepared(tmp_path)
    run(tmp_path, site, collector)
    assert (tmp_path / "dist/media/bio/portrait-1x1-800.webp").is_file()

    run(tmp_path, site, collector, images=spec(widths=[400], fallback_width=400))
    assert not (tmp_path / "dist/media/bio/portrait-1x1-800.webp").exists()
    assert (tmp_path / "dist/media/bio/portrait-1x1-400.webp").is_file()


def test_old_cache_formats_are_forgotten(tmp_path):
    old = tmp_path / ".heron-cache"
    (old / "media/bio").mkdir(parents=True)
    (old / "media/bio/portrait-1x1-400.webp").write_bytes(b"stale")
    (old / "media.json").write_text("{}", encoding="utf-8")
    site, collector = prepared(tmp_path)
    run(tmp_path, site, collector)
    assert not (old / "media").exists() and not (old / "media.json").exists()
    assert (tmp_path / "dist/media/bio/portrait-1x1-400.webp").read_bytes() != b"stale"


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
    from heron.core import output

    site, collector = prepared(tmp_path)
    monkeypatch.setattr(output.os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError("нельзя")))
    run(tmp_path, site, collector)
    out = tmp_path / "dist" / "media" / "bio" / "portrait-1x1-400.webp"
    assert out.is_file()
    assert out.stat().st_nlink == 1
