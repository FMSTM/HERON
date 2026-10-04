"""Слаг страницы: адрес отдельно от имени файла.

Имя файла — идентификатор страницы, по нему движок сводит переводы и
находит страницу в меню. Слаг — то, что видит посетитель в адресной
строке. Пока это одно и то же, переименование адреса рвёт связи между
языками; поэтому разделено.
"""

from heron.core import links, report, tree
from heron.modules import sitemap
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
            "uk/services/_index.md": sites.page("Послуги", type="category", slug="perelik"),
            "uk/services/design.md": sites.page("Дизайн"),
            "uk/services/deep/_index.md": sites.page("Вглиб", type="category", slug="vglyb"),
            "uk/services/deep/one.md": sites.page("Одна"),
        },
    )
    assert not collector.failed
    assert sorted(site.by_url) == [
        "/",
        "/perelik/",
        "/perelik/design/",
        "/perelik/vglyb/",
        "/perelik/vglyb/one/",
    ]
    assert site.by_url["/perelik/vglyb/one/"].key == "services/deep/one"


def test_nav_and_menu_still_addressed_by_file_key(tmp_path):
    site, config, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/services/_index.md": sites.page("Послуги", type="category", slug="perelik"),
            "ru/index.md": sites.page("Главная"),
            "ru/services/_index.md": sites.page("Каталог", type="category", slug="katalog"),
        },
        nav={"main": ["services"]},
    )
    links.resolve(site, config, sites.theme(), collector)
    assert [p.url for p in site.nav["uk"]["main"]] == ["/perelik/"]
    assert [p.url for p in site.nav["ru"]["main"]] == ["/ru/katalog/"]


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
        "uk/services/design.md": sites.page("Дизайн"),
    }
    site, _, collector = scan(tmp_path, files)
    assert not collector.failed
    assert sorted(site.by_url) == ["/", "/services/", "/services/design/"]
    assert [p.key for p in site.pages] == ["", "services", "services/design"]


def test_broken_internal_link_reports_line_and_href(tmp_path):
    site, config, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/services/_index.md": sites.page("Послуги", type="category", slug="perelik"),
            "uk/bio.md": (
                "---\ntitle: Біографія\nh1: Біографія\ndescription: Опис\n---\n\n"
                "## Що це {#what}\n\n"
                "[нікуди](/nowhere/) і [ключ](/services/) і [цілий](/perelik/) і [якір](#what)\n"
            ),
        },
    )
    links.resolve(site, config, sites.theme(), collector)
    broken = [w for w in collector.warnings if w.kind == "ссылки"]
    assert [(w.path, w.line, w.message) for w in broken] == [
        ("uk/bio.md", 9, "ссылка /nowhere/ никуда не ведёт")
    ]
    result = report.build(site, config, sites.theme())
    assert result.broken_links == [("uk/bio.md", 9, "/nowhere/")]


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


LINKS = {"links": [{"field": "topics", "type": "topic", "back": "services"}]}


def test_relations_hold_when_the_address_is_renamed(tmp_path):
    site, config, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/topics/_index.md": sites.page("Теми", type="category", slug="temy"),
            "uk/topics/leak.md": sites.page("Протікання", type="topic", slug="protikannya"),
            "uk/services/_index.md": sites.page("Роботи", type="category", slug="roboty"),
            "uk/services/patch.md": sites.page(
                "Латка", type="service", slug="latka", topics=["leak"]
            ),
        },
    )
    links.resolve(site, config, sites.theme(**LINKS), collector)
    assert [e.code for e in collector.errors] == []
    service = site.by_url["/roboty/latka/"]
    assert [p.url for p in service.related["topics"]] == ["/temy/protikannya/"]
    topic = site.by_url["/temy/protikannya/"]
    assert [p.url for p in topic.related["services"]] == ["/roboty/latka/"]


def test_relation_points_at_the_page_of_its_own_language(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/leak.md": sites.page("Протікання", type="topic", slug="protikannya"),
        "uk/patch.md": sites.page("Латка", type="service", topics=["leak"]),
        "ru/index.md": sites.page("Главная"),
        "ru/leak.md": sites.page("Протечка", type="topic", slug="protechka"),
        "ru/patch.md": sites.page("Заплатка", type="service", topics=["leak"]),
    }
    site, config, collector = scan(tmp_path, files)
    links.resolve(site, config, sites.theme(**LINKS), collector)
    assert [e.code for e in collector.errors] == []
    assert [p.url for p in site.by_url["/patch/"].related["topics"]] == ["/protikannya/"]
    assert [p.url for p in site.by_url["/ru/patch/"].related["topics"]] == ["/ru/protechka/"]


def test_same_file_name_in_two_folders_is_ambiguous(tmp_path):
    site, config, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/a/leak.md": sites.page("Протікання А", type="topic"),
            "uk/b/leak.md": sites.page("Протікання Б", type="topic"),
            "uk/patch.md": sites.page("Латка", type="service", topics=["leak"]),
        },
    )
    links.resolve(site, config, sites.theme(**LINKS), collector)
    assert [e.code for e in collector.errors] == ["E006"]
    assert "неоднозначно" in collector.errors[0].message


