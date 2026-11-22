"""JSON-LD 0.3.1: `*` над списком строк, предупреждение о пустой подстановке, имена крошек.

- `{{ organization.same_as.* }}` над списком адресов-строк давал пустой список,
  и `sameAs` молча пропадал: `*` оставлял только карты. Теперь строки и числа
  берутся как есть, карты - как раньше.
- Ключ, выброшенный из-за пустой подстановки, называется предупреждением
  (ключ и подстановка); выброшенный литерал - нет.
- Имя элемента `BreadcrumbList` - та же подпись, что видит человек в крошках
  стартовой темы (`Page.crumb_name`).
"""

from __future__ import annotations

import html
import json
import re

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core import tree
from heron.core.errors import Collector
from heron.modules import jsonld
from tests import sites

# --- `*` -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("items", "path", "want"),
    [
        (["https://a.example", "https://b.example"], "org.same_as.*", None),
        (
            [{"href": "https://a.example"}, {"href": "https://b.example"}],
            "org.same_as.*.href",
            None,
        ),
        (["https://a.example", {"href": "https://b.example"}], "org.same_as.*.href", None),
        ([1, 2.5, True], "org.same_as.*", [1, 2.5]),
    ],
)
def test_star_keeps_scalars_and_maps_dicts(items, path, want):
    data = {"org": {"same_as": items}}
    got = jsonld._fill({"sameAs": "{{ " + path + " }}"}, data, "uk")
    expected = want or ["https://a.example", "https://b.example"]
    assert got == {"sameAs": expected}


def test_star_over_dicts_without_tail_keeps_dicts():
    nodes = [{"@type": "Person", "name": "А"}, {"@type": "Person", "name": "Б"}]
    got = jsonld._fill({"member": "{{ org.people.* }}"}, {"org": {"people": nodes}}, "uk")
    assert got == {"member": nodes}


def test_star_over_empty_list_drops_key_and_records_it():
    dropped: list[tuple[str, str]] = []
    got = jsonld._fill(
        {"name": "X", "sameAs": "{{ org.same_as.* }}"},
        {"org": {"same_as": []}},
        "uk",
        dropped,
        "schema.entity",
    )
    assert got == {"name": "X"}
    assert dropped == [("schema.entity.sameAs", "{{ org.same_as.* }}")]


def test_literal_empty_value_is_not_recorded():
    dropped: list[tuple[str, str]] = []
    got = jsonld._fill({"name": "X", "telephone": "", "fax": None}, {}, "uk", dropped)
    assert got == {"name": "X"}
    assert dropped == []


# --- предупреждение ---------------------------------------------------------------------


def _verify(tmp_path, entity, pages=None, **extra):
    files = pages or {"uk/index.md": sites.page("Головна"), "uk/a.md": sites.page("А")}
    content = sites.build(tmp_path, files)
    config = sites.config(schema={"entity": entity}, **extra)
    site, _ = tree.scan(content, config)
    theme = sites.theme(types={"page": {"uses": [], "jsonld": ["WebPage"]}})
    collector = Collector()
    for page in site.pages:
        jsonld.verify(page, config, theme, collector, site)
    return collector, site, config, theme


def _markup_warnings(collector):
    return [w for w in collector.warnings if w.kind == "разметка"]


def test_strings_same_as_reaches_the_graph(tmp_path):
    entity = {"@type": "Organization", "@id": "#org", "sameAs": "{{ organization.same_as.* }}"}
    collector, site, config, theme = _verify(
        tmp_path, entity, organization={"same_as": ["https://a.example", "https://b.example"]}
    )
    node = jsonld.entity(config, "uk", site)
    assert node["sameAs"] == ["https://a.example", "https://b.example"]
    assert _markup_warnings(collector) == []


def test_empty_placeholder_warns_once_with_key_and_placeholder(tmp_path):
    entity = {
        "@type": "Organization",
        "@id": "#org",
        "name": "X",
        "sameAs": "{{ organization.same_as.* }}",
        "telephone": "{{ contact.phone }}",
    }
    collector, *_ = _verify(tmp_path, entity, organization={"same_as": []})
    found = _markup_warnings(collector)
    # два ключа, хотя страниц две: сквозной узел называется один раз
    assert len(found) == 2
    texts = " ".join(str(w.message) for w in found)
    assert "schema.entity.sameAs" in texts and "{{ organization.same_as.* }}" in texts
    assert "schema.entity.telephone" in texts and "{{ contact.phone }}" in texts
    assert {w.path for w in found} == {"site.yaml"}
    assert collector.errors == []


