"""В media/ лежит не только то, что движок умеет обрабатывать.

Видео, памятка, презентация — такой же объявленный ресурс страницы, как
картинка. Пока движок видел только изображения, всё прочее оседало в
static/ и ехало в сборку мимо проверок и мимо обработки.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from heron.core import build as pipeline
from heron.core import links, media, report, tree
from heron.core.errors import Collector
from heron.scaffold import create
from tests import sites


def _page(**fields) -> str:
    meta = {"title": "Сторінка", "h1": "Сторінка", "description": "Опис", **fields}
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{head}\n---\n\nТекст.\n"


def _site(tmp_path: Path, files: dict[str, str]):
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    links.resolve(site, sites.config(), sites.theme(), collector)
    return site, collector


def test_video_from_a_field_is_collected(tmp_path):
    site, _ = _site(tmp_path, {"uk/index.md": _page(video="media/video/reportazh.mp4")})
    assert "media/video/reportazh.mp4" in media.references(site)


def test_document_linked_from_text_is_collected(tmp_path):
    files = {
        "uk/index.md": (
            "---\ntitle: X\nh1: X\ndescription: Опис\n---\n\n"
            "## Що {#what}\n\n[памʼятка](media/docs/pamyatka.pdf)\n"
        )
    }
    site, _ = _site(tmp_path, files)
    assert "media/docs/pamyatka.pdf" in media.references(site)


def test_any_file_lands_in_dist_as_is(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(
        _page(video="media/video/x.mp4"), encoding="utf-8"
    )
    source = root / "media" / "video" / "x.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes("ролик".encode())

    pipeline.run(root)
    copied = root / "dist" / "media" / "video" / "x.mp4"
    assert copied.is_file()
    assert copied.read_bytes() == source.read_bytes()


def test_missing_file_of_any_type_is_e007(tmp_path):
    site, collector = _site(tmp_path, {"uk/index.md": _page(video="media/video/нет.mp4")})
    media.verify(site, tmp_path, collector)
    errors = [e for e in collector.errors if e.code == "E007"]
    assert errors and "uk/index.md" in errors[0].path


def test_heavy_file_warns_with_page_name(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(
        _page(video="media/video/big.mp4"), encoding="utf-8"
    )
    heavy = root / "media" / "video" / "big.mp4"
    heavy.parent.mkdir(parents=True)
    heavy.write_bytes(b"0" * (media.HEAVY + 1))

    result = pipeline.run(root)
    weighty = [w for w in result.collector.warnings if "весит" in w.message]
    assert weighty and "uk/index.md" in weighty[0].path


def test_unused_file_stays_out_of_the_build_and_shows_in_report(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(_page(), encoding="utf-8")
    forgotten = root / "media" / "foto" / "старое.jpg"
    forgotten.parent.mkdir(parents=True)
    forgotten.write_bytes(b"1")

    result = pipeline.run(root)
    assert not (root / "dist" / "media" / "foto" / "старое.jpg").exists()
    assert "media/foto/старое.jpg" in result.report.unused_media


def test_content_in_static_is_reported(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(_page(), encoding="utf-8")
    (root / "static").mkdir(exist_ok=True)
    (root / "static" / "video.mp4").write_bytes(b"1")
    (root / "static" / "ads.txt").write_text("ок", encoding="utf-8")

    site, collector = tree.scan(root / "content", sites.config())
    links.resolve(site, sites.config(), sites.theme(), collector)
    built = report.build(site, sites.config(), sites.theme(), site_root=root)
    assert built.static_media == ["static/video.mp4"]
    assert "static/ads.txt" not in built.static_media
    assert not Collector().errors


def test_file_declared_in_site_yaml_is_collected(tmp_path):
    """Картинка для соцсетей объявлена в site.yaml — её тоже надо собрать."""
    config = sites.config(
        seo={"og_default_image": "media/og/default.jpg", "title_suffix": ""},
        site={
            "domain": "example.com",
            "theme": "demo",
            "default_lang": "uk",
            "languages": ["uk"],
        },
    )
    content = sites.build(tmp_path, {"uk/index.md": _page()})
    site, _ = tree.scan(content, config)
    assert "media/og/default.jpg" in media.references(site, config)
    assert media.declared_by(site, config)["media/og/default.jpg"] == ["site.yaml"]


def test_notes_next_to_masters_are_not_reported(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(_page(), encoding="utf-8")
    (root / "media").mkdir(exist_ok=True)
    (root / "media" / "README.md").write_text("что ещё нарисовать", encoding="utf-8")
    site, _ = tree.scan(root / "content", sites.config())
    assert media.unused(site, root) == []
