"""JSON-LD: сквозной узел без @id ищется по равенству, а не по пустому суффиксу."""

from __future__ import annotations

from heron.core import tree
from heron.core.errors import Collector
from heron.modules import jsonld
from tests import sites


def _verify(tmp_path, entity):
    files = {"uk/index.md": sites.page("Головна"), "uk/a.md": sites.page("А")}
    content = sites.build(tmp_path, files)
    config = sites.config(schema={"entity": entity})
    site, _ = tree.scan(content, config)
    theme = sites.theme(types={"page": {"uses": [], "jsonld": ["WebPage"]}})
    collector = Collector()
    for page in site.pages:
        jsonld.verify(page, config, theme, collector, site)
    return collector


def _codes(collector):
    return [e.code for e in collector.errors]


def test_no_id_filled_address_no_error(tmp_path):
    entity = {
        "@type": "Organization",
        "name": "Мастерська",
        "address": {"@type": "PostalAddress", "addressLocality": "Київ"},
    }
    assert "E020" not in _codes(_verify(tmp_path, entity))


def test_no_id_empty_locality_is_error(tmp_path):
    entity = {
        "@type": "Organization",
        "name": "Мастерська",
        "address": {"@type": "PostalAddress", "addressLocality": ""},
    }
    assert "E020" in _codes(_verify(tmp_path, entity))


def test_with_id_behaviour_unchanged(tmp_path):
    ok = {
        "@type": "Organization",
        "@id": "#org",
        "address": {"@type": "PostalAddress", "addressLocality": "Київ"},
    }
    bad = {**ok, "address": {"@type": "PostalAddress", "addressLocality": ""}}
    assert "E020" not in _codes(_verify(tmp_path / "ok", ok))
    assert "E020" in _codes(_verify(tmp_path / "bad", bad))
