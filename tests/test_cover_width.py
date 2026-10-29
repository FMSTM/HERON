"""Крупный запасной файл обложки: images.cover_width."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import media, tree
from heron.core.render.env import cover_of
from tests import sites
from tests.test_media import master


def _photo(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), (200, 100, 50)).save(path)


def _run(tmp_path, src: str, spec: ImagesSpec, cache: Path | None = None):
    content = sites.build(tmp_path, {"uk/index.md": sites.page("Головна", image=src)})
    config = sites.config()
    site, collector = tree.scan(content, config)
    manifest = media.build(
        site, tmp_path, tmp_path / "dist", spec, collector, cache_dir=cache, config=config
    )
    return site, config, manifest, collector


def _spec(**over) -> ImagesSpec:
    return ImagesSpec(widths=[400], ratios=["1:1"], formats=["webp"], **over)


def test_default_cover_width_is_1200():
    assert ImagesSpec().cover_width == 1200


def test_cover_width_must_be_positive():
    with pytest.raises(ValueError):
        ImagesSpec(cover_width=0)


def test_large_master_gets_1200_jpeg_and_cover_url_uses_it(tmp_path):
    _photo(tmp_path / "img" / "c.jpg", 2000)
    site, config, manifest, _ = _run(tmp_path, "img/c.jpg", _spec())
    assert (tmp_path / "dist" / "img" / "c-1x1-1200.jpg").is_file()
    got = cover_of(manifest, config)(site.pages[0])
    assert got is not None and got["url"].endswith("/img/c-1x1-1200.jpg")


def test_small_master_returns_master_and_warns(tmp_path):
    _photo(tmp_path / "img" / "c.jpg", 900)
    site, config, manifest, collector = _run(tmp_path, "img/c.jpg", _spec())
    assert not (tmp_path / "dist" / "img" / "c-1x1-1200.jpg").exists()
    got = cover_of(manifest, config)(site.pages[0])
    assert got is not None and got["url"].endswith("/img/c.jpg")
    assert any(
        w.kind == "картинки" and "обложка меньше 1200 px: img/c.jpg" in w.message
        for w in collector.warnings
    )


def test_custom_cover_width(tmp_path):
    _photo(tmp_path / "img" / "c.jpg", 2000)
    _, _, manifest, _ = _run(tmp_path, "img/c.jpg", _spec(cover_width=1600))
    assert (tmp_path / "dist" / "img" / "c-1x1-1600.jpg").is_file()
    assert not (tmp_path / "dist" / "img" / "c-1x1-1200.jpg").exists()


def test_transparent_png_gets_png_variant(tmp_path):
    master(tmp_path / "img" / "c.png", size=2000)
    _, _, manifest, _ = _run(tmp_path, "img/c.png", _spec())
    assert (tmp_path / "dist" / "img" / "c-1x1-1200.png").is_file()


def test_cache_is_not_recut_on_second_build(tmp_path):
    _photo(tmp_path / "img" / "c.jpg", 2000)
    cache = tmp_path / ".cache"
    _run(tmp_path, "img/c.jpg", _spec(), cache)
    kept = next(cache.rglob("*-1x1-1200.jpg"))
    before = kept.stat().st_mtime_ns
    _run(tmp_path, "img/c.jpg", _spec(), cache)
    assert kept.stat().st_mtime_ns == before


def _check_site(tmp_path: Path, size: int):
    from heron.core import build as pipeline
    from heron.scaffold import create

    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    _photo(root / "media" / "c.jpg", size)
    (root / "content" / "uk" / "index.md").write_text(
        sites.page("Головна", image="media/c.jpg"), encoding="utf-8"
    )
    return pipeline.check(root)


def test_check_warns_about_small_cover(tmp_path):
    result = _check_site(tmp_path, 900)
    assert any(
        w.kind == "картинки" and "обложка меньше 1200 px: media/c.jpg" in w.message
        for w in result.collector.warnings
    )
    assert not [e for e in result.collector.errors if "обложка" in e.message]


def test_check_silent_for_large_cover(tmp_path):
    result = _check_site(tmp_path, 1600)
    assert not any("обложка меньше" in w.message for w in result.collector.warnings)