def test_link_follows_the_page_into_its_own_language(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/care/_index.md": sites.page("Догляд", type="category", slug="doglyad"),
        "uk/care/roof.md": sites.page("Дах", slug="dakh"),
        "uk/about.md": (
            "---\ntitle: Про\nh1: Про\ndescription: Опис\n---\n\n"
            "## Що це {#what}\n\n[дах](/doglyad/dakh/)\n"
        ),
        "ru/index.md": sites.page("Главная"),
        "ru/care/_index.md": sites.page("Уход", type="category", slug="ukhod"),
        "ru/care/roof.md": sites.page("Крыша", slug="krysha"),
        "ru/about.md": (
            "---\ntitle: Про\nh1: Про\ndescription: Опис\n---\n\n"
            "## Что это {#what}\n\n[крыша](/doglyad/dakh/)\n"
        ),
    }
    site, config, collector = scan(tmp_path, files)
    links.resolve(site, config, sites.theme(), collector)
    assert [w for w in collector.warnings if w.kind == "ссылки"] == []
    assert 'href="/doglyad/dakh/"' in site.by_url["/about/"].section("what").html
    assert 'href="/ru/ukhod/krysha/"' in site.by_url["/ru/about/"].section("what").html


def test_link_already_in_its_own_language_is_left_alone(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/roof.md": sites.page("Дах", slug="dakh"),
        "ru/index.md": sites.page("Главная"),
        "ru/roof.md": sites.page("Крыша", slug="krysha"),
        "ru/about.md": (
            "---\ntitle: Про\nh1: Про\ndescription: Опис\n---\n\n"
            "## Что это {#what}\n\n[крыша](/ru/krysha/)\n"
        ),
    }
    site, config, collector = scan(tmp_path, files)
    links.resolve(site, config, sites.theme(), collector)
    assert [w for w in collector.warnings if w.kind == "ссылки"] == []
    assert 'href="/ru/krysha/"' in site.by_url["/ru/about/"].section("what").html


def test_untranslated_target_still_says_so(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/roof.md": sites.page("Дах", slug="dakh"),
        "ru/index.md": sites.page("Главная"),
        "ru/about.md": (
            "---\ntitle: Про\nh1: Про\ndescription: Опис\n---\n\n"
            "## Что это {#what}\n\n[крыша](/dakh/)\n"
        ),
    }
    site, config, collector = scan(tmp_path, files)
    links.resolve(site, config, sites.theme(), collector)
    said = [w for w in collector.warnings if w.kind == "ссылки"]
    assert len(said) == 1
    assert "на 'ru' этой страницы нет" in said[0].message
    assert 'href="/dakh/"' in site.by_url["/ru/about/"].section("what").html


def test_anchor_and_query_survive_localization(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/roof.md": sites.page("Дах", slug="dakh"),
        "ru/index.md": sites.page("Главная"),
        "ru/roof.md": sites.page("Крыша", slug="krysha"),
        "ru/about.md": (
            "---\ntitle: Про\nh1: Про\ndescription: Опис\n---\n\n"
            "## Что это {#what}\n\n[крыша](/dakh/#tsena)\n"
        ),
    }
    site, config, collector = scan(tmp_path, files)
    links.resolve(site, config, sites.theme(), collector)
    assert 'href="/ru/krysha/#tsena"' in site.by_url["/ru/about/"].section("what").html


NESTED = {
    "uk/index.md": sites.page("Головна"),
    "uk/care/_index.md": sites.page("Догляд", type="category", slug="doglyad"),
    "uk/care/roof/_index.md": sites.page("Дах", type="category", slug="dakh"),
    "uk/care/roof/tiles.md": sites.page("Черепиця", slug="cherepytsya"),
    "ru/index.md": sites.page("Главная"),
    "ru/care/_index.md": sites.page("Уход", type="category", slug="ukhod"),
    "ru/care/roof/_index.md": sites.page("Крыша", type="category", slug="krysha"),
    "ru/care/roof/tiles.md": sites.page("Черепица", slug="cherepitsa"),
}


def test_family_and_breadcrumbs_survive_slugs_at_every_level(tmp_path):
    site, config, collector = scan(tmp_path, NESTED)
    links.resolve(site, config, sites.theme(), collector)
    assert not collector.failed
    page = site.by_url["/ru/ukhod/krysha/cherepitsa/"]
    assert page.parent is site.by_url["/ru/ukhod/krysha/"]
    assert [c.url for c in page.breadcrumbs] == ["/ru/", "/ru/ukhod/", "/ru/ukhod/krysha/"]
    assert [c.url for c in site.by_url["/ru/ukhod/"].children] == ["/ru/ukhod/krysha/"]


def test_hreflang_pairs_localized_addresses(tmp_path):
    site, config, collector = scan(tmp_path, NESTED)
    links.resolve(site, config, sites.theme(), collector)
    page = site.by_url["/doglyad/dakh/cherepytsya/"]
    assert sitemap.alternates(page, config) == [
        ("ru", "https://example.com/ru/ukhod/krysha/cherepitsa/"),
        ("uk", "https://example.com/doglyad/dakh/cherepytsya/"),
        ("x-default", "https://example.com/doglyad/dakh/cherepytsya/"),
    ]
