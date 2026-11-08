"""Классификатор конфигуратора через валидатор разметки: каждая пара (вид, специализация)."""

from __future__ import annotations

from typing import Any

import pytest

from heron.contracts.site import SiteConfig
from heron.modules import jsonld
from heron.schemaorg.validate import validate
from heron.setup import answers as ans
from heron.setup.answers import Answers, classifier, fields_for, lineage, merge, vocab

KINDS = list(vocab()["types"])
SPECS = [(d["id"], s) for d in classifier() for s in d["items"]]


def _is_person(kind: str) -> bool:
    return lineage(kind)[0] == "Person"


PAIRS = [
    pytest.param(kind, d_id, spec["id"], id=f"{kind}-{spec['id']}")
    for kind in KINDS
    for d_id, spec in SPECS
    if not _is_person(kind) or "person" in spec
]


def _sample(name: str, spec: dict[str, Any]) -> Any:
    kind = spec.get("kind")
    if kind == "number":
        return 1.0
    if kind == "country":
        return "AT"
    if kind == "lines":
        return ["a"]
    if kind == "hours":
        return ["Mo-Fr 09:00-18:00"]
    if kind == "media":
        return "media/x.jpg"
    if kind == "date":
        return "2013"
    if kind == "enum":
        return [_first_enum(spec)] if spec.get("multiple") else _first_enum(spec)
    if kind == "subtype":
        return spec["options"][0]
    if kind == "bool":
        return True
    return "x"


def _first_enum(spec: dict[str, Any]) -> str:
    return next(iter(vocab()["labels"][spec["enum"]]))


def _answers(kind: str, direction: str, specialization: str) -> Answers:
    probe = Answers.model_validate(
        {"about": {"type": kind, "direction": direction, "specialization": specialization}}
    )
    fields = {n: _sample(n, vocab()["fields"][n]) for n in fields_for(probe.about)}
    return Answers.model_validate(
        {
            "site": {"name": "Test", "domain": "example.com", "languages": ["en"]},
            "about": {
                "type": kind,
                "direction": direction,
                "specialization": specialization,
                "fields": fields,
                "contacts": [
                    {"type": "phone", "purpose": "main", "value": "+00 000 000 00 00"},
                    {"type": "email", "value": "a@example.com"},
                    {"type": "telegram", "value": "heron_test"},
                ],
            },
        }
    )


@pytest.mark.parametrize(("kind", "direction", "specialization"), PAIRS)
def test_markup_has_no_findings(kind: str, direction: str, specialization: str) -> None:
    data = merge({}, _answers(kind, direction, specialization), ">=0.1")
    config = SiteConfig(**data)
    node = jsonld.entity(config, "en")
    assert node is not None, (kind, specialization)
    found = validate(node).findings
    assert found == [], [(f.code, f.path, f.value) for f in found]


def test_vocab_props_are_dictionary_properties() -> None:
    from heron.schemaorg import vocab as schema_vocab

    sv = schema_vocab()
    for name, spec in vocab()["fields"].items():
        head = ans.prop_head(spec["prop"])
        if spec["prop"] == "address.house":
            continue
        assert sv.is_property(head), (name, head)


def test_vocab_types_are_dictionary_types() -> None:
    from heron.schemaorg import vocab as schema_vocab

    sv = schema_vocab()
    for kind in KINDS:
        assert sv.is_type(kind), kind
