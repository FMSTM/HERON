"""Генераторы: sitemap, hreflang, robots, llms.txt, JSON-LD, редиректы, лента."""

import json

import pytest

from heron.core import links, tree
from heron.core.environment import BuildEnv
from heron.modules import feed, jsonld, llms, redirects, robots, sitemap
from tests import sites

FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/bio.md": sites.page("Біографія", updated="2026-09-01"),
    "uk/services/_index.md": sites.page("Послуги", type="category", children_type="service"),
    "uk/services/consulting.md": sites.page("Консультація", order=1),
    "ru/index.md": sites.page("Главная"),
    "ru/bio.md": sites.page("Биография"),
}


@pytest.fixture
def built(tmp_path):
    content = sites.build(tmp_path, FILES)
    config = sites.config()
    site, collector = tree.scan(content, config)
    theme = sites.theme()
    links.resolve(site, config, theme, collector)
    return site, config, theme, collector


def test_sitemap_index_lists_languages(built):
    site, config, _, _ = built
    files = sitemap.generate(site, config)
    assert "sitemap-uk.xml" in files and "sitemap-ru.xml" in files
    assert "https://example.com/sitemap-uk.xml" in files["sitemap.xml"]


def test_sitemap_contains_absolute_urls_and_lastmod(built):
    site, config, _, _ = built
    uk = sitemap.generate(site, config)["sitemap-uk.xml"]
    assert "<loc>https://example.com/bio/</loc>" in uk
    assert "<lastmod>2026-09-01</lastmod>" in uk


def test_hreflang_is_symmetric(built):
    site, config, _, _ = built
    files = sitemap.generate(site, config)
    assert 'hreflang="ru" href="https://example.com/ru/bio/"' in files["sitemap-uk.xml"]
    assert 'hreflang="uk" href="https://example.com/bio/"' in files["sitemap-ru.xml"]
    assert 'hreflang="x-default" href="https://example.com/bio/"' in files["sitemap-ru.xml"]


def test_page_without_translation_has_no_alternates(built):
    site, config, _, _ = built
    uk = sitemap.generate(site, config)["sitemap-uk.xml"]
    block = uk.split("<loc>https://example.com/services/consulting/</loc>")[1].split("</url>")[0]
    assert "xhtml:link" not in block


def test_noindex_page_stays_out_of_sitemap(tmp_path):
    files = {**FILES, "uk/secret.md": sites.page("Службова", noindex=True)}
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, _ = tree.scan(content, config)
    assert "/secret/" not in sitemap.generate(site, config)["sitemap-uk.xml"]


def test_robots_points_at_sitemap(built):
    _, config, _, _ = built
    text = robots.generate(config, BuildEnv.named("prod"))["robots.txt"]
    assert "Sitemap: https://example.com/sitemap.xml" in text
    assert text.startswith("User-agent: *")


def test_robots_extra_lines(tmp_path):
    config = sites.config(seo={"robots_extra": ["Disallow: /tmp/"]})
    text = robots.generate(config, BuildEnv.named("prod"))["robots.txt"]
    assert "Disallow: /tmp/" in text


def test_robots_closes_everything_outside_prod(built):
    """Дев-сборка не должна попадать в индекс, даже если её кто-то выложил."""
    _, config, _, _ = built
    text = robots.generate(config, BuildEnv.named("dev"))["robots.txt"]
    assert text == "User-agent: *\nDisallow: /\n"


def test_robots_closed_by_default(built):
    """Забыть указать окружение можно; получить открытый robots — нельзя."""
    _, config, _, _ = built
    assert "Disallow: /" in robots.generate(config)["robots.txt"]


def test_llms_lists_catalogs_with_children(built):
    site, config, _, _ = built
    text = llms.generate(site, config)["llms.txt"]
    assert "# Головна" in text
    assert "## Послуги" in text
    assert "[Консультація](https://example.com/services/consulting/)" in text


def test_llms_full_carries_the_text(built):
    site, config, _, _ = built
    full = llms.generate(site, config)["llms-full.txt"]
    assert "Вступление." in full
    assert "URL: https://example.com/bio/" in full


def test_llms_full_can_be_switched_off(tmp_path):
    content = sites.build(tmp_path, FILES)
    config = sites.config(seo={"llms_txt": False})
    site, _ = tree.scan(content, config)
    assert "llms-full.txt" not in llms.generate(site, config)