def test_page_block_placeholder_warns_on_the_page(tmp_path):
    pages = {
        "uk/index.md": sites.page("Головна"),
        "uk/a.md": sites.page("А", schema={"WebPage": {"keywords": "{{ page.nope }}"}}),
    }
    collector, *_ = _verify(tmp_path, {"@type": "Organization", "@id": "#org"}, pages)
    found = _markup_warnings(collector)
    assert len(found) == 1
    assert found[0].path.endswith("a.md")
    assert "schema.WebPage.keywords" in str(found[0].message)


def test_filled_placeholders_do_not_warn(tmp_path):
    entity = {"@type": "Organization", "@id": "#org", "telephone": "{{ contact.phone }}"}
    collector, *_ = _verify(tmp_path, entity, contact={"phone": "+00 000"})
    assert _markup_warnings(collector) == []


def test_starter_site_has_no_markup_warnings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    result = CliRunner().invoke(main, ["build", "demo", "--out", str(tmp_path / "dist")])
    assert result.exit_code == 0, result.output
    assert "is not written - the placeholder" not in result.output
    assert "не выведен - подстановка" not in result.output


# --- крошки ---------------------------------------------------------------------------


def test_breadcrumb_name_is_the_visible_label(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна", nav_title="Дім"),
        "uk/guides/_index.md": sites.page("Усі посібники", nav_title="Посібники"),
        "uk/guides/start.md": sites.page("Десять хвилин до сайту", nav_title="Початок"),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, _ = tree.scan(content, config)
    from heron.core import links

    links.resolve(site, config, sites.theme(), Collector())
    page = next(p for p in site.pages if p.key == "guides/start")
    names = [i["name"] for i in jsonld.breadcrumbs(page, config)["itemListElement"]]
    assert names == [c.crumb_name for c in [*page.breadcrumbs, page]]


VISIBLE = re.compile(r'<nav class="breadcrumbs"[^>]*>(.*?)</nav>', re.S)
LABEL = re.compile(r"<a [^>]*>(.*?)</a>|<span aria-current=\"page\">(.*?)</span>", re.S)
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _crumb_names(graph):
    nodes = graph.get("@graph", [graph])
    lists = [n for n in nodes if n.get("@type") == "BreadcrumbList"]
    return [i["name"] for i in lists[0]["itemListElement"]] if lists else None


def test_starter_demo_visible_crumbs_equal_jsonld_on_every_page(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    # подпись в меню отличается от h1 и у раздела, и у страницы в нём
    child = tmp_path / "demo/content/en/structure/categories.md"
    text = child.read_text(encoding="utf-8")
    if "\nnav_title:" in text:
        text = re.sub(r"\nnav_title: .*", '\nnav_title: "Cats"', text, count=1)
    else:
        text = text.replace("\nh1:", '\nnav_title: "Cats"\nh1:', 1)
    assert 'nav_title: "Cats"' in text
    child.write_text(text, encoding="utf-8")
    out = tmp_path / "dist"
    result = CliRunner().invoke(main, ["build", "demo", "--env", "prod", "--out", str(out)])
    assert result.exit_code == 0, result.output
    checked = 0
    for path in sorted(out.rglob("*.html")):
        page = path.read_text(encoding="utf-8")
        visible = VISIBLE.search(page)
        graphs = [json.loads(s) for s in LD.findall(page)]
        marked = next((n for n in map(_crumb_names, graphs) if n), None)
        if visible is None:
            # 404 (ответ с кодом 404, в индекс не идёт) рисуется без крошек
            assert marked is None or "404" in path.relative_to(out).as_posix(), path
            continue
        shown = [html.unescape((a or b).strip()) for a, b in LABEL.findall(visible.group(1))]
        assert marked == shown, path
        checked += 1
    assert checked >= 3
