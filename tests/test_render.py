"""Рендеринг: окружение, макросы модулей, строки интерфейса."""

import pytest

from heron.core import links, tree
from heron.core.errors import Collector, HeronError
from heron.core.render import env as envmod
from heron.core.render import pages as render
from tests import sites

FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/bio.md": (
        "---\ntitle: Біографія\nh1: Про мене\ndescription: Опис\n---\n\n"
        "## Що це {#what}\n\nАбзац тексту.\n\n"
        "## Коротко {#quick-facts}\n\nСтаж | 27 років\nОперацій | 9000\n"
    ),
}


def prepared(tmp_path, files=None, templates=None, strings=None, **over):
    content = sites.build(tmp_path, files or FILES)
    config = sites.config(**over)
    theme_path = sites.theme_dir(tmp_path, templates=templates, strings=strings)
    site, collector = tree.scan(content, config)
    theme = sites.theme()
    links.resolve(site, config, theme, collector)
    return theme_path, site, config, theme, collector


def test_page_renders_with_sections(tmp_path):
    theme_path, site, config, theme, collector = prepared(
        tmp_path,
        **{
            "site": {
                "domain": "example.com",
                "theme": "demo",
                "default_lang": "uk",
                "languages": ["uk"],
            }
        },
    )
    html = render.render_site(theme_path, site, config, theme, collector)
    assert not collector.failed
    bio = html["/bio/"]
    assert "<h1>Про мене</h1>" in bio
    assert "Абзац тексту" in bio
    assert "<dt>Стаж</dt><dd>27 років</dd>" in bio


def test_missing_section_renders_nothing(tmp_path):
    theme_path, site, config, theme, collector = prepared(tmp_path)
    html = render.render_site(theme_path, site, config, theme, collector)
    home = html["/"]
    assert "<dl>" not in home  # quick-facts на главной нет
    assert "prose" in home  # what есть


def test_interface_strings_come_from_theme(tmp_path):
    theme_path, site, config, theme, collector = prepared(tmp_path)
    html = render.render_site(theme_path, site, config, theme, collector)
    assert "Записатися" in html["/"]


def test_missing_string_warns_and_shows_key(tmp_path):
    theme_path, site, config, theme, collector = prepared(tmp_path, strings={})
    html = render.render_site(theme_path, site, config, theme, collector)
    assert "book_now" in html["/"]
    assert any("book_now" in w.message for w in collector.warnings)
    assert not collector.failed


def test_absolute_url_helper(tmp_path):
    theme_path, site, config, theme, collector = prepared(tmp_path)
    html = render.render_site(theme_path, site, config, theme, collector)
    assert 'href="https://example.com/bio/"' in html["/bio/"]


def test_missing_template_for_type_is_e008(tmp_path):
    theme_path, site, config, theme, collector = prepared(
        tmp_path, templates={"home.html": sites.PAGE_TEMPLATE}
    )
    render.render_site(theme_path, site, config, theme, collector)
    assert [e.code for e in collector.errors] == ["E008"]
    assert "page" in str(collector.errors[0])


def test_missing_module_template_is_e008(tmp_path):
    tpl = '{% extends "base.html" %}{% block content %}{{ mod.gallery("what") }}{% endblock %}'
    theme_path, site, config, theme, collector = prepared(
        tmp_path, templates={"page.html": tpl, "home.html": tpl}
    )
    render.render_site(theme_path, site, config, theme, collector)
    assert collector.failed
    assert all(e.code == "E008" for e in collector.errors)
    assert "gallery" in str(collector.errors[0])


def test_typo_in_template_is_e010(tmp_path):
    tpl = '{% extends "base.html" %}{% block content %}{{ page.h2 }}{% endblock %}'
    theme_path, site, config, theme, collector = prepared(
        tmp_path, templates={"page.html": tpl, "home.html": tpl}
    )
    render.render_site(theme_path, site, config, theme, collector)
    assert collector.failed
    assert collector.errors[0].code == "E010"


def test_content_is_escaped_but_section_html_is_not(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/x.md": (
            "---\ntitle: 'Лапки \"та\" <кут>'\nh1: 'Лапки \"та\" <кут>'\n"
            "description: Опис\n---\n\n## Що {#what}\n\n**Жирний** текст.\n"
        ),
    }
    theme_path, site, config, theme, collector = prepared(tmp_path, files=files)
    html = render.render_site(theme_path, site, config, theme, collector)
    page = html["/x/"]
    assert "&lt;кут&gt;" in page
    assert "<strong>Жирний</strong>" in page


def test_strings_object_behaves_like_mapping():
    collector = Collector()
    strings = envmod.Strings({"a": "А"}, "uk", collector)
    assert strings.a == "А"
    assert strings["a"] == "А"
    assert "a" in strings
    assert strings.b == "b"
    assert len(collector.warnings) == 1
    assert strings.b == "b"  # повторный промах не плодит предупреждений
    assert len(collector.warnings) == 1


def test_render_page_raises_for_unknown_type(tmp_path):
    theme_path, site, config, theme, collector = prepared(tmp_path)
    page = site.by_url["/bio/"]
    page.type = "нет-такого"
    env = envmod.make(theme_path, config)
    strings = envmod.load_strings(theme_path, "uk", collector)
    with pytest.raises(HeronError) as exc:
        render.render_page(env, page, site, config, theme, strings, collector)
    assert exc.value.code == "E008"
