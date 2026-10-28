"""Политика проверки разметки: происхождение находок, строгость, исключения."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from heron.contracts.site import SchemaException
from heron.core import build as pipeline
from heron.core import tree
from heron.core.environment import BuildEnv
from heron.core.errors import Collector
from heron.core.report import schema_lines
from heron.modules import jsonld
from heron.scaffold import create
from heron.schemaorg import policy
from tests import sites

TODAY = date(2026, 10, 28)
KEY = "SCH002:site.yaml:schema.entity.worksFor"
ENTITY = {"entity": {"@type": "IndividualPhysician", "@id": "#me", "worksFor": "Клиника"}}


def _run(
    tmp_path,
    schema=None,
    exceptions=(),
    prod=True,
    allow=(),
    page_schema=None,
    jsonld_t=("WebPage",),
):
    files = {
        "uk/index.md": sites.page("Головна", **({"schema": page_schema} if page_schema else {})),
        "uk/a.md": sites.page("А"),
        "uk/b.md": sites.page("Б"),
    }
    content = sites.build(tmp_path, files)
    over = {"schema_exceptions": list(exceptions)}
    if schema:
        over["schema"] = schema
    site_ = {"domain": "example.com", "theme": "demo", "default_lang": "uk", "languages": ["uk"]}
    config = sites.config(site=site_, **over)
    site, _ = tree.scan(content, config)
    theme = sites.theme(types={"page": {"uses": [], "jsonld": list(jsonld_t)}})
    collector = Collector()
    check = policy.SchemaCheck(prod, list(allow), config.schema_exceptions, TODAY)
    for page in site.pages:
        jsonld.verify(page, config, theme, collector, site, check)
    return check.finish(collector, "ru"), collector, check


def test_prod_error_with_key_in_hint(tmp_path):
    section, collector, check = _run(tmp_path, ENTITY)
    assert [e.code for e in collector.errors] == ["SCH002"]
    error = collector.errors[0]
    assert error.path == "site.yaml"
    assert KEY in error.hint
    assert section.findings[0].key == KEY
    assert section.findings[0].pages == 3  # одна находка с трёх страниц


def test_dev_warning_not_error(tmp_path):
    section, collector, _ = _run(tmp_path, ENTITY, prod=False)
    assert not collector.errors
    head = "SCH002 site.yaml:schema.entity.worksFor"
    assert any(w.message.startswith(head) and w.kind == "schema.org" for w in collector.warnings)


def test_exception_passes_prod_and_reported(tmp_path):
    exc = SchemaException(key=KEY, reason="так надо", until=TODAY + timedelta(days=5))
    section, collector, _ = _run(tmp_path, ENTITY, [exc])
    assert not collector.errors and not collector.warnings
    assert section.excepted[0].reason == "так надо"
    text = "\n".join(schema_lines(section, "ru"))
    assert "Исключения разметки: 1" in text and "так надо" in text


def test_unused_exception_warns(tmp_path):
    good = SchemaException(key=KEY, reason="r")
    stale = SchemaException(key="SCH001:site.yaml:schema.entity.@type", reason="r")
    section, collector, _ = _run(tmp_path, ENTITY, [good, stale])
    assert section.unused == [stale.key]
    assert any("Лишнее исключение" in w.message for w in collector.warnings)


def test_expired_exception_fails_again(tmp_path):
    exc = SchemaException(key=KEY, reason="r", until=TODAY - timedelta(days=1))
    section, collector, _ = _run(tmp_path, ENTITY, [exc])
    assert [e.code for e in collector.errors] == ["SCH002"]
    assert any("Исключение просрочено" in w.message for w in collector.warnings)
    assert section.expired


def test_allow_flag_excepts_once(tmp_path):
    section, collector, _ = _run(tmp_path, ENTITY, allow=[KEY])
    assert not collector.errors
    assert section.excepted[0].source == "flag"


def test_unused_allow_flag_warns(tmp_path):
    section, collector, _ = _run(tmp_path, None, allow=[KEY])
    assert section.unused == [KEY]


def test_origin_page_frontmatter(tmp_path):
    section, collector, _ = _run(tmp_path, page_schema={"WebPage": {"bogusProp": "x"}})
    entry = section.findings[0]
    assert entry.file.endswith("index.md")
    assert entry.path == "schema.WebPage.bogusProp"


def test_origin_site_yaml_shared_kind(tmp_path):
    section, _, _ = _run(tmp_path, {"WebPage": {"bogusProp": "x"}})
    assert section.findings[0].key == "SCH002:site.yaml:schema.WebPage.bogusProp"


def test_origin_theme_type(tmp_path):
    section, _, _ = _run(tmp_path, jsonld_t=("NoSuchType",))
    assert section.findings[0].key == "SCH001:theme.yaml:types.page.jsonld.0"


def test_core_nodes_clean(tmp_path):
    section, collector, _ = _run(tmp_path, jsonld_t=("WebPage", "WebSite"))
    assert section.findings == [] and not collector.errors and section.nodes > 0


def _config(schema, exceptions=()):
    return sites.config(
        site={
            "domain": "example.com",
            "theme": "demo",
            "default_lang": "uk",
            "languages": ["uk", "en"],
        },
        schema=schema,
        schema_exceptions=list(exceptions),
    )


def test_site_findings_entity():
    result = policy.site_findings(_config(ENTITY), today=TODAY)
    assert [e.key for e in result.active] == [KEY]
    assert result.active[0].detail("ru") and result.active[0].hint("en")


def test_site_findings_excepted():
    exc = SchemaException(key=KEY, reason="r")
    result = policy.site_findings(_config(ENTITY, [exc]), today=TODAY)
    assert result.active == [] and len(result.excepted) == 1


def test_site_findings_shared_website_clean():
    result = policy.site_findings(_config({"WebSite": {"alternateName": "X"}}), today=TODAY)
    assert result.active == []


# --- через heron.core.build.check на настоящем скелете (heron new) ---

HOME = "---\ntitle: Демо - коротко о сайте\nh1: Демо\ndescription: Коротко\n---\n\nТекст.\n"
ABOUT = "---\ntitle: О нас - подробно\nh1: О нас\ndescription: Страница о нас\n---\n\nТекст.\n"


@pytest.fixture
def scaffold(tmp_path, monkeypatch):
    monkeypatch.delenv("SITE_ENV", raising=False)
    epoch = int(datetime(2026, 10, 28, tzinfo=UTC).timestamp())
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(epoch))
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(HOME, encoding="utf-8")
    (root / "content" / "uk" / "about.md").write_text(ABOUT, encoding="utf-8")
    return root


def _site_yaml(root, extra: str) -> None:
    path = root / "site.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")


ENTITY_YAML = "schema:\n  entity:\n    \"@type\": IndividualPhysician\n    worksFor: Клиника\n"


def _check(root, env=None, allow=()):
    return pipeline.check(root, env=env, allow_schema=allow)


def test_scaffold_core_nodes_have_no_findings(scaffold):
    result = _check(scaffold, env=BuildEnv.named("prod"))
    section = result.report.schema
    assert section.findings == [] and section.nodes > 0
    assert not [e for e in result.collector.errors if e.code.startswith("SCH")]


def test_check_without_site_env_gives_warnings(scaffold):
    _site_yaml(scaffold, ENTITY_YAML)
    result = _check(scaffold, env=None)
    assert not [e for e in result.collector.errors if e.code.startswith("SCH")]
    head = "SCH002 site.yaml:schema.entity.worksFor"
    assert any(w.message.startswith(head) for w in result.collector.warnings)
    assert result.report.schema.findings[0].pages >= 2  # одна находка со всех страниц


def test_check_prod_gives_error_with_key(scaffold):
    _site_yaml(scaffold, ENTITY_YAML)
    result = _check(scaffold, env=BuildEnv.named("prod"))
    errors = [e for e in result.collector.errors if e.code == "SCH002"]
    assert len(errors) == 1 and errors[0].path == "site.yaml" and KEY in errors[0].hint
    assert result.report.schema.as_json()["findings"][0]["severity"] == "error"


def test_check_prod_exception_unused_and_expired(scaffold):
    _site_yaml(
        scaffold,
        ENTITY_YAML
        + "schema_exceptions:\n"
        + f"  - key: \"{KEY}\"\n    reason: пока без клиники\n"
        + "  - key: \"SCH001:site.yaml:schema.entity\"\n    reason: лишнее\n",
    )
    result = _check(scaffold, env=BuildEnv.named("prod"))
    assert not [e for e in result.collector.errors if e.code.startswith("SCH")]
    data = result.report.schema.as_json()
    assert data["excepted"][0]["key"] == KEY and data["excepted"][0]["reason"] == "пока без клиники"
    assert data["unused"] == ["SCH001:site.yaml:schema.entity"]
    assert any("SCH001:site.yaml:schema.entity" in w.message for w in result.collector.warnings)


def test_check_prod_expired_exception_fails_again(scaffold):
    expired = f"schema_exceptions:\n  - key: \"{KEY}\"\n    reason: r\n    until: 2026-10-27\n"
    _site_yaml(scaffold, ENTITY_YAML + expired)
    result = _check(scaffold, env=BuildEnv.named("prod"))
    codes = [e.code for e in result.collector.errors if e.code.startswith("SCH")]
    assert codes == ["SCH002"]
    assert result.report.schema.expired[0].key == KEY


def test_check_allow_schema_flag(scaffold):
    _site_yaml(scaffold, ENTITY_YAML)
    result = _check(scaffold, env=BuildEnv.named("prod"), allow=[KEY])
    assert not [e for e in result.collector.errors if e.code.startswith("SCH")]
    assert result.report.schema.excepted[0].source == "flag"
