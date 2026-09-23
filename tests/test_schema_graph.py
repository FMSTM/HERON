"""Граф schema.org: сквозной узел сайта, подстановки и проверки.

Типы здесь нарочно нейтральные. Ядро не знает предметную область ни одного
сайта: какой тип у страницы — решает тема, какие значения — site.yaml.
"""

from __future__ import annotations

import json

import pytest

from heron.core import links, tree
from heron.core.errors import Collector
from heron.modules import jsonld
from tests import sites

ENTITY = {
    "entity": {
        "@id": "#owner",
        "@type": "Person",
        "name": "{{ organization.name }}",
        "description": "{{ organization.about }}",
        "telephone": "{{ contact.phone }}",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "{{ contact.street }}",
            "addressLocality": "{{ contact.city }}",
            "addressCountry": "{{ contact.country }}",
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": "{{ contact.geo.0 }}",
            "longitude": "{{ contact.geo.1 }}",
        },
        "openingHours": "{{ contact.hours }}",
        "sameAs": ["{{ contact.site }}"],
    }
}

CONTACT = {
    "phone": "+100000000",
    "street": "Street 1",
    "street_ru": "Улица 1",
    "city": "Town",
    "city_ru": "Город",
    "country": "UA",
    "geo": [47.8, 35.1],
    "hours": "Mo-Fr 09:00-17:00",
    "site": "https://example.com/",
}

ORGANIZATION = {"name": "Кто-то", "about": "About", "about_ru": "Описание"}


def _config(**over):
    data = {"schema": ENTITY, "contact": CONTACT, "organization": ORGANIZATION}
    data.update(over)
    return sites.config(**data)


def _site(tmp_path, files, config):
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site, collector


def test_entity_is_filled_from_site_yaml(tmp_path):
    config = _config()
    site, _ = _site(tmp_path, {"uk/index.md": sites.page("Головна")}, config)
    node = jsonld.entity(config, "uk")
    assert node["name"] == "Кто-то"
    assert node["address"]["addressLocality"] == "Town"
    assert node["geo"]["latitude"] == 47.8  # число осталось числом
    assert node["openingHours"] == "Mo-Fr 09:00-17:00"
    assert node["@id"] == "https://example.com/#owner"


def test_language_suffix_wins_on_its_page(tmp_path):
    """На русской странице {{ contact.city }} — это city_ru."""
    config = _config()
    assert jsonld.entity(config, "ru")["address"]["addressLocality"] == "Город"
    assert jsonld.entity(config, "ru")["description"] == "Описание"
    assert jsonld.entity(config, "uk")["description"] == "About"


def test_value_without_data_is_dropped(tmp_path):
    """Пустое поле в разметке хуже отсутствующего: его считают заявленным."""
    contact = {k: v for k, v in CONTACT.items() if k != "hours"}
    config = _config(contact=contact)
    assert "openingHours" not in jsonld.entity(config, "uk")


def test_entity_is_on_every_page_but_not_on_noindex(tmp_path):
    config = _config()
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/tech.md": sites.page("Службова", noindex=True),
    }
    site, _ = _site(tmp_path, files, config)
    theme = sites.theme()
    for page in site.pages:
        graph = jsonld.build(page, config, theme)
        has_entity = any(str(n.get("@id", "")).endswith("#owner") for n in graph)
        assert has_entity is (not page.meta.noindex), page.source


def test_id_is_the_same_across_languages(tmp_path):
    config = _config()
    assert jsonld.entity(config, "uk")["@id"] == jsonld.entity(config, "ru")["@id"]


def test_page_type_node_comes_from_the_theme(tmp_path):
    config = _config()
    theme = sites.theme(types={"service": {"uses": [], "jsonld": ["Service"]}})
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/one.md": sites.page("Послуга", type="service"),
    }
    site, collector = _site(tmp_path, files, config)
    page = next(p for p in site.pages if p.type == "service")
    kinds = [n.get("@type") for n in jsonld.build(page, config, theme)]
    assert "Service" in kinds
    assert jsonld.verify(page, config, theme, collector) and not collector.errors


