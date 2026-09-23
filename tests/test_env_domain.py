"""Домен по окружению, полный набор hreflang и 404 вне карты сайта."""

from __future__ import annotations

from heron.core import links, tree
from heron.core.build import for_env
from heron.core.environment import BuildEnv
from heron.modules import sitemap
from tests import sites


def _config(**over):
    site = {
        "domain": "example.com",
        "domains": {"dev": "dev.example.com", "prod": "example.com"},
        "theme": "demo",
        "default_lang": "uk",
        "languages": ["uk", "ru"],
    }
    site.update(over.pop("site", {}))
    return sites.config(site=site, **over)


def test_domain_follows_the_environment():
    config = _config()
    for_env(config, BuildEnv.named("dev"))
    assert config.site.domain == "dev.example.com"


def test_prod_keeps_its_own():
    config = _config()
    for_env(config, BuildEnv.named("prod"))
    assert config.site.domain == "example.com"


def test_unknown_environment_falls_back():
    config = _config()
    for_env(config, BuildEnv(name="stage"))
    assert config.site.domain == "example.com"


def test_without_the_block_nothing_changes():
    config = sites.config()
    for_env(config, BuildEnv.named("dev"))
    assert config.site.domain == "example.com"


def test_scheme_is_stripped_from_domains():
    config = _config(site={"domains": {"dev": "https://dev.example.com/"}})
    for_env(config, BuildEnv.named("dev"))
    assert config.site.domain == "dev.example.com"


def _built(tmp_path, files):
    config = _config()
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site, config


def test_alternates_include_self_and_default(tmp_path):
    """Набор без самоссылки поисковик считает несогласованным."""
    files = {"uk/index.md": sites.page("Головна"), "ru/index.md": sites.page("Главная")}
    site, config = _built(tmp_path, files)
    page = next(p for p in site.pages if p.lang == "ru")
    langs = [lang for lang, _ in sitemap.alternates(page, config)]
    assert langs == ["ru", "uk", "x-default"]


def test_page_without_translations_has_no_set(tmp_path):
    files = {"uk/index.md": sites.page("Головна"), "uk/alone.md": sites.page("Сама")}
    site, config = _built(tmp_path, files)
    page = next(p for p in site.pages if p.key == "alone")
    assert page.translations == {}


def test_404_stays_out_of_the_sitemap(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/404.md": sites.page("Не знайдено", type="404"),
    }
    site, config = _built(tmp_path, files)
    xml = sitemap.generate(site, config)["sitemap-uk.xml"]
    assert "/404/" not in xml
    assert "<loc>https://example.com/</loc>" in xml
