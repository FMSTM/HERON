"""Пометка «перевод не готов» (`translation: pending`, ST7): черновая сборка с плашкой, боевая без.

Спецификация: docs/ru/spec/20-data-contract.md §4.2, «Перевод не готов».
"""

from __future__ import annotations

import json
import re

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.scaffold import create


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=["ru", "en", "de"], notes="ru", demo=True)
    return root


def mark(path, value="pending"):
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("published: true", f"translation: {value}", 1), encoding="utf-8")


def test_production_does_not_publish_a_pending_language(site, tmp_path):
    mark(site / "content" / "de" / "themes.md")
    built = pipeline.run(site, dist=tmp_path / "prod", env=BuildEnv.named("prod"))
    assert not built.collector.errors, built.collector.errors
    dist = tmp_path / "prod"
    assert not (dist / "de" / "themes").exists()
    assert (dist / "en" / "themes" / "index.html").is_file()
    assert "/de/themes/" not in "".join(p.read_text() for p in dist.glob("sitemap*.xml"))
    html = (dist / "themes" / "index.html").read_text()
    assert 'hreflang="en"' in html and 'hreflang="de"' not in html
    assert 'href="/de/themes/"' not in (dist / "de" / "index.html").read_text()  # меню de
    assert ("de", "de/themes.md", False) in built.report.pending
    assert "de - de/themes.md (не опубликована)" in built.report.render("ru")
    assert "de - de/themes.md (not published)" in built.report.render("en")
    held = [w for w in built.collector.warnings if w.path == "de/themes.md"]
    assert held and held[0].kind == "переводы"
    # пункт меню без версии de - не отдельное предупреждение: о странице уже сказано
    assert not any(
        "themes" in str(w.message) and w.path == "site.yaml" for w in built.collector.warnings
    )


def test_strict_production_build_fails_on_pending(site, tmp_path):
    mark(site / "content" / "de" / "themes.md")
    result = CliRunner().invoke(
        main, ["build", str(site), "--env", "prod", "--strict", "--out", str(tmp_path / "o")]
    )
    assert result.exit_code == 1
    assert "translation: pending" in result.output


def test_draft_build_shows_the_page_with_a_banner(site, tmp_path):
    mark(site / "content" / "de" / "themes.md")
    built = pipeline.run(site, dist=tmp_path / "dev", env=BuildEnv.named("dev"))
    assert not built.collector.errors
    page = (tmp_path / "dev" / "de" / "themes" / "index.html").read_text()
    assert re.search(r'<body[^>]*><div class="heron-pending" role="status"', page)
    assert "content/de/themes.md" in page and "translation: pending" in page
    assert "heron-pending" not in (tmp_path / "dev" / "themes" / "index.html").read_text()
    assert ("de", "de/themes.md", True) in built.report.pending
    assert "/de/themes/" in (tmp_path / "dev" / "sitemap-de.xml").read_text()


def test_removing_the_mark_publishes_the_page(site, tmp_path):
    path = site / "content" / "de" / "themes.md"
    mark(path)
    pipeline.run(site, dist=tmp_path / "a", env=BuildEnv.named("prod"))
    assert not (tmp_path / "a" / "de" / "themes").exists()
    path.write_text(path.read_text().replace("translation: pending", "published: true"))
    pipeline.run(site, dist=tmp_path / "b", env=BuildEnv.named("prod"))
    assert (tmp_path / "b" / "de" / "themes" / "index.html").is_file()


def test_check_json_lists_pending_by_environment(site):
    mark(site / "content" / "de" / "themes.md")
    dev = json.loads(CliRunner().invoke(main, ["check", str(site), "--json"]).output)
    assert {"lang": "de", "path": "de/themes.md", "published": True} in dev["pending"]
    prod = json.loads(
        CliRunner().invoke(main, ["check", str(site), "--json", "--env", "prod"]).output
    )
    assert {"lang": "de", "path": "de/themes.md", "published": False} in prod["pending"]


def test_bad_value_is_e002(site):
    mark(site / "content" / "en" / "themes.md", "maybe")
    result = pipeline.check(site)
    assert any(e.code == "E002" and "pending" in str(e.message) for e in result.collector.errors)


def test_translation_is_a_frontmatter_field_with_one_value():
    from pydantic import ValidationError

    from heron.contracts.frontmatter import PageMeta
    from heron.contracts.schemas import frontmatter_schema

    base = {"title": "T", "h1": "H", "description": "D"}
    assert PageMeta(**base, translation="pending").pending
    assert not PageMeta(**base).pending
    with pytest.raises(ValidationError):
        PageMeta(**base, translation="done")
    prop = frontmatter_schema("en")["properties"]["translation"]
    assert {"enum": ["pending"]} in prop["anyOf"]


def test_describe_and_edit_model_know_the_field(site):
    from heron import edit
    from heron.core import describe

    theme, config = describe.load(site)
    contract = describe.contract(theme, config, "en")
    item = next(f for f in contract["service"]["page"] if f["name"] == "translation")
    assert item["group"] == "publishing" and item["values"] == ["pending"] and item["hint"]
    path = site / "content" / "de" / "themes.md"
    page = edit.set(edit.load(path, contract, rel="content/de/themes.md"), "translation", "pending")
    # пометка встаёт на место заготовки в группе 7 SEO-блока, с её подсказкой
    assert re.search(r"\ntranslation: pending +# pending - ", page.text)
    back = edit.set(page, "translation", None)
    assert back.text == path.read_text(encoding="utf-8")
