"""Поворот по EXIF Orientation — до геометрии, кадрирования и кодирования."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import build as pipeline
from heron.core import media
from heron.scaffold import create

RED = (255, 0, 0)


def _photo(path: Path, orientation: int) -> None:
    """Портрет 400×600 на экране, красная метка слева сверху; в файле — боком."""
    shown = Image.new("RGB", (400, 600), (255, 255, 255))
    shown.paste(RED, (0, 0, 80, 80))
    turn = Image.Transpose.ROTATE_90 if orientation == 6 else Image.Transpose.ROTATE_270
    exif = Image.Exif()
    exif[0x0112] = orientation
    shown.transpose(turn).save(path, exif=exif, quality=95)


def _close(pixel, colour, slack=40) -> bool:
    return all(abs(a - b) <= slack for a, b in zip(pixel, colour, strict=True))


@pytest.mark.parametrize("orientation", [6, 8])
def test_shape_and_slice_follow_orientation(tmp_path, orientation):
    src = tmp_path / "photo.jpg"
    _photo(src, orientation)
    assert Image.open(src).size == (600, 400)  # в файле — боком
    shape = media.shape_of(src)
    assert (shape.width, shape.height) == (400, 600)
    spec = ImagesSpec.model_validate(
        {"widths": [200], "ratios": ["2:3"], "formats": ["webp"], "fallback_width": 200}
    )
    out = tmp_path / "slice.webp"
    media.slice_master("media/photo.jpg", src, spec, [("2:3", "webp", 200, out)])
    sliced = Image.open(out)
    assert sliced.size == (200, 300)
    assert _close(sliced.convert("RGB").getpixel((5, 5)), RED)
    assert 0x0112 not in sliced.getexif()


@pytest.mark.parametrize("orientation", [6, 8])
def test_build_renditions_are_upright(tmp_path, orientation):
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True)
    _photo(root / "media" / "photo.jpg", orientation)
    index = root / "content" / "en" / "index.md"
    index.write_text(
        index.read_text("utf-8") + "\n\n## Pic {#pic}\n\n![A photo](media/photo.jpg)\n",
        encoding="utf-8",
    )
    home = root / "theme" / "templates" / "home.html"
    home.write_text(
        home.read_text("utf-8").replace(
            "{% block content %}",
            "{% block content %}{{ picture('media/photo.jpg', '16:9', alt='x') }}",
            1,
        ),
        encoding="utf-8",
    )
    result = pipeline.run(root, strict=True)
    assert not result.failed, [e.message for e in result.collector.errors]
    html = (root / "dist" / "index.html").read_text("utf-8")
    # 16:9 из портрета 400×600 — кадр 400×225; без поворота было бы 600 в ширину
    assert 'width="400" height="225"' in html
    entries = [p.parent.name for p in (root / ".heron-cache").rglob("shape.json")]
    assert entries and all(
        p.parent.parent.name.startswith(f"v{media.CACHE_VERSION}-")
        for p in (root / ".heron-cache").rglob("shape.json")
    )
    assert media.CACHE_VERSION >= 5
