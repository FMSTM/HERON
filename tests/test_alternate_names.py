"""site.alternate_names -> WebSite.alternateName."""

from __future__ import annotations

from heron.core import tree
from heron.modules import jsonld
from tests import sites


def _node(tmp_path, url="/", **config_over):
    files = {"uk/index.md": sites.page("Головна"), "ru/index.md": sites.page("Главная")}
    content = sites.build(tmp_path, files)
    config = sites.config(**config_over)
    site, _ = tree.scan(content, config)
    theme = sites.theme(
        types={
            "home": {"uses": [], "jsonld": ["WebSite"]},
            "page": {"uses": [], "jsonld": ["WebSite"]},
        }
    )
    graph = jsonld.build(site.by_url[url], config, theme, site)
    return next(n for n in graph if n.get("@type") == "WebSite"), config


def _site(**extra):
    return {
        "domain": "example.com",
        "theme": "demo",
        "default_lang": "uk",
        "languages": ["uk", "ru"],
        **extra,
    }


def test_field_goes_to_alternate_name(tmp_path):
    node, _ = _node(tmp_path, site=_site(name="Сайт", alternate_names=["Site", "Сайт.ua"]))
    assert node["name"] == "Сайт"
    assert node["alternateName"] == ["Site", "Сайт.ua"]


def test_language_value_overrides(tmp_path):
    node, _ = _node(
        tmp_path,
        url="/ru/",
        site=_site(alternate_names=["Site"], alternate_names_ru=["Сайт"]),
    )
    assert node["alternateName"] == ["Сайт"]


def test_explicit_schema_wins(tmp_path):
    node, _ = _node(
        tmp_path,
        site=_site(alternate_names=["Site"]),
        schema={"WebSite": {"alternateName": ["Own"]}},
    )
    assert node["alternateName"] == ["Own"]


def test_empty_means_no_key(tmp_path):
    node, _ = _node(tmp_path, site=_site())
    assert "alternateName" not in node


def test_site_dump_contains_field(tmp_path):
    _, config = _node(tmp_path, site=_site(alternate_names=["Site"]))
    assert config.model_dump()["site"]["alternate_names"] == ["Site"]
