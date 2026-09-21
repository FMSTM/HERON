"""Связи с подписями: слаги, карты и подстановка подписи по умолчанию."""

from heron.core import links, tree
from tests import sites

THEME = {
    "name": "demo",
    "links": [{"field": "procedures", "type": "service", "back": "conditions_for"}],
}


def build(tmp_path, field: str) -> tuple:
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/services/_index.md": sites.page("Послуги", type="category", children_type="service"),
        "uk/services/one.md": sites.page("Перша послуга").replace(
            "Вступление.", "Вступ.\n\nОбіцянка першої послуги."
        ),
        "uk/services/two.md": sites.page("Друга послуга", description="Опис другої"),
        "uk/conditions.md": f"---\ntitle: Стан\nh1: Стан\ndescription: Опис\n{field}\n---\n\nТекст.\n",
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    theme = sites.theme(links=THEME["links"])
    links.resolve(site, config, theme, collector)
    return site, collector


def test_plain_slugs_still_work(tmp_path):
    site, collector = build(tmp_path, "procedures: [one, two]")
    related = site.by_key[("uk", "conditions")].related["procedures"]
    assert sorted(item.slug for item in related) == ["one", "two"]
    assert not collector.errors


def test_maps_carry_the_note(tmp_path):
    site, _ = build(
        tmp_path,
        "procedures:\n  - slug: one\n    note: Основна операція\n",
    )
    related = site.by_key[("uk", "conditions")].related["procedures"]
    assert related[0].note == "Основна операція"


def test_mixed_forms_in_one_list(tmp_path):
    site, collector = build(
        tmp_path,
        "procedures:\n  - slug: one\n    note: Підпис\n  - two\n",
    )
    related = site.by_key[("uk", "conditions")].related["procedures"]
    notes = {item.slug: item.note for item in related}
    assert notes["one"] == "Підпис"
    assert notes["two"] == "Опис другої"  # подписи нет — берём описание
    assert not collector.errors


def test_note_defaults_to_promise(tmp_path):
    site, _ = build(tmp_path, "procedures: [one]")
    related = site.by_key[("uk", "conditions")].related["procedures"]
    assert related[0].note == "Обіцянка першої послуги."


def test_unknown_slug_is_an_error(tmp_path):
    _, collector = build(tmp_path, "procedures: [неіснуюча]")
    assert [e.code for e in collector.errors] == ["E006"]
