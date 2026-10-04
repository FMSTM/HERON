"""Ключи конфига: analytics, seo.llms_note, links[].required.

Спецификация: docs/spec/20-data-contract.md, разделы 5 и 6.
"""

from __future__ import annotations

import pytest
import yaml

from heron.contracts.site import SiteConfig
from heron.core import build as pipeline
from heron.core import links, tree
from heron.core.environment import BuildEnv
from heron.scaffold import create
from tests import sites


def test_analytics_unknown_key_fails():
    with pytest.raises(ValueError):
        SiteConfig.model_validate(
            {
                "heron": ">=0.1",
                "site": {"domain": "x.org", "theme": "t"},
                "analytics": {"ga4": "G-1", "piwik": "7"},
            }
        )


def test_metrika_number_becomes_text():
    cfg = SiteConfig.model_validate(
        {"heron": ">=0.1", "site": {"domain": "x.org", "theme": "t"}, "analytics": {"metrika": 7}}
    )
    assert cfg.analytics.metrika == "7"


def _site(tmp_path, extra: dict):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    for block, values in extra.items():
        conf.setdefault(block, {})
        conf[block] = {**(conf[block] or {}), **values}
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), encoding="utf-8")
    (root / "content" / "uk" / "index.md").write_text(
        "---\ntitle: Г\nh1: Головна\ndescription: Опис головної\n---\n\nТекст.\n",
        encoding="utf-8",
    )
    (root / "content" / "uk" / "a.md").write_text(
        "---\ntitle: А\nh1: Сторінка\ndescription: Опис\n---\n\nТекст.\n", encoding="utf-8"
    )
    return root


def test_counters_only_in_prod_and_no_metrika_in_scaffold(tmp_path):
    root = _site(tmp_path, {"analytics": {"ga4": "G-TEST1", "gtm": "GTM-TEST2"}})
    assert "metrika" not in (root / "site.yaml").read_text(encoding="utf-8")

    pipeline.run(root, env=BuildEnv.named("dev"))
    dev = (root / "dist" / "index.html").read_text(encoding="utf-8")
    assert "G-TEST1" not in dev and "GTM-TEST2" not in dev

    pipeline.run(root, env=BuildEnv.named("prod"))
    prod = (root / "dist" / "index.html").read_text(encoding="utf-8")
    assert "G-TEST1" in prod and "GTM-TEST2" in prod
    assert "mc.yandex.ru" not in prod


def test_llms_note_lands_in_llms_txt(tmp_path):
    note = "### Як звʼязатися\n\nТелефон: +00 000 000 00 00."
    root = _site(tmp_path, {"seo": {"llms_note": {"uk": note}}})
    assert not pipeline.run(root).failed
    text = (root / "dist" / "llms.txt").read_text(encoding="utf-8")
    assert note in text
    # после описания, до перечня страниц
    assert text.index("Опис головної") < text.index(note) < text.index("Сторінка")


def test_required_link_missing_on_its_type_warns(tmp_path):
    files = {
        "uk/index.md": sites.page("Г"),
        "uk/topic/_index.md": sites.page("Теми", children_type="topic"),
        "uk/topic/roofing.md": sites.page("Покрівля"),
        "uk/services/_index.md": sites.page("Послуги", children_type="service"),
        "uk/services/with.md": sites.page("З", topic=["roofing"]),
        "uk/services/without.md": sites.page("Без"),
        "uk/about.md": sites.page("Про"),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    theme = sites.theme(links=[{"field": "topic", "type": "topic", "on": "service", "required": 1}])
    site, collector = tree.scan(content, config)
    links.resolve(site, config, theme, collector)
    said = [w for w in collector.warnings if w.kind == "связи"]
    assert [w.path for w in said] == ["uk/services/without.md"]
    assert "минимум 1" in said[0].message


def test_required_counts_targets_where_field_present(tmp_path):
    files = {
        "uk/index.md": sites.page("Г"),
        "uk/a.md": sites.page("A", related=[]),
        "uk/b.md": sites.page("B", related=["a"]),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    theme = sites.theme(links=[{"field": "related", "required": 2}])
    site, collector = tree.scan(content, config)
    links.resolve(site, config, theme, collector)
    said = [w for w in collector.warnings if w.kind == "связи"]
    # у b одна ссылка из двух; у a поле пустое, а `on` не задан — молчим
    assert [w.path for w in said] == ["uk/b.md"]


def test_bare_on_key_in_theme_yaml_survives_yaml_booleans():
    """`on:` без кавычек YAML читает как true — тема всё равно грузится."""
    from heron.contracts.theme import ThemeConfig

    data = yaml.safe_load("name: t\nlinks:\n  - field: topic\n    on: service\n    required: 1\n")
    theme = ThemeConfig.model_validate(data)
    assert theme.links[0].on == "service"
