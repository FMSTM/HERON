"""Стартовая тема `heron new`: og/twitter/robots из коробки, без правок темы."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest
from PIL import Image

from heron.core import build as pipeline
from heron.core.environment import PROD, BuildEnv
from heron.scaffold import create
from tests import sites


class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        a = dict(attrs)
        key = a.get("property") or a.get("name")
        if key and "content" in a:
            self.tags[key] = a["content"]


def _meta(path: Path) -> dict[str, str]:
    parser = _Meta()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.tags


def _site(tmp_path: Path, cover: bool = True) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=False)
    sites.clear_content(root)
    if cover:
        (root / "media").mkdir(exist_ok=True)
        Image.new("RGB", (1600, 900), (120, 80, 40)).save(root / "media" / "cover.png")
    files = {"en/_index.md": sites.page("Home", image="media/cover.png", image_alt="Фото")}
    if cover:
        files["en/_index.md"] = sites.page("Home", image="media/cover.png", image_alt="Фото")
    else:
        files["en/_index.md"] = sites.page("Home")
    sites.build(root, files)
    return root


def _build(root: Path, tmp_path: Path, env: BuildEnv):
    dist = tmp_path / "dist"
    result = pipeline.run(root, dist=dist, env=env)
    assert not result.failed, [e.message for e in result.collector.errors]
    return dist


def test_prod_has_full_social_meta(tmp_path):
    root = _site(tmp_path)
    dist = _build(root, tmp_path, BuildEnv(name=PROD, indexable=True))
    tags = _meta(dist / "index.html")
    assert tags["og:image"].startswith("https://")
    assert tags["og:image:width"] == "1200"
    assert tags["og:image:alt"] == "Фото"
    assert tags["og:site_name"] == "S"
    assert tags["og:locale"] == "en_US"
    assert tags["twitter:card"] == "summary_large_image"
    assert tags["twitter:title"] and tags["twitter:description"]
    assert tags["twitter:image"] == tags["og:image"]
    assert "max-image-preview:large" in tags["robots"]


def test_dev_is_noindex_without_preview(tmp_path):
    root = _site(tmp_path)
    dist = _build(root, tmp_path, BuildEnv())
    robots = _meta(dist / "index.html")["robots"]
    assert "noindex" in robots and "nofollow" in robots
    assert "max-image-preview" not in robots


def test_no_cover_means_no_image_tags(tmp_path):
    root = _site(tmp_path, cover=False)
    dist = _build(root, tmp_path, BuildEnv(name=PROD, indexable=True))
    tags = _meta(dist / "index.html")
    for key in ("og:image", "og:image:width", "og:image:height", "twitter:image"):
        assert key not in tags
    assert tags["twitter:title"]


@pytest.mark.parametrize("name", ["og:title", "og:url"])
def test_existing_tags_kept(tmp_path, name):
    root = _site(tmp_path)
    dist = _build(root, tmp_path, BuildEnv())
    assert name in _meta(dist / "index.html")
