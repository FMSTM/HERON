"""Резолв связей: семьи, переводы, крошки, объявленные ссылки, меню."""

from heron.core import links, tree
from tests import sites

CATALOG = {
    "uk/index.md": sites.page("Головна"),
    "uk/poslugi/_index.md": sites.page("Послуги", type="category", children_type="procedure"),
    "uk/poslugi/mikro.md": sites.page("Мікро", order=2, treats=["hryzha"]),
    "uk/poslugi/spondylodez.md": sites.page("Спондилодез", order=1),
    "uk/likuvannya/_index.md": sites.page("Лікування", type="category", children_type="condition"),
    "uk/likuvannya/hryzha.md": sites.page("Грижа"),
}

LINKS = {"links": [{"field": "treats", "type": "condition", "back": "procedures_for"}]}


def resolved(tmp_path, files, theme_over=None, **over):
    content = sites.build(tmp_path, files)
    config = sites.config(**over)
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(**(theme_over or {})), collector)
    return site, collector


def test_children_collected_and_sorted_by_order(tmp_path):
    site, _ = resolved(tmp_path, CATALOG)
    catalog = site.by_url["/poslugi/"]
    assert [c.h1 for c in catalog.children] == ["Спондилодез", "Мікро"]


def test_parent_is_the_folder_page(tmp_path):
    site, _ = resolved(tmp_path, CATALOG)
    assert site.by_url["/poslugi/mikro/"].parent is site.by_url["/poslugi/"]


def test_breadcrumbs_start_at_home(tmp_path):
    site, _ = resolved(tmp_path, CATALOG)
    crumbs = site.by_url["/poslugi/mikro/"].breadcrumbs
    assert [c.url for c in crumbs] == ["/", "/poslugi/"]


def test_home_has_no_breadcrumbs(tmp_path):
    site, _ = resolved(tmp_path, CATALOG)
    assert site.by_url["/"].breadcrumbs == []


def test_translations_match_by_path(tmp_path):
    files = {
        "uk/poslugi/mikro.md": sites.page("Мікро"),
        "ru/poslugi/mikro.md": sites.page("Микро"),
    }
    site, _ = resolved(tmp_path, files)
    page = site.by_url["/poslugi/mikro/"]
    assert page.translations["ru"].url == "/ru/poslugi/mikro/"
    assert page.translations["ru"].translations["uk"] is page


def test_missing_translation_is_simply_absent(tmp_path):
    site, _ = resolved(tmp_path, {"uk/bio.md": sites.page("Біо")})
    assert site.by_url["/bio/"].translations == {}


def test_declared_link_resolves_and_builds_backlink(tmp_path):
    site, collector = resolved(tmp_path, CATALOG, theme_over=LINKS)
    assert not collector.failed
    mikro = site.by_url["/poslugi/mikro/"]
    hryzha = site.by_url["/likuvannya/hryzha/"]
    assert [p.url for p in mikro.related["treats"]] == ["/likuvannya/hryzha/"]
    assert [p.url for p in hryzha.related["procedures_for"]] == ["/poslugi/mikro/"]


def test_link_into_nowhere_is_e006(tmp_path):
    files = dict(CATALOG)
    files["uk/poslugi/mikro.md"] = sites.page("Мікро", treats=["нет-такой"])
    _, collector = resolved(tmp_path, files, theme_over=LINKS)
    assert [e.code for e in collector.errors] == ["E006"]


def test_link_to_wrong_type_is_e006(tmp_path):
    files = dict(CATALOG)
    files["uk/poslugi/mikro.md"] = sites.page("Мікро", treats=["spondylodez"])
    _, collector = resolved(tmp_path, files, theme_over=LINKS)
    assert collector.failed
    assert "condition" in str(collector.errors[0])


def test_link_field_unknown_to_core_is_ignored_without_declaration(tmp_path):
    files = dict(CATALOG)
    site, collector = resolved(tmp_path, files)
    assert not collector.failed
    assert site.by_url["/poslugi/mikro/"].related == {}


def test_required_count_is_a_warning_not_an_error(tmp_path):
    theme_over = {"links": [{"field": "treats", "type": "condition", "required": 2}]}
    site, collector = resolved(tmp_path, CATALOG, theme_over=theme_over)
    assert not collector.failed
    assert any("treats" in w.message for w in collector.warnings)


def test_nav_resolved_per_language(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/bio.md": sites.page("Біо"),
        "ru/index.md": sites.page("Главная"),
        "ru/bio.md": sites.page("Био"),
    }
    site, collector = resolved(tmp_path, files, nav={"main": ["bio"]})
    assert [p.url for p in site.nav["uk"]["main"]] == ["/bio/"]
    assert [p.url for p in site.nav["ru"]["main"]] == ["/ru/bio/"]
    assert not collector.failed


def test_nav_pointing_at_nothing_is_a_warning(tmp_path):
    _, collector = resolved(tmp_path, {"uk/index.md": sites.page()}, nav={"main": ["нет"]})
    assert not collector.failed
    assert any("меню" in w.message for w in collector.warnings)
