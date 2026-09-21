"""Картинки: сбор ссылок, кроп из мастера, варианты, кэш, разметка."""

from pathlib import Path

import pytest
from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import links, media, tree
from tests import sites


def master(path: Path, size: int = 1200, margin: float = 0.2) -> None:
    """Квадратный мастер: объект по центру, запас по краям.

    Рисуется вставкой прямоугольника, а не попиксельно: полмиллиона вызовов
    putpixel на картинку — это секунды на ровном месте, помноженные
    на число тестов.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pad = int(size * margin)
    body = Image.new("RGBA", (size - 2 * pad, size - 2 * pad), (30, 80, 160, 255))
    image.paste(body, (pad, pad))
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


def test_missing_image_is_e007_in_strict(tmp_path):
    """В проде и в CI собирают со --strict: битая картинка дороже сборки."""
    files = {"uk/index.md": sites.page("Головна", image="img/нет.png")}
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    media.build(site, tmp_path, tmp_path / "dist", ImagesSpec(), collector, strict=True)
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


def test_illustration_is_fitted_not_cropped(tmp_path):
    """Рисунок доходит до края кадра — кроп срезал бы его, вписывание нет."""
    content = sites.build(tmp_path, FILES)
    master(tmp_path / "img" / "bio" / "portrait.png", margin=0.02)
    site, collector = tree.scan(content, sites.config())
    spec = ImagesSpec(widths=[800], ratios=["16:9", "4:3", "1:1"], formats=["webp"])
    media.build(site, tmp_path, tmp_path / "dist", spec, collector)

    for ratio, label in (("16:9", "16x9"), ("4:3", "4x3"), ("1:1", "1x1")):
        path = tmp_path / "dist" / "img" / "bio" / f"portrait-{label}-800.webp"
        with Image.open(path) as out:
            left, right = (int(part) for part in ratio.split(":"))
            assert round(out.width / out.height, 2) == round(left / right, 2)
            box = out.convert("RGBA").getbbox()
            # рисунок квадратный: если бы его кропнули, он перестал бы им быть
            assert abs((box[2] - box[0]) - (box[3] - box[1])) <= 2
            # и добивка прозрачная, а не залитая
            assert out.convert("RGBA").getpixel((0, 0))[3] == 0
    assert not any("упирается в край" in w.message for w in collector.warnings)


def test_photo_without_alpha_is_cropped(tmp_path):
    """У фотографии полей взять неоткуда, поэтому её по-прежнему кропает."""
    content = sites.build(tmp_path, FILES)
    path = tmp_path / "img" / "bio" / "portrait.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 900), (20, 60, 120)).save(path)
    site, collector = tree.scan(content, sites.config())
    spec = ImagesSpec(widths=[400], ratios=["1:1"], formats=["webp"])
    media.build(site, tmp_path, tmp_path / "dist", spec, collector)

    with Image.open(tmp_path / "dist" / "img" / "bio" / "portrait-1x1-400.webp") as out:
        assert out.width == out.height


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


def test_missing_image_is_a_warning_while_writing(tmp_path):
    """Страницу пишут раньше, чем рисуют иллюстрацию."""
    files = {"uk/index.md": sites.page("Головна", image="img/нет.png")}
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    media.build(site, tmp_path, tmp_path / "dist", ImagesSpec(), collector)
    assert not collector.failed
    assert any("нет.png" in w.message for w in collector.warnings)


def test_opaque_alpha_is_dropped():
    """Непрозрачная альфа уводит кодировщики на медленный путь — и не нужна."""
    from PIL import Image

    from heron.core.media import _opaque

    assert _opaque(Image.new("RGBA", (8, 8), (10, 20, 30, 255))).mode == "RGB"


def test_real_transparency_survives():
    from PIL import Image

    from heron.core.media import _opaque

    image = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))
    assert _opaque(image).mode == "RGBA"


def test_references_include_theme_fields(tmp_path):
    """Тема вправе объявить своё поле с картинкой — её тоже надо нарезать."""
    files = {
        "uk/index.md": sites.page(
            "Головна",
            image="img/a.png",
            photo_second="img/b.jpg",
            gallery=["img/g1.png", "img/g2.png"],
            not_an_image="просто строка",
        )
    }
    content = sites.build(tmp_path, files)
    site, _ = tree.scan(content, sites.config())
    assert media.references(site) == {"img/a.png", "img/b.jpg", "img/g1.png", "img/g2.png"}


def test_missing_image_warning_names_the_page(tmp_path):
    """«Нет на диске» без имени страницы заставляет искать объявление руками."""
    files = {"uk/index.md": sites.page("Головна", image="img/нет.png")}
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    media.build(site, tmp_path, tmp_path / "dist", ImagesSpec(), collector)
    missing = [w for w in collector.warnings if w.kind == "картинки"]
    assert [w.path for w in missing] == ["uk/index.md"]
    assert "img/нет.png" in missing[0].message
