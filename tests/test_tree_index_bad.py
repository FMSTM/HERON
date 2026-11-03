"""Негодный _index.md даёт одну ошибку с относительным путём."""

from heron.core import tree
from tests import sites


def _scan(tmp_path, files, raw=None):
    content = sites.build(tmp_path, files)
    for rel, data in (raw or {}).items():
        path = content / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return tree.scan(content, sites.config())


def test_cp1251_index_gives_single_e001(tmp_path):
    raw = {"uk/sec/_index.md": "---\ntitle: Привет\n---\n\nТекст\n".encode("cp1251")}
    _, collector = _scan(
        tmp_path,
        {"uk/index.md": sites.page(), "uk/sec/Bad Name.md": sites.page()},
        raw,
    )
    codes = [e.code for e in collector.errors]
    assert codes.count("E001") == 1
    assert "E005" in codes
    e001 = next(e for e in collector.errors if e.code == "E001")
    assert str(e001.path).endswith("sec/_index.md")
    assert not str(e001.path).startswith("/")


def test_broken_yaml_index_gives_single_e001(tmp_path):
    _, collector = _scan(
        tmp_path,
        {"uk/index.md": sites.page(), "uk/sec/_index.md": "---\ntitle: [oops\n---\n\nx\n"},
    )
    assert [e.code for e in collector.errors].count("E001") == 1


def test_good_index_keeps_slug_and_children_type(tmp_path):
    site, collector = _scan(
        tmp_path,
        {
            "uk/index.md": sites.page(),
            "uk/sec/_index.md": sites.page("Розділ", slug="razdel", children_type="service"),
            "uk/sec/a.md": sites.page("А"),
        },
    )
    assert not collector.failed
    assert "/razdel/a/" in site.by_url
    assert site.by_url["/razdel/a/"].type == "service"
