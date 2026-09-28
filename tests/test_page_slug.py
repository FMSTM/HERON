"""Слаг страницы: адрес отдельно от имени файла.

Имя файла — идентификатор страницы, по нему движок сводит переводы и
находит страницу в меню. Слаг — то, что видит посетитель в адресной
строке. Пока это одно и то же, переименование адреса рвёт связи между
языками; поэтому разделено.
"""

from heron.core import links, report, tree
from tests import sites


def scan(tmp_path, files, **over):
    content = sites.build(tmp_path, files)
    config = sites.config(**over)
    site, collector = tree.scan(content, config)
    return site, config, collector


def test_slug_changes_url_not_key(tmp_path):
    site, _, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/bio.md": sites.page("Біографія", slug="pro-mene"),
        },
    )
    assert not collector.failed
    page = site.by_url["/pro-mene/"]
    assert page.source == "uk/bio.md"
    assert page.key == "bio"
    assert "/bio/" not in site.by_url


def test_translations_hold_when_languages_have_different_slugs(tmp_path):
    site, config, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/bio.md": sites.page("Біографія", slug="pro-mene"),
            "ru/index.md": sites.page("Главная"),
            "ru/bio.md": sites.page("Биография", slug="obo-mne"),
        },
    )
    links.resolve(site, config, sites.theme(), collector)
    uk = site.by_url["/pro-mene/"]
    ru = site.by_url["/ru/obo-mne/"]
    assert uk.translations["ru"] is ru
    assert ru.translations["uk"] is uk


def test_section_slug_carries_children(tmp_path):
    site, _, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/services/_index.md": sites.page("Послуги", type="category", slug="poslugy"),
            "uk/services/consulting.md": sites.page("Консультація"),
            "uk/services/deep/_index.md": sites.page("Вглиб", type="category", slug="vglyb"),
            "uk/services/deep/one.md": sites.page("Одна"),
        },
    )
    assert not collector.failed
    assert sorted(site.by_url) == [
        "/",
        "/poslugy/",
        "/poslugy/consulting/",
        "/poslugy/vglyb/",
        "/poslugy/vglyb/one/",
    ]
    assert site.by_url["/poslugy/vglyb/one/"].key == "services/deep/one"


def test_nav_and_menu_still_addressed_by_file_key(tmp_path):
    site, config, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/services/_index.md": sites.page("Послуги", type="category", slug="poslugy"),
            "ru/index.md": sites.page("Главная"),
            "ru/services/_index.md": sites.page("Услуги", type="category", slug="uslugi"),
        },
        nav={"main": ["services"]},
    )
    links.resolve(site, config, sites.theme(), collector)
    assert [p.url for p in site.nav["uk"]["main"]] == ["/poslugy/"]
    assert [p.url for p in site.nav["ru"]["main"]] == ["/ru/uslugi/"]


def test_two_slugs_into_one_address_is_an_error(tmp_path):
    _, _, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/bio.md": sites.page("Біографія", slug="pro-mene"),
            "uk/about.md": sites.page("Про", slug="pro-mene"),
        },
    )
    assert [e.code for e in collector.errors] == ["E004"]


def test_slug_colliding_with_a_file_name_is_an_error(tmp_path):
    _, _, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/bio.md": sites.page("Біографія"),
            "uk/about.md": sites.page("Про", slug="bio"),
        },
    )
    assert [e.code for e in collector.errors] == ["E004"]


def test_bad_slug_is_an_error_not_a_silent_fallback(tmp_path):
    _, _, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/bio.md": sites.page("Біографія", slug="Про Мене"),
        },
    )
    assert [e.code for e in collector.errors] == ["E002"]


def test_site_without_slugs_is_unchanged(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/services/_index.md": sites.page("Послуги", type="category"),
        "uk/services/consulting.md": sites.page("Консультація"),
    }
    site, _, collector = scan(tmp_path, files)
    assert not collector.failed
    assert sorted(site.by_url) == ["/", "/services/", "/services/consulting/"]
    assert [p.key for p in site.pages] == ["", "services", "services/consulting"]


def test_broken_internal_link_reports_line_and_href(tmp_path):
    site, config, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/services/_index.md": sites.page("Послуги", type="category", slug="poslugy"),
            "uk/bio.md": (
                "---\ntitle: Біографія\nh1: Біографія\ndescription: Опис\n---\n\n"
                "## Що це {#what}\n\n"
                "[розділ](/services/) і [цілий](/poslugy/) і [якір](#what)\n"
            ),
        },
    )
    links.resolve(site, config, sites.theme(), collector)
    broken = [w for w in collector.warnings if w.kind == "ссылки"]
    assert [(w.path, w.line, w.message) for w in broken] == [
        ("uk/bio.md", 9, "ссылка /services/ никуда не ведёт")
    ]
    result = report.build(site, config, sites.theme())
    assert result.broken_links == [("uk/bio.md", 9, "/services/")]


def test_media_and_anchors_are_not_links_to_pages(tmp_path):
    site, config, collector = scan(
        tmp_path,
        {
            "uk/index.md": (
                "---\ntitle: Головна\nh1: Головна\ndescription: Опис\n---\n\n"
                "## Що це {#what}\n\n"
                "[файл](/media/doc.pdf) [зовні](https://example.org/x/) [якір](#what)\n"
            ),
        },
    )
    links.resolve(site, config, sites.theme(), collector)
    assert [w for w in collector.warnings if w.kind == "ссылки"] == []
