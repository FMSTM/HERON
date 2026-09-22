"""Адрес файла для темы и видео как ресурс страницы."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import build as pipeline
from heron.core import links, media, tree
from heron.core.errors import Collector
from heron.core.render import env as render_env
from heron.scaffold import create
from tests import sites


def _page(**fields) -> str:
    meta = {"title": "Сторінка", "h1": "Сторінка", "description": "Опис", **fields}
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{head}\n---\n\nТекст.\n"


def master(path: Path, size: int = 1200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), (30, 80, 160)).save(path)


@pytest.fixture
def sliced(tmp_path):
    """Нарезанная картинка и готовый манифест."""
    files = {"uk/index.md": _page(image="media/foto/portrait.jpg")}
    content = sites.build(tmp_path, files)
    master(tmp_path / "media" / "foto" / "portrait.jpg")
    site, collector = tree.scan(content, sites.config())
    links.resolve(site, sites.config(), sites.theme(), collector)
    manifest = media.build(
        site,
        tmp_path,
        tmp_path / "dist",
        ImagesSpec(ratios=["16:9", "1:1"], widths=[400, 800, 1200], formats=["webp"]),
        collector,
        cache_dir=tmp_path / ".cache",
    )
    return manifest, collector


def test_plain_url_points_at_the_file_itself(sliced, tmp_path):
    manifest, collector = sliced
    url = render_env.media_url(manifest, collector)
    assert url("media/foto/portrait.jpg") == "/media/foto/portrait.jpg"
    # файл действительно лежит в сборке, иначе ссылка ведёт в никуда
    assert (tmp_path / "dist" / "media" / "foto" / "portrait.jpg").is_file()


def test_ratio_and_width_pick_the_variant(sliced):
    manifest, collector = sliced
    url = render_env.media_url(manifest, collector)
    got = url("media/foto/portrait.jpg", ratio="16:9", width=800)
    assert "-16x9-800." in got
    assert got.startswith("/media/foto/")


def test_width_takes_the_next_size_up(sliced):
    manifest, collector = sliced
    url = render_env.media_url(manifest, collector)
    assert "-16x9-800." in url("media/foto/portrait.jpg", ratio="16:9", width=500)


def test_missing_variant_warns_instead_of_empty(sliced):
    manifest, collector = sliced
    url = render_env.media_url(manifest, collector)
    got = url("media/foto/portrait.jpg", ratio="21:9")
    assert got == "/media/foto/portrait.jpg"
    assert any("21:9" in w.message for w in collector.warnings)


def test_any_file_gets_a_url(sliced):
    manifest, collector = sliced
    url = render_env.media_url(manifest, collector)
    assert url("media/docs/pamyatka.pdf") == "/media/docs/pamyatka.pdf"


def _site(tmp_path, **fields):
    content = sites.build(tmp_path, {"uk/index.md": _page(**fields)})
    site, collector = tree.scan(content, sites.config())
    return site, collector


def test_local_video_becomes_an_object(tmp_path):
    site, _ = _site(
        tmp_path,
        video="media/video/x.mp4",
        video_poster="media/video/x-poster.jpg",
        video_title="Репортаж",
    )
    video = site.pages[0].video
    assert video and not video.external
    assert video.src == "/media/video/x.mp4"
    assert video.poster == "/media/video/x-poster.jpg"
    assert video.title == "Репортаж"


def test_external_video_is_marked_and_needs_no_poster(tmp_path):
    site, collector = _site(tmp_path, video="https://example.com/watch?v=1")
    video = site.pages[0].video
    assert video.external and video.src == "https://example.com/watch?v=1"
    media.check_video(site, collector)
    assert collector.errors == []


def test_local_video_without_poster_is_an_error(tmp_path):
    site, collector = _site(tmp_path, video="media/video/x.mp4")
    media.check_video(site, collector)
    assert [e.code for e in collector.errors] == ["E019"]
    assert collector.errors[0].path == "uk/index.md"


def test_page_without_video_has_none(tmp_path):
    site, _ = _site(tmp_path)
    assert site.pages[0].video is None


def test_video_and_poster_land_in_the_build(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(
        _page(video="media/video/x.mp4", video_poster="media/video/x-poster.jpg"),
        encoding="utf-8",
    )
    (root / "media" / "video").mkdir(parents=True)
    (root / "media" / "video" / "x.mp4").write_bytes(b"film")
    master(root / "media" / "video" / "x-poster.jpg", size=600)

    result = pipeline.run(root)
    assert not result.collector.errors
    assert (root / "dist" / "media" / "video" / "x.mp4").is_file()
    assert (root / "dist" / "media" / "video" / "x-poster.jpg").is_file()


def test_collector_untouched(tmp_path):
    assert not Collector().errors
