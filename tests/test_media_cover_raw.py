"""raw_references: мастер обложки всегда едет в сборку целиком."""

from __future__ import annotations

from heron.core import media, tree
from tests import sites


def _raw(tmp_path, files, **config_over):
    content = sites.build(tmp_path, files)
    config = sites.config(**config_over)
    site, _ = tree.scan(content, config)
    return media.raw_references(site, config)


def _md(title: str, intro: str = "Вступление.", **fields) -> str:
    return sites.page(title, **fields).replace("Вступление.", intro, 1)


def test_frontmatter_image_is_raw(tmp_path):
    raw = _raw(tmp_path, {"uk/index.md": _md("Головна", image="media/bio/portrait.jpg")})
    assert "media/bio/portrait.jpg" in raw


def test_intro_cover_is_raw(tmp_path):
    raw = _raw(tmp_path, {"uk/index.md": _md("Головна", intro="Текст ![Підпис](media/intro.jpg) далі.")})
    assert "media/intro.jpg" in raw


def test_og_default_image_and_localized(tmp_path):
    raw = _raw(
        tmp_path,
        {"uk/index.md": _md("Головна")},
        seo={
            "og_default_image": "media/og.jpg",
            "i18n": {"og_default_image": {"ru": "media/og-ru.jpg"}},
        },
    )
    assert {"media/og.jpg", "media/og-ru.jpg"} <= raw


def test_external_image_is_not_raw(tmp_path):
    raw = _raw(tmp_path, {"uk/index.md": _md("Головна", image="https://cdn.example.com/x.jpg")})
    assert not any("example.com" in item for item in raw)
