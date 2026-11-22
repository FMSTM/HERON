"""Нарезки 0.3.2: запасной файл без PNG, исходники без ссылок не едут в сборку.

- прозрачный PNG (хоть один не непрозрачный пиксель) - запасной файл WebP с
  альфой; обложке для краулеров рядом - PNG той же пропорции шириной cover_width;
- непрозрачный PNG - JPG, как фотография; рядом мастер `x.jpg` - PNG остаётся;
- JPG, WebP, SVG - как раньше;
- мастер и файлы, которые движок не режет, едут в сборку, только если на них
  ссылается собранный сайт; прочие названы в отчёте (сведение);
- одинаковый вход - одинаковые байты.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import build as pipeline
from heron.core import media, tree
from heron.core.errors import Collector
from heron.scaffold import create
from tests import sites


def _transparent(path: Path, size: int = 1600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    image.paste(Image.new("RGBA", (size // 2, size // 2), (200, 40, 40, 255)), (size // 4,) * 2)
    image.save(path)


def _opaque_png(path: Path, size: int = 1600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # RGBA с полностью непрозрачной альфой - для движка это не прозрачность
    Image.new("RGBA", (size, size), (40, 90, 160, 255)).save(path)


def _photo(path: Path, size: int = 1600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), (90, 60, 30)).save(path)


def _plan(src: str, root: Path, cover: bool = False):
    spec = ImagesSpec(widths=[400, 800], ratios=["1:1"], formats=["avif", "webp"])
    return media.plan_master(src, root / src, spec, cover=cover)["1:1"]


def test_transparent_png_falls_back_to_webp_and_cover_to_png(tmp_path):
    _transparent(tmp_path / "media" / "a.png")
    plain = _plan("media/a.png", tmp_path)
    assert plain.fallback == "media/a-1x1-800.webp"
    assert "cover" not in plain.sources
    cover = _plan("media/a.png", tmp_path, cover=True)
    assert cover.fallback == "media/a-1x1-800.webp"
    assert [rel for _, rel in cover.sources["cover"]] == ["media/a-1x1-1200.png"]
    # имена avif и webp не меняются
    assert [rel for _, rel in cover.sources["webp"]] == [
        "media/a-1x1-400.webp",
        "media/a-1x1-800.webp",
    ]
    assert not any(rel.endswith(".png") for _, rel in cover.sources["origin"])


def test_opaque_png_falls_back_to_jpg(tmp_path):
    _opaque_png(tmp_path / "media" / "b.png")
    rendition = _plan("media/b.png", tmp_path, cover=True)
    assert rendition.fallback == "media/b-1x1-800.jpg"
    assert "cover" not in rendition.sources  # JPG краулеры понимают


def test_opaque_png_next_to_a_jpg_master_stays_png(tmp_path):
    _opaque_png(tmp_path / "media" / "c.png")
    _photo(tmp_path / "media" / "c.jpg")
    assert _plan("media/c.png", tmp_path).fallback == "media/c-1x1-800.png"
    assert _plan("media/c.jpg", tmp_path).fallback == "media/c-1x1-800.jpg"


@pytest.mark.parametrize(("name", "make"), [("d.jpg", _photo), ("e.webp", _photo)])
def test_other_formats_keep_their_fallback(tmp_path, name, make):
    path = tmp_path / "media" / name
    make(path)
    if name.endswith(".webp"):
        Image.open(path).save(path, format="WEBP")
    ext = Path(name).suffix
    assert _plan(f"media/{name}", tmp_path).fallback.endswith(f"-1x1-800{ext}")


# --- сборка ----------------------------------------------------------------------------


LINK = re.compile(r"""(?:src|href|content)="(?:https?://[^/"]+)?/(media/[^"?#]+)""")
SRCSET = re.compile(r'srcset="([^"]+)"')


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("SITE_ENV", raising=False)
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    _transparent(root / "media" / "logo-art.png")
    _opaque_png(root / "media" / "shot.png")
    (root / "media" / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>', encoding="utf-8"
    )
    (root / "media" / "unused.pdf").write_bytes(b"%PDF-1.4 x")
    (root / "media" / "linked.pdf").write_bytes(b"%PDF-1.4 y")
    page = root / "content" / "en" / "docs.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "---\ntitle: Docs\nh1: Docs\ndescription: About the docs page.\n"
        "image: media/logo-art.png\nimage_alt: Art\n---\n\nIntro.\n"
        "\n![Shot](media/shot.png)\n\n![Icon](media/icon.svg)\n\n"
        "[PDF](media/linked.pdf)\n"
    )
    page.write_text(text, encoding="utf-8")
    return root


