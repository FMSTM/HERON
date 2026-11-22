"""JSON-LD 0.3.1: `@id` и связи по умолчанию, предмет страницы, FAQPage, 404, точность geo.

- узел страницы - `@id` `<адрес>#webpage`, WebSite - `<корень>#website`, предметный
  узел - `<адрес>#service`/`#condition`/`#procedure`/`#<тип>`;
- страница - `isPartOf` сайта (если сайт выводит WebSite), `mainEntity`/`about` -
  предметные узлы; WebSite - `publisher`, Service - `provider` сквозного узла;
- имя предмета - `crumb_name`, мета-описание ему не подставляется;
- `{{ page.url }}` - абсолютный адрес страницы;
- FAQPage из секции: `url`, `inLanguage`, `isPartOf`; `schema: {FAQPage: null}` -
  без FAQPage;
- 404: без крошек и сквозного узла;
- geo меньше 5 знаков - сведение отчёта, не предупреждение (`--strict` его не считает).

Заданное явно главнее, явное `null` или `""` выключает значение по умолчанию.
"""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core import links, report, tree
from heron.core.errors import Collector
from heron.modules import jsonld
from heron.schemaorg.validate import validate
from tests import sites

B = "https://example.com"
ENTITY = {"@type": "Organization", "@id": "#org", "name": "Майстерня"}
FAQ_BODY = (
    "\n## Питання {#faq}\n\n### Скільки коштує?\n\nДомовимось.\n\n### Як довго?\n\nТиждень.\n"
)


def _graph(
    tmp_path,
    kinds=("WebPage",),
    entity: Any = ENTITY,
    own=None,
    shared=None,
    page_type="page",
    key="a",
    nav_title="Коротко",
    extra_types=None,
    body="",
):
    fields: dict[str, Any] = {"nav_title": nav_title}
    if own is not None:
        fields["schema"] = own
    text = sites.page("Довгий заголовок сторінки", **fields) + body
    files = {"uk/index.md": sites.page("Головна"), f"uk/{key}.md": text}
    content = sites.build(tmp_path, files)
    schema = dict(shared or {})
    if entity is not None:
        schema["entity"] = entity
    config = sites.config(schema=schema) if schema else sites.config()
    site, _ = tree.scan(content, config)
    types = {page_type: {"uses": [], "jsonld": list(kinds)}, **(extra_types or {})}
    theme = sites.theme(types=types)
    links.resolve(site, config, theme, Collector())
    page = next(p for p in site.pages if p.key == key)
    if page_type != "page":
        page.type = page_type
    return jsonld.build(page, config, theme, site), page, config, theme, site


def _of(graph, kind):
    return next(n for n in graph if n.get("@type") == kind)


# --- 5. @id и связи --------------------------------------------------------------------


def test_page_node_and_subject_get_ids_and_links(tmp_path):
    graph, *_ = _graph(tmp_path, kinds=("WebPage", "Service"))
    page, service = _of(graph, "WebPage"), _of(graph, "Service")
    assert page["@id"] == f"{B}/a/#webpage"
    assert service["@id"] == f"{B}/a/#service"
    assert page["mainEntity"] == {"@id": f"{B}/a/#service"}
    assert service["provider"] == {"@id": f"{B}/#org"}
    # сайт WebSite не выводит - ссылаться не на что
    assert "isPartOf" not in page
    for node in (page, service):
        assert validate(node).findings == []


# Типы и хвосты - из таблицы рядом со словарём (heron/schemaorg/id-suffixes.json):
# предметные имена schema.org в ядре и его тестах не пишутся.
TABLE = list(jsonld._suffixes())
SECOND, THIRD = TABLE[1], TABLE[2]


@pytest.mark.parametrize(("kind", "tail"), [*TABLE, ("Product", "product")])
def test_subject_suffixes(tmp_path, kind, tail):
    graph, *_ = _graph(tmp_path, kinds=("WebPage", kind), entity=None)
    assert _of(graph, kind)["@id"] == f"{B}/a/#{tail}"
    assert _of(graph, "WebPage")["mainEntity"] == {"@id": f"{B}/a/#{tail}"}


def test_second_subject_goes_to_about(tmp_path):
    graph, *_ = _graph(tmp_path, kinds=("WebPage", SECOND[0], THIRD[0]))
    page = _of(graph, "WebPage")
    assert page["mainEntity"] == {"@id": f"{B}/a/#{SECOND[1]}"}
    assert page["about"] == {"@id": f"{B}/a/#{THIRD[1]}"}


def test_website_id_publisher_and_is_part_of(tmp_path):
    graph, *_ = _graph(
        tmp_path,
        kinds=("WebPage",),
        extra_types={"home": {"uses": [], "jsonld": ["WebSite"]}},
        own={"WebSite": {}},
    )
    website, page = _of(graph, "WebSite"), _of(graph, "WebPage")
    assert website["@id"] == f"{B}/#website"
    assert website["publisher"] == {"@id": f"{B}/#org"}
    assert page["isPartOf"] == {"@id": f"{B}/#website"}
    assert validate(website).findings == []


