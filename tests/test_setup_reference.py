"""Приёмка S5, часть A: анкета на данных эталона даёт ту же разметку, что ручная."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from heron.contracts.site import SiteConfig
from heron.modules import jsonld
from heron.schemaorg.validate import validate
from heron.setup.answers import Answers, merge, read

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures" / "doctor"

_spec = importlib.util.spec_from_file_location(
    "extract_entity", HERE / "tools" / "extract_entity.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def _manual() -> dict[str, Any]:
    return yaml.safe_load((FIXTURES / "site-manual.yaml").read_text(encoding="utf-8"))


def _configs() -> tuple[SiteConfig, SiteConfig]:
    manual = _manual()
    bare = copy.deepcopy(manual)
    del bare["schema"]["entity"]
    answers = Answers.model_validate(
        json.loads((FIXTURES / "answers.json").read_text(encoding="utf-8"))
    )
    setup = merge(bare, answers, manual["heron"])
    return SiteConfig.model_validate(manual), SiteConfig.model_validate(setup)


@pytest.mark.parametrize("lang", ["uk", "en"])
def test_setup_matches_manual(lang: str):
    config_manual, config_setup = _configs()
    a = jsonld.entity(config_manual, lang)
    b = jsonld.entity(config_setup, lang)
    assert a is not None and b is not None
    assert tool.compare(a, b) == []
    assert tool.normalize(a, keep_url="url" in a) == tool.normalize(b, keep_url="url" in a)


@pytest.mark.parametrize("lang", ["uk", "en"])
def test_setup_markup_valid(lang: str):
    _, config_setup = _configs()
    b = jsonld.entity(config_setup, lang)
    assert b is not None
    assert validate(b).findings == []


def test_compare_reports_difference():
    config_manual, config_setup = _configs()
    a = jsonld.entity(config_manual, "uk")
    b = copy.deepcopy(jsonld.entity(config_setup, "uk"))
    assert a is not None and b is not None
    b["telephone"] = "+00 111"
    diffs = tool.compare(a, b)
    assert len(diffs) == 1 and diffs[0].startswith("telephone")


def test_normalize_rules():
    node = {
        "@type": "IndividualPhysician",
        "@id": "https://example.org/#x",
        "image": {"@type": "ImageObject"},
        "url": "https://example.org/",
        "medicalSpecialty": ["b", "a"],
        "sameAs": ["https://a"],
        "geo": {"latitude": 1, "longitude": 2.5},
    }
    other = {
        "@type": "IndividualPhysician",
        "@id": "#other",
        "medicalSpecialty": ["a", "b"],
        "sameAs": "https://a",
        "geo": {"latitude": 1.0, "longitude": 2.5},
    }
    assert tool.normalize(node, keep_url=False) == tool.normalize(other, keep_url=False)
    assert "url" in tool.normalize(node, keep_url=True)
    assert tool.compare(other, node) == []  # url нет в первом - игнорируется


def test_extract_graph(tmp_path: Path):
    page = tmp_path / "index.html"
    graph = {"@graph": [{"@type": "WebSite"}, {"@type": "IndividualPhysician", "name": "X"}]}
    page.write_text(
        f'<html><script type="application/ld+json">{json.dumps(graph)}</script></html>',
        encoding="utf-8",
    )
    assert tool.extract(page)["name"] == "X"
    page.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(LookupError):
        tool.extract(page)


def test_read_keeps_manual_practices_node():
    from heron.setup.answers import classifier

    manual = _manual()
    answers = read(manual)
    fields = answers.about.fields
    assert fields["practices_at_type"] == "Hospital"
    assert fields["practices_at"] == "City Hospital"
    assert fields["practices_at_street"] == "Hospital street 5"
    assert fields["practices_at_city"] == "Example City"
    assert fields["practices_at_postal_code"] == "00001"
    saved = merge(manual, answers, manual["heron"])
    practices = saved["schema"]["entity"]["practicesAt"]
    assert practices["name"] == "City Hospital"
    assert practices["address"]["streetAddress"] == "Hospital street 5"
    # Save на пустых ответах не теряет ручной узел целиком
    assert "practicesAt" in saved["schema"]["entity"]
    assert classifier()


def test_person_labels_differ_for_clinic_and_practice():
    from heron.setup.answers import specialization

    one = specialization("health-01")
    two = specialization("health-02")
    assert one and two
    assert one[1]["person"]["en"] != two[1]["person"]["en"]
    assert one[1]["person"]["ru"] != two[1]["person"]["ru"]


def test_read_and_save_keep_manual_hospital_affiliation():
    manual = _manual()
    manual["schema"]["entity"]["hospitalAffiliation"] = {
        "@type": "Hospital",
        "name": "Regional Hospital",
    }
    answers = read(manual)
    assert answers.about.fields["hospital_affiliation"] == "Regional Hospital"
    saved = merge(manual, answers, manual["heron"])
    entity = saved["schema"]["entity"]
    # оба ручных узла переживают Save целиком, литералы не заменены дырами
    assert entity["hospitalAffiliation"] == manual["schema"]["entity"]["hospitalAffiliation"]
    assert entity["practicesAt"] == manual["schema"]["entity"]["practicesAt"]
    assert saved["organization"]["works_for"] == "City Hospital"
    assert saved["organization"]["hospital_affiliation"] == "Regional Hospital"
