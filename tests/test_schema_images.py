"""SCH006: картинка из разметки есть в сборке; мастера из блоков schema едут целиком."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PIL import Image

from heron.contracts.site import SiteConfig
from heron.core import build as pipeline
from heron.core import media
from heron.core.environment import BuildEnv
from heron.scaffold import create
from heron.schemaorg.images import image_refs, local_path, source_exists
from tests import sites

HOME = "---\ntitle: Головна\n---\nТекст\n"


@pytest.fixture
def scaffold(tmp_path, monkeypatch):
    monkeypatch.delenv("SITE_ENV", raising=False)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(int(datetime(2026, 10, 28, tzinfo=UTC).timestamp())))
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(HOME, encoding="utf-8")
    return root


def _entity(root, image: str) -> None:
    path = root / "site.yaml"
    block = f'\nschema:\n  entity:\n    "@type": Organization\n    name: Demo\n    image: "{image}"\n'
    path.write_text(path.read_text(encoding="utf-8") + block, encoding="utf-8")


def _photo(root, name="photo.jpg") -> None:
    folder = root / "media"
    folder.mkdir(exist_ok=True)
    Image.new("RGB", (1600, 900), "red").save(folder / name)


def _codes(result):
    return [e.code for e in result.collector.errors] + [
        w.message.split(" ", 1)[0] for w in result.collector.warnings
    ]


def test_image_refs_all_props_and_nested_url():
    node = {
        "@type": "Organization",
        "logo": {"@type": "ImageObject", "url": "/a.png"},
        "image": ["/b.png", {"contentUrl": "/c.png"}],
        "primaryImageOfPage": {"url": "/d.png"},
        "name": "x",
    }
    got = dict(image_refs(node))
    assert got == {
        "logo.url": "/a.png",
        "image.0": "/b.png",
        "image.1.contentUrl": "/c.png",
        "primaryImageOfPage.url": "/d.png",
    }


def test_local_path_own_foreign_data(tmp_path):
    config = sites.config(site={"domain": "example.com", "theme": "demo"})
    assert isinstance(config, SiteConfig)
    assert local_path("https://example.com/media/a.jpg?x=1", config) == "media/a.jpg"
    assert local_path("/media/a.jpg", config) == "media/a.jpg"
    assert local_path("https://other.org/a.jpg", config) is None
    assert local_path("data:image/png;base64,AAA", config) is None


def test_source_exists_master_slice_static(tmp_path):
    _photo(tmp_path)
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "logo.png").write_bytes(b"x")
    assert source_exists(tmp_path, "media/photo.jpg")
    assert source_exists(tmp_path, "media/photo-16x9-800.webp")
    assert not source_exists(tmp_path, "media/nope-16x9-800.webp")
    assert not source_exists(tmp_path, "media/nope.jpg")
    assert source_exists(tmp_path, "logo.png")
    assert not source_exists(tmp_path, "gone.png")


def test_check_missing_image_prod_is_error_with_key(scaffold):
    _entity(scaffold, "{{ site.base }}media/nope.jpg")
    result = pipeline.check(scaffold, env=BuildEnv.named("prod"))
    errors = [e for e in result.collector.errors if e.code == "SCH006"]
    assert len(errors) == 1 and errors[0].path == "site.yaml"
    assert "SCH006:site.yaml:schema.entity.image" in errors[0].hint


def test_check_dev_is_warning(scaffold):
    _entity(scaffold, "{{ site.base }}media/nope.jpg")
    result = pipeline.check(scaffold, env=None)
    assert not [e for e in result.collector.errors if e.code == "SCH006"]
    assert any(w.message.startswith("SCH006 ") for w in result.collector.warnings)


def test_check_existing_image_and_foreign_domain_clean(scaffold):
    _photo(scaffold)
    _entity(scaffold, "{{ site.base }}media/photo.jpg")
    result = pipeline.check(scaffold, env=BuildEnv.named("prod"))
    assert "SCH006" not in _codes(result)
    other = scaffold.parent / "other"
    other.mkdir()
    create(other, name="o", languages=["uk"])
    (other / "content" / "uk" / "index.md").write_text(HOME, encoding="utf-8")
    _entity(other, "https://cdn.example.org/x.jpg")
    assert "SCH006" not in _codes(pipeline.check(other, env=BuildEnv.named("prod")))


def test_build_missing_image_prod_fails(scaffold, tmp_path):
    _entity(scaffold, "{{ site.base }}media/nope.jpg")
    result = pipeline.run(scaffold, tmp_path / "dist", env=BuildEnv.named("prod"))
    assert [e for e in result.collector.errors if e.code == "SCH006"]


def test_build_master_from_markup_ships_whole(scaffold, tmp_path):
    _photo(scaffold)
    _entity(scaffold, "{{ site.base }}media/photo.jpg")
    dist = tmp_path / "dist"
    result = pipeline.run(scaffold, dist, env=BuildEnv.named("prod"))
    assert not [e for e in result.collector.errors if e.code == "SCH006"]
    assert (dist / "media" / "photo.jpg").is_file()
    assert (dist / "media" / "photo.jpg").read_bytes() == (scaffold / "media" / "photo.jpg").read_bytes()


def test_image_object_url_and_primary_image_checked(scaffold):
    path = scaffold / "site.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\nschema:\n  entity:\n    "@type": Organization\n    name: Demo\n'
        '    logo:\n      "@type": ImageObject\n      url: "/media/logo-missing.png"\n',
        encoding="utf-8",
    )
    result = pipeline.check(scaffold, env=BuildEnv.named("prod"))
    keys = [e.hint for e in result.collector.errors if e.code == "SCH006"]
    assert keys and "schema.entity.logo.url" in keys[0]


def test_schema_media_collects_masters(scaffold):
    _photo(scaffold)
    _entity(scaffold, "{{ site.base }}media/photo.jpg")
    result = pipeline.check(scaffold, env=None)
    assert "media/photo.jpg" in media.raw_references(result.site, result.config)