def test_website_id_is_the_same_on_every_language(tmp_path):
    files = {"uk/index.md": sites.page("Головна"), "ru/index.md": sites.page("Главная")}
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, _ = tree.scan(content, config)
    theme = sites.theme(types={"home": {"uses": [], "jsonld": ["WebSite"]}})
    ids = set()
    for page in site.pages:
        page.type = "home"
        ids |= {n["@id"] for n in jsonld.build(page, config, theme, site) if "@id" in n}
    assert ids == {f"{B}/#website"}


def test_explicit_values_win_and_null_opts_out(tmp_path):
    own = {
        "WebPage": {"@id": "{{ page.url }}#main", "isPartOf": None, "mainEntity": None},
        "Service": {"@id": "{{ page.url }}#procedure", "provider": {"@id": "#other"}},
    }
    graph, *_ = _graph(
        tmp_path, kinds=("WebPage", "Service"), own=own, shared={"WebSite": {"name": "X"}}
    )
    page, service = _of(graph, "WebPage"), _of(graph, "Service")
    assert page["@id"] == f"{B}/a/#main"
    assert "isPartOf" not in page and "mainEntity" not in page
    assert service["@id"] == f"{B}/a/#procedure"
    assert service["provider"] == {"@id": f"{B}/#other"}


def test_page_url_placeholder(tmp_path):
    own = {THIRD[0]: {"@id": "{{ page.url }}#procedure", "sameAs": "{{ page.url }}"}}
    graph, *_ = _graph(tmp_path, kinds=("WebPage",), own=own)
    node = _of(graph, THIRD[0])
    assert node["@id"] == f"{B}/a/#procedure"
    assert node["sameAs"] == f"{B}/a/"


def test_entity_without_id_gives_no_provider(tmp_path):
    graph, *_ = _graph(tmp_path, kinds=("WebPage", "Service"), entity={"@type": "Organization"})
    assert "provider" not in _of(graph, "Service")


def test_untyped_kind_outside_vocabulary_is_untouched(tmp_path):
    graph, *_ = _graph(tmp_path, kinds=("WebPage", "NotAType"))
    assert "@id" not in _of(graph, "NotAType")
    assert "mainEntity" not in _of(graph, "WebPage")


# --- 6. предмет страницы --------------------------------------------------------------


def test_subject_name_is_crumb_name_and_no_meta_description(tmp_path):
    graph, *_ = _graph(tmp_path, kinds=("WebPage", THIRD[0]))
    node = _of(graph, THIRD[0])
    assert node["name"] == "Коротко"
    assert "description" not in node
    page = _of(graph, "WebPage")
    assert page["name"] == "Довгий заголовок сторінки" and page["description"]


def test_subject_name_falls_back_to_h1(tmp_path):
    graph, *_ = _graph(tmp_path, kinds=("WebPage", "Service"), nav_title=None)
    assert _of(graph, "Service")["name"] == "Довгий заголовок сторінки"


# --- 7. FAQPage ------------------------------------------------------------------------


def test_faq_node_gets_url_language_and_is_part_of(tmp_path):
    graph, *_ = _graph(tmp_path, shared={"WebSite": {}}, body=FAQ_BODY)
    node = _of(graph, "FAQPage")
    assert node["url"] == f"{B}/a/"
    assert node["inLanguage"] == "uk"
    assert node["isPartOf"] == {"@id": f"{B}/#website"}
    assert len(node["mainEntity"]) == 2
    assert validate(node).findings == []


@pytest.mark.parametrize("where", ["own", "shared"])
def test_faq_opt_out(tmp_path, where):
    block = {"FAQPage": None}
    kwargs = {"own": block} if where == "own" else {"shared": block}
    graph, *_ = _graph(tmp_path, body=FAQ_BODY, **kwargs)
    assert not [n for n in graph if n.get("@type") == "FAQPage"]


# --- 8. 404 ----------------------------------------------------------------------------


def test_404_has_no_breadcrumbs_and_no_entity(tmp_path):
    graph, page, config, theme, site = _graph(tmp_path, kinds=(), page_type="404", key="404")
    assert graph == []
    collector = Collector()
    jsonld.verify(page, config, theme, collector, site)
    assert [e.code for e in collector.errors] == []


def test_starter_404_page_has_no_jsonld(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    out = tmp_path / "dist"
    result = CliRunner().invoke(main, ["build", "demo", "--env", "prod", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "application/ld+json" not in (out / "404.html").read_text(encoding="utf-8")
    assert "application/ld+json" in (out / "structure/index.html").read_text(encoding="utf-8")


# --- 9. geo ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "short"),
    [(55.1, True), ("47.8388", True), ("50.50900", False), (50.12345, False), ("x", False)],
)
def test_geo_precision(value, short):
    assert report.geo_short(value) is short


def test_geo_note_is_in_report_and_not_a_warning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    path = tmp_path / "demo" / "site.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\ncontact:\n  geo: [50.45, "30.52345"]\n'
        + 'schema:\n  entity:\n    "@type": LocalBusiness\n    "@id": "#org"\n'
        + '    geo:\n      "@type": GeoCoordinates\n'
        + '      latitude: "{{ contact.geo.0 }}"\n      longitude: "{{ contact.geo.1 }}"\n',
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        main,
        [
            "build",
            "demo",
            "--env",
            "prod",
            "--strict",
            "--notes",
            "en",
            "--out",
            str(tmp_path / "d"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "50.45" in result.output and "latitude" in result.output
    assert "30.52345" not in result.output
