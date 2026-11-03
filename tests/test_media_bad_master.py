"""E036: мастер картинки есть, но не читается как изображение."""

from __future__ import annotations

import io

from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import media, tree
from heron.core.errors import Collector
from tests import sites

SPEC = ImagesSpec(widths=[400], ratios=["1:1"], formats=["webp"])


def _good_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1200, 900), (20, 60, 120)).save(buffer, "JPEG")
    return buffer.getvalue()


def _site(tmp_path, files: dict[str, bytes], **fields):
    content = sites.build(tmp_path, {"uk/index.md": sites.page("Головна", **fields)})
    for rel, data in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    config = sites.config()
    site, _ = tree.scan(content, config)
    return site, config


def _plan(tmp_path, site, config=None):
    collector = Collector()
    manifest = media.plan(site, tmp_path, SPEC, collector, config=config)
    return manifest, collector


def test_plan_bad_masters_give_e036(tmp_path):
    good = _good_bytes()
    cases = {
        "text": b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 10\n",
        "empty": b"",
        "truncated": good[: len(good) // 2],
    }
    for name, data in cases.items():
        sub = tmp_path / name
        _site(sub, {"media/bad.jpg": data, "media/ok.jpg": good}, image="media/bad.jpg")
        content_text = (sub / "content/uk/index.md").read_text(encoding="utf-8")
        (sub / "content/uk/index.md").write_text(
            content_text.replace("Вступление.", "Вступление. ![](media/ok.jpg)", 1),
            encoding="utf-8",
        )
        config = sites.config()
        site, _ = tree.scan(sub / "content", config)
        manifest, collector = _plan(sub, site, config)
        errors = [e for e in collector.errors if e.code == "E036"]
        assert len(errors) == 1, name
        assert "media/bad.jpg" in str(errors[0])
        assert "uk/index.md" in str(errors[0])
        assert collector.failed, name  # ошибка и без --strict, в отличие от E007
        assert "media/bad.jpg" not in manifest.masters, name
        assert "media/ok.jpg" in manifest.masters, name
        assert any(src == "media/ok.jpg" for src, *_ in manifest.planned.values()), name


def test_verify_covers_bad_cover_gives_e036(tmp_path):
    good = _good_bytes()
    for name, data in {"text": b"not an image", "truncated": good[:200]}.items():
        sub = tmp_path / name
        site, config = _site(sub, {"media/cover.jpg": data}, image="media/cover.jpg")
        collector = Collector()
        media.verify_covers(site, sub, collector, SPEC, config)
        assert [e.code for e in collector.errors] == ["E036"], name
        assert "media/cover.jpg" in str(collector.errors[0])


def test_good_master_unchanged(tmp_path):
    site, config = _site(tmp_path, {"media/cover.jpg": _good_bytes()}, image="media/cover.jpg")
    manifest, collector = _plan(tmp_path, site, config)
    assert not collector.errors
    assert manifest.planned
    verify = Collector()
    media.verify_covers(site, tmp_path, verify, SPEC, config)
    assert not verify.errors


def test_cover_sources_matches_page_selection(tmp_path):
    site, config = _site(tmp_path, {}, image="media/cover.jpg")
    expected = {
        chosen[0].lstrip("./")
        for page in site.pages
        if (chosen := page.cover_source(config)) and not media.EXTERNAL.match(chosen[0])
    }
    assert media.cover_sources(site, config) == expected
    assert "media/cover.jpg" in expected
    assert media.cover_sources(site, None) == set()
