"""Обход content/ и построение URL из путей."""

from heron.core import tree
from tests import sites


def scan(tmp_path, files, **over):
    content = sites.build(tmp_path, files)
    config = sites.config(**over)
    return tree.scan(content, config)


def test_url_from_path(tmp_path):
    site, collector = scan(
        tmp_path,
        {
            "uk/index.md": sites.page("Головна"),
            "uk/bio.md": sites.page("Біографія"),
            "uk/services/_index.md": sites.page("Послуги", type="category"),
            "uk/services/consulting.md": sites.page("Консультація"),
        },
    )
    assert not collector.failed
    assert sorted(site.by_url) == ["/", "/bio/", "/services/", "/services/consulting/"]


def test_non_default_language_gets_prefix(tmp_path):
    site, _ = scan(tmp_path, {"uk/index.md": sites.page(), "ru/index.md": sites.page()})
    assert sorted(site.by_url) == ["/", "/ru/"]


def test_home_type_and_index_are_the_same_page(tmp_path):
    site, _ = scan(tmp_path, {"uk/index.md": sites.page("Головна")})
    home = site.by_url["/"]
    assert home.type == "home"
    assert home.key == ""


def test_children_type_inherited_from_folder(tmp_path):
    site, _ = scan(
        tmp_path,
        {
            "uk/services/_index.md": sites.page(
                "Послуги", type="category", children_type="service"
            ),
            "uk/services/consulting.md": sites.page("Консультація"),
        },
    )
    assert site.by_url["/services/"].type == "category"
    assert site.by_url["/services/consulting/"].type == "service"


def test_explicit_type_beats_inheritance(tmp_path):
    site, _ = scan(
        tmp_path,
        {
            "uk/services/_index.md": sites.page("Послуги", children_type="service"),
            "uk/services/special.md": sites.page("Особлива", type="page"),
        },
    )
    assert site.by_url["/services/special/"].type == "page"


def test_slug_override(tmp_path):
    site, _ = scan(tmp_path, {"uk/old-name.md": sites.page("Сторінка", slug="new-name")})
    assert "/new-name/" in site.by_url


def test_bad_filename_is_e005(tmp_path):
    _, collector = scan(tmp_path, {"uk/Плохое_Имя.md": sites.page()})
    assert [e.code for e in collector.errors] == ["E005"]


def test_url_collision_is_e004(tmp_path):
    _, collector = scan(
        tmp_path,
        {"uk/one.md": sites.page("Раз"), "uk/two.md": sites.page("Два", slug="one")},
    )
    assert [e.code for e in collector.errors] == ["E004"]


def test_unpublished_page_is_skipped(tmp_path):
    site, _ = scan(
        tmp_path,
        {"uk/index.md": sites.page(), "uk/draft.md": sites.page("Чернетка", published=False)},
    )
    assert "/draft/" not in site.by_url


def test_missing_language_tree_is_a_warning(tmp_path):
    _, collector = scan(tmp_path, {"uk/index.md": sites.page()})
    assert not collector.failed
    assert any("ru" in w.message for w in collector.warnings)


def test_sections_are_parsed_during_scan(tmp_path):
    site, _ = scan(tmp_path, {"uk/index.md": sites.page()})
    home = site.by_url["/"]
    assert home.has("what")
    assert home.intro is not None and "Вступление" in home.intro.raw


def test_broken_file_does_not_stop_the_walk(tmp_path):
    site, collector = scan(
        tmp_path,
        {"uk/good.md": sites.page("Добра"), "uk/bad.md": "без фронтматтера\n"},
    )
    assert "/good/" in site.by_url
    assert [e.code for e in collector.errors] == ["E001"]


def test_url_helper():
    assert tree.url_for("uk", "uk", []) == "/"
    assert tree.url_for("uk", "uk", ["a", "b"]) == "/a/b/"
    assert tree.url_for("ru", "uk", ["a"]) == "/ru/a/"