def test_jsonld_types_come_from_theme(built):
    site, config, _, _ = built
    theme = sites.theme(types={"page": {"uses": [], "jsonld": ["Article"]}})
    page = site.by_url["/bio/"]
    graph = jsonld.build(page, config, theme)
    assert graph[0]["@type"] == "Article"
    assert graph[0]["url"] == "https://example.com/bio/"
    assert graph[0]["inLanguage"] == "uk"
    assert graph[0]["dateModified"] == "2026-09-01"


def test_jsonld_without_declaration_still_has_breadcrumbs(built):
    site, config, theme, _ = built
    graph = jsonld.build(site.by_url["/services/consulting/"], config, theme)
    crumbs = next(node for node in graph if node["@type"] == "BreadcrumbList")
    names = [item["name"] for item in crumbs["itemListElement"]]
    assert names == ["Головна", "Послуги", "Консультація"]


def test_jsonld_merges_site_and_page_overrides(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/bio.md": (
            "---\ntitle: Біо\nh1: Біо\ndescription: Опис\n"
            "schema:\n  Person:\n    jobTitle: Лікар\n---\n\nТекст.\n"
        ),
    }
    content = sites.build(tmp_path, files)
    config = sites.config(schema={"Person": {"worksFor": "Клініка"}})
    site, _ = tree.scan(content, config)
    theme = sites.theme(types={"page": {"jsonld": ["Person"]}})
    node = jsonld.build(site.by_url["/bio/"], config, theme)[0]
    assert node["worksFor"] == "Клініка"
    assert node["jobTitle"] == "Лікар"


def test_jsonld_faq_built_from_section(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/q.md": (
            "---\ntitle: Питання\nh1: Питання\ndescription: Опис\n---\n\n"
            "## Часті питання {#faq}\n\n### Боляче?\n\nНі.\n"
        ),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, _ = tree.scan(content, config)
    graph = jsonld.build(site.by_url["/q/"], config, sites.theme())
    faq = next(node for node in graph if node["@type"] == "FAQPage")
    assert faq["mainEntity"][0]["name"] == "Боляче?"


def test_jsonld_render_is_valid_json(built):
    site, config, theme, _ = built
    text = jsonld.render(site.by_url["/services/consulting/"], config, theme)
    payload = json.loads(text)
    assert payload["@context"] == "https://schema.org"


def test_redirects_map_format(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/services/consulting.md": sites.page("Консультація", redirect_from=["/uslugi/mikro/"]),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    out = redirects.generate(site, collector)
    assert out["redirects.map"] == "/uslugi/mikro/  /services/consulting/;\n"
    assert not collector.failed


def test_gone_is_separate_from_moved(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна", gone=["/community/", "/forum/"]),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    out = redirects.generate(site, collector)
    assert out["gone.map"] == "/community/  1;\n/forum/  1;\n"


def test_redirect_onto_existing_page_is_e009(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/bio.md": sites.page("Біо", redirect_from=["/"]),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    redirects.generate(site, collector)
    assert [e.code for e in collector.errors] == ["E009"]


def test_one_old_url_into_two_places_is_e009(tmp_path):
    files = {
        "uk/a.md": sites.page("А", redirect_from=["/old/"]),
        "uk/b.md": sites.page("Б", redirect_from=["/old/"]),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    redirects.generate(site, collector)
    assert collector.failed
    assert "два места" in str(collector.errors[0])


def test_feed_absent_without_setting(built):
    site, config, _, _ = built
    assert feed.generate(site, config) == {}


def test_feed_lists_pages_of_the_type(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/blog/_index.md": sites.page("Блог", type="category", children_type="article"),
        "uk/blog/first.md": sites.page("Перша", updated="2026-01-01"),
        "uk/blog/second.md": sites.page("Друга", updated="2026-05-05"),
    }
    content = sites.build(tmp_path, files)
    config = sites.config(seo={"feed": "article"})
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    xml = feed.generate(site, config)["feed.xml"]
    assert xml.index("Друга") < xml.index("Перша")
    assert "<updated>2026-05-05T00:00:00Z</updated>" in xml


def test_home_is_not_listed_as_a_section(built):
    site, config, _, _ = built
    text = llms.generate(site, config)["llms.txt"]
    assert text.count("## Послуги") == 1
    assert "## Головна" not in text
