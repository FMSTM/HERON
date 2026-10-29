"""Справочник анкеты: вариант врача, его поля и подписи значений schema.org."""

from __future__ import annotations

from typing import Any

import pytest

from heron.schemaorg import vocab as schema_vocab
from heron.setup.answers import fields_of, lineage, vocab

KIND = "IndividualPhysician"
NEW_FIELDS = [
    "medical_specialty",
    "practices_at_type",
    "practices_at",
    "practices_at_street",
    "practices_at_city",
    "practices_at_region",
    "practices_at_postal_code",
    "practices_at_country",
    "hospital_affiliation",
    "accepts_new_patients",
]
DASHES = ("—", "–")


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    return vocab()


def _texts(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [text for value in node.values() for text in _texts(value)]
    if isinstance(node, list):
        return [text for value in node for text in _texts(value)]
    return []


def test_type_and_lineage(data: dict[str, Any]) -> None:
    spec = data["types"][KIND]
    assert spec["parent"] == "LocalBusiness"
    assert spec["person_name"] is True
    assert spec["label"]["ru"] == "Врач, принимает в клинике или больнице"
    assert spec["label"]["en"]
    assert lineage(KIND) == ["Organization", "LocalBusiness", KIND]
    assert schema_vocab().is_subtype(KIND, "LocalBusiness")


def test_fields_of_kind(data: dict[str, Any]) -> None:
    assert data["types"][KIND]["fields"] == NEW_FIELDS
    own = fields_of(KIND)
    assert own[0] == "name"
    assert "opening_hours" in own and "street" in own
    for name in NEW_FIELDS:
        assert name in data["fields"], name
        assert name in own


def test_specialty_labels_cover_all_members(data: dict[str, Any]) -> None:
    members = schema_vocab().members("MedicalSpecialty")
    labels = data["labels"]["MedicalSpecialty"]
    assert len(members) == 42
    assert set(labels) == set(members)
    for value in members:
        assert labels[value]["ru"].strip(), value
        assert labels[value]["en"].strip(), value
    assert labels["Neurologic"]["ru"] == "Неврология"


def test_specialty_field_is_enum(data: dict[str, Any]) -> None:
    spec = data["fields"]["medical_specialty"]
    assert spec["kind"] == "enum"
    assert spec["enum"] == "MedicalSpecialty"
    assert spec["multiple"] is True
    assert spec["emit"] == "url"
    assert schema_vocab().is_enum(spec["enum"])


def test_workplace_options_are_medical_subtypes(data: dict[str, Any]) -> None:
    spec = data["fields"]["practices_at_type"]
    assert spec["kind"] == "subtype"
    assert spec["of"] == "MedicalOrganization"
    assert spec["options"]
    for option in spec["options"]:
        assert schema_vocab().is_subtype(option, "MedicalOrganization"), option
        label = data["labels"]["MedicalOrganization"][option]
        assert label["ru"].strip() and label["en"].strip()
    assert "Organization" not in spec["options"]


@pytest.mark.parametrize("name", NEW_FIELDS)
def test_prop_head_allowed(data: dict[str, Any], name: str) -> None:
    head = data["fields"][name]["prop"].split(".")[0]
    assert schema_vocab().allows(KIND, head), head


def test_no_works_for_on_kind() -> None:
    assert not schema_vocab().allows(KIND, "worksFor")
    assert "works_for" not in fields_of(KIND)


def test_address_fallbacks(data: dict[str, Any]) -> None:
    fields = data["fields"]
    for part in ("city", "region", "postal_code", "country"):
        assert fields[f"practices_at_{part}"]["fallback"] == f"contact.{part}"
    assert fields["practices_at_country"]["kind"] == "country"


def test_bool_and_hours_kinds(data: dict[str, Any]) -> None:
    accepts = data["fields"]["accepts_new_patients"]
    assert accepts["kind"] == "bool"
    assert accepts["prop"] == "isAcceptingNewPatients"
    hours = data["fields"]["opening_hours"]
    assert hours["kind"] == "hours"
    assert "Mo-Fr" not in hours["hint"]["ru"]


def test_texts_without_long_dashes(data: dict[str, Any]) -> None:
    nodes = [data["types"][KIND], data["labels"]] + [data["fields"][n] for n in NEW_FIELDS]
    for text in _texts(nodes):
        assert not any(dash in text for dash in DASHES), text
