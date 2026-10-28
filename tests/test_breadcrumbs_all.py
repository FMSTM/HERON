"""BreadcrumbList на всех типах страниц, кроме главной языка (ТЗ E5.2)."""

from __future__ import annotations

from heron.core import links, tree
from heron.modules import jsonld
from tests import sites

TYPES = {name: {"uses": [], "jsonld": ["WebPage"]} for name in ("article", "service", "profile")}


def _resolve(tmp_path, files):
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(types=TYPES), collector)
    return site, config


def _files(with_home=True):
    files = {
        "uk/blog/index.md": sites.page("Блог"),
        "uk/blog/post.md": sites.page("Стаття", type="article"),
        "uk/services/index.md": sites.page("Послуги"),
        "uk/services/one.md": sites.page("Послуга", type="service"),
        "uk/team/anna.md": sites.page("Анна", type="profile"),
        "uk/404.md": sites.page("Не знайдено"),
        "ru/index.md": sites.page("Главная"),
        "ru/about.md": sites.page("О нас"),
    }
    if with_home:
        files["uk/index.md"] = sites.page("Головна")
    return files


def _homes(site, config):
    default = config.site.default_lang
    return {p.lang: p for p in site.pages if p.url == ("/" if p.lang == default else f"/{p.lang}/")}


def test_every_page_but_home_has_breadcrumbs_starting_at_home(tmp_path):
    site, config = _resolve(tmp_path, _files())
    homes = _homes(site, config)
    assert set(homes) == {"uk", "ru"}
    checked = 0
    for page in site.pages:
        if page is homes[page.lang] or page.url.endswith("/404/") or page.key == "404":
            continue
        node = jsonld.breadcrumbs(page, config)
        assert node is not None, page.url
        assert node["@type"] == "BreadcrumbList"
        items = node["itemListElement"]
        home_item = f"https://example.com{homes[page.lang].url}".rstrip("/")
        assert items[0]["item"].rstrip("/") == home_item, page.url
        assert [i["position"] for i in items] == list(range(1, len(items) + 1))
        assert items[-1]["item"].endswith(page.url)
        checked += 1
    assert checked >= 6


def test_home_has_no_breadcrumbs(tmp_path):
    site, config = _resolve(tmp_path, _files())
    for page in _homes(site, config).values():
        assert page.breadcrumbs == []
        assert jsonld.breadcrumbs(page, config) is None


def test_typed_pages_nested_chain(tmp_path):
    site, config = _resolve(tmp_path, _files())
    post = site.by_url["/blog/post/"]
    names = [i["name"] for i in jsonld.breadcrumbs(post, config)["itemListElement"]]
    # Вложенный index.md не страница раздела (/blog/index/), родителя у статьи нет:
    # цепочка - главная языка и сама страница.
    assert names == ["Головна", "Стаття"]


def test_site_without_language_home_has_no_breadcrumbs(tmp_path):
    site, config = _resolve(tmp_path, _files(with_home=False))
    page = site.by_url["/blog/post/"]
    assert page.breadcrumbs == []
    assert jsonld.breadcrumbs(page, config) is None
    assert "/" not in site.by_url
    assert jsonld.breadcrumbs(site.by_url["/team/anna/"], config) is None


def test_not_found_page_behaviour_is_fixed(tmp_path):
    site, config = _resolve(tmp_path, _files())
    nf = next(p for p in site.pages if p.key == "404")
    # Зафиксировано: у страницы 404 крошки есть (главная языка + она сама).
    node = jsonld.breadcrumbs(nf, config)
    assert node is not None
    assert node["itemListElement"][0]["name"] == "Головна"
