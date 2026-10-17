"""Пути к ресурсам из текста и кэш, общий для нескольких сайтов.

- `/media/x.png` в markdown не находился и не доезжал до сборки;
- `media/x.svg` на вложенной странице указывал в `/раздел/страница/media/…`;
- `photo.jpg` и `photo.png` давали одни и те же имена нарезок;
- общий `.heron-cache` адресовался путями сайта: сайт Б получал картинки А.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest
import yaml
from PIL import Image

from heron.core import build as pipeline
from heron.core import media
from heron.scaffold import create

PAGE = "---\ntitle: {t}\nh1: {t} page\ndescription: D\n{extra}---\n\n{body}\n"


def make(base: Path, name: str, colour=(200, 30, 30)) -> Path:
    root = base / name
    root.mkdir(parents=True)
    create(root, name="demo", languages=["en"])
    theme = root / "theme" / "theme.yaml"
    data = yaml.safe_load(theme.read_text(encoding="utf-8"))
    data["images"] = {"widths": [400], "ratios": ["1:1"], "formats": ["webp"]}
    theme.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    page = root / "theme" / "templates" / "page.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</h1>",
            "</h1>{% if page.meta.image %}"
            "{{ picture(page.meta.image, '1:1', alt='p') }}{% endif %}",
            1,
        ),
        encoding="utf-8",
    )
    (root / "media").mkdir(exist_ok=True)
    Image.new("RGB", (800, 800), colour).save(root / "media" / "photo.jpg")
    (root / "content/en/card.md").write_text(
        PAGE.format(t="Card", extra="image: media/photo.jpg\nimage_alt: p\n", body="Text."),
        encoding="utf-8",
    )
    return root


def colour_of(path: Path) -> tuple[int, int, int]:
    with Image.open(path) as image:
        return image.convert("RGB").getpixel((10, 10))


def close(a, b, tolerance=12) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


def ok(root: Path, **kw):
    result = pipeline.run(root, **kw)
    assert not result.failed, [str(e) for e in result.collector.errors]
    return result


# --- пути из текста ------------------------------------------------------------


def test_root_absolute_media_in_markdown_lands_in_the_build(tmp_path):
    root = make(tmp_path, "site")
    Image.new("RGB", (40, 40)).save(root / "media" / "picture.png")
    (root / "content/en/about.md").write_text(
        PAGE.format(t="About", extra="", body="![Pic](/media/picture.png)"), encoding="utf-8"
    )
    ok(root)
    assert (root / "dist/media/picture.png").is_file()
    assert 'src="/media/picture.png"' in (root / "dist/about/index.html").read_text("utf-8")


def test_relative_media_on_a_nested_page_points_to_the_root(tmp_path):
    root = make(tmp_path, "site")
    (root / "media" / "file.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>', encoding="utf-8"
    )
    nested = root / "content/en/services/design.md"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        PAGE.format(
            t="Design", extra="", body="![Scheme](media/file.svg)\n\n[Download](./media/file.svg)"
        ),
        encoding="utf-8",
    )
    ok(root)
    html = (root / "dist/services/design/index.html").read_text("utf-8")
    assert 'src="/media/file.svg"' in html
    assert 'href="/media/file.svg"' in html
    assert 'src="media/file.svg"' not in html
    assert (root / "dist/media/file.svg").is_file()


def test_same_stem_in_two_formats_is_e027(tmp_path):
    root = make(tmp_path, "site")
    Image.new("RGBA", (800, 800), (0, 0, 0, 0)).save(root / "media" / "photo.png")
    (root / "content/en/other.md").write_text(
        PAGE.format(t="Other", extra="image: media/photo.png\nimage_alt: p\n", body="Text."),
        encoding="utf-8",
    )
    result = pipeline.run(root)
    assert "E027" in [e.code for e in result.collector.errors]


# --- общий кэш ----------------------------------------------------------------


def test_two_sites_with_the_same_names_do_not_mix(tmp_path):
    red = make(tmp_path, "red", colour=(200, 30, 30))
    blue = make(tmp_path, "blue", colour=(30, 30, 200))
    out = tmp_path / "out"
    ok(red, dist=out / "red")
    ok(blue, dist=out / "blue")  # тот же .heron-cache: out/.heron-cache
    ok(red, dist=out / "red")
    rel = "media/photo-1x1-400.webp"
    assert close(colour_of(out / "red" / rel), (200, 30, 30))
    assert close(colour_of(out / "blue" / rel), (30, 30, 200))
    entries = [p for p in media.store(out / ".heron-cache").iterdir() if p.is_dir()]
    assert len(entries) == 2  # по записи на содержимое, а не одна на имя


def _build(args) -> str:
    root, dist = args
    result = pipeline.run(Path(root), dist=Path(dist))
    return "ok" if not result.failed else "; ".join(str(e) for e in result.collector.errors)


@pytest.mark.parametrize("same", [False, True])
def test_concurrent_builds_share_the_cache_safely(tmp_path, same):
    colours = [(200, 30, 30), (200, 30, 30) if same else (30, 30, 200)]
    sites = [make(tmp_path, f"s{i}", colour=c) for i, c in enumerate(colours)]
    out = tmp_path / "out"
    jobs = [(str(site), str(out / site.name)) for site in sites] * 2
    context = multiprocessing.get_context("spawn")
    with context.Pool(4) as pool:
        assert pool.map(_build, jobs) == ["ok"] * len(jobs)
    for site, colour in zip(sites, colours, strict=True):
        assert close(colour_of(out / site.name / "media/photo-1x1-400.webp"), colour)
    leftovers = [p for p in (out / ".heron-cache").rglob("*.tmp")]
    assert leftovers == []  # ни одного недописанного файла


def test_cache_identity_is_content_and_parameters(tmp_path):
    root = make(tmp_path, "site")
    ok(root)
    entry = media.store(root / ".heron-cache") / media.digest(root / "media/photo.jpg")
    assert (entry / "crop-1x1-400.webp").is_file()
    # тот же выходной файл из другого содержимого — другая запись
    Image.new("RGB", (800, 800), (0, 200, 0)).save(root / "media" / "photo.jpg")
    ok(root)
    assert close(colour_of(root / "dist/media/photo-1x1-400.webp"), (0, 200, 0))
