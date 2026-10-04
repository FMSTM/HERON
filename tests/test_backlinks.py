"""Обратные связи: внутри одного типа, от нескольких типов, ссылка на себя.

Спецификация: docs/spec/20-data-contract.md, раздел 6, «Обратные связи».
"""

from __future__ import annotations

from heron.core import links, tree
from tests import sites


def resolve(tmp_path, files, link_specs):
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(links=link_specs), collector)
    return site, collector


SERVICES = {
    "uk/index.md": sites.page("Г"),
    "uk/services/_index.md": sites.page("Послуги", children_type="service"),
    "uk/services/a.md": sites.page("Аудит", related=["b", "c"]),
    "uk/services/b.md": sites.page("Бухгалтерія", related=["c"]),
    "uk/services/c.md": sites.page("Ведення справ", order=1),
}


def test_service_to_service_builds_backlinks(tmp_path):
    site, collector = resolve(
        tmp_path, SERVICES, [{"field": "related", "type": "service", "back": "related_from"}]
    )
    assert not collector.failed
    a, b, c = (site.page(f"services/{x}", "uk") for x in "abc")
    assert [p.url for p in a.related["related"]] == ["/services/c/", "/services/b/"]
    assert [p.url for p in c.related["related_from"]] == ["/services/a/", "/services/b/"]
    assert [p.url for p in b.related["related_from"]] == ["/services/a/"]


def test_self_link_is_skipped_with_warning(tmp_path):
    files = {**SERVICES, "uk/services/a.md": sites.page("Аудит", related=["a", "b"])}
    site, collector = resolve(
        tmp_path, files, [{"field": "related", "type": "service", "back": "related_from"}]
    )
    a = site.page("services/a", "uk")
    assert [p.url for p in a.related["related"]] == ["/services/b/"]
    assert "related_from" not in a.related
    said = [w for w in collector.warnings if "саму себя" in w.message]
    assert [w.path for w in said] == ["uk/services/a.md"]
    assert not collector.failed


def test_one_back_name_from_two_source_types_is_one_mixed_list(tmp_path):
    files = {
        "uk/index.md": sites.page("Г"),
        "uk/topic/_index.md": sites.page("Теми", children_type="topic"),
        "uk/topic/roofing.md": sites.page("Покрівля"),
        "uk/services/_index.md": sites.page("Послуги", children_type="service"),
        "uk/services/s1.md": sites.page("Зрозуміла послуга", topic=["roofing"]),
        "uk/articles/_index.md": sites.page("Статті", children_type="article"),
        "uk/articles/a1.md": sites.page("Стаття", topic=["roofing"], order=1),
    }
    specs = [
        {"field": "topic", "type": "topic", "back": "mentioned_in", "on": "service"},
        {"field": "topic", "type": "topic", "back": "mentioned_in", "on": "article"},
    ]
    site, collector = resolve(tmp_path, files, specs)
    assert not collector.failed
    roofing = site.page("topic/roofing", "uk")
    back = roofing.related["mentioned_in"]
    # один список, без дублей, по order, затем по h1
    assert [p.url for p in back] == ["/articles/a1/", "/services/s1/"]
    # тема фильтрует по типу
    assert [p.type for p in back] == ["article", "service"]
    assert [p.url for p in back if p.type == "service"] == ["/services/s1/"]
