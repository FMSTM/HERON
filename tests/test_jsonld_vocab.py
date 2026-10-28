"""JSON-LD движка: базовые свойства узла только у типов, которым их разрешает schema.org."""

from __future__ import annotations

import shutil

import pytest

from heron.core import build as pipeline
from heron.core import links, tree
from heron.core.environment import BuildEnv
from heron.modules import jsonld
from heron.scaffold import create
from tests import sites
from tests.test_agent_docs import TEMPLATES, _png

FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/bio.md": sites.page("Біо", date="2026-08-01", updated="2026-09-01"),
}


@pytest.fixture
def built(tmp_path):
    content = sites.build(tmp_path, FILES)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site, config


def _node(built, kind):
    site, config = built
    theme = sites.theme(types={"page": {"uses": [], "jsonld": [kind]}})
    return jsonld.build(site.by_url["/bio/"], config, theme)[0]


def test_service_has_no_language_or_dates(built):
    node = _node(built, "Service")
    assert node["@type"] == "Service"
    for prop in ("inLanguage", "datePublished", "dateModified"):
        assert prop not in node
    assert node["name"] and node["url"] == "https://example.com/bio/"
    assert "description" in node


def test_article_keeps_language_and_dates(built):
    node = _node(built, "Article")
    assert node["inLanguage"] == "uk"
    assert node["datePublished"].startswith("2026-08-01")
    assert node["dateModified"].startswith("2026-09-01")


def test_website_keeps_language(built):
    assert _node(built, "WebSite")["inLanguage"] == "uk"


def test_unknown_type_behaves_as_before(built):
    node = _node(built, "NoSuchType")
    assert node["inLanguage"] == "uk"
    assert "dateModified" in node


def test_site_from_templates_has_no_schema_findings(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    shutil.copy(TEMPLATES / "site.yaml", root / "site.yaml")
    create(root, name="demo", languages=["en", "ru"])
    shutil.copy(TEMPLATES / "theme.yaml", root / "theme" / "theme.yaml")
    templates = root / "theme" / "templates"
    page_tpl = (templates / "page.html").read_text(encoding="utf-8")
    for kind in ("service", "category", "article"):
        (templates / f"{kind}.html").write_text(page_tpl, encoding="utf-8")
    for name in ("default.png", "default-ru.png"):
        _png(root / "media" / "og" / name)
    head = "---\ntitle: {t}\nh1: {h}\ndescription: Description\n{x}---\n\nText.\n"
    files = {
        "en/index.md": head.format(t="Site home", h="Home", x=""),
        "ru/index.md": head.format(t="Главная сайта", h="Главная", x=""),
        "en/404.md": head.format(t="Not found", h="No such page", x=""),
        "ru/404.md": head.format(t="Не найдено", h="Страницы нет", x=""),
        "en/services/_index.md": head.format(
            t="Catalog", h="Our catalog", x="children_type: service\n"
        ),
        "en/services/design.md": (TEMPLATES / "page.md").read_text(encoding="utf-8"),
        "en/services/planning.md": head.format(t="Planning", h="Space planning", x=""),
    }
    for rel, text in files.items():
        path = root / "content" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = pipeline.run(root, env=BuildEnv.named("prod"), strict=True)
    found = [str(f) for f in (*result.collector.errors, *result.collector.warnings)]
    assert not [f for f in found if "SCH0" in f], found
    # strict в песочнице падает на предупреждениях о датах без git-истории (не SCH):
    # обычный prod обязан собраться.
    assert not pipeline.run(root, env=BuildEnv.named("prod")).failed
