"""Разметка <picture>: srcset, размеры, ленивая загрузка."""

import pytest

from heron.contracts.theme import ImagesSpec
from heron.core import media, tree
from heron.core.errors import Collector
from heron.core.render import env as envmod
from tests import sites
from tests.test_media import master

FILES = {"uk/index.md": sites.page("Головна", image="img/a.png", image_alt="Опис")}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Нарезать картинки один раз на весь модуль.

    Кодирование AVIF — единственное, что здесь долго. Четыре теста читают
    один и тот же результат, пересобирать его каждому незачем.
    """
    root = tmp_path_factory.mktemp("picture")
    content = sites.build(root, FILES)
    master(root / "img" / "a.png", size=1000)
    config = sites.config()
    site, collector = tree.scan(content, config)
    spec = ImagesSpec(widths=[400, 800], ratios=["1:1", "16:9"], formats=["avif", "webp"])
    manifest = media.build(site, root, root / "dist", spec, collector)
    return manifest, collector


def test_picture_markup(built):
    manifest, collector = built
    render = envmod.picture(manifest, collector)
    html = str(
        render("img/a.png", ratio="16:9", alt="Портрет", sizes="(max-width: 600px) 100vw, 50vw")
    )
    assert '<source type="image/avif"' in html
    assert '<source type="image/webp"' in html
    assert "/img/a-16x9-400.webp 400w" in html
    assert 'alt="Портрет"' in html
    assert 'loading="lazy"' in html
    assert 'width="800"' in html and 'height="450"' in html


def test_first_screen_image_is_not_lazy(built):
    manifest, collector = built
    render = envmod.picture(manifest, collector)
    html = str(render("img/a.png", ratio="1:1", lazy=False))
    assert "loading=" not in html


def test_alt_is_escaped(built):
    manifest, collector = built
    render = envmod.picture(manifest, collector)
    html = str(render("img/a.png", alt='Лапки "та" <кут>'))
    assert "&lt;кут&gt;" in html and "<кут>" not in html


def test_unknown_ratio_warns_and_renders_nothing(built):
    manifest, collector = built
    render = envmod.picture(manifest, collector)
    assert str(render("img/a.png", ratio="3:2")) == ""
    assert any("3:2" in w.message for w in collector.warnings)


def test_missing_image_renders_nothing():
    collector = Collector()
    render = envmod.picture(media.Manifest(), collector)
    assert str(render("img/нет.png")) == ""
