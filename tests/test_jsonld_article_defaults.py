"""JSON-LD 0.3.1: значения по умолчанию у статьи (Article и подтипы по словарю).

`headline` - h1 страницы целиком (Google длину больше не ограничивает),
`image` - обложка страницы (та же, что og:image), `publisher` - ссылка на
сквозной узел сайта с `@id`. Заданное темой, сайтом или страницей главнее,
явное `null` или `""` выключает значение по умолчанию. Автора движок не
придумывает.
"""

from __future__ import annotations

from typing import Any

from heron.core import tree
from heron.modules import jsonld
from heron.schemaorg.validate import validate
from tests import sites

ENTITY = {"@type": "Organization", "@id": "#org", "name": "Майстерня"}
LONG = "Дуже довгий заголовок статті " * 6


def _node(
    tmp_path, kind="Article", entity=ENTITY, cover=True, schema=None, h1=LONG, site_schema=None
):
    fields: dict[str, Any] = {}
    if schema is not None:
        fields["schema"] = schema
    files = {"uk/index.md": sites.page("Головна"), "uk/a.md": sites.page(h1, **fields)}
    content = sites.build(tmp_path, files)
    shared: dict[str, Any] = dict(site_schema or {})
    if entity is not None:
        shared["entity"] = entity
    config = sites.config(schema=shared) if shared else sites.config()
    site, _ = tree.scan(content, config)
    theme = sites.theme(types={"page": {"uses": [], "jsonld": [kind]}})
    page = next(p for p in site.pages if p.key == "a")
    if cover:
        url = "https://example.com/media/cover-1200.jpg"
        page.cover_of = lambda _p: {"src": "c.jpg", "url": url, "width": 1200, "height": 630}
    graph = jsonld.build(page, config, theme, site)
    node = next(n for n in graph if n.get("@type") == kind)
    return node


def test_article_gets_headline_image_publisher(tmp_path):
    node = _node(tmp_path)
    assert node["headline"] == LONG.strip() or node["headline"] == LONG
    assert len(node["headline"]) > 110  # без обрезки
    assert node["image"] == "https://example.com/media/cover-1200.jpg"
    assert node["publisher"] == {"@id": "https://example.com/#org"}
    assert "author" not in node
    assert validate(node).findings == []


def test_blogposting_subtype_works(tmp_path):
    node = _node(tmp_path, kind="BlogPosting")
    assert {"headline", "image", "publisher"} <= set(node)
    assert validate(node).findings == []


def test_explicit_values_are_kept(tmp_path):
    own = {
        "Article": {
            "headline": "Свій заголовок",
            "image": "https://example.com/own.jpg",
            "publisher": {"@type": "Organization", "name": "Інший"},
        }
    }
    node = _node(tmp_path, schema=own)
    assert node["headline"] == "Свій заголовок"
    assert node["image"] == "https://example.com/own.jpg"
    assert node["publisher"] == {"@type": "Organization", "name": "Інший"}


def test_site_block_values_win_too(tmp_path):
    node = _node(tmp_path, site_schema={"Article": {"headline": "З сайту", "publisher": None}})
    assert node["headline"] == "З сайту"
    assert "publisher" not in node  # явное null в site.yaml тоже выключает


def test_explicit_null_or_empty_opts_out(tmp_path):
    own = {"Article": {"headline": None, "image": "", "publisher": None}}
    node = _node(tmp_path, schema=own)
    assert not {"headline", "image", "publisher"} & set(node)


def test_no_cover_no_image(tmp_path):
    node = _node(tmp_path, cover=False)
    assert "image" not in node and "headline" in node


def test_no_entity_no_publisher(tmp_path):
    assert "publisher" not in _node(tmp_path, entity=None)


def test_entity_without_id_no_publisher(tmp_path):
    entity = {"@type": "Organization", "name": "Майстерня"}
    assert "publisher" not in _node(tmp_path, entity=entity)


def test_entity_of_other_type_no_publisher(tmp_path):
    entity = {"@type": "Place", "@id": "#place", "name": "Місце"}
    assert "publisher" not in _node(tmp_path, entity=entity)


def test_webpage_is_untouched(tmp_path):
    node = _node(tmp_path, kind="WebPage")
    assert not {"headline", "image", "publisher"} & set(node)
