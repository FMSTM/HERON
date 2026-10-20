"""Подпись движка: meta generator и комментарий — при сборке, отключаются build.generator."""

from pathlib import Path

import yaml

from heron.core import build as pipeline
from heron.core.render.signature import COMMENT, META, sign
from heron.scaffold import create


def test_sign_places_comment_after_doctype_and_meta_in_head():
    html = sign("<!doctype html>\n<html><head><title>x</title></head><body></body></html>")
    assert html.startswith("<!doctype html>\n" + COMMENT)
    assert '<head>\n<meta name="generator" content="HERON">' in html
    assert sign(html) == html  # второй раз ничего не добавляет


def test_theme_generator_is_kept():
    html = sign('<html><head><meta name="generator" content="Mine"></head></html>')
    assert META not in html and 'content="Mine"' in html


def _site(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en", "ru"], fish=True)
    return root


def test_every_page_is_signed_and_nothing_is_written_to_the_site(tmp_path: Path):
    root = _site(tmp_path)
    result = pipeline.run(root)
    assert not result.failed
    pages = list((root / "dist").rglob("*.html"))
    assert pages and all(META in p.read_text(encoding="utf-8") for p in pages)
    assert all("Built with HERON" in p.read_text(encoding="utf-8") for p in pages)
    for path in [root / "site.yaml", *(root / "content").rglob("*.md")]:
        assert "generator" not in path.read_text(encoding="utf-8")


def test_generator_can_be_switched_off(tmp_path: Path):
    root = _site(tmp_path)
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data["build"]["generator"] = False
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    pipeline.run(root)
    html = (root / "dist" / "index.html").read_text(encoding="utf-8")
    assert META not in html and "Built with HERON" not in html
