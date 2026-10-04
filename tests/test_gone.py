"""410 для адресов, которых больше нет: `gone` в site.yaml.

Спецификация: docs/spec/20-data-contract.md, раздел 5, блок `gone`.
"""

from __future__ import annotations

import pytest
import yaml

from heron.contracts.site import SiteConfig, parse_gone
from heron.core import build as pipeline
from heron.core import tree
from heron.modules import redirects
from heron.scaffold import create
from tests import sites
from tests.nginx_server import needs_nginx, serve

PAGE = "---\ntitle: {t}\nh1: {t}\ndescription: Опис\n{extra}---\n\nТекст.\n"


def make(tmp_path, gone, pages=None):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["gone"] = gone
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), encoding="utf-8")
    pages = pages or {
        "uk/index.md": PAGE.format(t="Головна", extra=""),
        "uk/about.md": PAGE.format(t="Про нас", extra="redirect_from: [/o-nas/]\n"),
    }
    for rel, text in pages.items():
        path = root / "content" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


# --- разбор записей ---------------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "parsed"),
    [
        ("/sample-page/", ("exact", "/sample-page/", "", None)),
        ("/wp/*", ("prefix", "/wp/", "", None)),
        ("/wp-*", ("prefix", "/wp-", "", None)),
        ("/?p=*", ("query", "/", "p", None)),
        ("/?p=12", ("query", "/", "p", "12")),
        ("/feed/?page_id=*", ("query", "/feed/", "page_id", None)),
    ],
)
def test_entry_forms(entry, parsed):
    assert parse_gone(entry) == parsed


@pytest.mark.parametrize(
    "entry", ["sample-page/", "/a/*/b/", "/?p", "/?a=1&b=2", "/*?p=1", "/?p=1*", "/a/#x"]
)
def test_bad_entries_fail_config(entry):
    with pytest.raises(ValueError):
        SiteConfig.model_validate(
            {"heron": ">=0.1", "site": {"domain": "x.org", "theme": "t"}, "gone": [entry]}
        )


# --- пересечения ------------------------------------------------------------


def _collect(tmp_path, gone, files):
    content = sites.build(tmp_path, files)
    config = sites.config(gone=gone)
    site, collector = tree.scan(content, config)
    return redirects.collect(site, collector, config), collector


def test_exact_gone_on_page_address_is_e022(tmp_path):
    _, collector = _collect(
        tmp_path, ["/about/"], {"uk/index.md": sites.page("Г"), "uk/about.md": sites.page("A")}
    )
    assert [e.code for e in collector.errors] == ["E022"]


def test_prefix_covering_page_is_e022(tmp_path):
    _, collector = _collect(
        tmp_path, ["/ab*"], {"uk/index.md": sites.page("Г"), "uk/about.md": sites.page("A")}
    )
    assert [e.code for e in collector.errors] == ["E022"]


def test_gone_crossing_redirect_from_is_e022(tmp_path):
    _, collector = _collect(
        tmp_path,
        ["/old/*"],
        {"uk/index.md": sites.page("Г"), "uk/a.md": sites.page("A", redirect_from=["/old/x/"])},
    )
    assert [e.code for e in collector.errors] == ["E022"]
    assert "/old/x/" in str(collector.errors[0])


def test_duplicate_is_a_warning(tmp_path):
    plan, collector = _collect(tmp_path, ["/x/", "/x/"], {"uk/index.md": sites.page("Г")})
    assert not collector.failed
    assert plan.gone == ["/x/"]
    assert any("дважды" in w.message for w in collector.warnings)


def test_query_entry_does_not_close_home(tmp_path):
    plan, collector = _collect(tmp_path, ["/?p=*"], {"uk/index.md": sites.page("Г")})
    assert not collector.failed
    assert plan.gone_queries == [("/", "p", None)]


def test_page_level_gone_still_works_but_warns(tmp_path):
    plan, collector = _collect(tmp_path, [], {"uk/index.md": sites.page("Г", gone=["/forum/"])})
    assert plan.gone == ["/forum/"]
    assert any("устарело" in w.message for w in collector.warnings)


# --- сборка и nginx ----------------------------------------------------------


def test_overlap_stops_the_build(tmp_path):
    root = make(tmp_path, ["/about/"])
    result = pipeline.run(root)
    assert result.failed
    assert [e.code for e in result.collector.errors] == ["E022"]


def test_config_carries_the_maps(tmp_path):
    root = make(tmp_path, ["/sample-page/", "/wp/*", "/?p=*"])
    result = pipeline.run(root)
    assert not result.failed
    conf = (root / "dist" / ".heron-nginx.conf").read_text(encoding="utf-8")
    assert "map $uri $heron_gone" in conf
    assert '"/sample-page/" 1;' in conf
    assert "return 410;" in conf
    assert "return 301 $heron_moved;" in conf


@needs_nginx
def test_nginx_answers_410_301_and_200(tmp_path):
    root = make(tmp_path, ["/sample-page/", "/wp/*", "/?p=*", "/?page_id=7"])
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:
        assert get("/sample-page/")[0] == 410
        assert get("/wp/")[0] == 410
        assert get("/wp/anything/deep/")[0] == 410
        assert get("/wp/wp-login.php")[0] == 410
        assert get("/?p=123")[0] == 410
        assert get("/?utm=1&p=5")[0] == 410
        assert get("/?page_id=7")[0] == 410
        assert get("/?page_id=8")[0] == 200
        assert get("/")[0] == 200
        assert get("/about/")[0] == 200
        assert get("/o-nas/") == (301, "/about/")
        assert get("/nope/")[0] == 404
