"""Что вскрыл первый пилот на бете.

Каждый тест — случай, на котором агент сайта споткнулся: сообщение
отправляло не туда, движок молчал или делал не то.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from heron.contracts.site import SiteConfig, localize
from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.core.parser import blocks, markdown, sections
from heron.scaffold import create


@pytest.fixture
def site(tmp_path) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en", "ru"])
    return root


def edit_yaml(path: Path, change) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def ld(html: str) -> list[dict]:
    found = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    data = json.loads(found.group(1))
    return data.get("@graph", [data])


# --- языковые значения во всех блоках site.yaml ------------------------------------


def test_every_block_of_site_yaml_follows_the_page_language():
    data = {
        "contact": {"address": "Main st", "address_ru": "Главная ул.", "city_ru": "Город"},
        "people": [{"name": "Ann", "name_ru": "Анна"}],
    }
    ru = localize(data, "ru")
    en = localize(data, "en")
    assert ru["contact"]["address"] == "Главная ул."
    assert ru["contact"]["city"] == "Город"  # есть только языковой ключ
    assert ru["people"][0]["name"] == "Анна"
    assert en["contact"]["address"] == "Main st"
    assert "city" not in en["contact"]
    # ключи с хвостом остаются: тема, выбиравшая язык руками, не ломается
    assert ru["contact"]["address_ru"] == "Главная ул."


def test_template_sees_localized_blocks(site):
    edit_yaml(
        site / "site.yaml",
        lambda d: d.update(contact={"phone": "+0", "address": "Main st", "address_ru": "Главная"}),
    )
    footer = site / "theme" / "partials" / "footer.html"
    footer.write_text(
        footer.read_text(encoding="utf-8") + '<p class="addr">{{ site.contact.address }}</p>',
        encoding="utf-8",
    )
    result = pipeline.run(site)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert '<p class="addr">Main st</p>' in (site / "dist" / "index.html").read_text()
    assert '<p class="addr">Главная</p>' in (site / "dist" / "ru" / "index.html").read_text()


def test_config_for_lang_keeps_core_blocks():
    config = SiteConfig.model_validate(
        {
            "heron": ">=0.1",
            "site": {
                "domain": "example.com",
                "theme": "main",
                "default_lang": "en",
                "languages": ["en", "ru"],
                "name": "Daybreak",
                "name_ru": "Рассвет",
            },
            "organization": {"name": "Org", "name_ru": "Орг"},
        }
    )
    ru = config.for_lang("ru")
    assert ru.site.name == "Рассвет"
    assert ru.extras["organization"]["name"] == "Орг"
    assert config.extras["organization"]["name"] == "Org"


# --- разметка ----------------------------------------------------------------------


def test_website_node_is_named_after_the_site(site):
    edit_yaml(site / "site.yaml", lambda d: d["site"].update(name="Daybreak", name_ru="Рассвет"))
    edit_yaml(
        site / "theme" / "theme.yaml", lambda d: d["types"]["home"].update(jsonld=["WebSite"])
    )
    result = pipeline.run(site)
    assert not result.failed, [str(e) for e in result.collector.errors]

    def website(path: Path) -> dict:
        return next(n for n in ld(path.read_text()) if n.get("@type") == "WebSite")

    assert website(site / "dist" / "index.html")["name"] == "Daybreak"
    assert website(site / "dist" / "ru" / "index.html")["name"] == "Рассвет"


# --- тема ----------------------------------------------------------------------------


def test_extends_without_templates_prefix_is_explained(site):
    (site / "theme" / "templates" / "landing.html").write_text(
        '{% extends "page.html" %}', encoding="utf-8"
    )
    index = site / "content" / "en" / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace("order: 0", "order: 0\ntype: landing"),
        encoding="utf-8",
    )
    edit_yaml(site / "theme" / "theme.yaml", lambda d: d["types"].update(landing={"uses": ["*"]}))
    with pytest.raises(HeronError) as error:
        result = pipeline.run(site)
        raise result.collector.errors[0]
    assert error.value.code == "E008"
    assert "templates/page.html" in error.value.hint


def test_own_fields_in_theme_fields_get_their_own_message(site):
    edit_yaml(site / "theme" / "theme.yaml", lambda d: d.update(fields=["nav_title", "topic"]))
    with pytest.raises(HeronError) as error:
        pipeline.run(site)
    assert error.value.code == "E023"
    assert "page.meta.get" in error.value.hint
    assert "topic" in error.value.message


def test_meta_get_reads_own_fields_without_failing(site):
    page = site / "theme" / "templates" / "page.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "<h1>{{ page.h1 }}</h1>",
            "<h1>{{ page.h1 }}</h1><i>{{ page.meta.get('topic', 'none') }}</i>",
        ),
        encoding="utf-8",
    )
    (site / "content" / "en" / "a.md").write_text(
        "---\ntitle: A\nh1: A\ndescription: D\ntopic: roofs\n---\n\nText.\n", encoding="utf-8"
    )
    (site / "content" / "en" / "b.md").write_text(
        "---\ntitle: B\nh1: B\ndescription: D\n---\n\nText.\n", encoding="utf-8"
    )
    result = pipeline.run(site)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert "<i>roofs</i>" in (site / "dist" / "a" / "index.html").read_text()
    assert "<i>none</i>" in (site / "dist" / "b" / "index.html").read_text()


# --- контент -------------------------------------------------------------------------


def test_type_404_without_quotes_is_still_the_404_page(site):
    notfound = site / "content" / "en" / "404.md"
    notfound.write_text(
        notfound.read_text(encoding="utf-8").replace("order: 999", "order: 999\ntype: 404"),
        encoding="utf-8",
    )
    result = pipeline.run(site)
    assert not result.failed
    assert not [w for w in result.collector.warnings if "404.md" in w.message]
    page = result.site.page("404", "en")
    assert page is not None and page.type == "404"


def test_facts_may_have_a_lead_paragraph():
    md = markdown.make()
    body = (
        "## Briefly {#quick .facts}\n\nThe format in short:\n\nFormat | in person\nTerm | a month\n"
    )
    _, found = sections.split(md, body, "x.md", offset=0)
    warnings = blocks.apply(md, found)
    section = found["quick"]
    assert section.kind == "facts"
    assert [row["key"] for row in section.data] == ["Format", "Term"]
    assert "The format in short" in section.lead
    assert not warnings


def test_site_icons_in_static_are_not_content(site):
    static = site / "static"
    for name in ("favicon.svg", "favicon-32.png", "apple-touch-icon.png", "photo.jpg"):
        (static / name).write_bytes(b"\x89PNG")
    result = pipeline.run(site)
    assert result.report.static_media == ["static/photo.jpg"]


def test_manual_dates_over_git_are_one_line_in_the_report(site):
    edit_yaml(site / "site.yaml", lambda d: d["build"].update(updated_from="file"))
    index = site / "content" / "en" / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace("order: 0", "order: 0\nupdated: 2026-01-01"),
        encoding="utf-8",
    )
    result = pipeline.run(site)
    assert result.report.manual_dates == (1, len(result.site.pages), "file")
    assert "перекрывает updated_from: file" in result.report.render()
    # отчёт, а не предупреждение: --strict из-за этого не падает
    assert not [w for w in result.collector.warnings if "updated" in w.message]