def _refs(dist: Path) -> set[str]:
    found: set[str] = set()
    for path in dist.rglob("*"):
        if "_heron" in path.relative_to(dist).parts or path.suffix not in {".html", ".xml"}:
            continue
        text = path.read_text(encoding="utf-8")
        found |= set(LINK.findall(text))
        for srcset in SRCSET.findall(text):
            for part in srcset.split(","):
                url = part.strip().split(" ")[0]
                found.add(url.lstrip("/").split("?")[0])
    return {r for r in found if r.startswith("media/")}


def test_build_ships_only_what_the_site_links_and_every_link_resolves(site):
    result = pipeline.run(site, dist=site / "dist")
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = site / "dist"
    files = {p.relative_to(dist).as_posix() for p in (dist / "media").rglob("*") if p.is_file()}
    files = {f for f in files if not f.endswith(".gz")}
    refs = _refs(dist)
    assert refs <= files, refs - files  # ни одной битой ссылки
    html = (dist / "docs" / "index.html").read_text(encoding="utf-8")
    # прозрачная картинка: PNG-нарезок нет, кроме варианта обложки для краулеров
    assert not any(re.search(r"logo-art-\d+x\d+-\d+\.png", f) for f in files if "1200" not in f)
    # og:image - PNG для краулеров (прозрачность сохраняется)
    assert re.search(r'og:image" content="[^"]*/media/logo-art-[0-9x]+-1200\.png', html), html
    # ссылки из текста - сам файл: картинка, svg, pdf
    assert {"media/shot.png", "media/icon.svg", "media/linked.pdf"} <= files
    # ни на что не ссылается - не едет, но назван в отчёте
    assert "media/logo-art.png" not in files
    assert "media/logo-art.png" in result.report.withheld_media
    assert "media/unused.pdf" not in files
    report = result.report.render("en")
    assert "media/ sources not shipped in the build" in report


def test_same_input_same_bytes(site, tmp_path):
    def digests(dist: Path) -> dict[str, str]:
        return {
            p.relative_to(dist).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (dist / "media").rglob("*")
            if p.is_file()
        }

    import shutil

    one = pipeline.run(site, dist=tmp_path / "one")
    # второй прогон - с пустым кэшем: нарезки кодируются заново
    shutil.rmtree(tmp_path / ".heron-cache", ignore_errors=True)
    shutil.rmtree(site / ".heron-cache", ignore_errors=True)
    two = pipeline.run(site, dist=tmp_path / "two")
    assert not one.failed and not two.failed
    assert digests(tmp_path / "one") == digests(tmp_path / "two")


def test_transparency_survives_in_webp_fallback_and_crawler_png(tmp_path):
    _transparent(tmp_path / "media" / "a.png", size=1600)
    spec = ImagesSpec(widths=[400, 800], ratios=["1:1"], formats=["webp"])

    content = sites.build(
        tmp_path, {"uk/a.md": sites.page("A", image="media/a.png", image_alt="a")}
    )
    model, _ = tree.scan(content, sites.config())
    media.build(model, tmp_path, tmp_path / "dist", spec, Collector(), config=sites.config())
    for name in ("a-1x1-800.webp", "a-1x1-1200.png"):
        with Image.open(tmp_path / "dist" / "media" / name) as image:
            assert image.mode == "RGBA", name
            assert image.getchannel("A").getextrema()[0] < 255, name
