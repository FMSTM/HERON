"""Поля фронтматтера, тип одиночной страницы и ключ главной.

Спецификация: docs/spec/20-data-contract.md, раздел 4.2.
"""

from __future__ import annotations

import re
from pathlib import Path

from heron.contracts.frontmatter import PageMeta
from heron.core import build as pipeline
from heron.core import links, tree
from heron.modules import jsonld
from heron.scaffold import create
from tests import sites

SPEC = Path(__file__).resolve().parents[1] / "docs" / "spec" / "20-data-contract.md"


def _documented_fields() -> set[str]:
    text = SPEC.read_text(encoding="utf-8")
    table = text[text.index("### 4.2 Фронтматтер") : text.index("#### Тип страницы")]
    names: set[str] = set()
    for line in table.splitlines():
        if line.startswith("| `"):
            first = line.split("|")[1]
            names.update(re.findall(r"`([a-z0-9_]+)`", first))
    return names


def test_every_core_field_is_in_the_table():
    """Таблица 20 §4.2 и модель не расходятся: поле в коде — строка в доках."""
    assert set(PageMeta.model_fields) <= _documented_fields()


def test_single_page_with_own_type_uses_its_template(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    content = root / "content" / "uk"
    (content / "index.md").write_text(
        "---\ntitle: Г\nh1: Головна\ndescription: О\n---\n\nТекст.\n", encoding="utf-8"
    )
    (content / "about.md").write_text(
        "---\ntitle: Про\nh1: Про нас\ndescription: О\ntype: about\n---\n\nТекст.\n",
        encoding="utf-8",
    )
    templates = root / "theme" / "templates"
    (templates / "about.html").write_text(
        '{% extends "base.html" %}{% block content %}<p class="about-tpl">{{ page.h1 }}</p>'
        "{% endblock %}",
        encoding="utf-8",
    )
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    html = (root / "dist" / "about" / "index.html").read_text(encoding="utf-8")
    assert 'class="about-tpl"' in html
    assert result.site.page("about", "uk").type == "about"


def _scan(tmp_path, nav):
    files = {
        "uk/index.md": sites.page("Головна"),
        "ru/index.md": sites.page("Главная"),
        "uk/about.md": sites.page("Про"),
        "ru/about.md": sites.page("О нас", slug="o-nas"),
    }
    content = sites.build(tmp_path, files)
    config = sites.config(nav={"main": nav})
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site, config, collector


def test_home_in_nav_by_slash_key(tmp_path):
    site, _, collector = _scan(tmp_path, ["/", "about"])
    assert [p.url for p in site.nav["uk"]["main"]] == ["/", "/about/"]
    assert [p.url for p in site.nav["ru"]["main"]] == ["/ru/", "/ru/o-nas/"]
    assert not [w for w in collector.warnings if w.kind == "меню"]


def test_site_page_by_key_and_slash(tmp_path):
    site, _, _ = _scan(tmp_path, [])
    assert site.page("/", "ru").url == "/ru/"
    assert site.page("", "uk").url == "/"
    assert site.page("/about/", "ru").url == "/ru/o-nas/"
    assert site.page("nope", "uk") is None


def test_home_in_schema_substitutions(tmp_path):
    site, config, _ = _scan(tmp_path, [])
    data = jsonld._data(config, "ru", site)
    assert data["pages"]["home"]["url"] == "https://example.com/ru/"
    assert data["pages"]["about"]["url"] == "https://example.com/ru/o-nas/"
    assert "" not in data["pages"]


def test_page_of_in_templates(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk", "ru"])
    for lang, title in (("uk", "Головна"), ("ru", "Главная")):
        (root / "content" / lang / "index.md").write_text(
            f"---\ntitle: {title} сайт\nh1: {title}\ndescription: О\n---\n\nТекст.\n",
            encoding="utf-8",
        )
    home = root / "theme" / "templates" / "home.html"
    home.write_text(
        '{% extends "base.html" %}{% block content %}'
        "<a class=\"home-link\" href=\"{{ page_of('/').url }}\">{{ page_of('/').h1 }}</a>"
        "{% endblock %}",
        encoding="utf-8",
    )
    assert not pipeline.run(root).failed
    ru = (root / "dist" / "ru" / "index.html").read_text(encoding="utf-8")
    assert '<a class="home-link" href="/ru/">Главная</a>' in ru