def test_page_may_declare_its_own_type(tmp_path):
    """Страница знает про себя больше типа — и должна иметь право сказать."""
    config = _config()
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/one.md": sites.page(
            "Процедура",
            schema={"Service": {"serviceType": "консультація"}},
        ),
    }
    site, collector = _site(tmp_path, files, config)
    page = next(p for p in site.pages if p.key == "one")
    graph = jsonld.build(page, config, sites.theme())
    service = next(n for n in graph if n.get("@type") == "Service")
    assert service["serviceType"] == "консультація"
    assert service["name"] == "Процедура"  # ядро подставило своё
    assert "Service" in jsonld.verify(page, config, sites.theme(), collector)


def test_entity_without_address_is_an_error(tmp_path):
    config = _config(contact={k: v for k, v in CONTACT.items() if k != "city"})
    site, collector = _site(tmp_path, {"uk/index.md": sites.page("Головна")}, config)
    jsonld.verify(site.pages[0], config, sites.theme(), collector)
    assert [e.code for e in collector.errors] == ["E020"]
    assert "адрес" in collector.errors[0].message


def test_money_is_refused(tmp_path):
    """Стоимость на сайте не публикуется — это требование, а не забывчивость."""
    entity = {"entity": {**ENTITY["entity"], "priceRange": "$$"}}
    config = _config(schema=entity)
    site, collector = _site(tmp_path, {"uk/index.md": sites.page("Головна")}, config)
    jsonld.verify(site.pages[0], config, sites.theme(), collector)
    assert any("деньги" in e.message for e in collector.errors)


def test_graph_is_valid_json(tmp_path):
    config = _config()
    site, _ = _site(tmp_path, {"uk/index.md": sites.page("Головна")}, config)
    payload = json.loads(jsonld.render(site.pages[0], config, sites.theme()))
    assert payload["@context"] == "https://schema.org"


def test_collector_untouched():
    assert not Collector().errors


@pytest.mark.parametrize("lang", ["uk", "ru"])
def test_entity_survives_both_languages(lang):
    assert jsonld.entity(_config(), lang)["telephone"] == "+100000000"


def test_list_is_plucked_by_star(tmp_path):
    """Соцсети объявлены один раз как {href, name} — в разметку нужен href."""
    contact = {
        **CONTACT,
        "social": [
            {"href": "https://a.example/x", "name": "A"},
            {"href": "https://b.example/y", "name": "B"},
        ],
    }
    entity = {"entity": {**ENTITY["entity"], "sameAs": "{{ contact.social.*.href }}"}}
    config = _config(contact=contact, schema=entity)
    node = jsonld.entity(config, "uk")
    assert node["sameAs"] == ["https://a.example/x", "https://b.example/y"]


def test_entity_can_point_at_a_page(tmp_path):
    """Адрес страницы и её фотография — из движка, а не вписаны руками."""
    entity = {
        "entity": {
            **ENTITY["entity"],
            "url": "{{ pages.about.url }}",
            "image": "{{ pages.about.image }}",
        }
    }
    config = _config(schema=entity)
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/about.md": sites.page("Про нас", image="media/foto/portrait.jpg"),
    }
    site, _ = _site(tmp_path, files, config)
    node = jsonld.entity(config, "uk", site)
    assert node["url"] == "https://example.com/about/"
    assert node["image"] == "https://example.com/media/foto/portrait.jpg"


def test_base_url_is_available(tmp_path):
    entity = {"entity": {**ENTITY["entity"], "url": "{{ site.base }}"}}
    config = _config(schema=entity)
    assert jsonld.entity(config, "uk")["url"] == "https://example.com/"


def test_missing_page_key_drops_the_field(tmp_path):
    entity = {"entity": {**ENTITY["entity"], "url": "{{ pages.nowhere.url }}"}}
    config = _config(schema=entity)
    site, _ = _site(tmp_path, {"uk/index.md": sites.page("Головна")}, config)
    assert "url" not in jsonld.entity(config, "uk", site)
