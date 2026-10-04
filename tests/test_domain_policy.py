"""Предметная область — в сайте и теме, не в ядре.

Запрет цен в разметке — решение сайта (`seo.allow_prices`), адрес и
координаты проверяются, только если сквозной узел их объявил, секций предметной
области в контракте ядра нет. Границу ядра по именам сайтов проверяет
scripts/check-boundaries.sh в scripts/check.sh.

Спецификация: docs/spec/20-data-contract.md, раздел 5, «Проверки на сборке».
"""

from __future__ import annotations

import json
from pathlib import Path

from heron.modules import jsonld
from tests import sites
from tests.test_schema_graph import CONTACT, ENTITY, _config, _site

ROOT = Path(__file__).resolve().parents[1]


def _verify(tmp_path, config):
    site, collector = _site(tmp_path, {"uk/index.md": sites.page("Головна")}, config)
    jsonld.verify(site.pages[0], config, sites.theme(), collector)
    return site, collector


def test_prices_refused_by_default(tmp_path):
    entity = {"entity": {**ENTITY["entity"], "priceRange": "$$"}}
    _, collector = _verify(tmp_path, _config(schema=entity))
    assert [e.code for e in collector.errors] == ["E020"]
    assert "allow_prices" in collector.errors[0].hint


def test_prices_allowed_by_site(tmp_path):
    entity = {"entity": {**ENTITY["entity"], "priceRange": "$$"}}
    config = _config(schema=entity, seo={"allow_prices": True})
    site, collector = _verify(tmp_path, config)
    assert not collector.failed
    payload = json.loads(jsonld.render(site.pages[0], config, sites.theme()))
    nodes = payload.get("@graph", [payload])
    assert any(n.get("priceRange") == "$$" for n in nodes)


def test_entity_without_address_keys_is_fine(tmp_path):
    """Сайт без офиса: узел не объявляет адрес — проверять нечего."""
    entity = {"entity": {k: v for k, v in ENTITY["entity"].items() if k not in ("address", "geo")}}
    _, collector = _verify(tmp_path, _config(schema=entity))
    assert not collector.failed


def test_declared_but_empty_address_is_still_e020(tmp_path):
    contact = {k: v for k, v in CONTACT.items() if k != "geo"}
    _, collector = _verify(tmp_path, _config(contact=contact))
    assert [e.code for e in collector.errors] == ["E020"]


def test_no_domain_sections_in_core_contract():
    spec = (ROOT / "docs" / "spec" / "20-data-contract.md").read_text(encoding="utf-8")
    assert "{#prep}" not in spec and "{#bring}" not in spec
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "heron").rglob("*.py"))
    assert '"prep"' not in code and '"bring"' not in code
