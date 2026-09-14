"""Отчёт check: заполненность, переводы, битые ссылки, сироты, долги."""

import pytest

from heron.core import links, report, tree
from tests import sites

FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/services/_index.md": sites.page("Послуги", type="category", children_type="service"),
    "uk/services/consulting.md": (
        "---\ntitle: Консультація\nh1: Консультація\ndescription: Опис\n---\n\n"
        "## Що це {#what}\n\nТекст.\n\n## Зайва {#leftover}\n\nТекст.\n"
    ),
    "ru/index.md": sites.page("Главная"),
}

THEME = {"types": {"service": {"uses": ["what", "contra", "faq"]}}}


@pytest.fixture
def built(tmp_path):
    content = sites.build(tmp_path, FILES)
    config = sites.config()
    site, collector = tree.scan(content, config)
    theme = sites.theme(**THEME)
    links.resolve(site, config, theme, collector)
    return site, config, theme, collector


def test_counts_by_language_and_type(built):
    site, config, theme, _ = built
    result = report.build(site, config, theme)
    assert result.pages_by_lang["uk"] == 3
    assert result.pages_by_type["service"] == 1


def test_missing_sections_become_debts(built):
    site, config, theme, _ = built
    result = report.build(site, config, theme)
    assert set(result.missing_sections) == {"contra", "faq"}
    assert "uk/services/consulting.md" in result.missing_sections["contra"]


def test_section_theme_does_not_use_is_reported(built):
    site, config, theme, _ = built
    result = report.build(site, config, theme)
    assert ("uk/services/consulting.md", "leftover") in result.unused_sections


def test_untranslated_pages_listed(built):
    site, config, theme, _ = built
    result = report.build(site, config, theme)
    assert "ru" in result.untranslated
    assert "services/consulting" in result.untranslated["ru"]


def test_broken_internal_link(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/a.md": (
            "---\ntitle: А\nh1: А\ndescription: Опис\n---\n\n"
            "## Текст {#what}\n\n[кудись](/нет-такой/)\n"
        ),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    result = report.build(site, config, sites.theme())
    assert result.broken_links == [("uk/a.md", "/нет-такой/")]


def test_asset_links_are_not_broken_pages(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/a.md": (
            "---\ntitle: А\nh1: А\ndescription: Опис\n---\n\n"
            "## Текст {#what}\n\n[файл](/static/doc.pdf)\n"
        ),
    }
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    links.resolve(site, sites.config(), sites.theme(), collector)
    result = report.build(site, sites.config(), sites.theme())
    assert result.broken_links == []


def test_unused_theme_modules(tmp_path):
    content = sites.build(tmp_path, FILES)
    theme_dir = sites.theme_dir(tmp_path)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    result = report.build(site, config, sites.theme(), theme_dir=theme_dir)
    assert "facts" not in result.unused_modules  # шаблон его зовёт
    assert result.unused_modules == []


def test_render_is_readable(built):
    site, config, theme, _ = built
    text = report.build(site, config, theme).render()
    assert "Страниц —" in text
    assert "Не заполнено:" in text
    assert "contra" in text


def test_summary_lists_errors_and_warnings(built):
    _, _, _, collector = built
    collector.error("E001", "битый YAML", path="a.md", line=2)
    collector.warn("title длиннее 60 знаков", path="b.md")
    text = report.summary(collector)
    assert "E001 a.md:2" in text
    assert "b.md: title длиннее" in text
