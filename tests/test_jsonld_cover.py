"""JSON-LD: обложка страницы в primaryImageOfPage и в подстановках."""

from __future__ import annotations

from typing import Any

from heron.core import tree
from heron.modules import jsonld
from tests import sites

COVER: dict[str, Any] = {
    "src": "media/c.jpg",
    "url": "https://example.com/media/c-1200.jpg",
    "width": 1200,
    "height": 630,
    "alt": "Подпись",
}


def _site(tmp_path, **config_over):
    files = {"uk/index.md": sites.page("Головна"), "uk/bio.md": sites.page("Біо")}
    content = sites.build(tmp_path, files)
    config = sites.config(**config_over)
    site, _ = tree.scan(content, config)
    return site, config


def _graph(site, config, kind, url="/bio/", cover=COVER):
    theme = sites.theme(types={"page": {"uses": [], "jsonld": [kind]}})
    for p in site.pages:
        p.cover_of = lambda _page, c=cover: c
    return jsonld.build(site.by_url[url], config, theme, site)


def test_webpage_gets_primary_image(tmp_path):
    site, config = _site(tmp_path)
    node = _graph(site, config, "WebPage")[0]
    assert node["primaryImageOfPage"] == {
        "@type": "ImageObject",
        "url": COVER["url"],
        "width": 1200,
        "height": 630,
        "caption": "Подпись",
    }


def test_profile_page_gets_primary_image(tmp_path):
    site, config = _site(tmp_path)
    assert _graph(site, config, "ProfilePage")[0]["primaryImageOfPage"]["url"] == COVER["url"]


def test_article_does_not_get_it(tmp_path):
    site, config = _site(tmp_path)
    assert "primaryImageOfPage" not in _graph(site, config, "Article")[0]


def test_explicit_value_is_kept(tmp_path):
    explicit = {"@type": "ImageObject", "url": "https://example.com/own.jpg"}
    site, config = _site(tmp_path, schema={"WebPage": {"primaryImageOfPage": explicit}})
    assert _graph(site, config, "WebPage")[0]["primaryImageOfPage"] == explicit


def test_no_cover_no_key(tmp_path):
    site, config = _site(tmp_path)
    assert "primaryImageOfPage" not in _graph(site, config, "WebPage", cover=None)[0]


def test_unknown_sizes_are_dropped(tmp_path):
    site, config = _site(tmp_path)
    bare = {**COVER, "width": None, "height": None, "alt": ""}
    image = _graph(site, config, "WebPage", cover=bare)[0]["primaryImageOfPage"]
    assert image["url"] == COVER["url"]
    assert "width" not in image and "height" not in image


def test_entity_image_substitution(tmp_path):
    site, config = _site(
        tmp_path,
        schema={"entity": {"@type": "Person", "@id": "#o", "image": "{{ pages.home.cover.url }}"}},
    )
    graph = _graph(site, config, "WebPage")
    ent = next(n for n in graph if n.get("@type") == "Person")
    assert ent["image"] == COVER["url"]


def test_neighbour_cover_does_not_depend_on_render_order(tmp_path):
    """Страница рендерится раньше главной — обложка главной уже известна."""
    site, config = _site(
        tmp_path,
        schema={"entity": {"@type": "Person", "@id": "#o", "image": "{{ pages.home.cover.url }}"}},
    )
    home = {**COVER, "url": "https://example.com/home.jpg"}
    bio = {**COVER, "url": "https://example.com/bio.jpg"}

    def resolve(page):
        return home if page.url == "/" else bio

    for p in site.pages:
        p.cover_of = resolve
    theme = sites.theme(types={"page": {"uses": [], "jsonld": ["WebPage"]}})
    graph = jsonld.build(site.by_url["/bio/"], config, theme, site)
    assert graph[0]["primaryImageOfPage"]["url"] == bio["url"]
    ent = next(n for n in graph if n.get("@type") == "Person")
    assert ent["image"] == home["url"]


def test_page_cover_substitution_and_missing(tmp_path):
    site, config = _site(tmp_path, schema={"WebPage": {"image": "{{ page.cover.url }}"}})
    assert _graph(site, config, "WebPage")[0]["image"] == COVER["url"]
    assert "image" not in _graph(site, config, "WebPage", cover=None)[0]
