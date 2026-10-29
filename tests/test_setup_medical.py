"""Врач в анкете: вложенные узлы practicesAt/hospitalAffiliation, fallback, emit url, bool."""

from __future__ import annotations

from typing import Any

from heron.modules import jsonld
from heron.schemaorg.validate import validate
from heron.setup.answers import Answers, _entity, merge, read
from tests import sites

FULL: dict[str, Any] = {
    "name": "Dr",
    "about": "About",
    "medical_specialty": ["Neurologic", "Surgical"],
    "practices_at_type": "Hospital",
    "practices_at": "City Hospital",
    "practices_at_street": "Main 1",
    "practices_at_city": "Lviv",
    "practices_at_region": "Lviv region",
    "practices_at_postal_code": "79000",
    "practices_at_country": "UA",
    "hospital_affiliation": "Clinic N1",
    "accepts_new_patients": True,
}


def answers(fields: dict[str, Any]) -> Answers:
    return Answers.model_validate(
        {
            "site": {"name": "X", "domain": "x.example.com", "languages": ["en"]},
            "about": {"type": "IndividualPhysician", "fields": fields},
        }
    )


def test_full_node():
    node = _entity(answers(FULL))
    assert node is not None
    assert node["@type"] == "IndividualPhysician"
    assert node["medicalSpecialty"] == [
        "https://schema.org/Neurologic",
        "https://schema.org/Surgical",
    ]
    assert node["practicesAt"] == {
        "@type": "Hospital",
        "name": "{{ organization.works_for }}",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "{{ organization.works_for_street }}",
            "addressLocality": "{{ organization.works_for_city }}",
            "addressRegion": "{{ organization.works_for_region }}",
            "postalCode": "{{ organization.works_for_postal_code }}",
            "addressCountry": "{{ organization.works_for_country }}",
        },
    }
    assert node["hospitalAffiliation"] == {
        "@type": "Hospital",
        "name": "{{ organization.hospital_affiliation }}",
    }
    assert node["isAcceptingNewPatients"] == "{{ organization.accepts_new_patients }}"
    for banned in ("worksFor", "jobTitle", "hasOccupation"):
        assert banned not in node


def test_no_workplace_name_no_node():
    fields = {k: v for k, v in FULL.items() if k != "practices_at"}
    node = _entity(answers(fields))
    assert node is not None
    assert "practicesAt" not in node
    assert "hospitalAffiliation" in node


def test_city_fallback():
    fields = {k: v for k, v in FULL.items() if k != "practices_at_city"}
    node = _entity(answers(fields))
    assert node is not None
    assert "addressLocality" not in node["practicesAt"]["address"]
    node = _entity(answers({**fields, "city": "Kyiv"}))
    assert node is not None
    assert node["practicesAt"]["address"]["addressLocality"] == "{{ contact.city }}"


def test_default_type_from_dictionary():
    fields = {k: v for k, v in FULL.items() if k != "practices_at_type"}
    node = _entity(answers(fields))
    assert node is not None
    assert node["practicesAt"]["@type"] == "MedicalOrganization"


def test_false_is_emitted():
    data = merge({}, answers({**FULL, "accepts_new_patients": False}), ">=0.1")
    assert data["organization"]["accepts_new_patients"] is False
    node = _entity(answers({**FULL, "accepts_new_patients": False}))
    assert node is not None
    config = sites.config(
        schema={"entity": node},
        organization=data["organization"],
        contact={"city": "Lviv"},
    )
    filled = jsonld.entity(config, "uk")
    assert filled is not None
    assert filled["isAcceptingNewPatients"] is False


def test_read_roundtrip():
    given = answers(FULL)
    data = merge({}, given, ">=0.1")
    assert read(data).about.fields == given.about.fields


def test_read_from_schema_entity_only():
    data = {
        "schema": {
            "entity": {
                "@type": "IndividualPhysician",
                "name": "{{ organization.name }}",
                "medicalSpecialty": [
                    "https://schema.org/Neurologic",
                    "https://schema.org/Surgical",
                ],
                "practicesAt": {"@type": "Hospital", "name": "{{ organization.works_for }}"},
            }
        },
        "organization": {"name": "Dr", "works_for": "City Hospital"},
    }
    fields = read(data).about.fields
    assert fields["medical_specialty"] == ["Neurologic", "Surgical"]
    assert fields["practices_at_type"] == "Hospital"
    assert fields["practices_at"] == "City Hospital"


def test_markup_valid_on_two_languages():
    given = answers({**FULL, "city": "Lviv"})
    data = merge({}, given, ">=0.1")
    config = sites.config(
        schema={"entity": data["schema"]["entity"]},
        organization=data["organization"],
        contact=data.get("contact", {}),
    )
    for lang in ("uk", "ru"):
        node = jsonld.entity(config, lang)
        assert node is not None
        assert validate(node).findings == []
