"""Название сайта, суффикс title и картинка для соцсетей по языкам.

Спецификация: docs/spec/20-data-contract.md, раздел 5, «Значения по языкам».
"""

from __future__ import annotations

import io

import pytest
import yaml
from PIL import Image

from heron.contracts.site import SiteConfig
from heron.core import build as pipeline
from heron.scaffold import create


def config(**site_over):
    data = {
        "heron": ">=0.1",
        "site": {
            "domain": "example.com",
            "theme": "t",
            "default_lang": "uk",
            "languages": ["uk", "ru"],
            "name": "Світанок",
            "name_ru": "Рассвет",
        },
        "seo": {"title_suffix": " — Світанок", "title_suffix_ru": " — Рассвет"},
    }
    data["site"].update(site_over)
    return SiteConfig.model_validate(data)


def test_suffix_key_is_stronger_than_plain():
    cfg = config()
    assert cfg.for_lang("ru").site.name == "Рассвет"
    assert cfg.for_lang("ru").seo.title_suffix == " — Рассвет"
    assert cfg.for_lang("uk").site.name == "Світанок"
    # исходный конфиг не меняется
    assert cfg.site.name == "Світанок"


def test_language_without_own_value_gets_plain_one():
    cfg = config(languages=["uk", "ru", "en"])
    assert cfg.for_lang("en").site.name == "Світанок"


def test_suffix_for_undeclared_language_fails():
    with pytest.raises(ValueError, match="name_de"):
        config(name_de="Gebiet")


def _png(path):
    buf = io.BytesIO()
    Image.new("RGB", (1200, 630), (10, 20, 30)).save(buf, "PNG")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())


def test_title_and_og_image_per_language(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk", "ru"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["site"].update(name="Світанок", name_ru="Рассвет")
    conf["seo"].update(
        title_suffix=" — Світанок",
        title_suffix_ru=" — Рассвет",
        og_default_image="media/og/uk.png",
        og_default_image_ru="media/og/ru.png",
    )
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), encoding="utf-8")
    _png(root / "media" / "og" / "uk.png")
    _png(root / "media" / "og" / "ru.png")
    for lang, h1 in (("uk", "Головна"), ("ru", "Главная")):
        (root / "content" / lang / "index.md").write_text(
            f"---\ntitle: {h1} сайту\nh1: {h1}\ndescription: О\n---\n\nТекст.\n",
            encoding="utf-8",
        )
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    uk = (root / "dist" / "index.html").read_text(encoding="utf-8")
    ru = (root / "dist" / "ru" / "index.html").read_text(encoding="utf-8")
    assert "<title>Головна сайту — Світанок</title>" in uk
    assert "<title>Главная сайту — Рассвет</title>" in ru
    assert "og/uk" in uk and "og/ru" not in uk
    assert "og/ru" in ru and "og/uk" not in ru
    # шапка тоже на языке страницы
    assert ">Рассвет<" in ru
    # обе картинки доехали до сборки
    assert list((root / "dist").rglob("uk*.png")) and list((root / "dist").rglob("ru*.png"))
