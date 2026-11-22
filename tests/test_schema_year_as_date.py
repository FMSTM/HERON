"""Год числом в свойстве-дате (выпуск 0.3.1, обратная совместимость с сайтами 0.1).

Сайт 0.1 держит `organization.since: 2011` (целое YAML) и пишет в разметку
`foundingDate: "{{ organization.since }}"`. Подстановка на всё значение отдаёт
число, а валидатор 0.3 счёл его SCH004 - и prod-сборка, проходившая на 0.1,
упала. Правило: четырёхзначный год целым числом (1000-9999, не bool) в свойстве,
чей диапазон включает Date или DateTime и не включает числа, допустим; в JSON-LD
он выводится строкой `"2011"`. Остальные числа в датах - по-прежнему SCH004.
"""

from __future__ import annotations

import json
import re

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.core import tree
from heron.modules import jsonld
from heron.schemaorg import vocab
from heron.schemaorg.validate import validate
from tests import sites

# --- валидатор -------------------------------------------------------------------------


def _codes(node):
    return [(f.code, f.path) for f in validate(node).findings]


@pytest.mark.parametrize(
    ("kind", "prop"),
    [
        ("Organization", "foundingDate"),
        ("Organization", "dissolutionDate"),
        ("Person", "birthDate"),
        ("Article", "datePublished"),
        ("Article", "dateModified"),
        ("Event", "startDate"),
    ],
)
def test_year_int_in_date_property_passes(kind, prop):
    assert _codes({"@type": kind, prop: 2011}) == []


@pytest.mark.parametrize("value", [5, 999, 10000, 20111, 2011.5, 2011.0, -2011])
def test_other_numbers_in_date_property_stay_sch004(value):
    assert _codes({"@type": "Organization", "foundingDate": value}) == [("SCH004", "foundingDate")]


def test_bool_in_date_property_stays_sch004():
    assert _codes({"@type": "Organization", "foundingDate": True}) == [("SCH004", "foundingDate")]


def test_string_year_still_passes():
    assert _codes({"@type": "Organization", "foundingDate": "2011"}) == []


def test_year_in_list_and_nested_node():
    node = {
        "@type": "Organization",
        "founder": {"@type": "Person", "birthDate": 1970},
        "foundingDate": [2011],
    }
    assert _codes(node) == []


def test_numeric_ranged_property_is_not_touched():
    # merchantReturnDays: Date | DateTime | Integer - число там законно само по себе.
    assert vocab().year_as_date("merchantReturnDays", 2011) is False
    assert vocab().year_as_date("foundingDate", 2011) is True
    assert vocab().year_as_date("foundingDate", True) is False
    assert vocab().year_as_date("numberOfEmployees", 2011) is False


# --- JSON-LD ---------------------------------------------------------------------------


def _entity(tmp_path, entity, **extra):
    content = sites.build(tmp_path, {"uk/index.md": sites.page("Головна")})
    config = sites.config(schema={"entity": entity}, **extra)
    site, _ = tree.scan(content, config)
    return config, site


def test_whole_value_substitution_writes_string(tmp_path):
    config, site = _entity(
        tmp_path,
        {
            "@type": "Organization",
            "foundingDate": "{{ organization.since }}",
            "numberOfEmployees": "{{ organization.staff }}",
        },
        organization={"since": 2011, "staff": 12},
    )
    node = jsonld.entity(config, "uk", site)
    assert node["foundingDate"] == "2011"
    # другое числовое свойство остаётся числом
    assert node["numberOfEmployees"] == 12
    assert validate(node).findings == []


def test_literal_int_writes_string_in_page_graph(tmp_path):
    config, site = _entity(
        tmp_path,
        {
            "@type": "Organization",
            "foundingDate": 2011,
            "founder": {"@type": "Person", "birthDate": 1970},
        },
    )
    theme = sites.theme(types={"page": {"uses": [], "jsonld": ["WebPage"]}})
    page = site.pages[0]
    text = jsonld.render(page, config, theme, site)
    data = json.loads(text)
    nodes = data.get("@graph", [data])
    org = next(n for n in nodes if n.get("@type") == "Organization")
    assert org["foundingDate"] == "2011"
    assert org["founder"]["birthDate"] == "1970"


def test_non_year_number_is_left_alone(tmp_path):
    config, site = _entity(tmp_path, {"@type": "Organization", "foundingDate": 20111})
    node = jsonld.entity(config, "uk", site)
    assert node["foundingDate"] == 20111
    assert ("SCH004", "foundingDate") in _codes(node)


def test_string_year_is_left_alone(tmp_path):
    config, site = _entity(tmp_path, {"@type": "Organization", "foundingDate": "2011"})
    assert jsonld.entity(config, "uk", site)["foundingDate"] == "2011"


# --- prod-сборка сайта 0.1 ------------------------------------------------------------


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    created = CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"])
    assert created.exit_code == 0, created.output
    path = tmp_path / "demo" / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["organization"] = {"since": 2011}
    data["schema"] = {
        **(data.get("schema") or {}),
        "entity": {
            "@type": "Organization",
            "@id": "#org",
            "name": "Demo",
            "foundingDate": "{{ organization.since }}",
        },
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert "since: 2011\n" in path.read_text(encoding="utf-8")
    return tmp_path / "demo"


def test_prod_build_of_01_site_with_year_passes(legacy, tmp_path):
    out = tmp_path / "dist"
    result = CliRunner().invoke(main, ["build", str(legacy), "--env", "prod", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "SCH004" not in result.output
    html = (out / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert scripts
    assert '"foundingDate": "2011"' in "".join(scripts)
