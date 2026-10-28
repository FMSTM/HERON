"""Картинки в карте сайта: `image:image` на странице, обложка первой, лимит 20."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from heron.contracts.frontmatter import PageMeta
from heron.core.build import SITEMAP_IMAGES, sitemap_images
from heron.core.media import Manifest
from heron.core.models import Page, Section, Site
from heron.modules import sitemap
from tests import sites

NS = {
    "s": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "i": "http://www.google.com/schemas/sitemap-image/1.1",
}


@pytest.fixture
def config():
    return sites.config(
        site={"domain": "example.com", "theme": "demo", "default_lang": "uk", "languages": ["uk"]}
    )


def _page(intro: str = "", **meta) -> Page:
    page = Page(
        lang="uk",
        source="uk/x.md",
        key="x",
        meta=PageMeta(title="T", h1="H", description="D", **meta),
    )
    if intro:
        page.intro = Section(id="intro", title="", level=0, raw=intro)
    return page


@pytest.fixture
def manifest() -> Manifest:
    out = Manifest()
    out.raw.add("media/cover.png")
    return out


def _images(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    return [e.text for e in root.iterfind(".//i:image/i:loc", NS)]


def _text(*names: str) -> str:
    return " ".join(f"![a](media/{n}.png)" for n in names)


def test_cover_first_then_text_images(config, manifest):
    page = _page(intro=_text("a", "b"), image="media/cover.png")
    got = sitemap_images(config, manifest)(page)
    assert got == [
        "https://example.com/media/cover.png",
        "https://example.com/media/a.png",
        "https://example.com/media/b.png",
    ]


def test_limit_and_duplicates(config, manifest):
    page = _page(intro=_text(*[f"p{i}" for i in range(25)]) + _text("p0", "p1"))
    got = sitemap_images(config, manifest)(page)
    assert len(got) == SITEMAP_IMAGES == 20
    assert len(set(got)) == 20


def test_foreign_domain_dropped(config, manifest):
    page = _page(intro=_text("a"), og_image="https://cdn.other.net/x.png")
    got = sitemap_images(config, manifest)(page)
    assert got == ["https://example.com/media/a.png"]


def test_generate_with_images_is_valid_xml(config, manifest):
    page = _page(intro=_text("a", "b"), image="media/cover.png")
    site = Site(pages=[page])
    xml = sitemap.generate(site, config, sitemap_images(config, manifest))["sitemap.xml"]
    assert 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' in xml
    assert _images(xml)[0] == "https://example.com/media/cover.png"
    assert len(_images(xml)) == 3


def test_not_indexable_has_no_images(config):
    site = Site(pages=[_page(intro=_text("a"))])
    xml = sitemap.generate(site, config, None)["sitemap.xml"]
    assert "image:image" not in xml
    assert "xmlns:image" not in xml
    ET.fromstring(xml)


def test_no_images_no_namespace(config, manifest):
    site = Site(pages=[_page()])
    xml = sitemap.generate(site, config, lambda page: [])["sitemap.xml"]
    assert "xmlns:image" not in xml
    ET.fromstring(xml)


def test_escape(config):
    site = Site(pages=[_page()])
    xml = sitemap.generate(site, config, lambda page: ["https://example.com/a.png?x=1&y=2"])
    assert _images(xml["sitemap.xml"]) == ["https://example.com/a.png?x=1&y=2"]


# --- интеграция: полная сборка в двух окружениях ---


def _build(tmp_path, env: str) -> list[str]:
    from heron.core import build
    from heron.core.environment import BuildEnv
    from heron.scaffold import create

    root = tmp_path / env / "site"
    create(root, name="Example", languages=["en"])
    dist = tmp_path / env / "dist"
    build.run(root, dist=dist, with_media=False, env=BuildEnv.named(env))
    xml = (dist / "sitemap.xml").read_text(encoding="utf-8")
    return [xml, *_images(xml)]


def test_build_dev_has_no_images(tmp_path):
    xml, *images = _build(tmp_path, "dev")
    assert images == []
    assert "xmlns:image" not in xml


def test_build_prod_sitemap_parses(tmp_path):
    xml, *images = _build(tmp_path, "prod")
    ET.fromstring(xml)
    assert ("xmlns:image" in xml) == bool(images)
    assert all(href.startswith("https://") for href in images)
