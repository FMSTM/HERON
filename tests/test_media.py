"""Картинки: сбор ссылок, кроп из мастера, варианты, кэш, разметка."""

from pathlib import Path

import pytest
from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import links, media, tree
from tests import sites


def master(path: Path, size: int = 1200, margin: int = 0.2) -> None:
    """Квадратный мастер: объект по центру, запас по краям."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pad = int(size * margin)
    for x in range(pad, size - pad):
        for y in range(pad, size - pad):
            image.putpixel((x, y), (30, 80, 160, 255))
    image.save(path)


FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/bio.md": sites.page("Біо", image="img/bio/portrait.png", image_alt="Портрет"),
}


@pytest.fixture
def prepared(tmp_path):
    content = sites.build(tmp_path, FILES)
    master(tmp_path / "img" / "bio" / "portrait.png")
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site, tmp_path, collector


def test_references_collected_from_frontmatter_and_body(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна", image="img/a.png"),
        "uk/x.md": (
            "---\ntitle: X\nh1: X\ndescription: Опис\n---\n\n"
            "## Що {#what}\n\n![Підпис](img/in-body.png)\n"
        ),
    }
    content = sites.build(tmp_path, files)
    site, _ = tree.scan(content, sites.config())
    assert media.references(site) == {"img/a.png", "img/in-body.png"}


def test_missing_image_is_e007(tmp_path):
    files = {"uk/index.md": sites.page("Головна", image="img/нет.png")}
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    media.build(site, tmp_path, tmp_path / "dist", ImagesSpec(), collector)
    assert [e.code for e in collector.errors] == ["E007"]


def test_variants_for_each_ratio_and_width(prepared):
    site, root, collector = prepared
    spec = ImagesSpec(widths=[400, 800], ratios=["1:1", "16:9"], formats=["webp"])
    manifest = media.build(site, root, root / "dist", spec, collector)
    square = manifest.get("img/bio/portrait.png", "1:1")
    wide = manifest.get("img/bio/portrait.png", "16:9")
    assert square is not None and wide is not None
    assert [w for w, _ in square.sources["webp"]] == [400, 800]
    assert (root / "dist" / "img" / "bio" / "portrait-1x1-800.webp").is_file()
    assert (root / "dist" / "img" / "bio" / "portrait-16x9-800.webp").is_file()


def test_crop_keeps_the_requested_ratio(prepared):
    site, root, collector = prepared
    spec = ImagesSpec(widths=[800], ratios=["16:9"], formats=["webp"])
    media.build(site, root, root / "dist", spec, collector)
    with Image.open(root / "dist" / "img" / "bio" / "portrait-16x9-800.webp") as out:
        assert round(out.width / out.height, 2) == round(16 / 9, 2)


def test_original_stays_untouched(prepared):
    site, root, collector = prepared
    before = (root / "img" / "bio" / "portrait.png").read_bytes()
    media.build(site, root, root / "dist", ImagesSpec(widths=[400]), collector)
    assert (root / "img" / "bio" / "portrait.png").read_bytes() == before


def test_fallback_in_original_format(prepared):
    site, root, collector = prepared
    spec = ImagesSpec(widths=[400], ratios=["1:1"], formats=["webp"])
    manifest = media.build(site, root, root / "dist", spec, collector)
    rendition = manifest.get("img/bio/portrait.png", "1:1")
    assert rendition.fallback.endswith(".png")
    assert (root / "dist" / rendition.fallback).is_file()


def test_width_larger_than_source_is_not_invented(prepared):
    site, root, collector = prepared
    spec = ImagesSpec(widths=[400, 4000], ratios=["1:1"], formats=["webp"])
    manifest = media.build(site, root, root / "dist", spec, collector)
    widths = [w for w, _ in manifest.get("img/bio/portrait.png", "1:1").sources["webp"]]
    assert widths == [400]


def test_object_touching_the_edge_warns(tmp_path):
    content = sites.build(tmp_path, FILES)
    master(tmp_path / "img" / "bio" / "portrait.png", margin=0.02)
    site, collector = tree.scan(content, sites.config())
    media.build(site, tmp_path, tmp_path / "dist", ImagesSpec(widths=[400]), collector)
    assert any("упирается в край" in w.message for w in collector.warnings)


def test_cache_skips_unchanged_source(prepared):
    site, root, collector = prepared
    spec = ImagesSpec(widths=[400], ratios=["1:1"], formats=["webp"])
    media.build(site, root, root / "dist", spec, collector)
    out = root / "dist" / "img" / "bio" / "portrait-1x1-400.webp"
    stamp = out.stat().st_mtime_ns
    media.build(site, root, root / "dist", spec, collector)
    assert out.stat().st_mtime_ns == stamp


def test_changed_source_is_reprocessed(prepared):
    site, root, collector = prepared
    spec = ImagesSpec(widths=[400], ratios=["1:1"], formats=["webp"])
    media.build(site, root, root / "dist", spec, collector)
    out = root / "dist" / "img" / "bio" / "portrait-1x1-400.webp"
    stamp = out.stat().st_mtime_ns
    master(root / "img" / "bio" / "portrait.png", size=900)
    media.build(site, root, root / "dist", spec, collector)
    assert out.stat().st_mtime_ns != stamp
