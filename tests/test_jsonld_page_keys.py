"""JSON-LD 0.3.1: `{{ pages.<ключ>.… }}` с ключом страницы из `-`, `_` и `/`.

Шаблон подстановки пропускал только `[a-zA-Z0-9_.*]`: `{{ pages.about-us.url }}`
и `{{ pages.services/roof-repair.url }}` не считались подстановкой, и
ключ разметки выходил пустым. Ключ после `pages.` читается по правилу ключей
страниц (`PAGE_KEY`: сегменты слага через `/`), атрибут - после точки.
"""

from __future__ import annotations

import pytest

from heron.core import tree
from heron.modules import jsonld
from tests import sites


@pytest.fixture
def site_and_config(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/about-us.md": sites.page("Про нас"),
        "uk/services/_index.md": sites.page("Послуги"),
        "uk/services/roof-repair.md": sites.page("Ремонт даху"),
        "uk/guides_and-tips/first-steps.md": sites.page("Перші кроки"),
    }
    content = sites.build(tmp_path, files)

    def make(entity):
        config = sites.config(schema={"entity": entity})
        site, _ = tree.scan(content, config)
        return jsonld.entity(config, "uk", site)

    return make


BASE = "https://example.com"


@pytest.mark.parametrize(
    ("hole", "want"),
    [
        ("{{ pages.about-us.url }}", f"{BASE}/about-us/"),
        ("{{ pages.services/roof-repair.url }}", f"{BASE}/services/roof-repair/"),
        (
            "{{ pages.guides_and-tips/first-steps.url }}",
            f"{BASE}/guides_and-tips/first-steps/",
        ),
        ("{{ pages.services.url }}", f"{BASE}/services/"),
        ("{{ pages.home.url }}", f"{BASE}/"),
    ],
)
def test_page_key_placeholders_resolve(site_and_config, hole, want):
    node = site_and_config({"@type": "Organization", "@id": "#org", "url": hole})
    assert node["url"] == want


def test_attribute_after_the_key_is_still_an_attribute(site_and_config):
    node = site_and_config(
        {
            "@type": "Organization",
            "@id": "#org",
            "name": "{{ pages.services/roof-repair.h1 }}",
            "description": "див. {{ pages.about-us.title }}",
        }
    )
    assert node["name"] == "Ремонт даху"
    assert node["description"] == "див. Про нас"


def test_unknown_key_with_hyphen_drops_the_value(site_and_config):
    node = site_and_config(
        {"@type": "Organization", "@id": "#org", "name": "X", "url": "{{ pages.nemaie-taki.url }}"}
    )
    assert node == {"@type": "Organization", "@id": f"{BASE}/#org", "name": "X"}


def test_plain_placeholders_unchanged():
    data = {"contact": {"city": "Київ", "social": [{"href": "https://a.example"}]}}
    got = jsonld._fill(
        {"a": "{{ contact.city }}", "b": "{{ contact.social.*.href }}", "c": "{{ a-b }}"},
        data,
        "uk",
    )
    # `{{ a-b }}` вне `pages.` - не подстановка, остаётся текстом, как раньше
    assert got == {"a": "Київ", "b": ["https://a.example"], "c": "{{ a-b }}"}
